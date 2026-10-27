#!/usr/bin/env python3
"""Bind a bounded JSVMP pipeline to a hosting evidence manifest.

The adapter never signs chain_accepted or validation_scope. A hosting project
runs its own validator. Standalone use omits --repo-root and still refuses a
dirty skill checkout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import jsvmp_toolchain as toolchain

SKILL_ROOT = Path(__file__).resolve().parents[1]
CASE_ID = __import__("re").compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if result.returncode:
        raise ValueError("git identity unavailable: " + result.stderr.strip())
    return result.stdout.strip()


def sha256(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def source_identity(skill_root: Path, repo_root: Path | None = None) -> dict:
    """Record executed script bytes. A dirty checkout cannot produce evidence."""
    checkout = Path(_git(skill_root, "rev-parse", "--show-toplevel")).resolve()
    head = _git(checkout, "rev-parse", "HEAD")
    status = _git(checkout, "status", "--porcelain", "--untracked-files=all")
    if status:
        raise ValueError("canonical skill checkout must be clean before evidence production")
    files = sorted([*skill_root.glob("scripts/**/*.py"), *skill_root.glob("scripts/**/*.js")])
    if any(path.is_symlink() or checkout not in path.resolve().parents for path in files):
        raise ValueError("skill scripts escape checkout or are symlinks")
    if not files:
        raise ValueError("skill scripts missing")
    sources = []
    for path in files:
        size, digest = sha256(path)
        sources.append({"path": path.relative_to(checkout).as_posix(), "bytes": size, "sha256": digest})
    result = {
        "head_commit": head,
        "dirty": False,
        "source_tree_sha256": hashlib.sha256(
            json.dumps(sources, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "sources": sources,
    }
    if repo_root is not None and checkout != repo_root.resolve():
        relative = checkout.relative_to(repo_root.resolve()).as_posix()
        index = _git(repo_root, "ls-files", "--stage", "--", relative).split()
        committed = _git(repo_root, "ls-tree", "HEAD", "--", relative).split()
        if len(index) < 3 or index[0] != "160000" or index[2] != "0":
            raise ValueError("hosting repository gitlink missing or conflicted")
        if len(committed) < 3 or committed[0] != "160000":
            raise ValueError("committed hosting gitlink missing")
        result.update(parent_index_gitlink=index[1], parent_head_gitlink=committed[2])
        if head != index[1]:
            raise ValueError("hosting index gitlink does not match canonical skill HEAD")
    return result


def validate_gate(path: Path, source_sha256: str) -> list[str]:
    """Return refusal reasons. Empty means the gate may admit this source."""
    try:
        gate = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"gate unreadable: {exc}"]
    reasons = []
    if not isinstance(gate, dict):
        return ["gate is not an object"]
    if gate.get("profile") != "jsvm-verifiable":
        reasons.append("gate profile is not jsvm-verifiable")
    if gate.get("next_skill") != "web-jsvmp":
        reasons.append("gate next_skill is not web-jsvmp")
    inputs = gate.get("inputs")
    digests = []
    if isinstance(inputs, list):
        digests = [item.get("sha256") for item in inputs if isinstance(item, dict) and item.get("role") == "source"]
    if source_sha256 not in digests:
        reasons.append("gate source hash does not match this input")
    return reasons


def _copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)


def _manifest(case_id: str, limitations: list[str]) -> dict:
    return {
        "schema_version": 1,
        "case_id": case_id,
        "profile": "jsvm-verifiable",
        "claim_scope": "partial",
        "artifacts": {
            "input_snapshot": "input.js",
            "opcode_map": "opcode_map.json",
            "disassembly": "disassembly.json",
            "runtime_trace": "trace.ndjson",
            "request_fixture": "fixture.json",
            "parity_report": "parity.json",
        },
        "checks": {
            "opcode_map_coverage": {"passed": True, "evidence": ["disassembly", "opcode_map"]},
            "trace_alignment": {"passed": True, "evidence": ["disassembly", "runtime_trace"]},
            "request_parity": {"passed": True, "evidence": ["parity_report", "request_fixture"]},
        },
        "limitations": limitations,
    }


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--bytecode-hex", required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--isa", type=Path)
    parser.add_argument("--gate", type=Path)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--node", default="node")
    parser.add_argument("--case-id", default="jsvmp-case")
    args = parser.parse_args(argv)
    if CASE_ID.fullmatch(args.case_id) is None:
        emit({"status": "rejected", "error": "case_id is not a hosting case id"})
        return 2
    try:
        identity = source_identity(SKILL_ROOT, args.repo_root)
    except ValueError as exc:
        emit({"status": "rejected", "error": str(exc)})
        return 2
    source_size, source_hash = sha256(args.source)
    if args.gate is not None:
        reasons = validate_gate(args.gate, source_hash)
        if reasons:
            emit({"status": "rejected", "error": "; ".join(reasons)})
            return 2
    out = args.output_dir
    evidence = args.evidence_dir
    out.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    for label, path in (("source", args.source), ("trace", args.trace), ("fixture", args.fixture), ("receipt", args.receipt)):
        size, digest = sha256(path)
        _copy(path, evidence / f"{digest}")
        (evidence / f"{label}.json").write_text(
            json.dumps({"bytes": size, "sha256": digest}, indent=2) + "\n",
            encoding="utf-8", newline="\n",
        )
    _copy(args.source, out / "input.js")
    _copy(args.trace, out / "trace.ndjson")
    _copy(args.fixture, out / "fixture.json")
    try:
        receipt = toolchain.opcode_recovery(
            args.trace, args.receipt, args.bytecode_hex, args.fixture, out, args.isa, args.node,
        )
    except toolchain.ToolchainError as exc:
        failure = {
            "status": "insufficient-evidence",
            "error": str(exc),
            "source_identity": {k: identity[k] for k in ("head_commit", "dirty", "source_tree_sha256")},
        }
        (out / "adapter-receipt.json").write_text(
            json.dumps(failure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n",
        )
        emit(failure)
        return 2
    limitations = [
        "fixture-only parity inside the bounded canonical ISA",
        "not algorithm-recovered",
        f"source bytes {source_size}",
    ]
    manifest = _manifest(args.case_id, limitations)
    forbidden = {"chain_accepted", "validation_scope"}
    if forbidden & set(manifest):
        emit({"status": "rejected", "error": "adapter must not sign host acceptance"})
        return 2
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n",
    )
    report = {
        "status": "manifest-written",
        "ok": True,
        "profile": "jsvm-verifiable",
        "claim_scope": "partial",
        "stage_receipt": receipt,
        "source_identity": {k: identity[k] for k in ("head_commit", "dirty", "source_tree_sha256")},
        "manifest": "manifest.json",
    }
    (out / "adapter-receipt.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n",
    )
    emit(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
