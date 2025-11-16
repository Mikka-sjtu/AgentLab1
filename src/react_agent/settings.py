import os

# OpenRouter 配置
BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# 默认模型（可切换其他的）
DEFAULT_MODEL_NAME = "google/gemma-3-27b-it:free"
