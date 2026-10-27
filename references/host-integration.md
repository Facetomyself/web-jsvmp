# 宿主集成

本文件只在 reverse_ENV 一类宿主里阅读。独立使用 CLI 和 `stage` 回执时不必读它。

公开仓挂到宿主的 `skill/web-jsvmp`，由 gitlink 固定提交。实现、trace schema 和 toolchain 只在这个仓里。宿主不复制第二份 CLI。

## 调度

宿主 `web_case.py next` 在当前步骤被 JS VM 挡住时给出一个 `readRef`，对应一个阶段文档。没有 opcode 证据时动作是 `route_web_jsvmp`。有 opcode 证据时动作是 `deobfuscation_gate`。gate 的 `profile=jsvm-verifiable` 且 `next_skill=web-jsvmp` 之后，才运行 [project-adapter.md](project-adapter.md)。

`jsvmBlocker` 只接受 `host-primitive`、`interpreter-structure`、`chaos-vm-instrument`、`opcode-recovery`、`variant-failure`、`ws-app-protocol`。一次只做一个阶段。阶段回执写完就停止，由宿主证据所有者决定是否再跑 `next`。

## 验收

共享验收器在宿主：

```sh
python skill/web-deobfuscation/scripts/validate_web_deobfuscation_case.py --manifest case.json --gate gate.json --report validation.json
```

`deobfuscation=pass` 只在报告的 `chain_accepted=true` 时成立。适配器的 `ok=true`、本地 `passed=true` 和 `claim_scope=partial` 都不能代替这个字段。适配器不写 `chain_accepted` 或 `validation_scope`。

知识库 `article/` 是可选来源，不是本仓运行依赖。缺文章时以阶段文档为准。
