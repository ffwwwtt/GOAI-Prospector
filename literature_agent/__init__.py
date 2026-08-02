"""
Literature Agent — 材料科学文献调研工具链
===========================================
为 Pi-Agent 提供文献检索、论文解析、知识图谱数据模型和构效关系发现能力。

模块：
  search.py    — 多源文献检索（arXiv API + Sciverse + Sci-Base）
  parser.py    — 论文解析器（PDF/DOCX/HTML → 结构化文本）
  extractor.py — 知识图谱数据模型 + 跨文献知识融合
  discovery.py — 构效关系发现引擎（贝叶斯优化/MCTS + LLM）
"""
