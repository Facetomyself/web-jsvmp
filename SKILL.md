---
name: web-jsvmp
description: Web VMP / JSVMP 专用叶。父级 next 在 JS VM 挡住当前步骤时按阻碍选一个阶段，不按表顺序调用；opcode Trace 与 fixture 齐备后才经 gate 做有界语义和前向 parity。不是 Windows VMProtect 或 Android Native VMP。
---

# Web VMP / JSVMP

## 发布与宿主集成边界

本仓库独立发布阶段说明、trace 合同和受限工具链，命令路径以仓库根为基准。下文的 `docs/agent-architecture.md`、`web-reverse` 的 dispatcher/case/facts、`web-deobfuscation` 的 gate/manifest schema/validator 与 `article/` 知识库均属于可选宿主工程，**不随本仓库发布**。宿主集成时将本仓库挂载到 `skill/web-jsvmp` 并遵循宿主合同；独立使用只验证本地工具产物，不能生成或声称宿主的 `deobfuscation=pass`。详见 [README.md](README.md)。

## 执行面

主线程只读本节；执行切片遵循 `docs/agent-architecture.md` 的「子代理」和「主动拆分」。只读本次命中的阶段 reference，不展开其他分支。

- 这是 Web/JS 自定义虚拟机的唯一叶，目录名保持 `web-jsvmp`，因为 gate 的 `next_skill` 指向它。看见 VM 形态不进入本 skill。当前步骤被 JS VM 挡住时，`web_case.py next` 给出一个 `readRef`：无 opcode 证据是 `route_web_jsvmp`，有 opcode 证据才是 `deobfuscation_gate`。直接命中本 skill 时仍先恢复上游 case，不绕过门禁。
- 一次只读 `next` 点名的阶段 reference；命中该文列出的明确触发条件时，再读对应的一个子 reference，产物仍归原阶段。做完回到 `web_case.py next`。不按下面的表从上到下做。`jsvmBlocker` 可写成 `host-primitive`、`interpreter-structure`、`chaos-vm-instrument`、`opcode-recovery`、`variant-failure` 或 `ws-app-protocol`；未写且没有 opcode 证据时默认解释器分型。opcode 验收仍要求分类 profile 为 `jsvm-verifiable`，并读共享 `skill/web-deobfuscation/references/case-contract.md` 的当前 profile。
- 回填 `deobfuscation=pass` 必须先有共享 validator 的 `chain_accepted=true`。宿主原语闭合、解释器分型、插桩笔记和失败谱系都不能单独当成叶成功。
- 回程交回 manifest、validation report、限制与原句柄，返回 `web-reverse` 的 `web_case.py next`。本 skill 不启动补环境或协议交付。
- 外部项目只按 [external-tools.md](references/external-tools.md) 当方法或可选工作站。不把无许可证或 AGPL 源码复制进仓库，也不把保护器当还原器。

失败边界不在取指/分发/状态三者中时（例如升级已成功、应用帧未对齐），`jsvmBlocker` 可能不适用；先回父 `web_case.py next` 重判边界，不要硬套 VM 阶段。

## 输入

源码快照/hash、上游 evidence pointer，以及本阶段真正用到的 gate pointer、opcode runtime Trace 或脱敏 fixture。Gate 是路由建议，不是恢复成功证明。没有带操作数或栈值的 Trace 时停在更早阶段，不进入 opcode 验收。

## 阶段

