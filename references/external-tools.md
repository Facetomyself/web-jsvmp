# 外部项目边界

检索日 2026-10-04。没有可整仓搬进来的通用 JSVMP 还原器。下面只记录方法或可选工作站。无许可证和 AGPL 的源码不复制进本仓库。保护器（把 JS 编译进自定义字节码的项目）不是还原器，不改造。

这些句子来自公开 README，不是本机运行结果。

| 项目 | 用法 | 不用它做什么 |
|---|---|---|
| [shape-security-decompiler-toolkit](https://github.com/g2asell2019/shape-security-decompiler-toolkit) | 只吸收「挂钩跨版本稳定的微指令，trace，再抬成 JS」。2022 年后无提交，无许可证 | 不把改过的解释器输出当成当前样本的语义；作者写明可能触发自校验，输出可能夹带假路径 |
| [reverse-chaosvm](https://github.com/jiushu666/reverse-chaosvm) | 只吸收静态流水线的阶段名：解码、反汇编、字符串、函数、CFG、opcode 语义、折叠、出 JS、用自带样例对拍 | 不复制源码；不把 token、浏览器自动化或滑块测试当还原器。无许可证 |
| [datadome-vm](https://github.com/xKiian/datadome-vm) | 只吸收顺序：先画这一版的内存槽位和 dispatcher，再写反汇编 | opcode 表和偏移只属于那个样本。无许可证，没有写成等价 JS |
| [firefox-reverse](https://github.com/WhiteNightShadow/firefox-reverse) | 需要引擎级 trace、拆分派发器或反汇编时，当外部工作站。README 点名 `jsvmp_trace`、`jsvmp_query`、`jsvmp_status`、`jsvmp_split_dispatcher`、`jsvmp_disassemble` | 不把 Firefox 补丁搬进技能仓。许可证元数据与 README 徽章不一致，不能据此抽代码 |
| [pychaosvm](https://github.com/aioqzone/pychaosvm) | 已有 ChaosVM 脚本、只需要对拍执行结果时，当外部 Python 包 | AGPL-3.0。README 没有反汇编或还原。不把源码抽进本仓库 |

webcrack、synchrony、de4js、decode-js、wakaru 的公开说明是混淆器清理或拆包，不是自定义字节码 VM。V8 code cache 工具也不进入本叶。
