# 变体失败谱系

动态 JSVMP 上，换一份资源才通过，不算修好。本阶段记录失败，不替代 `request_parity`。

可选宿主知识库引用（`article/` 不随本仓库发布；缺失时使用本文件的独立说明）：知识来源是 `article/web-reverse/jsvmp-variant-failure-lineage-procedure.md` 的 S1–S5、F1–F6，以及同名 archive。两篇都是 source-report，独立运行复现为 0。原始资源留在受控证据区，不写进技能，也不写进公开报告。

## 绑定

每次先写下：资源 hash、来源时段、bytecode 或 dispatcher 的版本线索、分析器版本、输入类型、目标边界、失败阶段。缺原失败资源就不能做同一资源回放。

## 通过条件

下面几条要同时成立，否则保持未知：

- 修复后回放的是原来那份失败资源。
- 缺失槽位已经指到 handler、常量构造或控制流分支之一。
- 交叉验证覆盖的是结构差异，不是同类样本的份数。
- 未知 opcode 和未确认分支仍标未知。
- 解析兼容、本地语义一致、下游业务结果分成三行，不合成一个成功率。

同一资源重试、同类新资源重试、换了变体重试分开计。换变体后的成功只说明至少一种变体能处理。

## 和 opcode 阶段的关系

槽位或位宽还没确认时，不进入会把未知填成默认值的还原。Trace 和 fixture 齐了，先回父 `web_case.py next`；只有它给出 `deobfuscation_gate` 且 gate 为 `jsvm-verifiable`、next_skill 为 `web-jsvmp` 后，才按 handoff 回到 [opcode-recovery.md](opcode-recovery.md)。本阶段不得单独把 `chain_accepted` 写成 true。
