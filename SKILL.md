---
name: web-jsvmp
description: Web VMP / JSVMP 专用叶。父级 next 在 JS VM 挡住当前步骤时按阻碍选一个阶段，不按表顺序调用；opcode Trace 与 fixture 齐备后才经 gate 做有界语义和前向 parity。不是 Windows VMProtect 或 Android Native VMP。
---

# Web VMP / JSVMP

## 发布边界

本仓库发布阶段说明、trace 合同、阶段回执和受限工具链。命令从仓库根运行。宿主调度、分类 gate 和共享 validator 不在本仓库里。独立运行只验证本地回执，不能声称宿主案例通过。宿主接缝见 [host-integration.md](references/host-integration.md) 和 [project-adapter.md](references/project-adapter.md)。

## 执行面

一次只做一个阶段。读该阶段的一篇说明；命中其中写明的分支时再读对应的一篇，产物仍归原阶段。不要按阶段表从上到下做完。

- 用 `python scripts/jsvmp_toolchain.py stage <name>` 写出该阶段回执。回执的 `status=insufficient-evidence` 就停止，不补默认 opcode。
- 阶段名只有 `host-primitive`、`interpreter-structure`、`chaos-vm-instrument`、`opcode-recovery`、`variant-failure`、`ws-app-protocol`。没有 opcode、操作数和栈观察时，不要跑 `opcode-recovery`。
- `opcode-recovery` 的共享 manifest 只通过 [project-adapter.md](references/project-adapter.md) 写出。手写 manifest 或在 manifest 里放 `chain_accepted` 都不是本 skill 的成功。
- 解释器分型、采集回执和失败笔记不能单独当成语义恢复。
- 本 skill 不补环境，不交付协议。外部项目只按 [external-tools.md](references/external-tools.md) 当方法参考。

失败边界不在取指、分发或 VM 状态时，不要硬套上面的阶段名。写出已有证据指针后停止。

## 输入

源码快照/hash、上游 evidence pointer，以及本阶段真正用到的 gate pointer、opcode runtime Trace 或脱敏 fixture。Gate 是路由建议，不是恢复成功证明。没有带操作数或栈值的 Trace 时停在更早阶段，不进入 opcode 验收。

## 阶段

| 阶段 | 唯一下一份说明 | 何时用 |
|---|---|---|
| `host-primitive` | [host-primitive.md](references/host-primitive.md) | 签名函数已是栈式 VM，但要先钩宿主原语，而不是拆 opcode |
| `interpreter-structure` | [interpreter-structure.md](references/interpreter-structure.md) | 只分型栈/寄存器/分发，还没有 opcode 表；请求入口和 dispatcher 定位读 [request-dispatcher.md](references/request-dispatcher.md) |
| `chaos-vm-instrument` | [chaos-vm-instrument.md](references/chaos-vm-instrument.md) | 用插桩给现有 trace/fixture 补观察，不单开验收；动态生成或自修改字节码读 [dynamic-bytecode.md](references/dynamic-bytecode.md)，低扰动与反调试读 [observation-integrity.md](references/observation-integrity.md) |
| `opcode-recovery` | [opcode-recovery.md](references/opcode-recovery.md) + [project-adapter.md](references/project-adapter.md) | 已有带操作数或栈值的 opcode trace、bytecode 与 fixture |
| `variant-failure` | [variant-failure.md](references/variant-failure.md) | 同一动态资源多轮失败，或修复后换了样本才通过 |
| `ws-app-protocol` | [ws-frame-protocol.md](references/ws-frame-protocol.md) | 升级已成功，但 WebSocket/二进制帧的 cmd 协议、codec 或 key 来源未对齐 |

表中 dispatcher 接受 6 个 `jsvmBlocker`。`layer-fingerprint` 不是合法 blocker，由 `host-primitive` 或 `interpreter-structure` 在算法所在层不明时按需读取；不要向父 facts 填此值。

按命中的那一份 reference 执行。`request-dispatcher`、`dynamic-bytecode`、`layer-fingerprint` 和 `observation-integrity` 是现有阶段的执行分支，不新增第二套状态机。分支做完后把结果写进原阶段回执并停止。

本技能内置 [工具链](references/toolchain.md)：统一 runtime event sink、严格 trace contract adapter、已声明 ISA 的 decoder、CFG/栈深检查、受限 JS emitter 与 fixture parity runner。sink 由目标专用 hook 在已知 handler/dispatcher 取值点调用；它不是通用自动 hook。默认字节 ISA 是教学/回归用；目标编码需提交 `--isa` 映射到工具当前支持的语义指令，未知 handler/副作用直接停住，不能猜填。RuyiTrace 3.3 的 `.opcode.bin` 只有偏移与 opcode 字节且 indexer 不展开；缺立即数/栈值不能凭关键词补 trace。

## 输出与验收

opcode_map、instruction_widths、disassembly、runtime_trace、request_fixture、parity_report；按需增加 `dispatch_evidence`、`dynamic_code_trace`、`layer_boundary`、`observation_integrity`。这些扩展字段只作为证据附件，不修改共享 manifest schema；按共享合同验证 coverage、trace_alignment、request_parity。每次采集须一并保存完整性 receipt；缺失/截断事件不得继续 lifting。

上面的扩展附件由生产者按当前假设检查，现有 validator 不解释它们，也不会自动证明观测无扰动。

## 内置工具链调用

命令详见 [toolchain.md](references/toolchain.md)。阶段回执用 `stage`。opcode 闭环由适配器串起：`normalize` → `lift --isa` → `align` → 栈效果检查 → `run`。Normalizer 强制同一 `run_id/source_sha256/vm_id` 和 `seq/pc/opcode/operands/stack_before/stack_after`。计数器或普通调用事件不是 opcode trace。Emitter 只实现受限 canonical ISA。未知 handler、调用、异常或副作用直接停住。Parity 报告的 `claim_scope` 保持 `fixture-only`，不代替宿主验收。

宿主要做链式验收时，用适配器写出的 manifest，再交给宿主自己的 validator。本仓库不复制那份 schema。

## 停点与回收

- 返回 `status`、回执或 manifest 路径、`claim_scope` 和不足证据。不 inline 原始 trace。
- 不安装依赖，不切换 runtime。
- 缺证据或 first divergence 时保留最后一份回执，状态为 `insufficient-evidence`。
