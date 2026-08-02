"""
Pi-Agent: 自主文献调研 Agent

架构层次：
  Layer 1: llm.py       — DeepSeek API 调用 + 工具定义
  Layer 2: agent.py     — ReAct 循环 + 事件驱动 + 状态机 + 会话 + 上下文压缩
  Layer 3: prompts.py   — 系统提示词
  Layer 4: tools.py     — 工具管线（读写文件、启停 Shell、监控进程）
"""

from pi_agent.agent import PiAgent

__all__ = ["PiAgent"]
