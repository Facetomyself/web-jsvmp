# WebSocket / 二进制帧协议分支

升级已成功，但应用层帧未对齐时进入本分支。产物是 `ws_protocol_evidence` 附件，归本分支，不是 `dispatch_evidence` 的重写。

## 记录项

按帧序记录，方向（send/recv）、opcode、payload 长度、rsv 位：

- 首帧：方向、opcode、长度、是否压缩；
- 帧间 cmd 编号：每帧解包后的命令字段（首字段或约定偏移），不凭长度猜；
- codec：msgpack / protobuf / 自定义（XOR+base62、长度前缀等），写实际字节证据；
- key 来源：解密/签名用的 key 从哪条消息哪个字段来，锚到帧序号。

## 与 opcode-recovery 的边界

本分支拆的是宿主协议帧，不是 VM 字节码。没有带操作数或栈值的 opcode trace 时，本分支不进入 opcode 验收；cmd 结构闭合后回父 `web_case.py next`。

## 附件格式

```json
{
  "ws_protocol_evidence": {
    "upgrade_url": "<path>",
    "frames": [{"seq": 0, "dir": "send", "opcode": 2, "len": 108, "cmd": 100}],
    "codec": "<observed>",
    "key_source": "<frame/field anchor>",
    "limits": ["未证明两帧正文相同"]
  }
}
```

升级层凭据（cookie/header）的闭环检查归 `request-dispatcher.md` 的 S1b，本分支不重复。
