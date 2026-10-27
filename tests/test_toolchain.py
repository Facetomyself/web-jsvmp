import importlib.util
import os
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

NODE = os.environ.get("JSVMP_NODE") or shutil.which("node")

SCRIPT = Path(__file__).parents[1] / "scripts" / "jsvmp_toolchain.py"
spec = importlib.util.spec_from_file_location("jsvmp_toolchain", SCRIPT)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class ToolchainTests(unittest.TestCase):
    def test_decode_and_cfg_build_real_branch_blocks(self):
        # arg0; if zero jump to return 9, else push 1/add/return
        code = "0200210d0002010100000010ff0109000000ff"
        decoded = tool.decode(code)
        cfg = tool.build_cfg(decoded)
        self.assertEqual([0, 2, 5, 7, 12, 13, 18], [x["pc"] for x in decoded["instructions"]])
        self.assertEqual(3, cfg["coverage"]["total_blocks"])
        self.assertEqual([0, 1, 2], cfg["coverage"]["reachable_blocks"])

    def test_decode_stops_on_unknown_and_truncated_operands(self):
        with self.assertRaisesRegex(tool.ToolchainError, "first divergence at pc=0"):
            tool.decode("7e")
        with self.assertRaisesRegex(tool.ToolchainError, "truncated PUSH_I32"):
            tool.decode("01ff")

    def test_failed_lift_retains_old_outputs_without_reporting_new_success(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "lifted"
            command = [sys.executable, str(SCRIPT), "lift"]
            subprocess.run(command + ["0200010100000010ff", "--out-dir", str(output)],
                           check=True, capture_output=True, text=True, encoding="utf-8")
            previous = {p.name: p.read_bytes() for p in output.iterdir()}
            failed = subprocess.run(command + ["7e", "--out-dir", str(output)],
                                    capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(2, failed.returncode)
            self.assertEqual("", failed.stdout)
            self.assertEqual("insufficient-evidence-or-error", json.loads(failed.stderr)["status"])
            self.assertEqual(previous, {p.name: p.read_bytes() for p in output.iterdir()})

    def test_custom_opcode_encoding_maps_to_semantic_profile(self):
        with tempfile.TemporaryDirectory() as td:
            isa_path=Path(td)/"isa.json"
            isa_path.write_text(json.dumps({"opcodes":[
                {"name":"ARG","byte":128,"semantic":"LOAD_ARG","operands":["u8"]},
                {"name":"I32","byte":129,"semantic":"PUSH_I32","operands":["i32le"]},
                {"name":"PLUS","byte":130,"semantic":"ADD","operands":[]},
                {"name":"RETURN","byte":255,"semantic":"RET","operands":[]}
            ]}),encoding="utf-8")
            decoded=tool.decode("8000810300000082ff", tool.load_isa(isa_path))
            self.assertEqual(["LOAD_ARG","PUSH_I32","ADD","RET"],[x["opcode"] for x in decoded["instructions"]])
            self.assertEqual(0x80,decoded["instructions"][0]["opcode_byte"])

    @unittest.skipUnless(NODE, "Node unavailable; set JSVMP_NODE or add node to PATH")
    def test_generated_branch_program_executes_both_cfg_paths(self):
        # arg0; JZ 14; arg1; push 1; add; ret; push 9; ret
        decoded=tool.decode("0200210e000201010100000010ff0109000000ff")
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); js=root/"vm.js"; fx=root/"fx.json"; report=root/"parity.json"
            js.write_text(tool.emit_js(decoded),encoding="utf-8")
            fx.write_text(json.dumps([{"args":[0,4],"expected":9},{"args":[1,4],"expected":5}]),encoding="utf-8")
            node=NODE
            self.assertTrue(tool.run_js(js,fx,report,node)["passed"])

    def test_trace_adapter_demands_vm_opcode_fields_and_same_identity(self):
        base = {"schema_version": 1, "run_id": "r", "source_sha256": "a"*64, "vm_id": "vm", "seq": 0, "pc": 0, "opcode": "PUSH_I32", "operands": [1], "stack_before": [], "stack_after": [1]}
        self.assertEqual(1, tool.validate_events([base])["events"])
        with self.assertRaisesRegex(tool.ToolchainError, "missing required fields"):
            tool.validate_events([{k:v for k,v in base.items() if k != "opcode"}])
        other = {**base, "seq": 1, "pc": 5, "run_id": "other"}
        with self.assertRaisesRegex(tool.ToolchainError, "share nonempty"):
            tool.validate_events([base, other])

    def test_align_trace_reports_operand_mismatch_and_unobserved_code(self):
        dec=tool.decode("0200010300000010ff")
        trace={"schema_version":1,"run_id":"r","vm_id":"v","source_sha256":"a"*64,"events":[
            {"seq":0,"pc":0,"opcode":"LOAD_ARG","operands":[0]},
            {"seq":1,"pc":2,"opcode":"PUSH_I32","operands":[4]},
            {"seq":2,"pc":7,"opcode":"ADD","operands":[]},
        ]}
        report=tool.align_trace(trace,dec,source_sha256="a"*64,vm_id="v",run_id="r")
        self.assertFalse(report["aligned"])
        self.assertEqual("operand-mismatch",report["mismatches"][0]["reason"])
        self.assertEqual([8],report["unobserved_static_pcs"])
        with self.assertRaisesRegex(tool.ToolchainError,"identity mismatch"):
            tool.align_trace(trace,dec,source_sha256="b"*64,vm_id="v",run_id="r")

    @unittest.skipUnless(NODE, "Node unavailable")
    def test_unified_adapter_emits_bounded_schema_rows_and_drop_receipt(self):
        node=NODE
        adapter=Path(__file__).parents[1]/"scripts"/"probe_adapter.js"
        code="const {TraceAdapter}=require(process.argv[1]);const rows=[];const t=new TraceAdapter({runId:'r',sourceSha256:'"+"a"*64+"',vmId:'v',maxEvents:1,sink:x=>rows.push(x)});t.emit({pc:0,opcode:'PUSH_I32',operands:[2],stackBefore:[],stackAfter:[2]});t.emit({pc:1,opcode:'RET',operands:[],stackBefore:[2],stackAfter:[]});console.log(JSON.stringify({rows,receipt:t.receipt()}));"
        proc=subprocess.run([node,"-e",code,str(adapter)],capture_output=True,text=True,encoding="utf-8",check=True)
        result=json.loads(proc.stdout)
        self.assertEqual(1,result["receipt"]["emitted"])
        self.assertTrue(result["receipt"]["truncated"])
        self.assertEqual(0,result["rows"][0]["seq"])

    def test_call_counter_is_not_misread_as_opcode_trace(self):
        receipt = json.loads((Path(__file__).parent/"fixtures"/"call_counter.invalid.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as td:
            src = Path(td)/"receipt.ndjson"; out=Path(td)/"trace.json"
            src.write_text(json.dumps(receipt)+"\n", encoding="utf-8")
            with self.assertRaisesRegex(tool.ToolchainError, "missing required fields"):
                tool.normalize(src,out,Path(td)/"collection.json")

    @unittest.skipUnless(NODE, "Node unavailable")
    def test_emit_and_execute_js_with_fixture_parity(self):
        # return arg0 + 3
        dec = tool.decode("0200010300000010ff")
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); js=root/"vm.js"; fixture=root/"fixture.json"; report=root/"parity.json"
            js.write_text(tool.emit_js(dec), encoding="utf-8")
            fixture.write_text(json.dumps([{"args":[7],"expected":10},{"args":[-3],"expected":0}]), encoding="utf-8")
            node=NODE
            result=tool.run_js(js,fixture,report,node)
            self.assertTrue(result["passed"])
            self.assertEqual("fixture-only", result["claim_scope"])

    @unittest.skipUnless(NODE, "Node unavailable")
    def test_cli_lift_and_parity_end_to_end(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); out=root/"lift"; fx=root/"fixture.json"; report=root/"parity.json"
            fx.write_text(json.dumps([{"args":[12],"expected":15}]),encoding="utf-8")
            subprocess.run([sys.executable,str(SCRIPT),"lift","0200010300000010ff","--out-dir",str(out)],check=True,capture_output=True,text=True)
            subprocess.run([sys.executable,str(SCRIPT),"run",str(out/"lifted.js"),str(fx),"--node",NODE,"--out",str(report)],check=True,capture_output=True,text=True)
            self.assertTrue(json.loads(report.read_text(encoding="utf-8"))["passed"])

    @unittest.skipUnless(NODE, "Node unavailable")
    def test_adapter_normalize_lift_align_and_run_pipeline(self):
        node=NODE
        adapter=Path(__file__).parents[1]/"scripts"/"probe_adapter.js"
        proc=subprocess.run([node,"-e",f"const {{TraceAdapter}}=require(process.argv[1]);const rows=[];const t=new TraceAdapter({{runId:'synthetic-fixture-r1',sourceSha256:'{'a'*64}',vmId:'vm-1',sink:x=>rows.push(x)}});t.emit({{pc:0,opcode:'LOAD_ARG',operands:[0],stackBefore:[],stackAfter:[12]}});t.emit({{pc:2,opcode:'PUSH_I32',operands:[3],stackBefore:[12],stackAfter:[12,3]}});t.emit({{pc:7,opcode:'ADD',operands:[],stackBefore:[12,3],stackAfter:[15]}});t.emit({{pc:8,opcode:'RET',operands:[],stackBefore:[15],stackAfter:[]}});console.log(JSON.stringify({{rows,receipt:t.receipt()}}));",str(adapter)],capture_output=True,text=True,encoding="utf-8",check=True)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); raw=root/"raw.ndjson"; collection=root/"collection.json"; norm=root/"trace.json"; out=root/"lift"; align=root/"align.json"; fixture=root/"fixture.json"; parity=root/"parity.json"
            capture=json.loads(proc.stdout); raw.write_text("".join(json.dumps(x)+"\n" for x in capture["rows"]),encoding="utf-8"); collection.write_text(json.dumps(capture["receipt"]),encoding="utf-8")
            fixture.write_text(json.dumps([{"args":[12],"expected":15}]),encoding="utf-8")
            subprocess.run([sys.executable,str(SCRIPT),"normalize",str(raw),"--receipt",str(collection),"--out",str(norm)],check=True,capture_output=True,text=True)
            subprocess.run([sys.executable,str(SCRIPT),"lift","0200010300000010ff","--out-dir",str(out)],check=True,capture_output=True,text=True)
            subprocess.run([sys.executable,str(SCRIPT),"align",str(norm),str(out/"disassembly.json"),"--source-sha256","a"*64,"--vm-id","vm-1","--run-id","synthetic-fixture-r1","--out",str(align)],check=True,capture_output=True,text=True)
            subprocess.run([sys.executable,str(SCRIPT),"run",str(out/"lifted.js"),str(fixture),"--node",node,"--out",str(parity)],check=True,capture_output=True,text=True)
            self.assertTrue(json.loads(align.read_text(encoding="utf-8"))["aligned"])
            self.assertTrue(json.loads(parity.read_text(encoding="utf-8"))["passed"])


if __name__ == "__main__":
    unittest.main()
