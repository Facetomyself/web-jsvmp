# 低扰动观测与反调试完整性

观测工具可能改变 VM 行为。没有插桩前后对照，就不能把“本地得到字符串”写成稳定语义。

## 观测规则

- 优先日志断点、采样或窄范围 wrapper，避免逐指令暂停；
- 记录 `debugger` 命中、暂停耗时、trace 丢失计数、探针异常和请求是否仍发出；
- 记录 `Function.prototype.toString`、DevTools 探测、计时器和 `navigator/window/WebGL` 分支是否被触发；
- 同一输入做未插桩 baseline 与插桩 run，比较 method、URL、headers、body 长度和目标响应，不只比较最终签名字符串。

## 附件格式

```json
{
  "observation_integrity": {
    "baseline_id": "<fixture-hash>",
    "probe_id": "<probe-hash>",
    "pause_ms": {"count": 0, "max": 0},
    "trace_dropped": 0,
    "anti_debug": ["debugger|toString|devtools|timer|environment"],
    "request_diff": {"method": false, "url": false, "headers": "unknown", "body_length": false, "response": "unknown"},
    "status": "aligned|disturbed|unknown"
  }
}
```

`aligned` 仅在声明的比较范围全部完成且无差异时使用；示例中的 headers 或 response 为 `unknown` 时，总状态也保持 `unknown`。对照应固定输入，并记录时间、随机数、会话和版本差异；无法固定的变量列为限制，不将自然波动直接归因于探针。

`disturbed` 时保留已有 trace 但停止语义升级；先降低观测扰动并重跑同一 fixture。环境缺口属于 `web-env-patcher`，本叶只记录它是否影响当前 trace。
