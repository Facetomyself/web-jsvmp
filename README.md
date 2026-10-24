# Web JSVMP Analysis Skill

面向 Web JavaScript 自定义虚拟机分析的分阶段技能与有界工具链。项目将请求入口定位、解释器分型、低扰动观测、字节码解码、控制流检查和 fixture 对拍组织为可追溯的分析过程，明确区分结构证据、局部语义一致与业务验收。

本项目不是通用 JSVMP 去虚拟化器，不会自动定位目标 VM、推断未知 handler 或恢复任意 JavaScript 程序。当前自动化验证使用合成样本；没有将真实困难目标或线上题目通过作为已完成能力。

## 能力范围

| 模块 | 已提供能力 | 明确边界 |
| --- | --- | --- |
| 阶段指引 | 宿主原语、解释器分型、插桩、opcode 恢复、变体失败分析 | 按当前阻碍选阶段，不是固定顺序的全自动流水线 |
| 统一探针适配器 | 接收目标 hook 的事件，绑定 run/source/VM 身份，输出有界完整性 receipt | 只记录调用方提供的观察，不自动 hook dispatcher |
| Trace 校验 | 校验字段、事件身份及采集计数，拒绝截断或只有调用计数的输入 | receipt 不是无扰动或目标真实性的独立证明 |
| Decode / lifting | 内置教学 ISA；自定义 opcode byte 与已支持语义的显式映射 | 不推断未知操作；编码限 `u8` / `u16le` / `i32le` |
| CFG | 基本块、分支边、静态可达性和栈深 merge 检查 | 不是完整路径覆盖或 CFG 优化器 |
| Codegen / parity | 生成受限 PC-dispatch JavaScript，使用 Node 对拍 fixture | 不提供结构化 AST 还原；通过只表示 `fixture-only` |

内置语义：`PUSH_I32`、`LOAD_ARG`、`ADD`、`XOR`、`ROTL`、`MUL32`、`JMP`、`JZ`、`RET`。动态跳转、调用与异常、对象及 Proxy 副作用、闭包、自修改代码和 WASM 不在当前 emitter 的实现范围内。

## 环境要求

- Python 3.10 或更高版本，仅使用标准库，无需安装 pip 依赖。
- Node.js 20 或更高版本，用于探针演示、生成 JavaScript 的执行和相关测试。
- `python` 和 `node` 应位于 `PATH`；如需指定 Node，CLI 使用 `--node <executable>`，测试使用 `JSVMP_NODE` 环境变量。
- 不会自动安装依赖、启动浏览器或下载目标脚本。

## 快速开始

在独立仓库根目录运行以下命令，不需要宿主项目、知识库或真实目标。

```sh
git clone https://github.com/Facetomyself/web-jsvmp.git
cd web-jsvmp
python -m unittest discover -s tests -v
python scripts/jsvmp_toolchain.py lift 0200010300000010ff --out-dir artifacts/add3
python scripts/jsvmp_toolchain.py run artifacts/add3/lifted.js tests/fixtures/add3.parity.json --node node --out artifacts/add3/parity.json
```

示例字节码表示 `return arg0 + 3`，不是实际保护器样本。`lift` 输出 `disassembly.json`、`cfg.json` 和 `lifted.js`；`run` 输出包含输入文件 hash、Node 版本及逐项结果的 parity 报告。预期为 `passed: true`、`claim_scope: fixture-only`。请同时检查命令退出码与报告字段；不得仅凭 exit 0 推断 fixture 通过。

完整链路的合成回归包含 `TraceAdapter → normalize → lift → align → run`，由测试 `test_adapter_normalize_lift_align_and_run_pipeline` 覆盖。目标侧采集需要自行实现与具体解释器匹配的 hook，详见 [工具链合同](references/toolchain.md)。

## 架构与数据流

```text
目标专用 VM hook（由集成方实现）
          │ 实际 pc / opcode / operands / stack
          ▼
  probe_adapter.js ─── collection receipt
          │ NDJSON                │
          └───────────┬───────────┘
                      ▼
                  normalize
                      │ 同一 run / source SHA-256 / VM
                      ▼
bytecode + ISA ── decode / lift ── disassembly + CFG + lifted.js
                      │                     │
normalized trace ─── align                  run ← fixtures
                      │                     │
           trace alignment report      fixture parity report
```

`align` 对齐动态指令与静态 PC/opcode/operand，不证明完整动态语义或未观察分支。`run` 比较生成程序与已声明 fixture 期望值，不代替原 VM 对拍、真实请求等价性或服务端业务验收。源码身份、fixture 来源、未覆盖分支和副作用限制应随证据保留。

## Skill 与宿主主线集成

[SKILL.md](SKILL.md) 是技能入口，`references/` 提供按阻碍选择的执行说明。独立工具链可直接运行；完整案件调度则依赖宿主工程。

宿主可使用 git submodule 将本仓库维护为 gitlink：

```sh
git submodule add https://github.com/Facetomyself/web-jsvmp.git skill/web-jsvmp
git submodule update --init --recursive
```

`submodule add` 仅适用于目标路径不存在或已妥善迁移的情况。已有普通目录应先保留工作树变更，再由宿主维护者完成索引迁移，不要直接覆盖。主仓提交 gitlink 指向的子仓 commit，技能修改在子仓单独审阅和发布。

宿主调用关系为：`web-reverse next → 当前 JSVMP 阶段 → 新证据 → next`；具备 opcode trace 和 fixture 后，由宿主分类 gate 准入有界恢复，再交共享 validator 检查证据合同。只有宿主报告明确满足其接受条件，才由证据所有者回填案件状态。本仓库不复制或替代该状态机。

**不随本仓库发布的宿主依赖：**

- `docs/agent-architecture.md`：宿主调度与子代理规则。
- `web-reverse` / `web_case.py`：case、facts 与 `next` dispatcher。
- `web-deobfuscation`：gate、共享 manifest schema 和 validator。
- `article/web-reverse/`：可选的外部知识库参考，仅作方法来源，并非独立运行的必需文件。

缺少这些组件时，只能使用本仓库的独立分析工具与方法说明，不应生成宿主 `deobfuscation=pass`、`chain_accepted` 或业务成功声明。

## 目录结构

```text
SKILL.md                 技能入口与阶段路由合同
references/              分阶段说明、工具链和外部工具边界
schemas/                 探针事件结构
scripts/                 Python CLI 与 JavaScript 事件 sink
tests/                   合成正向/负向回归与 CLI 链路测试
.github/workflows/       Windows / Linux 测试配置
```

## 测试与验证

```sh
python -m unittest discover -s tests -v
python scripts/jsvmp_toolchain.py --help
node --check scripts/probe_adapter.js
```

测试覆盖解码边界、自定义 ISA、分支 CFG、trace 身份与 operand 对齐、采集截断、非 opcode 计数器拒绝及生成代码 fixture parity。没有 Node 时相关执行测试会跳过；有跳过的测试结果不能称为完整链路验证。CI 配置覆盖 Windows / Linux、Python 3.10 / 3.13 和 Node 20；配置存在不代表远端执行已经通过。

## 许可证与来源

当前发布内容尚未指定明确的开源许可证，因此未添加 `LICENSE`，也不授予额外的使用、修改或再分发许可。公开可见不等于已开源授权；发布方确定许可证后应单独补充。

外部项目仅作方法参考或可选独立工作站，边界见 [external-tools.md](references/external-tools.md)。本项目不附带目标脚本、用户会话、浏览器身份数据或真实业务原始回执。
