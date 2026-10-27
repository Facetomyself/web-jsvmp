# 宿主原语

在拆 opcode 之前，确认签名函数是不是栈式 VM，以及明文是不是从宿主原语出来的。

可选宿主知识库引用（`article/` 不随本仓库发布；缺失时使用本文件的独立说明）：知识来源是 `article/web-reverse/vmp-host-primitive-to-purecalc-procedure.md` 的 S1–S6、A1–A4、F1–F3。本文件不复制正文，也不把文中样例盐、字母表或抓包条数写成事实。该文 basis 是 source-report，知识库没有重跑对拍。

算法所在层未确认时按需读 [layer-fingerprint.md](layer-fingerprint.md)；它是本阶段分支，不是新的 `jsvmBlocker`。宿主调用探针改变行为或 baseline 不一致时，读 [observation-integrity.md](observation-integrity.md)，回填本阶段附件。

## 进入与停止

四类入口只包括：哈希、WebCrypto、编码或 `JSON.stringify`、页面自己挂上的 `sm3` / `md5`。函数不是栈式 VM 时，本阶段不适用，回到 `web-reverse`。

一次只换一个变量。钩到的摘要名和标准库对不上时，先记差分，不用标准库结果当 oracle。发送前又把已签名 URL 编码一次，就停。

## 停止条件

同一输入 fixture、连续 3 次 host 差异实验仍未改变 token id 或任何目标边界字段时，把排除项写入失败谱系并停止。不在本阶段进入 opcode。

## 产物

留下明文模板和字段顺序、每段 provenance、已经闭合的那一层规范化、以及 A1–A4 里对应的一句状态。缺的记未知。

A1–A3 闭合时写出阶段笔记并停止，不新开 profile。笔记用 `stage host-primitive --note <note.json> --out <receipt.json>`。`note.json` 必须是 `schema_version: 1`、`entered_opcode: false`，以及非空 `evidence_pointers`。A4（明文钩不到，或原语本身被改写）同样只保留缺口。缺操作数、栈值或 fixture 时不能进入 opcode。不得在笔记或回执里写 `chain_accepted`。
