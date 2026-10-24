# 动态生成与自修改字节码

本分支用于解释“静态断点不命中”或“运行后 code 数组看似明文但路径仍错”的情况。它只产出动态代码事件，不凭事件给 opcode 命名。

## 动态生成

在目标调用边界内捕获 `eval`、`new Function` 或等价代码生成入口，记录生成时机、调用者指针、源码 hash、长度和是否再次生成。先保存生成结果，再对生成后的 VM 建立普通 dispatcher 证据；不要把生成器源码当成最终解释器。

## 自修改观察

对已确认的 code/bytecode 容器设置窄范围写入观察，记录 `index`、旧值、新值、写入者和虚拟 `pc`。只观察目标容器，避免全局 `Proxy` 改变时序。解密点按执行顺序记录还原后的字节，并同时保留运行后数组快照。

## 必查的三种误判

1. 首遍 key 为 0 时，第一次 XOR 是恒等，不能据此宣称“发生了解密”。
2. 分支未覆盖的槽位仍可能是密文，运行后 dump 不是完整明文数组。
3. 循环或滚动 key 可能把槽位再次改回密文，必须保留轮次和覆盖范围。

## 产物

```json
{
  "dynamic_code_trace": {
    "generation": [{"kind": "eval|Function", "source_sha256": "<hash>", "length": 0}],
    "writes": [{"container": "<id>", "index": 0, "old": "<redacted>", "new": "<redacted>", "pc": "<pc>", "round": 1}],
    "path_bytes": [{"pc": "<pc>", "byte": "<redacted>", "order": 0}],
    "post_run_snapshot": "<hash>",
    "limits": ["仅覆盖本次路径", "未确认 opcode 语义"]
  }
}
```

缺少写入时机、路径顺序或原始资源 hash 时返回 `insufficient-evidence`；不要用静态密文数组补齐 trace。
