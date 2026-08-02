# GOAI 赛道三 · 材料科学文献驱动的构效关系自主发现（Pi-Agent）

一个面向「前沿探索 AI for Research」开放探索赛题的文献驱动科学发现智能体。
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
```

也可以通过环境变量 `DEEPSEEK_API_KEY` / `SCIVERSE_API_KEY` 提供。
- DeepSeek：推理大模型（OpenAI 兼容接口，可用任意兼容端点替换）。
- Sciverse：学术文献检索（可选；缺失时自动回退到纯 arXiv 检索）。

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
├── gap_report.md             # Agent 识别的研究空白（Gap 1-7）
├── survey_report.md          # 阶段一调研报告（含 6 章 + 参考文献）
└── discovery/
    ├── hypotheses.json       # 阶段二假设（4 条，含材料/性质/预期关系/置信度）
    ├── search_h0-3.json      # 每条假设的贝叶斯/MCTS 搜索结果与证据索引
    ├── discovery_report.md   # 发现报告（正结果/负结果/外部验证状态）
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
pi_agent/
├── agent.py                # PiAgent 主循环（事件驱动 + 状态机 + 工具管线）
├── llm.py                  # LLM 调用 + 工具 schema（DeepSeek/OpenAI 兼容）
├── tools.py                # 22 个工具实现（含文献调研/发现类工具）
├── prompts.py              # 系统提示词（两阶段流程 + 预算策略）
├── state_machine.py        # Agent 状态机（IDLE→RUN→DONE 等）
├── events.py / context.py / session.py / config.py
literature_agent/
├── search.py               # arXiv + Sciverse 检索与缓存
├── parser.py               # PDF/DOCX/HTML → Markdown 解析
├── extractor.py            # 实体/数值抽取
└── discovery.py            # 贝叶斯优化 + MCTS + 外部数据库验证
scripts/baseline_random_search.py   # 随机探索参照系（复现说明见下）
docs/problem_definition.md          # 问题定义文档（初赛提交物）
```

## 初赛提交物（docs/）

- [docs/problem_definition.md](docs/problem_definition.md) — 初赛方案说明（问题定义 + 技术方案 + 已验证案例）
- [docs/system_description.md](docs/system_description.md) — Agent 系统说明（架构 + 机制 + 增量 + 复现）
- [docs/route_a_proposal.md](docs/route_a_proposal.md) — 路线 A：构效关系发现 Proposal

## 参照系与复现说明

## 参照系与复现说明

为排除"发现只是随机运气"，提供**同预算公平对比**参照系：

```bash
python scripts/baseline_random_search.py --iterations 40 --seeds 10
```

在同一证据索引（`knowledge_graph.md` / `paper_summaries.md`）上，以相同评估预算
（默认 40 次 = 10 初始随机 + 30 轮 UCB 采集）公平对比两类策略：
复现 Agent 的贝叶斯搜索 vs 同预算随机均匀采样，跨 10 个种子比较每假设最优打分中位数。输出：

```
workspace/outputs/literature_survey/discovery/baseline_random.json
```

**复现步骤**（与本轮 32 轮运行一致）：

1. `python main.py --topic "MOF materials for CO2 capture" --budget 600 --fresh`
2. 运行结束后检查 `workspace/outputs/literature_survey/` 五件套是否齐全
3. 运行参照系脚本（同预算公平对比，10 种子取中位数）

**本轮结果（600s 测试主题）**：4 条假设同预算下贝叶斯 vs 随机全部 parity
（|diff_median| ≤ 0.001，wins 6/10）——如实记录为负结果：当前发现信号来自文献证据结构
而非搜索算法，增强打分函数区分度是下一步重点。

**随机种子说明**：LLM 采样（DeepSeek）不保证可复现，但搜索打分由文献数值确定性计算；
如需固定随机种子可设置 `PYTHONHASHSEED` 与 `numpy.random.seed`（默认不固定）。

## 合规披露

- **商业 API**：DeepSeek（推理，`deepseek-v4-flash`）、Sciverse（文献检索）。调用环节见 `utils/config.py` 与 `literature_agent/search.py`；替代方案：任意 OpenAI 兼容端点（环境变量切换）、纯 arXiv 检索（零成本）。费用假设：600s 单轮约数十次 LLM 调用。对可复现性的影响：LLM 结论由 Agent 携带论文 ID 证据链，可被独立核验。
- **数据来源**：arXiv 摘要/全文为开放获取；Sciverse 仅取标题+摘要用于内部调研，不对外再分发。缓存位于 `workspace/data/literature_cache/`（已 gitignore）。
- **密钥管理**：`.api_key` 已 gitignore，不入库。

## 许可

代码采用 MIT 许可（待定）。文档与运行产物以 CC BY 4.0 公开（不含第三方 API 数据）。
