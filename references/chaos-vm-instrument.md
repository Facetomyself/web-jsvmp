# Chaos VM 插桩

本阶段只为现有 opcode Trace 和 fixture 补观察。不单开验收，不恢复成一份可提交的通过。

可选宿主知识库引用（`article/` 不随本仓库发布；缺失时使用本文件的独立说明）：知识来源是 `article/web-reverse/tencent-tdc-slider-vmp-part2-tea-collect-pow.md` 及其 reference。上篇环境补丁（`tencent-tdc-slider-vmp-part1-env-patch.md`）归 `web-env-patcher`，不在本叶做。

## 按缺口读一个执行分支

- `eval/new Function` 生成解释器、运行中 code 容器变化或滚动解码：读 [dynamic-bytecode.md](dynamic-bytecode.md)。
- 插桩后请求消失、时序分歧或反调试触发，或尚未建立 baseline 对照：读 [observation-integrity.md](observation-integrity.md)。

本阶段适用于自定义 JS VM 取证；下面的 ChaosVM 文章仅提供样本经验。子分支回填本阶段附件，不自动触发另一 skill。

## 观察什么

栈式 VM 上，插桩点是解释器对宿主函数的 `.apply` / `.call`，以及会改虚拟栈的运算指令。记录虚拟程序计数、opcode、操作数、栈变化和宿主调用。这些记录要能填进共享 manifest 的 `runtime_trace` 与 `request_fixture`。

填不满操作数或栈值时，停在 first divergence，返回 `insufficient-evidence`。不要用文章里的算法名、字段角色或作者对拍代替本次 trace。

## 返回与升级

观察闭合后运行 `stage chaos-vm-instrument --trace <trace.ndjson> --receipt <collection.json> --out-dir <dir>`。截断、丢事件、身份不一致或只有调用计数时，回执是 `insufficient-evidence`，并且不会进入 opcode。采集通过只表示回执完整，不是语义恢复。

## 外部执行器

腾讯 ChaosVM 脚本需要在 Python 里对拍执行结果时，外部工具边界见 [external-tools.md](external-tools.md) 的 pychaosvm。它只执行，不反汇编。AGPL 源码不进入本仓库。
