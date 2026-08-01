"""
Dify 知识库客户端
封装 Dify Dataset API，支持创建知识库、上传文档、检索
"""
import json
import logging
from typing import Optional, List

import httpx

from app.core.config import (
    DIFY_BASE_URL,
    DIFY_DATASET_API_KEY,
    DIFY_INDEXING_TECHNIQUE,
    DIFY_PROCESS_RULE,
    DIFY_EMBEDDING_MODEL,
    DIFY_EMBEDDING_MODEL_PROVIDER,
    DIFY_RERANKING_PROVIDER,
    DIFY_RERANKING_MODEL,
    WELCOME_DOC_PATH,
)

logger = logging.getLogger(__name__)


class DifyKB:
    """
    用户知识库客户端

    使用方式：
        # 静态方法：创建知识库（注册时调用）
        dataset_id = DifyKB.create_dataset("张三_abc12345", "用户知识库")

        # 实例方法：操作已有知识库
        kb = DifyKB(dataset_id)
        results = kb.query("什么是微积分")
    """

    def __init__(self, dataset_id: str):
        if not dataset_id:
            raise ValueError("dataset_id 不能为空")
        self.dataset_id = dataset_id
        self.client = httpx.Client(
            timeout=httpx.Timeout(60.0, connect=10.0)
        )
        self.headers = {
            "Authorization": f"Bearer {DIFY_DATASET_API_KEY}",
            "Content-Type": "application/json",
        }

    # ─── 静态方法 ─────────────────────────────────────────

    @staticmethod
    def create_dataset(name: str, description: str = "") -> str:
        """
        创建一个空知识库，返回 dataset_id

        使用通义 multimodal-embedding-v1 + gte-rerank 进行混合检索

        Args:
            name: 知识库名称
            description: 知识库描述

        Returns:
            dataset_id (str): Dify 返回的知识库 UUID

        Raises:
            RuntimeError: Dify API 调用失败
        """
        url = f"{DIFY_BASE_URL}/datasets"
        headers = {
            "Authorization": f"Bearer {DIFY_DATASET_API_KEY}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "name": name,
            "description": description,
            "permissions": "only_me",
            "provider": "vendor",
        }

        # 只有配置了 provider 时才传 embedding 参数，否则让 Dify Cloud 用默认值
        if DIFY_EMBEDDING_MODEL_PROVIDER:
            payload["embedding_model"] = DIFY_EMBEDDING_MODEL
            payload["embedding_model_provider"] = DIFY_EMBEDDING_MODEL_PROVIDER

        retrieval_model: dict = {
            "search_method": "hybrid_search",
            "top_k": 10,
            "score_threshold_enabled": False,
        }

        # 只有配置了 provider 时才传 rerank 参数
        if DIFY_RERANKING_PROVIDER:
            retrieval_model["reranking_enable"] = True
            retrieval_model["reranking_model"] = {
                "reranking_provider_name": DIFY_RERANKING_PROVIDER,
                "reranking_model_name": DIFY_RERANKING_MODEL,
            }
        else:
            retrieval_model["reranking_enable"] = False

        payload["retrieval_model"] = retrieval_model

        try:
            with httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
                response = client.post(url, headers=headers, json=payload)
        except httpx.RequestError as e:
            logger.error(f"DifyKB.create_dataset - 网络请求失败: {e}")
            raise RuntimeError(f"无法连接到 Dify 服务: {e}")

        if response.status_code not in (200, 201):
            logger.error(
                f"DifyKB.create_dataset - 创建失败 "
                f"(status={response.status_code}): {response.text}"
            )
            raise RuntimeError(
                f"Dify 知识库创建失败 (HTTP {response.status_code})"
            )

        res_data = response.json()
        dataset_id = res_data.get("id")
        if not dataset_id:
            raise RuntimeError("Dify 返回数据缺少 id 字段")
        logger.info(f"DifyKB.create_dataset - 知识库创建成功: {dataset_id} ({name})")
        return dataset_id

    @staticmethod
    def upload_welcome_document(dataset_id: str) -> bool:
        """
        向新知识库上传欢迎文档

        Args:
            dataset_id: 知识库 ID

        Returns:
            bool: 是否上传成功
        """
        import os
        from pathlib import Path

        # 定位 welcome doc 文件（相对于 kt_backend/ 目录）
        backend_dir = Path(__file__).resolve().parent.parent.parent
        doc_path = backend_dir / WELCOME_DOC_PATH

        if not doc_path.exists():
            logger.warning(f"DifyKB.upload_welcome_document - 欢迎文档不存在: {doc_path}")
            return False

        url = f"{DIFY_BASE_URL}/datasets/{dataset_id}/document/create-by-file"

        data = {
            "indexing_technique": DIFY_INDEXING_TECHNIQUE,
            "process_rule": {"mode": "automatic"},
            "doc_form": "text_model",
        }

        try:
            with open(doc_path, "rb") as f:
                files = {
                    "data": (None, json.dumps(data), "application/json"),
                    "file": (doc_path.name, f, "application/octet-stream"),
                }
                upload_headers = {"Authorization": f"Bearer {DIFY_DATASET_API_KEY}"}
                with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
                    response = client.post(url, headers=upload_headers, files=files)
        except Exception as e:
            logger.error(f"DifyKB.upload_welcome_document - 上传失败: {e}")
            return False

        if response.status_code not in (200, 201):
            logger.warning(
                f"DifyKB.upload_welcome_document - 上传失败 "
                f"(status={response.status_code}): {response.text}"
            )
            return False

        logger.info(f"DifyKB.upload_welcome_document - 欢迎文档已上传: dataset_id={dataset_id}")
        return True

    @staticmethod
    def delete_dataset(dataset_id: str) -> bool:
        """
        删除 Dify 知识库

        Args:
            dataset_id: 知识库 ID

        Returns:
            bool: 是否删除成功
        """
        url = f"{DIFY_BASE_URL}/datasets/{dataset_id}"
        headers = {"Authorization": f"Bearer {DIFY_DATASET_API_KEY}"}

        try:
            with httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
                response = client.delete(url, headers=headers)
        except httpx.RequestError as e:
            logger.error(f"DifyKB.delete_dataset - 网络请求失败: {e}")
            return False

        if response.status_code not in (200, 204):
            logger.warning(
                f"DifyKB.delete_dataset - 删除失败 "
                f"(status={response.status_code}): {response.text}"
            )
            return False

        logger.info(f"DifyKB.delete_dataset - 知识库已删除: {dataset_id}")
        return True

    # ─── 实例方法 ─────────────────────────────────────────

    def query(self, query_text: str, top_k: int = 5) -> List[dict]:
        """
        检索知识库

        Args:
            query_text: 检索文本
            top_k: 返回结果数量（会被 Dify 服务端 top_k 上限截断）

        Returns:
            [{score: float, content: str}, ...]
        """
        url = f"{DIFY_BASE_URL}/datasets/{self.dataset_id}/retrieve"
        payload = {
            "query": query_text,
            "retrieval_model": {
                "search_method": "hybrid_search",
                "reranking_enable": True,
                "top_k": top_k,
                "score_threshold_enabled": False,
            },
        }

        try:
            response = self.client.post(url, headers=self.headers, json=payload)
        except httpx.RequestError as e:
            logger.error(f"DifyKB.query - 网络请求失败: {e}")
            return []

        if response.status_code != 200:
            logger.warning(
                f"DifyKB.query - 检索失败 "
                f"(status={response.status_code}): {response.text}"
            )
            return []

        resp = response.json()
        records = resp.get("records", [])
        results = []
        for rec in records:
            segment = rec.get("segment") or {}
            document = segment.get("document") or {}
            dify_document_id = (
                segment.get("document_id")
                or document.get("id")
            )
            results.append({
                "score": rec.get("score", 0),
                "content": segment.get("content", ""),
                "dify_document_id": dify_document_id,
                "document_name": document.get("name"),
            })
        return results

    def add_document(
        self, file_path: str, upload_filename: Optional[str] = None
    ) -> dict:
        """
        上传文档到知识库

        Args:
            file_path: 本地文件路径
            upload_filename: 提交给 Dify 的文件名（需含扩展名）

        Returns:
            成功: {"batch_id": str, "document_id": str}
            失败: {"error": str, "http_status": int}
        """
        from pathlib import Path

        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            logger.error(f"DifyKB.add_document - 文件不存在: {file_path}")
            return {"error": "本地文件不存在", "http_status": 500}

        url = f"{DIFY_BASE_URL}/datasets/{self.dataset_id}/document/create-by-file"

        data = {
            "indexing_technique": DIFY_INDEXING_TECHNIQUE,
            "process_rule": DIFY_PROCESS_RULE,
            "doc_form": "text_model",
        }

        filename = upload_filename or file_path_obj.name
        mime_type = self._guess_upload_mime(filename)

        try:
            with open(file_path, "rb") as f:
                files = {
                    "data": (None, json.dumps(data), "application/json"),
                    "file": (filename, f, mime_type),
                }
                # headers 不包含 Content-Type，交给 httpx 自动处理 multipart
                upload_headers = {"Authorization": f"Bearer {DIFY_DATASET_API_KEY}"}
                response = self.client.post(
                    url, headers=upload_headers, files=files
                )
        except Exception as e:
            logger.error(f"DifyKB.add_document - 上传失败: {e}")
            return {"error": str(e), "http_status": 502}

        if response.status_code not in (200, 201):
            detail = self._extract_error_message(response)
            logger.error(
                f"DifyKB.add_document - 上传失败 "
                f"(status={response.status_code}): {response.text}"
            )
            return {"error": detail, "http_status": response.status_code}

        resp = response.json()
        batch_id = resp.get("batch")
        doc_id = resp.get("document", {}).get("id")
        logger.info(
            f"DifyKB.add_document - 上传成功 "
            f"doc_id={doc_id} batch_id={batch_id}"
        )
        return {"batch_id": batch_id, "document_id": doc_id}

    @staticmethod
    def _guess_upload_mime(filename: str) -> str:
        from pathlib import Path

        mapping = {
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".csv": "text/csv",
            ".json": "application/json",
            ".html": "text/html",
            ".htm": "text/html",
            ".pdf": "application/pdf",
            ".docx": (
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }
        return mapping.get(Path(filename).suffix.lower(), "application/octet-stream")

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
            message = payload.get("message") or payload.get("code") or ""
            if message:
                return str(message)
        except ValueError:
            pass
        text = (response.text or "").strip()
        return text or f"Dify 返回 HTTP {response.status_code}"

    def get_indexing_status(self, batch_id: str) -> dict:
        """
        查询文档索引状态

        Args:
            batch_id: 批次 ID

        Returns:
            {"status": "completed"|"indexing"|"error", ...}
        """
        url = (
            f"{DIFY_BASE_URL}/datasets/{self.dataset_id}"
            f"/documents/{batch_id}/indexing-status"
        )
        try:
            response = self.client.get(url, headers=self.headers)
        except httpx.RequestError as e:
            logger.error(f"DifyKB.get_indexing_status - 请求失败: {e}")
            return {"status": "error", "error": str(e)}

        if response.status_code != 200:
            return {"status": "error", "error": response.text}

        return response.json()

    def list_documents(self, page: int = 1, limit: int = 20) -> dict:
        """
        列出知识库中的文档

        Args:
            page: 页码
            limit: 每页数量

        Returns:
            {
                "data": [{
                    "id", "name", "file_type", "file_size",
                    "indexing_status", "created_at", "updated_at"
                }, ...],
                "total": int
            }
        """
        url = f"{DIFY_BASE_URL}/datasets/{self.dataset_id}/documents"
        params = {"page": page, "limit": limit}
        try:
            response = self.client.get(url, headers=self.headers, params=params)
        except httpx.RequestError as e:
            logger.error(f"DifyKB.list_documents - 请求失败: {e}")
            return {"data": [], "total": 0, "error": str(e)}

        if response.status_code != 200:
            logger.warning(
                f"DifyKB.list_documents - 查询失败 "
                f"(status={response.status_code}): {response.text}"
            )
            return {"data": [], "total": 0}

        resp = response.json()
        return {
            "data": resp.get("data", []),
            "total": resp.get("total", 0),
            "page": resp.get("page", page),
            "limit": resp.get("limit", limit),
        }

    def delete_document(self, document_id: str) -> bool:
        """
        删除知识库中的文档

        Args:
            document_id: 文档 ID

        Returns:
            bool: 是否成功
        """
        url = f"{DIFY_BASE_URL}/datasets/{self.dataset_id}/documents/{document_id}"
        try:
            response = self.client.delete(url, headers=self.headers)
        except httpx.RequestError as e:
            logger.error(f"DifyKB.delete_document - 请求失败: {e}")
            return False

        if response.status_code not in (200, 204):
            logger.warning(
                f"DifyKB.delete_document - 删除失败 "
                f"(status={response.status_code}): {response.text}"
            )
            return False

        logger.info(f"DifyKB.delete_document - 删除成功: {document_id}")
        return True
