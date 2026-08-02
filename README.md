# GOAI 赛道三 · 材料科学文献驱动的构效关系自主发现（Prospector）

一个面向「GOAI 赛道三 · 前沿探索 AI for Research」**算法赛题（方向三：材料科学文献驱动的科学发现智能体）**的文献驱动科学发现智能体。
Agent 在有限时间预算内自主完成：**文献检索 → 摘要整理 → 知识图谱撰写 → Gap 识别 → 构效关系假设 → 贝叶斯/MCTS 搜索 → 外部数据库验证 → 报告生成**，全程无需人工干预。

设计要点：**不构建 JSON 知识图谱**——知识抽取、关系识别与图谱撰写全部由 Agent 以 Markdown 形式自主完成（`knowledge_graph.md`），LLM 从自然语言文本中推理比结构化模板更可靠。

## 快速开始

### 环境要求

- Python 3.10+（开发环境 3.13）
- 操作系统：Windows / Linux / macOS

### 安装

```bash
python -m venv .venv
.venv\Scripts\activate.bat          # Windows
source .venv/bin/activate        # Linux/macOS
pip install -r requirements.txt
```

### 配置 API Key

在项目根目录创建 `.api_key` 文件（已被 `.gitignore` 排除，不会入库）：

```
DEEPSEEK_API_KEY=sk-xxxx
SCIVERSE_API_KEY=sci_xxxx
MATERIALS_PROJECT_API_KEY=xxx    # 可选：外部数据库验证
MINERU_API_KEY=xxx               # 可选：云端 PDF 解析（缺失时回退本地 MarkItDown）
```

也可以通过环境变量提供（`DEEPSEEK_API_KEY` / `SCIVERSE_API_KEY` / `MATERIALS_PROJECT_API_KEY` / `MINERU_API_KEY`）。
- DeepSeek：推理大模型（OpenAI 兼容接口，可用任意兼容端点替换）。
- Sciverse：学术文献检索（可选；缺失时自动回退到纯 arXiv 检索）。
- Materials Project / NOMAD：构效关系的外部数据库交叉验证（可选）。
- MinerU：可选，中文/复杂 PDF 解析质量更好。

### 运行

```bash
python main.py --topic "MOF materials for CO2 capture" --budget 600
```

| 参数 | 说明 | 默认 |
|------|------|------|
| `--topic` | 调研主题（必填） | — |
| `--budget` | 时间预算（秒） | 7200 |
| `--output` | 输出根目录 | `workspace/outputs/` |
| `--fresh` | 强制从头开始，忽略已有记忆/缓存 | 关 |

不带 `--fresh` 续跑时，Agent 会读取 `workspace/memory/survey/MEMORY.md` 继承上一轮结论。

## 输出结构

```
workspace/outputs/literature_survey/
├── paper_summaries.md        # 检索结果的摘要整理（供 Agent 阅读）
├── knowledge_graph.md        # Agent 自写的知识图谱（材料/性质/数值/关系/矛盾）
├── knowledge_graph_audit.md  # 图谱审计（数值冲突/重复/溯源缺失）
├── gap_report.md             # Agent 识别的研究空白（类型/严重度/证据/验证方案）
├── survey_report.md          # 阶段一调研报告（含参考文献 DOI 表）
└── discovery/
    ├── hypotheses.json       # 阶段二假设（材料/性质/预期关系/置信度/验证状态）
    ├── novelty_report.md     # 系统性新颖性核查（known/partial/new + 边界说明）
    ├── search_hN.json        # 每条假设的贝叶斯/MCTS 搜索结果与证据索引
    ├── discovery_report.md   # 发现报告（正结果/负结果/外部验证状态）
    ├── model_comparison.md   # 新规律 vs 基线/前人公式的 R²/RMSE 对比
    ├── scientific_explanation.md  # 构效关系的科学机制解释
    └── discovery_report.json
```

过程产物：

```
workspace/logs/trajectory_survey.json            # 完整运行轨迹（每轮思考/工具/预算）
workspace/data/literature_cache/                 # 文献缓存（papers.json / search_log.jsonl）
workspace/memory/survey/MEMORY.md                # 跨轮记忆索引
workspace/memory/survey/survey-*.md              # 单轮运行总结
workspace/memory/survey/survey-reflection.md     # 运行反思（下轮改进方向）
```

