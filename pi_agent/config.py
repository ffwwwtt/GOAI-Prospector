"""
Pi-Agent 配置 — 复用项目全局配置常量，补充 Agent 专属设置。
"""
import os
import sys

# ── 从项目全局配置复出 ──
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from utils.config import (  # noqa: E402, F401 — intentional re-export
    TOTAL_BUDGET_SECONDS,
    SAFETY_MARGIN_SECONDS,
    DEEPSEEK_API_KEY,
    DEEPSEEK_MODEL,
    DEEPSEEK_MAX_INPUT_TOKENS,
    DEEPSEEK_MAX_OUTPUT_TOKENS,
    DEEPSEEK_MAX_TOKENS,
    DEEPSEEK_BASE_URL,
)

# ── Pi-Agent 专属设置 ──
CONTEXT_COMPRESSION_THRESHOLD = 2_800_000  # 压缩阈值（字符数），约 800K tokens，留 20% 给模型回复
MAX_TOOL_OUTPUT_LENGTH = 250_000           # 单次工具输出最大字符数
MAX_RETRIES_LLM = 5                        # API 最大重试次数
CHECKPOINT_INTERVAL = 1                    # 每 N 轮保存一次 checkpoint
