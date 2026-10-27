"""Stage receipts and the hosting adapter. Synthetic add3 only."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import jsvmp_toolchain as tool
import project_adapter as adapter

NODE = os.environ.get("JSVMP_NODE") or shutil.which("node")
ADD3 = "0200010300000010ff"
SHA = "a" * 64


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")


def add3_trace(directory: Path, *, stack_after=None) -> tuple[Path, Path]:
    rows = [
        {"schema_version": 1, "run_id": "synthetic-add3-r1", "source_sha256": SHA, "vm_id": "vm-1",
         "seq": 0, "pc": 0, "opcode": "LOAD_ARG", "operands": [0], "stack_before": [], "stack_after": [7]},
        {"schema_version": 1, "run_id": "synthetic-add3-r1", "source_sha256": SHA, "vm_id": "vm-1",
         "seq": 1, "pc": 2, "opcode": "PUSH_I32", "operands": [3], "stack_before": [7], "stack_after": [7, 3]},
        {"schema_version": 1, "run_id": "synthetic-add3-r1", "source_sha256": SHA, "vm_id": "vm-1",
         "seq": 2, "pc": 7, "opcode": "ADD", "operands": [], "stack_before": [7, 3], "stack_after": [10]},
        {"schema_version": 1, "run_id": "synthetic-add3-r1", "source_sha256": SHA, "vm_id": "vm-1",
         "seq": 3, "pc": 8, "opcode": "RET", "operands": [], "stack_before": [10], "stack_after": []},
    ]
    if stack_after is not None:
        rows[2]["stack_after"] = stack_after
    trace = directory / "trace.ndjson"
    trace.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8", newline="\n")
    receipt = directory / "collection.json"
    write_json(receipt, {
        "schema_version": 1, "run_id": "synthetic-add3-r1", "source_sha256": SHA, "vm_id": "vm-1",
        "emitted": 4, "dropped": 0, "truncated": False,
    })
    return trace, receipt


class StageTests(unittest.TestCase):
    def test_markers_do_not_assign_a_machine_shape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "vm.js"
            source.write_text("while (true) { switch (opcode) { case 1: break; } } const bytecode = new Uint8Array([1]);", encoding="utf-8")
            out = root / "receipt.json"
            proc = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "jsvmp_toolchain.py"), "stage", "interpreter-structure",
                 "--source", str(source), "--out", str(out)],
                capture_output=True, text=True, encoding="utf-8", check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            receipt = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "markers-present")
            self.assertFalse(receipt["typed"])
            self.assertNotIn("stack", json.dumps(receipt["markers"]))

    def test_incomplete_markers_refuse_a_shape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "plain.js"
            source.write_text("const value = 1;", encoding="utf-8")
            out = root / "receipt.json"
            proc = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "jsvmp_toolchain.py"), "stage", "interpreter-structure",
                 "--source", str(source), "--out", str(out)],
                capture_output=True, text=True, encoding="utf-8", check=False,
            )
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["status"], "insufficient-evidence")

    def test_truncated_collection_is_not_opcode_recovery(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            trace, receipt = add3_trace(root)
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            payload["truncated"] = True
            write_json(receipt, payload)
            proc = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "jsvmp_toolchain.py"), "stage", "chaos-vm-instrument",
                 "--trace", str(trace), "--receipt", str(receipt), "--out-dir", str(root / "out")],
                capture_output=True, text=True, encoding="utf-8", check=False,
            )
            self.assertEqual(proc.returncode, 2)
            stage = json.loads((root / "out" / "stage-receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(stage["status"], "insufficient-evidence")
            self.assertNotIn("opcode_map.json", os.listdir(root / "out"))

    def test_stack_effect_mismatch_stops(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            trace, receipt = add3_trace(root, stack_after=[10, 1])
            proc = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "jsvmp_toolchain.py"), "stage", "opcode-recovery",
                 "--trace", str(trace), "--receipt", str(receipt), "--bytecode-hex", ADD3,
                 "--fixture", str(ROOT / "tests" / "fixtures" / "add3.parity.json"),
                 "--out-dir", str(root / "out"), "--node", NODE or "node"],
                capture_output=True, text=True, encoding="utf-8", check=False,
            )
            self.assertEqual(proc.returncode, 2)
            stage = json.loads((root / "out" / "stage-receipt.json").read_text(encoding="utf-8"))
            self.assertIn("stack effect", stage["reason"])

    @unittest.skipUnless(NODE, "Node unavailable")
    def test_fixture_mismatch_does_not_write_a_success_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            trace, receipt = add3_trace(root)
            fixture = root / "fixture.json"
            write_json(fixture, [{"args": [1], "expected": 0}])
            proc = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "jsvmp_toolchain.py"), "stage", "opcode-recovery",
                 "--trace", str(trace), "--receipt", str(receipt), "--bytecode-hex", ADD3,
                 "--fixture", str(fixture), "--out-dir", str(root / "out"), "--node", NODE],
                capture_output=True, text=True, encoding="utf-8", check=False,
            )
            self.assertEqual(proc.returncode, 2)
            stage = json.loads((root / "out" / "stage-receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(stage["status"], "insufficient-evidence")
            self.assertIn("fixture parity failed", stage["reason"])
            self.assertFalse((root / "out" / "manifest.json").exists())

    def test_unknown_semantic_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "isa.json"
            write_json(path, {"opcodes": [{"name": "CALL", "byte": 9, "semantic": "CALL", "operands": []}]})
            with self.assertRaises(tool.ToolchainError):
                tool.load_isa(path)

    def test_note_stage_cannot_enter_opcode(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            note = root / "note.json"
            write_json(note, {"schema_version": 1, "entered_opcode": True, "evidence_pointers": ["evidence/a"]})
            with self.assertRaises(tool.ToolchainError):
                tool.note_stage("host-primitive", note)
            write_json(note, {"schema_version": 1, "entered_opcode": False, "evidence_pointers": ["evidence/a"]})
            receipt = tool.note_stage("ws-app-protocol", note)
            self.assertEqual(receipt["claim_scope"], "not-opcode")
            self.assertFalse(receipt["entered_opcode"])


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.checkout = self.root / "skill" / "web-jsvmp"
        (self.checkout / "scripts").mkdir(parents=True)
        (self.checkout / "scripts" / "jsvmp_toolchain.py").write_text("print('fixture')\n", encoding="utf-8")
        self.git(self.root, "init", "-q")
        self.git(self.checkout, "init", "-q")
        self.git(self.checkout, "add", ".")
        self.git(self.checkout, "commit", "-qm", "base")
        self.git(self.root, "add", "skill/web-jsvmp")
        self.git(self.root, "commit", "-qm", "gitlink")

    def git(self, root: Path, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(root), "-c", "user.name=fixture", "-c", "user.email=fixture@invalid", *args],
            text=True, stderr=subprocess.DEVNULL,
        )

    def test_dirty_checkout_and_gitlink_mismatch_are_refused(self):
        with self.assertRaisesRegex(ValueError, "must be clean"):
            (self.checkout / "scripts" / "extra.py").write_text("x = 1\n", encoding="utf-8")
            adapter.source_identity(self.checkout, self.root)
        (self.checkout / "scripts" / "extra.py").unlink()
        self.git(self.root, "update-index", "--cacheinfo", "160000," + "a" * 40 + ",skill/web-jsvmp")
        with self.assertRaisesRegex(ValueError, "gitlink does not match"):
            adapter.source_identity(self.checkout, self.root)

    @unittest.skipUnless(NODE, "Node unavailable")
    def test_success_manifest_is_partial_and_not_chain_accepted(self):
        work = self.root / "case"
        work.mkdir()
        source = work / "source.js"
        source.write_text("/* synthetic add3 source placeholder */\n", encoding="utf-8")
        trace, receipt = add3_trace(work)
        fixture = ROOT / "tests" / "fixtures" / "add3.parity.json"
        source_hash = adapter.sha256(source)[1]
        gate = work / "gate.json"
        write_json(gate, {
            "profile": "jsvm-verifiable",
            "next_skill": "web-jsvmp",
            "inputs": [{"role": "source", "sha256": source_hash, "path": str(source), "bytes": source.stat().st_size}],
        })
        identity = {"head_commit": "b" * 40, "dirty": False, "source_tree_sha256": "c" * 64}
        with patch.object(adapter, "source_identity", return_value=identity):
            code = adapter.main([
                "--source", str(source), "--trace", str(trace), "--receipt", str(receipt),
                "--bytecode-hex", ADD3, "--fixture", str(fixture),
                "--output-dir", str(work / "out"), "--evidence-dir", str(work / "cas"),
                "--gate", str(gate), "--node", NODE,
            ])
        self.assertEqual(code, 0)
        manifest = json.loads((work / "out" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["profile"], "jsvm-verifiable")
        self.assertEqual(manifest["claim_scope"], "partial")
        self.assertNotIn("chain_accepted", manifest)
        self.assertNotIn("validation_scope", manifest)
        parity = json.loads((work / "out" / "parity.json").read_text(encoding="utf-8"))
        self.assertTrue(parity["passed"])
        self.assertEqual(parity["claim_scope"], "fixture-only")

    def test_bad_gate_does_not_run_pipeline(self):
        work = self.root / "bad"
        work.mkdir()
        source = work / "source.js"
        source.write_text("placeholder\n", encoding="utf-8")
        trace, receipt = add3_trace(work)
        gate = work / "gate.json"
        write_json(gate, {"profile": "ast-safe", "next_skill": "ast-deobfuscation", "inputs": []})
        with patch.object(adapter, "source_identity", return_value={"head_commit": "b" * 40, "dirty": False, "source_tree_sha256": "c" * 64}):
            code = adapter.main([
                "--source", str(source), "--trace", str(trace), "--receipt", str(receipt),
                "--bytecode-hex", ADD3, "--fixture", str(ROOT / "tests" / "fixtures" / "add3.parity.json"),
                "--output-dir", str(work / "out"), "--evidence-dir", str(work / "cas"), "--gate", str(gate),
            ])
        self.assertEqual(code, 2)
        self.assertFalse((work / "out" / "manifest.json").exists())

    def test_host_validator_accepts_structure_and_keeps_chain_bit(self):
        validator_path = ROOT.parent / "web-deobfuscation" / "scripts" / "validate_web_deobfuscation_case.py"
        if not validator_path.is_file() or not NODE:
            self.skipTest("host validator or Node is unavailable")
        spec = importlib.util.spec_from_file_location("host_validator", validator_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        work = self.root / "host"
        work.mkdir()
        source = work / "source.js"
        source.write_text("/* synthetic */\n", encoding="utf-8")
        trace, receipt = add3_trace(work)
        fixture = ROOT / "tests" / "fixtures" / "add3.parity.json"
        files = {"source": source, "trace": trace, "fixture": fixture}
        inputs = []
        for role, path in files.items():
            size, digest = adapter.sha256(path)
            inputs.append({"role": role, "path": str(path.resolve()), "bytes": size, "sha256": digest})
        gate = work / "gate.json"
        write_json(gate, {"profile": "jsvm-verifiable", "next_skill": "web-jsvmp", "inputs": inputs})
        identity = {"head_commit": "b" * 40, "dirty": False, "source_tree_sha256": "c" * 64}
        with patch.object(adapter, "source_identity", return_value=identity):
            code = adapter.main([
                "--source", str(source), "--trace", str(trace), "--receipt", str(receipt),
                "--bytecode-hex", ADD3, "--fixture", str(fixture),
                "--output-dir", str(work / "out"), "--evidence-dir", str(work / "cas"),
                "--gate", str(gate), "--node", NODE, "--case-id", "synthetic.add3",
            ])
        self.assertEqual(code, 0)
        report = module.validate_manifest(work / "out" / "manifest.json", gate_path=gate)
        self.assertTrue(report["ok"], report["errors"])
        self.assertTrue(report["chain_accepted"])
        self.assertEqual(report["validation_scope"], "gate-bound")
        manifest = json.loads((work / "out" / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("chain_accepted", manifest)


if __name__ == "__main__":
    unittest.main()
