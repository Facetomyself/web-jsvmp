# 算法所在层分流

本文件由 `host-primitive` 或 `interpreter-structure` 按需读取；不是可写进 `jsvmBlocker` 的独立阶段。产物回填原阶段，再回父 `web_case.py next`，不从本表直接跳转叶技能。

逐 opcode 是最后手段。先判断当前 VM 是算法本体、宿主调用壳，还是通往 WASM/内层 VM 的转发层。

## 四路判断

| 观察 | 处理 | 停点 |
|---|---|---|
| handler 主要调用 `MD5/SM3/WebCrypto/JSON.stringify` 等宿主原语 | 记录原语输入/输出与字段顺序 | 宿主边界闭合后回纯算，不拆 opcode |
| 调用 WASM export 或另一台解释器 | 记录模块/实例 hash、wrapper 输入输出和版本 | 回父 next 重判 boundary；WASM 由 gate 路由，内层 VM 绑定新实例证据 |
| handler 做稳定的算术/位运算，且无更深边界 | 建立数据流 fingerprint | 骨架仍不闭合则补 Trace/fixture，回父 next 经 gate 进入 opcode |
| 只看到字符串搬运、环境分支或参数包装 | 先补环境/请求边界 | 不认定 JSVMP 核心 |

fingerprint 只写依据：字长、轮数、旋转位数、乘法常量、调用边界或输入输出差分。MD5/SM3 等名字是候选，不是结论；没有运行时对照时标为 `source-hypothesis`。

## `layer_boundary` 附件

```json
{
  "layer_boundary": {
    "current": "host-primitive|outer-vm|inner-vm|wasm|unknown",
    "input": "<hash-or-shape>",
    "output": "<hash-or-shape>",
    "module_sha256": "<hash-or-null>",
    "fingerprint": [{"name": "<candidate>", "basis": "<observation>", "confidence": "candidate"}],
    "stop_reason": "host-closed|delegated|needs-opcode|unknown"
  }
}
```

宿主层闭合或环境缺口的处理也由父 next 决定，本附件不直接启动纯算或补环境。

外层成功运行不等于算法恢复；输入输出边界、版本身份和调用方向没有锁定时，保持 `unknown`。