## 架构

```
main.py                     # 入口：参数解析 + 预算 + 异常处理
prospector/
├── agent.py                # Prospector 主循环（事件驱动 + 状态机 + 工具管线）
├── llm.py                  # LLM 调用 + 工具 schema（DeepSeek/OpenAI 兼容）
├── tools.py                # 24 个工具实现（含文献调研/发现类工具）
├── prompts.py              # 系统提示词（两阶段流程 + 预算策略）
├── state_machine.py        # Agent 状态机（IDLE→RUN→DONE 等）
├── events.py / context.py / session.py / config.py
literature_agent/
├── search.py               # arXiv + Sciverse 检索与缓存
├── parser.py               # PDF/DOCX/HTML → Markdown 解析
├── extractor.py            # 实体/数值抽取
└── discovery.py            # 贝叶斯/MCTS×LLM 搜索 + 双轨验证 + 新颖性核查 + 模型对比
```

## 初赛提交物

完整提交包见 `submission_initial/`（方案说明、系统说明、路线 A Proposal、主案例调研报告、跨主题验证、证据归档），配套文档：

- [docs/problem_definition.md](docs/problem_definition.md) — 初赛方案说明（问题定义 + 技术方案 + 已验证案例）
- [docs/system_description.md](docs/system_description.md) — Agent 系统说明（架构 + 机制 + 增量 + 复现）
- [docs/route_a_proposal.md](docs/route_a_proposal.md) — 路线 A：构效关系发现 Proposal

## 可复现性说明

- **确定性打分**：文献搜索与证据打分由确定性计算完成（材料覆盖率 + 材料×性质共现 + 数值贴近文献值），不依赖 LLM 采样；
- **证据可核验**：LLM 采样（DeepSeek）不保证逐字节可复现，但所有结论附带论文 ID ↔ DOI 证据链，可独立核验；
- **随机种子**：如需固定，可设置 `PYTHONHASHSEED` 与 `numpy.random.seed`（默认不固定）；
- **复现命令**：`python main.py --topic "<任意材料主题>" --budget 1800`，运行结束后检查输出结构中的五件套与 discovery/ 产物。

跨主题验证（MOF/CO₂、卤化物钙钛矿、热电、锂电正极）结果见 `submission_initial/03_跨主题验证报告.md`。

## 合规披露

- **商业 API**：DeepSeek（推理，`deepseek-v4-flash`）、Sciverse（文献检索）、Materials Project / NOMAD（外部数据库验证）。调用环节见 `utils/config.py`、`literature_agent/search.py`、`literature_agent/discovery.py`；替代方案：任意 OpenAI 兼容端点（环境变量切换）、纯 arXiv 检索（零成本）。费用假设：600s 单轮约数十次 LLM 调用。对可复现性的影响：LLM 结论由 Agent 携带论文 ID 证据链，可被独立核验。
- **数据来源**：arXiv 摘要/全文为开放获取；Sciverse 仅取标题+摘要用于内部调研，不对外再分发；Materials Project / NOMAD 仅查询。缓存位于 `workspace/data/literature_cache/`（已 gitignore）。
- **密钥管理**：`.api_key` 已 gitignore，不入库。
- **闭源模型使用说明**：选择 DeepSeek（闭源推理模型）因其推理质量/成本比与 1M 上下文窗口；迁移成本低——OpenAI 兼容接口，切换端点仅需改环境变量（`DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`）；对可复现性的影响通过"论文 ID 证据链可独立核验"缓解。
- **基于已有项目**：`markitdown_utils/` 改编自微软 markitdown（MIT，Copyright Adam Fourney），仅保留 PDF/DOCX/HTML 转换器并适配科学文献解析；Agent 系统其余部分均为本项目原创。
- **第三方依赖与许可证**：依赖见 `requirements.txt`（均为开源许可）；`vendor/bash` 为 MSYS2 Git Bash（GPLv2+），仅用于 Windows 兼容运行环境，未做修改。

## 许可

代码采用 MIT 许可。文档与运行产物以 CC BY 4.0 公开（不含第三方 API 数据）。
