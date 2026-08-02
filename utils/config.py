"""全局配置常量"""
import os
from pathlib import Path

# 时间预算
TOTAL_BUDGET_SECONDS = 7200  # 2 小时
SAFETY_MARGIN_SECONDS = 300  # 5 分钟安全余量

# ── API Key ──
# 方式1: 环境变量 DEEPSEEK_API_KEY
# 方式2: 项目根目录创建 .api_key 文件，写入 DeepSeek API Key

def _load_api_key_file() -> dict[str, str]:
    """解析 .api_key 文件，支持两种格式：
    第一行（无 =）：视为 DEEPSEEK_API_KEY（向后兼容）
    后续 KEY=VALUE 行：解析为对应环境变量
    """
    keys: dict[str, str] = {}
    key_file = Path(__file__).resolve().parent.parent / ".api_key"
    if not key_file.exists():
        return keys
    for line in key_file.read_text().strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            keys[k.strip()] = v.strip()
        else:
            # 向后兼容：纯文本行视为 DeepSeek key
            if "DEEPSEEK_API_KEY" not in keys:
                keys["DEEPSEEK_API_KEY"] = line
    return keys


def _resolve_api_key() -> str:
    env_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if env_key:
        return env_key
    return _load_api_key_file().get("DEEPSEEK_API_KEY", "")

# 加载 Sciverse key
_SCIVERSE_KEY = os.environ.get("SCIVERSE_API_KEY", "") or _load_api_key_file().get("SCIVERSE_API_KEY", "")
if _SCIVERSE_KEY:
    os.environ.setdefault("SCIVERSE_API_KEY", _SCIVERSE_KEY)

DEEPSEEK_API_KEY = _resolve_api_key()

# DeepSeek V4 Flash
# Context window: 1M input, 384K output
# https://api-docs.deepseek.com/quick_start/pricing/
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEEPSEEK_MAX_INPUT_TOKENS = 1_000_000   # 1M context window
DEEPSEEK_MAX_OUTPUT_TOKENS = 384_000    # 384K max output
DEEPSEEK_MAX_TOKENS = DEEPSEEK_MAX_OUTPUT_TOKENS  # 向后兼容别名
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