| 阶段 | 唯一下一份说明 | 何时用 |
|---|---|---|
| `host-primitive` | [host-primitive.md](references/host-primitive.md) | 签名函数已是栈式 VM，但要先钩宿主原语，而不是拆 opcode |
| `interpreter-structure` | [interpreter-structure.md](references/interpreter-structure.md) | 只分型栈/寄存器/分发，还没有 opcode 表；请求入口和 dispatcher 定位读 [request-dispatcher.md](references/request-dispatcher.md) |
| `chaos-vm-instrument` | [chaos-vm-instrument.md](references/chaos-vm-instrument.md) | 用插桩给现有 trace/fixture 补观察，不单开验收；动态生成或自修改字节码读 [dynamic-bytecode.md](references/dynamic-bytecode.md)，低扰动与反调试读 [observation-integrity.md](references/observation-integrity.md) |
| `opcode-recovery` | [opcode-recovery.md](references/opcode-recovery.md) + [toolchain.md](references/toolchain.md) | Gate 已给出带操作数或栈值的 opcode Trace 与 fixture |
| `variant-failure` | [variant-failure.md](references/variant-failure.md) | 同一动态资源多轮失败，或修复后换了样本才通过 |
| `ws-app-protocol` | [ws-frame-protocol.md](references/ws-frame-protocol.md) | 升级已成功，但 WebSocket/二进制帧的 cmd 协议、codec 或 key 来源未对齐 |

表中 dispatcher 接受 6 个 `jsvmBlocker`。`layer-fingerprint` 不是合法 blocker，由 `host-primitive` 或 `interpreter-structure` 在算法所在层不明时按需读取；不要向父 facts 填此值。

按命中的那一份 reference 执行。`request-dispatcher`、`dynamic-bytecode`、`layer-fingerprint` 和 `observation-integrity` 是现有阶段的执行分支，不新增第二套 case 或状态机；完成后回填原阶段产物。

本技能内置 [工具链](references/toolchain.md)：统一 runtime event sink、严格 trace contract adapter、已声明 ISA 的 decoder、CFG/栈深检查、受限 JS emitter 与 fixture parity runner。sink 由目标专用 hook 在已知 handler/dispatcher 取值点调用；它不是通用自动 hook。默认字节 ISA 是教学/回归用；目标编码需提交 `--isa` 映射到工具当前支持的语义指令，未知 handler/副作用直接停住，不能猜填。RuyiTrace 3.3 的 `.opcode.bin` 只有偏移与 opcode 字节且 indexer 不展开；缺立即数/栈值不能凭关键词补 trace。

## 输出与验收

opcode_map、instruction_widths、disassembly、runtime_trace、request_fixture、parity_report；按需增加 `dispatch_evidence`、`dynamic_code_trace`、`layer_boundary`、`observation_integrity`。这些扩展字段只作为证据附件，不修改共享 manifest schema；按共享合同验证 coverage、trace_alignment、request_parity。每次采集须一并保存完整性 receipt；缺失/截断事件不得继续 lifting。

上面的扩展附件由生产者按当前假设检查，现有 validator 不解释它们，也不会自动证明观测无扰动。

## 内置工具链调用

命令详见 [toolchain.md](references/toolchain.md)。最小闭环为：原始 runtime probe → `normalize` → `lift --isa` → `align` → 用脱敏 fixture 调 `run`。Normalizer 强制同一 `run_id/source_sha256/vm_id` 和 `seq/pc/opcode/operands/stack_before/stack_after`；计数器或普通调用事件不是 opcode trace。Emitter 只实现受限 canonical ISA；CFG 检查静态栈深与 merge，未支持的动态跳转、调用、异常、副作用或语义直接返回缺口。Parity 报告绑定输入 hash，只表示这些 fixture 在生成 JS 下通过，不替代共享 gate/validator 或服务端验收。

共享验收器：`skill/web-deobfuscation/scripts/validate_web_deobfuscation_case.py --manifest <case.json> --gate <gate.json> --report <validation.json>`。不得复制 schema 或另建状态机；validator 校验的是证据结构，实际语义/对拍仍由证据生产者证明。

链式回填 `deobfuscation=pass` 前必须检查 report 的 `chain_accepted=true`；缺字段、false 或仅 `ok=true` 都不能作为叶成功。父 case/facts 仍由证据所有者显式回填，不由 validator 自动执行。

## 停点与回收

- 返回 `status`、manifest/validation/evidence 路径、`claim_scope`、不足证据、原 `session_id`/`instance_id`（如有）、建议下一步；不 inline 原始 Trace 或敏感值。
- 不安装依赖、不切 runtime；额外工具先按父技能边界确认。
- 缺证据或 first divergence：保留最后验证边界并返回 `triage-only`/`insufficient-evidence`，由上游安排下一次有界实验。
