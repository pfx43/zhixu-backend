import os

from app.core import paddle_env  # noqa: F401
import urllib.parse
from pathlib import Path
from dotenv import load_dotenv

from app.core.app_config import get_app_config

load_dotenv()

_app_cfg = get_app_config()

SECRET_KEY = os.getenv("SECRET_KEY", "your-very-secret-key")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

# 项目根目录（zhishi/），无论从 backend/ 还是仓库根启动均可解析
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR
_DEFAULT_SQLITE_PATH = _REPO_ROOT / "data" / "zhishi.db"


def _default_database_url() -> str:
    return f"sqlite:///{_DEFAULT_SQLITE_PATH.as_posix()}"


SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", _default_database_url())

# MySQL 连接参数（仅当 DATABASE_URL 未设置且需回退 MySQL 时使用；团队环境请直接设 DATABASE_URL）
password = urllib.parse.quote_plus(os.getenv("DB_PASSWORD", "@430524Lj"))
host = os.getenv("DB_HOST", "127.0.0.1")
port = os.getenv("DB_PORT", "3306")
db_name = os.getenv("DB_NAME", "my_ai_app")
user = os.getenv("DB_USER", "root")

# SMTP 邮件配置
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "your-email@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "your-app-password")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USER)
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Zhishi Backend")

# 邮箱验证码有效期（分钟）
EMAIL_VERIFICATION_EXPIRE_MINUTES = int(os.getenv("EMAIL_VERIFICATION_EXPIRE_MINUTES", 15))

# 密码重置链接有效期（分钟）
PASSWORD_RESET_EXPIRE_MINUTES = int(os.getenv("PASSWORD_RESET_EXPIRE_MINUTES", 30))

# 应用前端 URL（用于验证链接）
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Dify 知识库配置
DIFY_BASE_URL = os.getenv("DIFY_BASE_URL", "https://api.dify.ai/v1")
DIFY_DATASET_API_KEY = os.getenv("DIFY_DATASET_API_KEY", "")
DIFY_INDEXING_TECHNIQUE = os.getenv("DIFY_INDEXING_TECHNIQUE", "high_quality")
DIFY_PROCESS_RULE = {
    "rules": {
        "pre_processing_rules": [
            {"id": "remove_extra_spaces", "enabled": True},
            {"id": "remove_urls_emails", "enabled": True},
        ],
        "segmentation": {"separator": "###", "max_tokens": 512},
    },
    "mode": "custom",
}

# Dify 嵌入模型 & Rerank 配置
DIFY_EMBEDDING_MODEL = os.getenv("DIFY_EMBEDDING_MODEL", "multimodal-embedding-v1")
DIFY_EMBEDDING_MODEL_PROVIDER = os.getenv("DIFY_EMBEDDING_MODEL_PROVIDER", "tongyi")
DIFY_RERANKING_PROVIDER = os.getenv("DIFY_RERANKING_PROVIDER", "tongyi")
DIFY_RERANKING_MODEL = os.getenv("DIFY_RERANKING_MODEL", "gte-rerank")

# 欢迎文档路径（相对于 kt_backend 目录）
WELCOME_DOC_PATH = os.getenv("WELCOME_DOC_PATH", "docs/欢迎使用知拾.md")

# 文件存储配置
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local").lower()  # local | cos
LOCAL_STORAGE_DIR = os.getenv("LOCAL_STORAGE_DIR", "storage")

# COS 存储配置
COS_SECRET_ID = os.getenv("COS_SECRET_ID", "")
COS_SECRET_KEY = os.getenv("COS_SECRET_KEY", "")
COS_BUCKET = os.getenv("COS_BUCKET", "")
COS_REGION = os.getenv("COS_REGION", "ap-guangzhou")

# 上传大小限制（MB），优先环境变量，其次 config.json
_env_upload_mb = os.getenv("UPLOAD_MAX_SIZE_MB")
if _env_upload_mb is not None:
    UPLOAD_MAX_SIZE_MB = int(_env_upload_mb)
elif _app_cfg.upload_max_size_mb > 0:
    UPLOAD_MAX_SIZE_MB = _app_cfg.upload_max_size_mb
else:
    UPLOAD_MAX_SIZE_MB = 0

# 兼容旧 USE_OSS 变量
if os.getenv("USE_OSS", "").lower() == "true" and STORAGE_BACKEND == "local":
    STORAGE_BACKEND = "cos"

# 上传文件大小上限（字节）；0 表示不限制
# 优先 DEBUG_MAX_UPLOAD_SIZE 环境变量；否则 config.json upload_max_size_mb
_env_upload = os.getenv("DEBUG_MAX_UPLOAD_SIZE")
if _env_upload is not None:
    DEBUG_MAX_UPLOAD_SIZE = int(_env_upload)
elif _app_cfg.upload_max_size_mb > 0:
    DEBUG_MAX_UPLOAD_SIZE = _app_cfg.upload_max_size_mb * 1024 * 1024
else:
    DEBUG_MAX_UPLOAD_SIZE = 0

