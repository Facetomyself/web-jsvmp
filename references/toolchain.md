# JSVMP 内置工具链

工具：`scripts/jsvmp_toolchain.py` 与 runtime-neutral sink `scripts/probe_adapter.js`；标准库 Python，无额外 pip 依赖。JS 执行用显式 `--node` 选择已有 Node。它实现统一事件 sink/校验合同和一小组可执行的 canonical semantics；不是自动定位 VM 或通用浏览器注入器，也不对不透明 handler 做 AI 猜测。目标专用 hook 要从其确切取指/解码/执行点调用 `TraceAdapter.emit`，传入值必须来自本次 VM 观察。

## 统一适配输入

Runtime-specific hook 负责定位目标 VM，并把每条 VM 指令交给 `TraceAdapter.emit`；sink 接收 UTF-8 NDJSON 行所对应的对象，字段见 `schemas/trace-event.schema.json`。`pc` 是 VM 指令位置；宿主 JS offset 不能混为 `pc`。同一循环可重复出现相同 `pc`，但 `seq` 唯一。每个 run、源 hash、VM instance 必须一致；stack before/after、立即数和 branch outcome 来自实际观察，未知字段不能填空值冒充观察。每次 run 结束保存 `receipt()`；`truncated=true` 的 trace 不能验收。

```javascript
const { TraceAdapter } = require("./scripts/probe_adapter.js");
const rows = [];
const adapter = new TraceAdapter({ runId, sourceSha256, vmId, maxEvents: 100000, sink: row => rows.push(row) });
// 必须从已证实的 VM handler/dispatcher 取值点调用，不从高频宿主 API 猜 VM 事件。
adapter.emit({ pc, opcode, operands, stackBefore, stackAfter, hostCalls, writes, branchTaken });
const collectionReceipt = adapter.receipt();
```

```sh
python scripts/jsvmp_toolchain.py normalize "<trace.ndjson>" --receipt "<collection-receipt.json>" --out "<normalized.json>"
```

这一步是严格校验器，不从 DevTools/DOMTrace/调用计数中合成 opcode 行。采集 receipt 必须证明事件计数一致且 `dropped=0/truncated=false`，没有 receipt 无法证明 trace 完整。比如 `Reflect.apply` 计数、handler 总调用数、仅 opcode byte 的 `.opcode.bin` 都不满足合同，会以错误停下。目标运行时取指 hook 目前需要按站点/VM 适配，没有伪称跨 runtime 的通用 hook。

## Decode、CFG 与 lifting

当前内置演示 ISA：`PUSH_I32`、`LOAD_ARG`、`ADD`、`XOR`、`ROTL`、`MUL32`、`JMP`、`JZ`、`RET`。生产目标的 opcode byte/宽度可通过 `--isa <json>` 映射到这些 canonical operations；operand encoding 暂支持 `u8`、`u16le`、`i32le`。mapping 必须有来源证据并与运行时 trace 对齐，不支持的 handler 不要映射到“最像”的操作。

```sh
python scripts/jsvmp_toolchain.py lift "<bytecode-hex>" --isa "<isa.json>" --out-dir "<case-output>"
```

产物：`disassembly.json`（原 PC/宽度/operand）、`cfg.json`（基本块/边/可达集合/entry stack depth）和 `lifted.js`。静态栈深不一致、下溢、未知字节或 branch 落在指令中间都会拒绝。当前 emitter 对 branch 输出受限的 PC-dispatch JS，而非 structured AST；不做死代码删除、路径合并或自动算法恢复。每个未观察分支保留在 CFG 中。

Trace 与 decoder 对齐时使用：

```sh
python scripts/jsvmp_toolchain.py align "<normalized-trace.json>" "<case-output>/disassembly.json" --source-sha256 "<source-sha256>" --vm-id "<vm-instance-id>" --run-id "<run-id>" --out "<case-output>/trace-alignment.json"
```

报告精确列出 PC/opcode/operand mismatch 和未观测指令。重复 `pc` 允许出现，工具不凭静态 map 填充动态缺失事件；静态 coverage 也不等于 runtime 路径覆盖。

语义限制：`ADD` 保留 JS `+` 的字符串拼接；位运算使用 JS Number 位语义；`MUL32` 是 `Math.imul`；`ROTL` 的 count 按 32-bit 语义处理。`BigInt` 多态、调用/异常、对象和 Proxy 副作用、getter/this、closure、动态 code write 及 WASM 必须先有专用 IR semantics；当前 emitter 不支持它们，不得压成纯算术。

## Fixture parity

Fixture JSON 是数组，每项 `{ "args": [...], "expected": value }`。runner 执行已生成 JS，报告实际/期望结果、Node 版本、JS/fixture hash 和 `claim_scope=fixture-only`：

```sh
python scripts/jsvmp_toolchain.py run "<case-output>/lifted.js" "<fixture.json>" --node node --out "<case-output>/parity.json"
```

非零或 `passed=false` 不得升级。将 decoder/lifted output、runtime trace、fixture 和实际 parity report 收拢到原共享 manifest，仍通过 `web-deobfuscation` gate 与 validator。不要把 `fixture-only` 改写为 `request_parity` 已完成，除非另有真实请求边界对照。

## 合成负向回归

`tests/fixtures/call_counter.invalid.json` 是人工构造的调用计数回执，不来自真实目标。它没有 opcode、operand、栈或固定输入；回归测试确保 normalize 将其拒绝为非 trace。该测试只验证错误输入拒绝，不是任何实际目标的恢复证据。
