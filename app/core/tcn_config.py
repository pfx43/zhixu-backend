"""TCN 引擎层连接配置 — 从环境变量读取"""

import os

TCN_BASE_URL = os.getenv("TCN_BASE_URL", "http://127.0.0.1:8001")
TCN_ADMIN_TOKEN = os.getenv("TCN_ADMIN_TOKEN", "")
TCN_TIMEOUT = int(os.getenv("TCN_TIMEOUT", "5"))
TCN_MAX_RETRIES = int(os.getenv("TCN_MAX_RETRIES", "2"))
TCN_ENABLED = os.getenv("TCN_ENABLED", "true").lower() == "true"
TCN_SECRET_SALT = os.getenv("TCN_SECRET_SALT", "zhixu-tcn-salt-2026")