# PDF 解析最多读取页数；0 表示不限制（大文件可设如 200 以控制内存/耗时）
PDF_MAX_PAGES = int(os.getenv("PDF_MAX_PAGES", str(_app_cfg.pdf_max_pages)))

# 扫描型 PDF OCR 最多处理页数；0 表示全页（大 PDF 可设如 50 控制耗时/API 配额）
PDF_OCR_MAX_PAGES = int(
    os.getenv("PDF_OCR_MAX_PAGES", str(_app_cfg.pdf_ocr_max_pages))
)

# PDF 页渲染 DPI（OCR 用）；过高可能导致图片超百度 OCR 4MB 限制
PDF_OCR_RENDER_DPI = int(
    os.getenv("PDF_OCR_RENDER_DPI", str(_app_cfg.pdf_ocr_render_dpi))
)

# OCR 单文档最大并行页数（config.json ocr_max_parallel_pages）
OCR_MAX_PARALLEL_PAGES = max(
    1,
    int(os.getenv("OCR_MAX_PARALLEL_PAGES", str(_app_cfg.ocr_max_parallel_pages))),
)

# OCR 影子文档按页存放的子目录名（config.json ocr_pages_dir_name）
OCR_PAGES_DIR_NAME = os.getenv(
    "OCR_PAGES_DIR_NAME", _app_cfg.ocr_pages_dir_name
)

# OCR 后端：local（默认，PaddleOCR 本地）| baidu | auto（先 Paddle 再百度）
OCR_BACKEND = os.getenv("OCR_BACKEND", _app_cfg.ocr_backend).lower()

# 文档解析/分段/索引是否后台异步（config.json document_pipeline_async）
DOCUMENT_PIPELINE_ASYNC = (
    os.getenv("DOCUMENT_PIPELINE_ASYNC", str(_app_cfg.document_pipeline_async)).lower()
    == "true"
)

# 出题 API 是否后台异步（config.json question_gen_async）
QUESTION_GEN_ASYNC = (
    os.getenv("QUESTION_GEN_ASYNC", str(_app_cfg.question_gen_async)).lower() == "true"
)

# Tina LLM / Agent 是否使用 apredict（config.json llm_async）
LLM_ASYNC = (
    os.getenv("LLM_ASYNC", str(_app_cfg.llm_async)).lower() == "true"
)

# 图片上传 OCR 是否后台异步（config.json image_ocr_async）
IMAGE_OCR_ASYNC = (
    os.getenv("IMAGE_OCR_ASYNC", str(_app_cfg.image_ocr_async)).lower() == "true"
)

# 单文档最多生成题目数（config.json max_questions_per_document）
MAX_QUESTIONS_PER_DOCUMENT = int(
    os.getenv(
        "MAX_QUESTIONS_PER_DOCUMENT",
        str(_app_cfg.max_questions_per_document),
    )
)

# Dify 知识库单文件大小上限（字节）；0 表示不限制，仅在上传前做本地预检
# 显式设置 DIFY_MAX_UPLOAD_SIZE 后才拦截；实际能否入库仍受 Dify Cloud 侧限制
DIFY_MAX_UPLOAD_SIZE = int(os.getenv("DIFY_MAX_UPLOAD_SIZE", "0"))

# 本地向量 RAG（Chroma + sentence-transformers）
RAG_BACKEND = os.getenv("RAG_BACKEND", "local").lower()  # local | dify
_CHROMA_DEFAULT = _REPO_ROOT / "data" / "chroma"
_CHROMA_ENV = os.getenv("CHROMA_PERSIST_DIR", "")
if _CHROMA_ENV:
    _chroma_path = Path(_CHROMA_ENV)
    CHROMA_PERSIST_DIR = str(
        _chroma_path if _chroma_path.is_absolute() else (_REPO_ROOT / _chroma_path)
    )
else:
    CHROMA_PERSIST_DIR = str(_CHROMA_DEFAULT)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")


def is_local_rag() -> bool:
    return RAG_BACKEND == "local"

# 百度 OCR 配置（从 zhishi_app/assets/config/baidu_ocr.json 读取）
import json as _json
from pathlib import Path as _Path
_ocr_config_path = _Path(__file__).resolve().parent.parent.parent / "zhishi_app" / "assets" / "config" / "baidu_ocr.json"
try:
    with open(_ocr_config_path, "r", encoding="utf-8") as _f:
        _ocr_cfg = _json.load(_f)
    BAIDU_OCR_API_KEY = os.getenv("BAIDU_OCR_API_KEY", _ocr_cfg.get("api_key", ""))
    BAIDU_OCR_SECRET_KEY = os.getenv("BAIDU_OCR_SECRET_KEY", _ocr_cfg.get("secret_key", ""))
    BAIDU_OCR_API_URL = os.getenv("BAIDU_OCR_API_URL", _ocr_cfg.get("api_url", "https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic"))
except Exception:
    BAIDU_OCR_API_KEY = os.getenv("BAIDU_OCR_API_KEY", "")
    BAIDU_OCR_SECRET_KEY = os.getenv("BAIDU_OCR_SECRET_KEY", "")
    BAIDU_OCR_API_URL = os.getenv("BAIDU_OCR_API_URL", "https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic")
