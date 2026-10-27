import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "phase_contracts.py"
SCHEMA = ROOT / "schemas" / "phase-artifact.schema.json"
SPEC = importlib.util.spec_from_file_location("phase_contracts", SCRIPT)
contracts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contracts)

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def ref(role, digest=HASH_A):
    return {"role": role, "sha256": digest}


def base(phase):
    common = {
        "schema_version": 1,
        "phase": phase,
        "status": "produced",
        "claim_scope": "artifact-only",
        "tool": {"name": "fixture-tool", "version": "1", "code_sha256": HASH_C},
        "evidence": [],
        "limitations": ["Synthetic contract test; no target semantics are asserted."],
    }
    if phase == "symexec":
        return {
            **common,
            "inputs": [ref("source"), ref("trace", HASH_B)],
            "outputs": [ref("ir", HASH_C)],
            "details": {"trace_status": "unknown", "event_count": 1, "ir_format": "test-ir-v1"},
        }
    if phase == "irfix":
        return {
            **common,
            "inputs": [ref("ir", HASH_A)],
            "outputs": [ref("ir", HASH_B)],
            "details": {
                "input_ir_sha256": HASH_A,
                "rules_sha256": HASH_C,
                "passes": ["normalize-test-ir"],
                "parity_status": "not-run",
                "parity_report_sha256": None,
                "idempotence_status": "not-run",
            },
        }
    return {
        **common,
        "inputs": [ref("module", HASH_A)],
        "outputs": [ref("analysis", HASH_B)],
        "details": {
            "module_sha256": HASH_A,
            "route": "route-id-1",
            "parity_status": "not-run",
            "parity_report_sha256": None,
        },
    }


class PhaseContractTests(unittest.TestCase):
    def test_schema_is_valid_json_and_contract_is_versioned(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        self.assertEqual(1, schema["properties"]["schema_version"]["const"])
        self.assertEqual(["symexec", "irfix", "wasm-stage9"], schema["properties"]["phase"]["enum"])

    def test_minimal_records_validate_for_all_optional_phases(self):
        for phase in ("symexec", "irfix", "wasm-stage9"):
            with self.subTest(phase=phase):
                result = contracts.validate_record(base(phase))
                self.assertEqual({"ok": True, "schema_version": 1, "phase": phase,
                                  "status": "produced", "claim_scope": "artifact-only"}, result)

    def test_symexec_trace_alignment_claim_requires_trace_report_and_verified_trace(self):
        record = base("symexec")
        record["claim_scope"] = "trace-alignment-only"
        with self.assertRaisesRegex(contracts.ContractError, "verified trace status"):
            contracts.validate_record(record)
        record["details"]["trace_status"] = "verified"
        record["evidence"] = [ref("trace-alignment-report", HASH_B)]
        self.assertTrue(contracts.validate_record(record)["ok"])

    def test_symexec_cannot_claim_fixture_parity(self):
        record = base("symexec")
        record["claim_scope"] = "fixture-only"
        with self.assertRaisesRegex(contracts.ContractError, "symexec claim_scope"):
            contracts.validate_record(record)

    def test_irfix_input_digest_must_bind_declared_ir_and_tool_rules_are_pinned(self):
        record = base("irfix")
        record["details"]["input_ir_sha256"] = HASH_B
        with self.assertRaisesRegex(contracts.ContractError, "does not bind"):
            contracts.validate_record(record)
        record["details"]["input_ir_sha256"] = HASH_A
        record["details"]["rules_sha256"] = "bad"
        with self.assertRaisesRegex(contracts.ContractError, "rules_sha256"):
            contracts.validate_record(record)

    def test_irfix_fixture_claim_needs_matching_parity_report(self):
        record = base("irfix")
        record["claim_scope"] = "fixture-only"
        record["details"]["parity_status"] = "passed"
        record["details"]["parity_report_sha256"] = HASH_C
        with self.assertRaisesRegex(contracts.ContractError, "fixture-parity-report"):
            contracts.validate_record(record)
        record["evidence"] = [ref("fixture-parity-report", HASH_C)]
        self.assertTrue(contracts.validate_record(record)["ok"])

    def test_wasm_module_is_bound_and_fixture_claim_needs_matching_report(self):
        record = base("wasm-stage9")
        record["details"]["module_sha256"] = HASH_B
        with self.assertRaisesRegex(contracts.ContractError, "bind the declared module"):
            contracts.validate_record(record)
        record["details"]["module_sha256"] = HASH_A
        record["details"]["route"] = ""
        with self.assertRaisesRegex(contracts.ContractError, "route must be a nonempty string"):
            contracts.validate_record(record)
        record["details"]["route"] = "route-id-1"
        record["claim_scope"] = "fixture-only"
        record["details"]["parity_status"] = "passed"
        record["details"]["parity_report_sha256"] = HASH_C
        with self.assertRaisesRegex(contracts.ContractError, "fixture-parity-report"):
            contracts.validate_record(record)
        record["evidence"] = [ref("fixture-parity-report", HASH_C)]
        self.assertTrue(contracts.validate_record(record)["ok"])

    def test_blocked_record_has_no_outputs_and_all_records_keep_limitations(self):
        record = base("irfix")
        record["status"] = "blocked"
        with self.assertRaisesRegex(contracts.ContractError, "cannot declare outputs"):
            contracts.validate_record(record)
        record["outputs"] = []
        self.assertTrue(contracts.validate_record(record)["ok"])
        record["limitations"] = []
        with self.assertRaisesRegex(contracts.ContractError, "limitations"):
            contracts.validate_record(record)

    def test_duplicate_artifact_roles_and_unknown_fields_are_rejected(self):
        record = base("symexec")
        record["inputs"].append(ref("source", HASH_B))
        with self.assertRaisesRegex(contracts.ContractError, "duplicate role"):
            contracts.validate_record(record)
        record = base("symexec")
        record["unexpected"] = "ignored?"
        with self.assertRaisesRegex(contracts.ContractError, "unsupported fields"):
            contracts.validate_record(record)

    def test_cli_prints_validation_receipt_and_rejects_invalid_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "record.json"
            path.write_text(json.dumps(base("wasm-stage9")), encoding="utf-8")
            valid = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True,
                                   text=True, encoding="utf-8", check=True)
            self.assertEqual("wasm-stage9", json.loads(valid.stdout)["phase"])
            record = copy.deepcopy(base("wasm-stage9"))
            record["details"]["module_sha256"] = "not-a-digest"
            path.write_text(json.dumps(record), encoding="utf-8")
            invalid = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True,
                                     text=True, encoding="utf-8")
            self.assertEqual(2, invalid.returncode)
            self.assertFalse(json.loads(invalid.stderr)["ok"])


if __name__ == "__main__":
    unittest.main()
