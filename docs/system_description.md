# Agent 系统说明（初赛提交物）

---

## 1. 定位

Prospector 是一个**主题无关**的文献驱动科学发现智能体：给定任意材料研究主题与时间预算，自主完成文献调研（基本任务）与构效关系发现（路线 A），全程无需人工干预。

## 2. 总体架构

```
main.py
│  参数解析（--topic / --budget / --fresh）+ 预算 + 异常处理
│
prospector/
├── agent.py         ReAct 主循环（Think→Act→Observe）、事件驱动、状态机、checkpoint、反思触发
├── llm.py           LLM 客户端（DeepSeek，OpenAI 兼容）+ 24 个工具 schema + JSON 修复 + 重试
├── tools.py         工具管线（24 个工具实现）+ LLM×搜索融合回调 + 知识审计/覆盖审计/新颖性核查/模型对比
├── prompts.py       两阶段系统提示词（预算策略、记忆格式、Think→Act 协议）
├── state_machine.py 状态机（IDLE→RUNNING→TOOL_EXECUTING→DONE）
├── events.py        发布/订阅事件总线
├── context.py       长对话自动压缩
├── session.py       checkpoint 保存/恢复
└── config.py        常量
│
literature_agent/
├── search.py         多源检索（arXiv / Sciverse / Sci-Base）+ 缓存 + 搜索日志
├── parser.py         文档解析（MarkItDown 本地 / MinerU 可选）
├── extractor.py      知识图谱数据模型 + Markdown 图谱审计
└── discovery.py      假设生成、新颖性核查、贝叶斯/MCTS 搜索、双轨验证、模型对比、发现报告
│
markitdown_utils/     本地 PDF/DOCX/HTML 解析（markitdown 裁剪版）
utils/                全局配置 + 预算追踪
vendor/bash/          Git Bash（Windows 下 shell 兼容）
```

## 3. 核心机制

| 机制 | 说明 |
|---|---|
| ReAct 循环 | 每轮 LLM 思考 → 执行工具 → 观察结果 → 更新记忆，直至预算耗尽或主动 stop |
| 时间预算 | 默认 7200s；按剩余比例分级提醒；耗尽强制收尾 |
| 事件驱动 | 10 类生命周期事件，轨迹日志全量记录（`workspace/logs/trajectory_survey.json`） |
| 状态机 | 合法状态迁移 + 进入/退出钩子 |
| Checkpoint | 每轮保存会话，中断续跑；干净退出自动清理 |
| 上下文压缩 | 超阈值自动分层摘要，保持窗口内 |
| 跨轮记忆 | MEMORY.md 索引 + 单轮总结 + 反思；续跑自动继承，不重复劳动 |

## 4. 工具清单（24 个）

- **通用（10）**：think、list_files、read_file、write_file、edit_file、run_shell、start_shell、check_shell、kill_shell、stop
- **文献调研（8）**：search_papers、assess_search_coverage、parse_paper、get_full_text、extract_knowledge、analyze_gaps、audit_knowledge_graph、generate_report
- **路线 A（6）**：generate_hypotheses、check_novelty、run_discovery_search、validate_discovery、run_model_comparison、generate_discovery_report

合计：10 + 8 + 6 = 24 个。

## 5. 基本任务能力

1. **检索与覆盖审计**：多源检索、缓存去重；确定性统计唯一论文/来源/年份/边际收益，输出建议补充检索词与停止决策。
2. **深度阅读**：Sciverse 全文片段 → PDF 下载解析（MarkItDown）→ arXiv 按标题回退 → 缓存复用。
3. **知识图谱与审计**：Agent 手写 Markdown 图谱（材料/性质/数值/关系/论文 ID）；审计工具自动检测数值冲突（→矛盾型 Gap）、重复写法、溯源缺失。
4. **Gap 识别**：矛盾结论 / 缺失连接 / 未探索空间，每条附证据论文与验证方案。
5. **调研报告**：结构化 Markdown + 证据链，中文撰写，论文标题保留原文。

## 6. 路线 A 能力

1. **假设生成**：LLM 基于 Gap 报告 + 论文摘要生成（材料/性质/预期关系/置信度/新颖性）。
2. **新颖性核查**（`check_novelty`）：反查已检索文献库，判定 known/partial/new，输出边界说明并修正新颖性分数——不采信 LLM 自评。
3. **搜索×LLM 融合**（`run_discovery_search`）：贝叶斯优化（k-NN 代理 + UCB 采集）与 MCTS；LLM 评估中间候选的科学合理性、引导剪枝与聚焦，评估次数落盘可审计。
4. **双轨验证**（`validate_discovery`）：无机材料走 Materials Project / NOMAD / OQMD 数据库；有机/框架材料走文献证据链（≥2 篇独立论文 → literature_supported）；数据库无记录时输出覆盖性说明。
5. **统计对比**（`run_model_comparison`）：抽取定量样本，拟合基线（均值/线性）与候选（二次/多特征）模型，输出 R²/RMSE 对比 + LLM 科学解释（含前人公式为何失效）。
6. **发现报告**：假设清单 + 证据链 + 验证状态 + 科学解释 + 负结果如实记录。

## 7. 通用性设计（无硬编码主题）

- 主题由命令行 `--topic` 传入；检索词、材料、性质、Gap、假设全部由运行时数据驱动。
- 性质关键词映射覆盖通用材料性质（带隙、容量、选择性、导热、介电、硬度、熔点、模量、热电、离子电导、强度、密度等）。
- 材料匹配支持元素+家族签名归一化（如 `Ni_xCo_y-MOF-74` ↔ `Ni/Co-MOF-74`），对化学式/家族名/别名均有效。
- 双轨验证按材料类型自适应；知识图谱审计、覆盖审计、新颖性核查均为通用确定性逻辑。

## 8. 增量说明

| 版本 | 关键增量 |
|---|---|
| v1（初始提交） | 完整四层架构、基本任务全流程、预算/记忆/checkpoint |
| v2 | NOMAD 验证接入 + MP 查询修复（_fields、requests）；知识图谱审计、双轨验证、全文深度阅读、检索覆盖审计 |
| v3 | 文献匹配元素/家族签名宽松化；get_full_text arXiv 标题回退 |
| v4 | 验证统一走工具（批量 all）；LLM×搜索融合（中间评估/剪枝）；新颖性核查；模型统计对比；性质映射通用化 |

## 9. 复现与环境

- Python 3.10+（开发环境 3.13），`.venv` 已就绪。
- 密钥：`.api_key`（`DEEPSEEK_API_KEY` 必需；`SCIVERSE_API_KEY`、`MATERIALS_PROJECT_API_KEY`、`MINERU_API_KEY` 可选）。
- 运行：`python main.py --topic "<主题>" --budget 1800`。
- 输出：`workspace/outputs/literature_survey/`（五件套 + 发现），轨迹与缓存见 `workspace/logs/`、`workspace/data/`。
