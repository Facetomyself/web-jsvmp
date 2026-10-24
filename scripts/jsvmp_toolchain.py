#!/usr/bin/env python3
"""Bounded JSVMP trace adapter, bytecode decoder, CFG/lifter and JS emitter.

This is a tooling core, not a runtime hook. Browser/runtime probes must emit
the normalized event contract and bind to the same source/vm/run identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

OPS = {
    "PUSH_I32": {"byte": 0x01, "width": 5, "operands": 1, "effect": (0, 1)},
    "LOAD_ARG": {"byte": 0x02, "width": 2, "operands": 1, "effect": (0, 1)},
    "ADD": {"byte": 0x10, "width": 1, "operands": 0, "effect": (2, 1)},
    "XOR": {"byte": 0x11, "width": 1, "operands": 0, "effect": (2, 1)},
    "ROTL": {"byte": 0x12, "width": 2, "operands": 1, "effect": (1, 1)},
    "MUL32": {"byte": 0x13, "width": 1, "operands": 0, "effect": (2, 1)},
    "JMP": {"byte": 0x20, "width": 3, "operands": 1, "effect": (0, 0), "branch": "always"},
    "JZ": {"byte": 0x21, "width": 3, "operands": 1, "effect": (1, 0), "branch": "zero"},
    "RET": {"byte": 0xFF, "width": 1, "operands": 0, "effect": (1, 0), "terminal": True},
}
BY_BYTE = {v["byte"]: k for k, v in OPS.items()}
IDENT = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
MAX_BYTECODE_BYTES = 1024 * 1024
MAX_TRACE_EVENTS = 250000
MAX_TRACE_LINE_BYTES = 1024 * 1024


class ToolchainError(Exception):
    pass


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def validate_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    if not events:
        raise ToolchainError("trace is empty")
    required = ("run_id", "source_sha256", "vm_id", "seq", "pc", "opcode", "operands", "stack_before", "stack_after")
    for i, e in enumerate(events):
        if any(k not in e for k in required):
            raise ToolchainError(f"event {i} missing required fields; counters are not opcode events")
        allowed = set(required) | {"schema_version", "hostCalls", "writes", "branchTaken", "timestampNs"}
        if set(e) - allowed:
            raise ToolchainError(f"event {i} has unsupported fields: {sorted(set(e)-allowed)}")
        if e.get("schema_version", 1) != 1 or not isinstance(e["run_id"], str) or not isinstance(e["vm_id"], str):
            raise ToolchainError(f"event {i} has invalid schema version or identity")
        if not isinstance(e["operands"], list) or not isinstance(e["stack_before"], list) or not isinstance(e["stack_after"], list):
            raise ToolchainError(f"event {i} operands and stack snapshots must be arrays")
    identity = {(e.get("run_id"), e.get("source_sha256"), e.get("vm_id")) for e in events}
    if len(identity) != 1 or any(not isinstance(v, str) or not v for v in next(iter(identity))):
        raise ToolchainError("events must share nonempty run_id/source_sha256/vm_id")
    digest = next(iter(identity))[1]
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ToolchainError("source_sha256 must be lowercase SHA-256")
    seen_seq: set[int] = set()
    for i, e in enumerate(events):
        if not isinstance(e["seq"], int) or e["seq"] < 0 or e["seq"] in seen_seq:
            raise ToolchainError(f"event {i} seq invalid or duplicated")
        if not isinstance(e["pc"], int) or e["pc"] < 0:
            raise ToolchainError(f"event {i} pc invalid")
        if not isinstance(e["opcode"], str) or not e["opcode"]:
            raise ToolchainError(f"event {i} opcode must be a nonempty string")
        seen_seq.add(e["seq"])
    return {"run_id": next(iter(identity))[0], "source_sha256": digest, "vm_id": next(iter(identity))[2], "events": len(events)}


def normalize(input_path: Path, output_path: Path, receipt_path: Path | None = None) -> dict[str, Any]:
    raw = input_path.read_bytes()
    if len(raw) > 128 * 1024 * 1024:
        raise ToolchainError("trace exceeds 128 MiB toolchain input bound")
    parsed: list[dict[str, Any]] = []
    try:
        for lineno, line in enumerate(raw.decode("utf-8").splitlines(), 1):
            if line.strip():
                if len(line.encode("utf-8")) > MAX_TRACE_LINE_BYTES:
                    raise ToolchainError(f"line {lineno} exceeds 1 MiB event bound")
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ToolchainError(f"line {lineno} is not an object")
                row.setdefault("schema_version", 1)
                parsed.append(row)
                if len(parsed) > MAX_TRACE_EVENTS:
                    raise ToolchainError("trace exceeds 250000 event bound")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ToolchainError(f"trace is not valid UTF-8 NDJSON: {exc}") from exc
    summary = validate_events(parsed)
    if receipt_path is None:
        raise ToolchainError("collector receipt is required; trace completeness cannot be inferred from rows alone")
    receipt = load_json(receipt_path)
    if not isinstance(receipt, dict) or receipt.get("schema_version") != 1:
        raise ToolchainError("collector receipt schema invalid")
    for key in ("run_id", "source_sha256", "vm_id"):
        if receipt.get(key) != summary[key]:
            raise ToolchainError(f"collector receipt {key} does not match trace")
    if receipt.get("truncated") is not False or receipt.get("dropped") != 0 or receipt.get("emitted") != len(parsed):
        raise ToolchainError("collector trace incomplete: truncated/dropped/emitted mismatch")
    normalized = {"schema_version": 1, **summary, "input_sha256": hashlib.sha256(raw).hexdigest(), "events": sorted(parsed, key=lambda e: e["seq"])}
    dump_json(output_path, normalized)
    return normalized


def load_isa(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return OPS
    data = load_json(path)
    rows = data.get("opcodes") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ToolchainError("ISA file must contain nonempty opcodes array")
    isa: dict[str, dict[str, Any]] = {}
    used: set[int] = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("semantic") not in OPS:
            raise ToolchainError("custom ISA semantic must map to a supported canonical operation")
        name, byte = row.get("name"), row.get("byte")
        operands = row.get("operands", [])
        semantic_spec = OPS[row["semantic"]]
        if not isinstance(name, str) or not name or not isinstance(byte, int) or not 0 <= byte <= 255 or byte in used:
            raise ToolchainError("custom ISA requires unique name and opcode byte 0..255")
        if not isinstance(operands, list) or any(x not in {"u8", "u16le", "i32le"} for x in operands):
            raise ToolchainError("operand formats limited to u8/u16le/i32le")
        spec = dict(OPS[row["semantic"]])
        spec.update({"name": name, "byte": byte, "semantic": row["semantic"], "formats": operands,
                     "width": 1 + sum({"u8": 1, "u16le": 2, "i32le": 4}[x] for x in operands),
                     "operands": len(operands)})
        if spec.get("branch") and operands != ["u16le"]:
            raise ToolchainError("branch operations require one u16le absolute target")
        if spec["semantic"] == "PUSH_I32" and operands != ["i32le"]:
            raise ToolchainError("PUSH_I32 requires i32le")
        required_formats = {"LOAD_ARG": ["u8"], "ROTL": ["u8"]}.get(spec["semantic"], operands)
        if operands != required_formats:
            raise ToolchainError(f"{spec['semantic']} operand format must be {required_formats}")
        if spec["semantic"] in {"ADD", "XOR", "MUL32", "RET"} and operands:
            raise ToolchainError(f"{spec['semantic']} does not take encoded operands")
        isa[name] = spec; used.add(byte)
    return isa


def decode(hex_text: str, isa: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    try:
        code = bytes.fromhex(hex_text)
    except ValueError as exc:
        raise ToolchainError(f"invalid hex bytecode: {exc}") from exc
    if len(code) > MAX_BYTECODE_BYTES:
        raise ToolchainError("bytecode exceeds 1 MiB toolchain bound")
    isa = isa or OPS
    by_byte = {v["byte"]: k for k, v in isa.items()}
    ins: list[dict[str, Any]] = []
    pc = 0
    while pc < len(code):
        start = pc
        byte = code[pc]; pc += 1
        if byte not in by_byte:
            raise ToolchainError(f"first divergence at pc={start}: unknown opcode byte 0x{byte:02x}")
        name = by_byte[byte]; spec = isa[name]; semantic = spec.get("semantic", name)
        end = start + spec["width"]
        if end > len(code):
            raise ToolchainError(f"first divergence at pc={start}: truncated {name} operand")
        operands: list[int] = []
        cursor = pc
        for fmt in spec.get("formats", []):
            width = {"u8": 1, "u16le": 2, "i32le": 4}[fmt]
            operands.append(int.from_bytes(code[cursor:cursor+width], "little", signed=(fmt == "i32le")))
            cursor += width
        if not spec.get("formats"):
            if semantic == "PUSH_I32": operands = [int.from_bytes(code[pc:pc+4], "little", signed=True)]
            elif semantic == "LOAD_ARG": operands = [code[pc]]
            elif semantic in {"ROTL", "JMP", "JZ"}: operands = [int.from_bytes(code[pc:pc+2], "little")]
        next_pc = end
        ins.append({"pc": start, "next_pc": next_pc, "opcode": semantic, "opcode_name": name, "opcode_byte": byte, "operands": operands, "width": spec["width"]})
        pc = end
    starts = {i["pc"] for i in ins}
    for i in ins:
        if OPS[i["opcode"]].get("branch"):
            target = i["operands"][0]
            if target not in starts:
                raise ToolchainError(f"branch at pc={i['pc']} targets non-instruction pc={target}")
    return {"bytecode_hex": code.hex(), "byte_length": len(code), "instruction_widths": {k: v["width"] for k, v in OPS.items()}, "instructions": ins}


def build_cfg(decoded: dict[str, Any]) -> dict[str, Any]:
    ins = decoded["instructions"]
    if not ins:
        raise ToolchainError("no instructions")
    leaders = {ins[0]["pc"]}
    bypc = {i["pc"]: i for i in ins}
    for idx, i in enumerate(ins):
        spec = OPS[i["opcode"]]
        if spec.get("branch"):
            leaders.add(i["operands"][0])
            if idx + 1 < len(ins): leaders.add(ins[idx+1]["pc"])
        elif spec.get("terminal") and idx + 1 < len(ins): leaders.add(ins[idx+1]["pc"])
    leader_list = sorted(leaders)
    blocks: list[dict[str, Any]] = []
    pc_to_block: dict[int, int] = {}
    for n, start in enumerate(leader_list):
        stop = leader_list[n+1] if n+1 < len(leader_list) else float("inf")
        block_ins = [i for i in ins if start <= i["pc"] < stop]
        if not block_ins: continue
        bid = len(blocks)
        for i in block_ins: pc_to_block[i["pc"]] = bid
        blocks.append({"id": bid, "start_pc": start, "instructions": block_ins, "successors": []})
    for idx, b in enumerate(blocks):
        last = b["instructions"][-1]; spec = OPS[last["opcode"]]
        succ: list[int] = []
        if spec.get("branch") == "always": succ.append(pc_to_block[last["operands"][0]])
        elif spec.get("branch") == "zero":
            succ.append(pc_to_block[last["operands"][0]])
            if idx + 1 < len(blocks): succ.append(blocks[idx+1]["id"])
        elif not spec.get("terminal") and idx + 1 < len(blocks): succ.append(blocks[idx+1]["id"])
        b["successors"] = list(dict.fromkeys(succ))
    depths: dict[int, int] = {0: 0}; work = [0]; max_depth = 0
    while work:
        bid = work.pop(0); depth = depths[bid]; block = blocks[bid]
        for inst in block["instructions"]:
            pop_count, push_count = OPS[inst["opcode"]]["effect"]
            if depth < pop_count:
                raise ToolchainError(f"stack underflow at pc={inst['pc']}: need {pop_count}, have {depth}")
            depth = depth - pop_count + push_count; max_depth = max(max_depth, depth)
        for succ in block["successors"]:
            if succ in depths and depths[succ] != depth:
                raise ToolchainError(f"inconsistent stack depth at CFG merge block={succ}: {depths[succ]} vs {depth}")
            if succ not in depths:
                depths[succ] = depth; work.append(succ)
    return {"entry": 0, "blocks": blocks, "pc_to_block": {str(k): v for k, v in pc_to_block.items()}, "stack_depth_at_entry": {str(k): v for k,v in sorted(depths.items())}, "max_stack_depth": max_depth, "coverage": {"instructions": len(ins), "reachable_blocks": reachable(blocks, 0), "total_blocks": len(blocks)}}


def align_trace(trace: dict[str, Any], decoded: dict[str, Any], *, source_sha256: str, vm_id: str, run_id: str) -> dict[str, Any]:
    """Check each dynamic event against its static instruction; never invent missing events."""
    if trace.get("schema_version") != 1 or not isinstance(trace.get("events"), list):
        raise ToolchainError("normalized trace schema invalid")
    if (trace.get("source_sha256"), trace.get("vm_id"), trace.get("run_id")) != (source_sha256, vm_id, run_id):
        raise ToolchainError("trace/disassembly source, VM, or run identity mismatch")
    static = {i["pc"]: i for i in decoded["instructions"]}
    mismatches = []
    covered: set[int] = set()
    for e in trace["events"]:
        inst = static.get(e.get("pc"))
        if inst is None:
            mismatches.append({"seq": e.get("seq"), "pc": e.get("pc"), "reason": "pc-not-in-disassembly"}); continue
        covered.add(inst["pc"])
        if e.get("opcode") not in {inst["opcode"], inst.get("opcode_name")}:
            mismatches.append({"seq":e.get("seq"),"pc":e["pc"],"reason":"opcode-mismatch","trace":e.get("opcode"),"static":inst["opcode"]})
        if e.get("operands") != inst["operands"]:
            mismatches.append({"seq":e.get("seq"),"pc":e["pc"],"reason":"operand-mismatch","trace":e.get("operands"),"static":inst["operands"]})
    return {"schema_version":1,"run_id":trace.get("run_id"),"vm_id":trace.get("vm_id"),"source_sha256":trace.get("source_sha256"),"trace_events":len(trace["events"]),"covered_static_pcs":sorted(covered),"unobserved_static_pcs":sorted(set(static)-covered),"mismatches":mismatches,"aligned":bool(trace["events"]) and not mismatches,"claim_scope":"trace-instruction-alignment-only"}


def reachable(blocks: list[dict[str, Any]], entry: int) -> list[int]:
    lookup = {b["id"]: b for b in blocks}; todo = [entry]; visited: set[int] = set()
    while todo:
        b = todo.pop()
        if b in visited or b not in lookup: continue
        visited.add(b); todo.extend(lookup[b]["successors"])
    return sorted(visited)


def emit_js(decoded: dict[str, Any], function_name: str = "vm") -> str:
    if not IDENT.fullmatch(function_name): raise ToolchainError("invalid JS function name")
    rows = []
    for i in decoded["instructions"]:
        op = i["opcode"]; args = i["operands"]; pc = i["pc"]
        if op == "PUSH_I32": stmt = f"stack.push({args[0]});"
        elif op == "LOAD_ARG": stmt = f"stack.push(args[{args[0]}]);"
        elif op == "ADD": stmt = "{ const b=stack.pop(), a=stack.pop(); stack.push(a+b); }"
        elif op == "XOR": stmt = "{ const b=stack.pop(), a=stack.pop(); stack.push((Number(a)|0) ^ (Number(b)|0)); }"
        elif op == "ROTL": stmt = f"{{ const a=Number(stack.pop())|0, n={args[0]}&31; stack.push((a<<n)|(a>>>(32-n))); }}"
        elif op == "MUL32": stmt = "{ const b=Number(stack.pop()), a=Number(stack.pop()); stack.push(Math.imul(a,b)); }"
        elif op == "JMP": stmt = f"pc={args[0]}; continue;"
        elif op == "JZ": stmt = f"{{ const c=stack.pop(); if (!c) pc={args[0]}; else pc={i['next_pc']}; continue; }}"
        elif op == "RET": stmt = "return stack.pop();"
        rows.append(f"      case {pc}: {stmt} pc={i['next_pc']}; break;")
    return "function " + function_name + "(...args) {\n  const stack=[]; let pc=0, steps=0;\n  for (;;) {\n    if (++steps > 1000000) throw new Error('VM step limit');\n    switch (pc) {\n" + "\n".join(rows) + "\n      default: throw new Error('invalid pc '+pc);\n    }\n  }\n}\nmodule.exports = " + function_name + ";\n"


def run_js(js_path: Path, fixture_path: Path, output_path: Path, node: str) -> dict[str, Any]:
    fixture = load_json(fixture_path)
    if not isinstance(fixture, list) or not fixture: raise ToolchainError("fixture must be nonempty array of {args, expected}")
    script = "const vm=require(process.argv[1]); const xs=JSON.parse(require('fs').readFileSync(process.argv[2],'utf8')); for (const x of xs) { let actual; try { actual=vm(...x.args); } catch(e) { actual={error:e.name+': '+e.message}; } console.log(JSON.stringify({actual,expected:x.expected,pass:JSON.stringify(actual)===JSON.stringify(x.expected)})); }"
    proc = subprocess.run([node, "-e", script, str(js_path.resolve()), str(fixture_path.resolve())], capture_output=True, text=True, encoding="utf-8", timeout=30)
    if proc.returncode: raise ToolchainError(f"generated JS runtime failed: {proc.stderr.strip()}")
    rows = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    report = {"schema_version": 1, "engine": "generated-js-in-node", "node_version": subprocess.run([node,"--version"],capture_output=True,text=True,encoding="utf-8").stdout.strip(), "generated_js_sha256": hashlib.sha256(js_path.read_bytes()).hexdigest(), "fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(), "fixtures": rows, "passed": bool(rows) and all(r["pass"] for r in rows), "claim_scope": "fixture-only"}
    dump_json(output_path, report)
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("normalize", help="validate/normalize adapter NDJSON")
    a.add_argument("trace", type=Path); a.add_argument("--receipt", required=True, type=Path); a.add_argument("--out", required=True, type=Path)
    d = sub.add_parser("decode", help="decode bounded built-in ISA")
    d.add_argument("bytecode_hex"); d.add_argument("--out", required=True, type=Path); d.add_argument("--isa", type=Path)
    al = sub.add_parser("align", help="align normalized dynamic events with decoded instructions")
    al.add_argument("trace", type=Path); al.add_argument("disassembly", type=Path); al.add_argument("--out", required=True, type=Path)
    al.add_argument("--source-sha256", required=True); al.add_argument("--vm-id", required=True); al.add_argument("--run-id", required=True)
    l = sub.add_parser("lift", help="decode and emit bounded JS + CFG")
    l.add_argument("bytecode_hex"); l.add_argument("--out-dir", required=True, type=Path); l.add_argument("--function", default="vm"); l.add_argument("--isa", type=Path)
    r = sub.add_parser("run", help="execute generated JS against fixtures and report parity")
    r.add_argument("js", type=Path); r.add_argument("fixture", type=Path); r.add_argument("--out", required=True, type=Path); r.add_argument("--node", default="node")
    args = p.parse_args()
    try:
        if args.cmd == "normalize":
            result = normalize(args.trace, args.out, args.receipt)
        elif args.cmd == "decode":
            result = decode(args.bytecode_hex, load_isa(args.isa)); dump_json(args.out, result)
        elif args.cmd == "align":
            result = align_trace(load_json(args.trace), load_json(args.disassembly),source_sha256=args.source_sha256,vm_id=args.vm_id,run_id=args.run_id); dump_json(args.out,result)
        elif args.cmd == "lift":
            dec = decode(args.bytecode_hex, load_isa(args.isa)); cfg = build_cfg(dec)
            args.out_dir.mkdir(parents=True, exist_ok=True)
            dump_json(args.out_dir/"disassembly.json", dec); dump_json(args.out_dir/"cfg.json", cfg)
            (args.out_dir/"lifted.js").write_text(emit_js(dec,args.function), encoding="utf-8", newline="\n")
            result = {"status":"lifted", "instructions":len(dec["instructions"]), "blocks":cfg["coverage"]["total_blocks"], "outputs":["disassembly.json","cfg.json","lifted.js"]}
        else:
            result = run_js(args.js,args.fixture,args.out,args.node)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ToolchainError, OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status":"insufficient-evidence-or-error", "error":str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
