#!/usr/bin/env python3
"""Validate optional, evidence-bound JSVMP phase artifact records.

These contracts describe artifacts produced by external analysis tools. They
do not implement symbol execution, IR rewriting, WebAssembly analysis, or the
host project's case dispatcher.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
PHASES = {"symexec", "irfix", "wasm-stage9"}
STATUSES = {"produced", "partial", "blocked"}
CLAIM_SCOPES = {"artifact-only", "trace-alignment-only", "fixture-only"}
PARITY_STATUSES = {"not-run", "passed", "failed"}
SHA256 = re.compile(r"^[a-f0-9]{64}$")


class ContractError(ValueError):
    """Raised when a phase artifact record violates its public contract."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be an object")
    return value


def _keys(value: dict[str, Any], required: set[str], allowed: set[str], label: str) -> None:
    missing = required - value.keys()
    extra = value.keys() - allowed
    if missing:
        raise ContractError(f"{label} missing fields: {', '.join(sorted(missing))}")
    if extra:
        raise ContractError(f"{label} has unsupported fields: {', '.join(sorted(extra))}")


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} must be a nonempty string")
    return value


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ContractError(f"{label} must be a lowercase SHA-256")
    return value


def _choice(value: Any, choices: set[str], label: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ContractError(f"{label} is invalid")
    return value


def _references(value: Any, label: str, *, allow_empty: bool = True) -> list[dict[str, str]]:
    if not isinstance(value, list) or (not allow_empty and not value):
        qualifier = "nonempty " if not allow_empty else ""
        raise ContractError(f"{label} must be a {qualifier}array")
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for index, item in enumerate(value):
        ref = _object(item, f"{label}[{index}]")
        _keys(ref, {"role", "sha256"}, {"role", "sha256"}, f"{label}[{index}]")
        role = _text(ref["role"], f"{label}[{index}].role")
        if role in seen:
            raise ContractError(f"{label} has duplicate role: {role}")
        seen.add(role)
        result.append({"role": role, "sha256": _sha256(ref["sha256"], f"{label}[{index}].sha256")})
    return result


def _one(refs: list[dict[str, str]], role: str, label: str) -> str:
    matches = [item["sha256"] for item in refs if item["role"] == role]
    if len(matches) != 1:
        raise ContractError(f"{label} requires exactly one {role!r} reference")
    return matches[0]


def _details(record: dict[str, Any], phase: str) -> dict[str, Any]:
    details = _object(record["details"], "details")
    if phase == "symexec":
        allowed = {"trace_status", "event_count", "ir_format"}
        _keys(details, allowed, allowed, "symexec details")
        _choice(details["trace_status"], {"verified", "incomplete", "unknown"}, "symexec trace_status")
        if isinstance(details["event_count"], bool) or not isinstance(details["event_count"], int) or details["event_count"] < 0:
            raise ContractError("symexec event_count must be a nonnegative integer")
        _text(details["ir_format"], "symexec ir_format")
    elif phase == "irfix":
        allowed = {"input_ir_sha256", "rules_sha256", "passes", "parity_status", "parity_report_sha256", "idempotence_status"}
        _keys(details, allowed, allowed, "irfix details")
        _sha256(details["input_ir_sha256"], "irfix input_ir_sha256")
        _sha256(details["rules_sha256"], "irfix rules_sha256")
        if not isinstance(details["passes"], list) or any(not isinstance(v, str) or not v.strip() for v in details["passes"]):
            raise ContractError("irfix passes must be an array of nonempty identifiers")
        _choice(details["parity_status"], PARITY_STATUSES, "irfix parity_status")
        _choice(details["idempotence_status"], PARITY_STATUSES, "irfix idempotence_status")
        _optional_report(details, "parity_status", "parity_report_sha256", "irfix")
    else:
        allowed = {"module_sha256", "route", "parity_status", "parity_report_sha256"}
        _keys(details, allowed, allowed, "wasm-stage9 details")
        _sha256(details["module_sha256"], "wasm-stage9 module_sha256")
        _text(details["route"], "wasm-stage9 route")
        _choice(details["parity_status"], PARITY_STATUSES, "wasm-stage9 parity_status")
        _optional_report(details, "parity_status", "parity_report_sha256", "wasm-stage9")
    return details


def _optional_report(details: dict[str, Any], status_key: str, report_key: str, label: str) -> None:
    status = details[status_key]
    digest = details[report_key]
    if status == "not-run":
        if digest is not None:
            raise ContractError(f"{label} {report_key} must be null when parity was not run")
    else:
        _sha256(digest, f"{label} {report_key}")


def validate_record(value: Any) -> dict[str, Any]:
    """Validate a single phase record and return a compact validation receipt."""
    record = _object(value, "record")
    fields = {"schema_version", "phase", "status", "claim_scope", "inputs", "tool", "outputs", "evidence", "details", "limitations"}
    _keys(record, fields, fields, "record")
    if isinstance(record["schema_version"], bool) or not isinstance(record["schema_version"], int) or record["schema_version"] != SCHEMA_VERSION:
        raise ContractError(f"schema_version must be {SCHEMA_VERSION}")
    phase = record["phase"]
    _choice(phase, PHASES, "phase")
    _choice(record["status"], STATUSES, "status")
    _choice(record["claim_scope"], CLAIM_SCOPES, "claim_scope")

    inputs = _references(record["inputs"], "inputs", allow_empty=False)
    outputs = _references(record["outputs"], "outputs")
    evidence = _references(record["evidence"], "evidence")
    tool = _object(record["tool"], "tool")
    _keys(tool, {"name", "version", "code_sha256"}, {"name", "version", "code_sha256"}, "tool")
    _text(tool["name"], "tool.name")
    _text(tool["version"], "tool.version")
    if tool["code_sha256"] is not None:
        _sha256(tool["code_sha256"], "tool.code_sha256")

    if record["status"] == "blocked" and outputs:
        raise ContractError("blocked records cannot declare outputs")
    if record["status"] != "blocked" and not outputs:
        raise ContractError("produced or partial records require at least one output")
    limitations = record["limitations"]
    if not isinstance(limitations, list) or not limitations or any(not isinstance(v, str) or not v.strip() for v in limitations):
        raise ContractError("limitations must be a nonempty array of nonempty strings")

    details = _details(record, phase)
    input_roles = {item["role"] for item in inputs}
    output_roles = {item["role"] for item in outputs}
    evidence_by_role = {item["role"]: item["sha256"] for item in evidence}

    if phase == "symexec":
        if not {"source", "trace"}.issubset(input_roles) or (record["status"] != "blocked" and "ir" not in output_roles):
            raise ContractError("symexec requires source and trace inputs and, unless blocked, an ir output")
        if record["claim_scope"] not in {"artifact-only", "trace-alignment-only"}:
            raise ContractError("symexec claim_scope must be artifact-only or trace-alignment-only")
        if record["claim_scope"] == "trace-alignment-only":
            if details["trace_status"] != "verified" or "trace-alignment-report" not in evidence_by_role:
                raise ContractError("trace-alignment-only requires verified trace status and its report")
    elif phase == "irfix":
        if "ir" not in input_roles or (record["status"] != "blocked" and "ir" not in output_roles):
            raise ContractError("irfix requires an ir input and, unless blocked, an ir output")
        if record["claim_scope"] not in {"artifact-only", "fixture-only"}:
            raise ContractError("irfix claim_scope must be artifact-only or fixture-only")
        if details["input_ir_sha256"] != _one(inputs, "ir", "irfix"):
            raise ContractError("irfix input_ir_sha256 does not bind the declared ir input")
        if details["parity_status"] != "not-run":
            if evidence_by_role.get("fixture-parity-report") != details["parity_report_sha256"]:
                raise ContractError("run irfix parity requires a matching fixture-parity-report")
        if record["claim_scope"] == "fixture-only" and details["parity_status"] != "passed":
            raise ContractError("fixture-only irfix scope requires passing fixture parity")
    else:
        if "module" not in input_roles or details["module_sha256"] != _one(inputs, "module", "wasm-stage9"):
            raise ContractError("wasm-stage9 module_sha256 must bind the declared module input")
        if record["claim_scope"] not in {"artifact-only", "fixture-only"}:
            raise ContractError("wasm-stage9 claim_scope must be artifact-only or fixture-only")
        if details["parity_status"] != "not-run":
            if evidence_by_role.get("fixture-parity-report") != details["parity_report_sha256"]:
                raise ContractError("run wasm parity requires a matching fixture-parity-report")
        if record["claim_scope"] == "fixture-only" and details["parity_status"] != "passed":
            raise ContractError("fixture-only wasm scope requires passing fixture parity")

    return {"ok": True, "schema_version": SCHEMA_VERSION, "phase": phase, "status": record["status"], "claim_scope": record["claim_scope"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate optional JSVMP phase artifact records")
    parser.add_argument("record", type=Path, help="UTF-8 JSON phase record")
    args = parser.parse_args(argv)
    try:
        value = json.loads(args.record.read_text(encoding="utf-8"))
        receipt = validate_record(value)
    except (OSError, json.JSONDecodeError, ContractError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
