# 请求入口与 dispatcher 定位

这一步解决“看见一大段混淆 JS，但还不知道哪台 VM 负责目标参数”的问题。它属于 `interpreter-structure` 的前置分支，不证明 opcode 语义。

## S1：从请求反查入口

先冻结一次真实请求的 method、URL path、参数名、body 字段、脚本 hash 和触发时间。用接口路径/参数搜索，或在 XHR/fetch 断点处沿调用栈回溯，直到找到签名拼装函数。只记录目标参数的调用链；设备指纹、挑战 cookie 和业务数据若未证明同属一台 VM，分开建边界。

## S2：确认 VM 边界

至少找到以下三个边界中的两个：

- 取指：从 code/bytecode/函数表读取虚拟指令或状态；
- 分发：`switch`、handler table、函数续接或状态对象选择动作；
- 状态：虚拟 `pc`、栈/寄存器、当前 frame 或返回槽位发生可重复变化。

常见形态是静态 `switch`、`handlers[op]` 表、threaded/闭包续接和多层 wrapper。热点函数、case 数量或“大数组”只能当线索，必须用请求触发次数、取指点和状态变化交叉确认。

## 最小证据

把以下 JSON 作为 `dispatch_evidence` 附件，不写入共享 manifest：

```json
{
  "request_anchor": {"method": "POST", "path": "/api/example", "field": "sig"},
  "script_sha256": "<hash>",
  "callsite": "<file-or-runtime-pointer>",
  "vm_boundary": {"fetch": "<pointer>", "dispatch": "<pointer>", "state": "<pointer>"},
  "shape": "switch|table|threaded|wrapper|unknown",
  "basis": "runtime-observation|static-observation",
  "limits": ["未确认 opcode 语义", "未证明与其他参数共用 VM"]
}
```

## 停止条件

找不到稳定请求锚时，回到上游请求取证；找不到可重复的取指/分发/状态边界时，保留 `unknown`，不要因混淆强行认定 JSVMP。能定位入口但只看到 WASM 或宿主密码原语时，交给 [layer-fingerprint.md](layer-fingerprint.md)，不要直接进入 opcode 恢复。
