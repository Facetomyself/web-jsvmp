# Opcode 有界恢复

本阶段的 `readRef` 是父 next 的准备指针，不是准入证明。执行前必须有共享 gate 的 `profile=jsvm-verifiable`、`next_skill=web-jsvmp` 和当前输入绑定；否则回上游取证或分类，不绕过 gate。

## 当前阶段所需证据

先锁定源码 hash、解释器实例、bytecode 来源与一个函数/请求边界。保留 Trace 的采样范围、丢失计数、时间与原 pointer；不能把两次运行中不同 VM 实例拼成一次语义证明。

## 结构到语义

1. 定位 bytecode 头、函数表、入口与退出，记录编码/端序/操作数宽度和依据。静态 switch case 数不是 opcode 覆盖率。
2. 对每个已观察 opcode 建立 PC/operand/栈或寄存器/控制流变化与来源 pointer；无法观察的字段明确 unknown，不由标识符名猜测。
3. 反汇编保留原 offset、原字节与目标地址；验证每条 instruction width，越界、解码失步或未知 opcode 在 first divergence 停止。
4. 同步 runtime trace，区分虚拟 PC 与宿主 JS offset；映射同一输入下可观察分支、内存与调用副作用，不能只比最终字符串。
5. 固定脱敏 fixture，在已批准 runtime 内对拍请求/signer 输出；记录输入域、随机/时间依赖、分支覆盖和未观测 opcode。不要默认执行下载来的目标代码。

## 从 handler 到有界 JS 的语义约束

反汇编、opcode 命名和语义提升是不同产物。只在当前目标函数的已观察路径上建立中间表示；保留未知 handler、间接跳转和异常出口，未知不能折叠为默认值。恢复栈高度与寄存器读写后再建基本块/CFG；跨分支合并需要路径证据，不把一条动态 Trace 当完整 CFG。

- 保留 JavaScript 的 `Number`/`BigInt` 类型边界。`Number` 位运算按 `ToInt32`/`ToUint32`，`>>>` 零扩展，位移计数取低 5 位；`BigInt` 不套用这套 32 位规则，且不支持 `>>>`。普通乘法、`Math.imul`、整数溢出和浮点舍入不可互换，Python 任意精度整数需显式模拟。
- 保留 `+` 的字符串拼接和类型转换、`undefined`/`null`/`NaN`/`-0`、比较与真值规则；测试值域内确实可收窄时写明依据。
- 字符串按 UTF-16 code unit 观察，分清 UTF-8、Base64 与 typed-array 的字节序/截断；恢复字节和恢复字符不能混用。
- 保留属性读取、getter/Proxy、原型、`this` 绑定、调用顺序、异常、宿主状态和可见内存写入；只有证明无副作用才折叠、重排或删除。时间和随机依赖固定于 fixture 或显式传参。

对拍按同一输入比较目标函数输出、分支/状态和请求边界的可观察副作用。用空值、符号边界、溢出、非 ASCII、异常等目标值域内的差分输入定位 first divergence；实际覆盖与未覆盖分别记入 parity_report。本仓库提供的受限 canonical ISA lifting、CFG 检查和 PC-dispatch JS emitter 见 [toolchain.md](toolchain.md)，不提供通用 opcode 恢复、CFG 优化或完整 JavaScript 语义实现。

## 产物与完成范围

共享 manifest 只由 [project-adapter.md](project-adapter.md) 写出，内含 opcode_map（含 opcodes、instruction_widths）、disassembly、runtime_trace、request_fixture、parity_report。parity 必须来自实际比较。不要手写 manifest，也不要写入人工 `passed: true`。适配器成功时 `claim_scope` 固定为 `partial`。

只恢复一个调用边界时 scope 保持 partial。algorithm-recovered 必须另有目标算法域与副作用等价证据；单样本通过、VMProtect 资料或 RuyiTrace opcode 字节都不能外推完整 VM 语义。

## 退回

缺操作数或栈状态、trace 丢失或不稳定时，`stage opcode-recovery` 写 `insufficient-evidence` 并停止。不改走 Windows vmp-reverse。没有操作数或栈标记的 trace 不能当成可验收 opcode。

## 按需案例

动态版本、key builder 或多轮失败时，改读本 skill 的 [variant-failure.md](variant-failure.md)。可选文章只作来源说明，缺失时以该阶段文档为准，不能替代本次 trace 或 fixture。
