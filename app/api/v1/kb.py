"""
知识库管理路由 — 分区 CRUD / 文件上传 / 文档列表 / 索引进度 / 删除 / 内容预览
所有接口需要登录鉴权，用户隔离
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.api.deps_quota import check_kb_quota
from app.core.config import DEBUG_MAX_UPLOAD_SIZE, USE_OSS, is_local_rag
from app.schemas.kb import CollectionCreate, CollectionUpdate
from app.services.knowledge import kb_service
from app.services.knowledge import page_service
from app.services.knowledge import segment_service
from app.crud import kb as kb_crud
from app.services.knowledge.file_parser import SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["知识库管理"])


def _format_size(bytes_val: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"


# ─── 知识库分区 ────────────────────────────────────────────

@router.get("/collections")
def list_collections(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """列出当前用户的知识库分区"""
    return kb_service.list_collections(
        db, current_user["user_id"], current_user.get("dataset_id")
    )


@router.post("/collections", status_code=status.HTTP_201_CREATED)
def create_collection(
    payload: CollectionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
    _kb_quota: dict = Depends(check_kb_quota),
):
    """创建知识库分区（受知识库数量配额限制）"""
    return kb_service.create_collection(
        db,
        current_user["user_id"],
        payload,
        current_user.get("dataset_id"),
    )


@router.patch("/collections/{collection_id}")
def update_collection(
    collection_id: str,
    payload: CollectionUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """更新分区名称或描述"""
    return kb_service.update_collection(
        db, current_user["user_id"], collection_id, payload
    )


# ─── 分区别名（兼容前端 /categories 路径） ─────────────────

@router.get("/categories")
def list_categories(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """列出当前用户的知识库分区（categories 别名）"""
    return kb_service.list_collections(
        db, current_user["user_id"], current_user.get("dataset_id")
    )


@router.post("/categories", status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CollectionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """创建知识库分区（categories 别名）"""
    return kb_service.create_collection(
        db,
        current_user["user_id"],
        payload,
        current_user.get("dataset_id"),
    )


@router.patch("/categories/{collection_id}")
def update_category(
    collection_id: str,
    payload: CollectionUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """更新分区名称或描述（categories 别名）"""
    return kb_service.update_collection(
        db, current_user["user_id"], collection_id, payload
    )


@router.delete("/categories/{collection_id}")
def delete_category(
    collection_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """删除知识库分区（categories 别名）"""
    return kb_service.delete_collection(
        db, current_user["user_id"], collection_id
    )


@router.delete("/collections/{collection_id}")
def delete_collection(
    collection_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """删除知识库分区"""
    return kb_service.delete_collection(
        db, current_user["user_id"], collection_id
    )


# ─── 上传文档 ────────────────────────────────────────────

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    collection_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """
    上传文档到用户的知识库分区

    流程：
        1. 文件大小校验
        2. SHA256 → global_documents 去重
        3. 解析文本并缓存
        4. 分段并写入 Chroma 向量索引（RAG_BACKEND=local）
        5. 写入 documents 表

  支持格式：txt, md, csv, json, html, pdf, docx 及图片 OCR
    """
    content_bytes = await file.read()
    try:
        return kb_service.upload_document(
            db=db,
            user_id=current_user["user_id"],
            user_dataset_id=current_user.get("dataset_id"),
            filename=file.filename or "",
            content_bytes=content_bytes,
            collection_id=collection_id,
            max_upload_size=DEBUG_MAX_UPLOAD_SIZE,
            use_oss=USE_OSS,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传文档异常: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"上传失败: {str(e)}",
        )


# ─── 文档列表 ────────────────────────────────────────────

@router.get("/documents")
def list_documents(
    page: int = 1,
    limit: int = 20,
    collection_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """列出当前用户知识库中的文档，可按 collection_id 过滤"""
    return kb_service.list_documents(
        db=db,
        user_id=current_user["user_id"],
        user_dataset_id=current_user.get("dataset_id"),
        page=page,
        limit=limit,
        collection_id=collection_id,
    )


# ─── 索引进度查询 ─────────────────────────────────────────

@router.get("/documents/{batch_id}/status")
def get_document_status(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """查询文档索引进度（使用上传返回的 batch_id / document_id）"""
    user_id = current_user["user_id"]

    if is_local_rag():
        doc = kb_crud.get_document_by_id_or_dify(db, user_id, batch_id)
        if not doc:
            doc = kb_crud.get_document_by_batch_id(db, user_id, batch_id)
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")
        return kb_service.document_status_payload(doc, batch_id)

    from app.services.knowledge.dify_kb import DifyKB

    dataset_id = current_user.get("dataset_id")
    if not dataset_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="您的知识库尚未创建，请先完成注册",
        )
    kb = DifyKB(dataset_id)
    result = kb.get_indexing_status(batch_id)

    if "data" in result and isinstance(result["data"], list) and len(result["data"]) > 0:
        item = result["data"][0]
        return {
            "batch_id": batch_id,
            "status": item.get("indexing_status", "unknown"),
            "error_message": item.get("error_message"),
            "completed_segments": item.get("completed_segments", 0),
            "total_segments": item.get("total_segments", 0),
        }

    return {
        "batch_id": batch_id,
        "status": result.get("status", "unknown"),
        "error": result.get("error"),
    }


# ─── 删除文档 ────────────────────────────────────────────

@router.delete("/documents/{doc_id}")
def delete_document(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """从知识库中删除文档（支持 documents.id 或 dify_document_id）"""
    return kb_service.delete_document(
        db,
        current_user["user_id"],
        current_user.get("dataset_id"),
        doc_id,
    )


# ─── 文档内容预览 ─────────────────────────────────────────

@router.get("/documents/{doc_id}/content")
def get_document_content(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """获取文档解析后的文本内容或预览元数据"""
    return kb_service.get_document_content(db, current_user["user_id"], doc_id)


@router.get("/documents/{doc_id}/file")
def get_document_file(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """下载/预览原始上传文件（PDF 等）"""
    return kb_service.serve_document_file(db, current_user["user_id"], doc_id)


@router.get("/documents/{doc_id}/segments")
def list_document_segments(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """列出文档分段（仅文档 owner 可访问）"""
    return segment_service.list_document_segments(
        db, current_user["user_id"], doc_id
    )


@router.get("/documents/{doc_id}/pages")
def list_document_pages(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """按页码平铺文档（从 parsed 文本 `## 第 N 页` 切分）"""
    return page_service.list_document_pages(
        db, current_user["user_id"], doc_id
    )


@router.get("/documents/{doc_id}/pages/{page_number}")
def get_document_page(
    page_number: int,
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """单页详情（双击进详情用）"""
    return page_service.get_document_page_detail(
        db, current_user["user_id"], doc_id, page_number
    )


# ─── 配置查询（供前端使用） ───────────────────────────────

@router.get("/config")
def get_kb_config(
    current_user: dict = Depends(get_current_active_user),
):
    """查询知识库配置（供前端展示提示等）"""
    return {
        "rag_backend": "local" if is_local_rag() else "dify",
        "use_oss": USE_OSS,
        "max_upload_size": DEBUG_MAX_UPLOAD_SIZE,
        "max_upload_size_display": (
            _format_size(DEBUG_MAX_UPLOAD_SIZE) if DEBUG_MAX_UPLOAD_SIZE else None
        ),
        "supported_extensions": list(SUPPORTED_EXTENSIONS.keys()),
    }
