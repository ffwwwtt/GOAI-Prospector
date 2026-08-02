# GOAI 赛道三 · 方向三：材料科学文献驱动的科学发现智能体

## 初赛方案说明（问题定义与技术方案）

---

## 1. 赛题理解

本赛题包含两部分，均需完成：

- **基本任务（必做）**：文献调研 Agent——自主完成文献检索与筛选、知识抽取、Research Gap 识别、结构化调研报告（含文献交叉引用与证据链）。
- **进阶路线（三选一）**：本项目选择 **路线 A：构效关系发现**（Structure-Property Relationship Discovery）。

## 2. 科学问题

材料科学的知识高度沉淀于非结构化文献之中——组分、结构、工艺与性能之间的关联大量散落在数十年论文里，人工阅读的覆盖能力与大模型时代的文献规模已形成根本落差。本项目要解决的核心问题是：

> **如何让一个 Agent 从文献出发，自主完成"检索 → 知识抽取 → Gap 识别 → 假设生成 → 搜索发现 → 外部验证 → 报告沉淀"的闭环，并产出可证伪、可追溯、可统计验证的构效关系发现？**

## 3. 系统概览

Prospector：一个**主题无关**的文献驱动科学发现智能体。

输入：任意材料研究主题（如 "MOF materials for CO2 capture"、"halide perovskites band gap"、"thermoelectric ZT optimization"）。
输出（在时间预算内自主完成）：

- 调研报告（含 Gap 清单、文献交叉引用、证据链）
- 知识图谱（Markdown，材料/性质/数值/关系，附论文 ID）
- 构效关系发现（假设 + 搜索证据 + 双轨验证 + 统计对比 + 科学解释）

全程无需人工干预；中断可续跑，跨轮可继承记忆。

## 4. 技术方案

### 4.1 整体架构（四层）

```
main.py ── 入口：参数解析 + 时间预算 + 异常处理
│
prospector/        Agent 核心（ReAct 主循环、事件驱动、状态机、
│                 LLM 客户端、工具管线、记忆、checkpoint、上下文压缩）
literature_agent/ 领域工具链（检索、解析、知识图谱、发现引擎）
markitdown_utils/ 本地文档解析（PDF/DOCX/HTML）
vendor/bash/      自带 Git Bash（Windows 兼容）
```

### 4.2 基本任务：四阶段流程

1. **检索与筛选**：多源检索（arXiv + Sciverse + Sci-Base），结果缓存去重；`assess_search_coverage` 确定性评估唯一论文数、来源分布、边际收益，给出"继续/停止检索"建议。
2. **知识抽取**：`extract_knowledge` 整理论文摘要 → Agent 深度阅读关键论文全文（`get_full_text`）→ 手写 Markdown 知识图谱 → `audit_knowledge_graph` 审计数值冲突/重复写法/溯源缺失（冲突直接成为矛盾型 Gap 候选）。
3. **Gap 识别**：Agent 基于摘要 + 审计报告，识别矛盾结论、缺失连接、未探索空间，输出 Gap 清单（含严重程度、证据论文、验证方案）。
4. **报告生成**：结构化调研报告（执行摘要、文献综述、材料-性质对比表、Gap 与未来方向、参考文献）。

### 4.3 路线 A：构效关系发现流水线

```
generate_hypotheses（LLM 生成假设）
  → check_novelty（系统性新颖性核查：known / partial / new）
  → run_discovery_search（贝叶斯优化 / MCTS × LLM 融合搜索）
  → validate_discovery（双轨验证：无机库 / 文献证据链）
  → run_model_comparison（新规律 vs 基线/前人公式的 R²/RMSE 对比）
  → generate_discovery_report（发现报告 + 科学解释）
```

### 4.4 关键机制

- **时间预算管理**：按剩余比例分级提醒，耗尽时强制收尾指令；API 等待不计入有效预算。
- **会话持久化**：每轮 checkpoint，中断后可无缝续跑（`--fresh` 强制重跑）。
- **跨轮记忆**：MEMORY.md 索引 + 单轮总结 + 反思日志，续跑自动继承。
- **上下文压缩**：长对话自动分层压缩，保持 1M token 窗口内。
- **证据链审计**：每条数值可追溯论文 ID；审计工具保证溯源缺失清零。
- **零虚假引用**：全部引用来自真实检索缓存，不引入任何编造文献。

## 5. 通用性设计（不绑定主题）

- 调研主题由 `--topic` 参数驱动，检索词、材料、性质关键词全部来自运行时数据。
- 性质关键词映射覆盖通用材料性质（带隙、容量、选择性、导热、介电、硬度、熔点、模量、热电、离子电导、强度、密度等），不绑定 MOF 或任何子领域。
- 双轨验证自适应材料类型：无机晶体走 MP/NOMAD/OQMD 数据库；有机/框架材料走文献证据链。
- 参照系设计：贝叶斯搜索 vs 同预算随机搜索公平对比，排除"发现只是随机运气"。

## 6. 已验证案例（示例主题，非绑定）

以 "MOF materials for CO2 capture" 为主题完成两次真实运行：

| 运行 | 轮次 | 论文 | 产出 |
|---|---|---|---|
| 600s 冒烟 | 30 轮 | 120 篇 | 5 条假设、完整五件套 |
| 1800s 深化 | 91 轮 | 180 篇 | 8 条假设全部 literature_supported；2 项定量元分析；矛盾统一（缺陷二象性）；水效应符号翻转（物理 0.87 vs 化学 1.25） |

引用全部可查（p1–p180 对应真实检索缓存），无虚假引用；被清晰解释的负结果（如双金属非单调、孔径带估计失败）如实记录。

**跨主题验证（证明通用性）**：另以三个独立主题各跑一轮 600s 端到端测试——卤化物钙钛矿带隙稳定性（96 篇）、热电材料 ZT 优化（140 篇）、锂电高镍正极容量保持率（174 篇），全部一次跑通完整闭环（检索→知识图谱+审计→Gap→假设→新颖性核查→LLM×搜索融合→批量双轨验证→发现报告），详见 `submission_initial/05_跨主题验证报告.md` 与 `submission_initial/evidence/`。

## 7. 合规与复现

- **商业 API 披露**：DeepSeek（推理，`deepseek-v4-flash`）、Sciverse（文献检索）、Materials Project（外部验证）——调用环节、费用假设、替代方案（任意 OpenAI 兼容端点 / 纯 arXiv 检索）均已披露。
- **密钥管理**：`.api_key` 已 gitignore，不入库。
- **闭源模型使用说明**：选择 DeepSeek（闭源推理模型）因其推理质量/成本比与 1M 上下文窗口；迁移成本低——OpenAI 兼容接口，切换端点仅需改环境变量；对可复现性的影响通过"论文 ID 证据链可独立核验"缓解。
- **基于已有项目**：`markitdown_utils/` 改编自微软 markitdown（MIT，Copyright Adam Fourney），仅保留 PDF/DOCX/HTML 转换器；Agent 系统其余部分均为本项目原创。
- **第三方依赖与许可证**：依赖见 `requirements.txt`（均为开源许可）；`vendor/bash` 为 MSYS2 Git Bash（GPLv2+），仅用于 Windows 兼容运行环境，未做修改。
- **复现命令**：
  ```bash
  pip install -r requirements.txt
  python main.py --topic "<任意材料主题>" --budget 1800
  ```
- **开源计划**：初赛不强制开源；复赛提交可运行代码仓库 + 复现说明。
