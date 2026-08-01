"""
文件存储服务 — 统一存取接口

使用方式：
    from app.services.storage_service import storage_service

    # 保存文件
    path = storage_service.save_file(user_id, filename, content_bytes)
    # 读取文件
    data = storage_service.get_file(user_id, filename)
    # 列表
    files = storage_service.list_user_files(user_id)
    # 删除
    storage_service.delete_file(user_id, filename)

配置：
    USE_OSS=False → 本地存储 (storage/{user_id}/)
    USE_OSS=True  → OSS 存储（未实现）
"""
import json
import logging
import re
import shutil
from pathlib import Path
from typing import List, Optional

from app.core.config import OCR_PAGES_DIR_NAME, USE_OSS, LOCAL_STORAGE_DIR

logger = logging.getLogger(__name__)

PAGE_FILE_PATTERN = re.compile(r"^page_(\d+)\.md$", re.IGNORECASE)


def build_page_markdown(page_number: int, text: str) -> str:
    """单页 OCR 影子 Markdown（含页标题）。"""
    body = text.strip() if text and text.strip() else "（本页未识别到文字）"
    return f"## 第 {page_number} 页\n\n{body}\n"


class LocalStorage:
    """本地文件系统存储"""

    def __init__(self, base_dir: str):
        self.base = Path(base_dir).resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def _user_dir(self, user_id: int, subdir: str = "original") -> Path:
        d = self.base / str(user_id) / subdir
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_file(self, user_id: int, filename: str, content: bytes) -> str:
        """保存文件，返回完整路径"""
        d = self._user_dir(user_id, "original")
        safe_name = Path(filename).name
        path = d / safe_name
        path.write_bytes(content)
        logger.info(f"LocalStorage.save_file: {path} ({len(content)} bytes)")
        return str(path)

    def save_text(self, user_id: int, filename: str, content: str) -> str:
        """保存文本文件（用于解析缓存）"""
        d = self._user_dir(user_id, "parsed")
        safe_name = Path(filename).name
        path = d / safe_name
        path.write_text(content, encoding="utf-8")
        logger.info(f"LocalStorage.save_text: {path} ({len(content)} chars)")
        return str(path)

    def get_file(self, user_id: int, filename: str) -> Optional[bytes]:
        """读取原始文件字节"""
        d = self._user_dir(user_id, "original")
        path = d / Path(filename).name
        if path.exists():
            return path.read_bytes()
        return None

    def get_parsed(self, user_id: int, filename: str) -> Optional[str]:
        """读取解析后的文本缓存"""
        d = self._user_dir(user_id, "parsed")
        path = d / Path(filename).name
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def delete_file(self, user_id: int, filename: str) -> bool:
        """删除原始文件（同时尝试删除对应的 parsed 缓存）"""
        d = self._user_dir(user_id, "original")
        path = d / Path(filename).name
        deleted = False
        if path.exists():
            path.unlink()
            deleted = True

        # 同时删除同名 parsed 缓存
        pd = self._user_dir(user_id, "parsed")
        ppath = pd / Path(filename).name
        if ppath.exists():
            ppath.unlink()
        return deleted

    def delete_user_storage(self, user_id: int) -> bool:
        """删除用户整个存储目录"""
        d = self.base / str(user_id)
        if d.exists():
            try:
                shutil.rmtree(str(d))
                logger.info(f"LocalStorage.delete_user_storage: 已删除 {d}")
                return True
            except OSError as e:
                logger.error(f"LocalStorage.delete_user_storage 失败: {e}")
                return False
        return False

    def list_user_files(self, user_id: int) -> List[dict]:
        """列出用户所有原始文件"""
        d = self._user_dir(user_id, "original")
        files = []
        for p in d.iterdir():
            if p.is_file():
                stat = p.stat()
                files.append({
                    "filename": p.name,
                    "size": stat.st_size,
                    "modified_at": stat.st_mtime,
                })
        return files

    # ─── 全局去重存储 ─────────────────────────────────────

    def _global_dir(self, hash_prefix: str) -> Path:
        d = self.base / "global" / hash_prefix
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_global_file(
        self, content_hash: str, content: bytes, suffix: str = ""
    ) -> str:
        """保存全局去重文件，路径 storage/global/{hash[:2]}/{hash}{suffix}"""
        normalized = suffix.lower()
        if normalized and not normalized.startswith("."):
            normalized = f".{normalized}"
        filename = f"{content_hash}{normalized}" if normalized else content_hash
        path = self._global_dir(content_hash[:2]) / filename
        path.write_bytes(content)
        logger.info(f"LocalStorage.save_global_file: {path} ({len(content)} bytes)")
        return str(path)

    def save_global_parsed(self, content_hash: str, content: str) -> str:
        """保存全局解析文本缓存（单文件，向后兼容）"""
        path = self._global_dir(content_hash[:2]) / f"{content_hash}.parsed.txt"
        path.write_text(content, encoding="utf-8")
        logger.info(f"LocalStorage.save_global_parsed: {path} ({len(content)} chars)")
        return str(path)

    def _global_parsed_pages_dir(self, content_hash: str) -> Path:
        return self._global_dir(content_hash[:2]) / f"{content_hash}.parsed"

    def save_global_parsed_pages(
        self,
        content_hash: str,
        page_texts: list[str],
        *,
        original_filename: str = "",
        ocr_used: bool = True,
    ) -> str:
        """OCR 按页写入影子文件夹，返回文件夹路径（作为 parsed_text_path）。"""
        base = self._global_parsed_pages_dir(content_hash)
        pages_dir = base / OCR_PAGES_DIR_NAME
        if base.exists():
            shutil.rmtree(base)
        pages_dir.mkdir(parents=True, exist_ok=True)

        for i, text in enumerate(page_texts, 1):
            page_path = pages_dir / f"page_{i:03d}.md"
            page_path.write_text(build_page_markdown(i, text), encoding="utf-8")

        manifest = {
            "version": 1,
            "original_filename": original_filename or "",
            "total_pages": len(page_texts),
            "ocr_used": ocr_used,
            "pages_dir": OCR_PAGES_DIR_NAME,
        }
        (base / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(
            "LocalStorage.save_global_parsed_pages: %s (%d pages)",
            base,
            len(page_texts),
        )
        return str(base)

    def save_global_parsed_content(
        self,
        content_hash: str,
        content: str,
        *,
        page_texts: Optional[list[str]] = None,
        original_filename: str = "",
        ocr_used: bool = False,
    ) -> str:
        """优先按页文件夹保存；无 page_texts 时写单文件。"""
        if page_texts is not None and len(page_texts) > 0:
            return self.save_global_parsed_pages(
                content_hash,
                page_texts,
                original_filename=original_filename,
                ocr_used=ocr_used,
            )
        return self.save_global_parsed(content_hash, content)

    @staticmethod
    def is_parsed_pages_dir(path: str) -> bool:
        p = Path(path)
        if not p.is_dir():
            return False
        return (p / OCR_PAGES_DIR_NAME).is_dir()

    def _parsed_pages_dir(self, parsed_path: str) -> Path:
        return Path(parsed_path) / OCR_PAGES_DIR_NAME

    def _iter_page_files(self, parsed_path: str) -> List[tuple[int, Path]]:
        pages_dir = self._parsed_pages_dir(parsed_path)
        if not pages_dir.is_dir():
            return []
        items: List[tuple[int, Path]] = []
        for p in pages_dir.iterdir():
            if not p.is_file():
                continue
            m = PAGE_FILE_PATTERN.match(p.name)
            if m:
                items.append((int(m.group(1)), p))
        items.sort(key=lambda x: x[0])
        return items

    def read_parsed_manifest(self, parsed_path: str) -> Optional[dict]:
        manifest_path = Path(parsed_path) / "manifest.json"
        if not manifest_path.is_file():
            return None
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def read_page_at_path(self, parsed_path: str, page_number: int) -> Optional[str]:
        page_path = self._parsed_pages_dir(parsed_path) / f"page_{page_number:03d}.md"
        if not page_path.is_file():
            return None
        return page_path.read_text(encoding="utf-8")

    def list_parsed_pages(
        self, parsed_path: str, *, include_content: bool = True
    ) -> List[dict]:
        """从按页文件夹列出页；每项含 page_number/title/content/content_length。"""
        pages: List[dict] = []
        for page_num, page_path in self._iter_page_files(parsed_path):
            content = page_path.read_text(encoding="utf-8") if include_content else ""
            pages.append(
                {
                    "page_number": page_num,
                    "title": f"第 {page_num} 页",
                    "content": content,
                    "content_length": page_path.stat().st_size,
                }
            )
        return pages

    def _read_combined_from_pages_dir(self, base: Path) -> Optional[str]:
        manifest = self.read_parsed_manifest(str(base))
        page_items = self._iter_page_files(str(base))
        if not page_items:
            return None

        name = (manifest or {}).get("original_filename") or "document"
        total = (manifest or {}).get("total_pages") or len(page_items)
        lines = [f"# {name}", "", f"> OCR 提取，共 {total} 页", ""]
        for _, page_path in page_items:
            lines.append(page_path.read_text(encoding="utf-8").strip())
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    def read_file_at_path(self, path: str) -> Optional[bytes]:
        p = Path(path)
        if p.exists() and p.is_file():
            return p.read_bytes()
        return None

    def read_text_at_path(self, path: str) -> Optional[str]:
        p = Path(path)
        if p.is_file():
            return p.read_text(encoding="utf-8")
        if p.is_dir() and self.is_parsed_pages_dir(path):
            return self._read_combined_from_pages_dir(p)
        return None

    def delete_file_at_path(self, path: str) -> bool:
        p = Path(path)
        if p.is_dir():
            try:
                shutil.rmtree(str(p))
                return True
            except OSError as e:
                logger.warning("delete_file_at_path (dir) failed path=%s: %s", path, e)
                return False
        if p.exists() and p.is_file():
            try:
                p.unlink()
                return True
            except OSError as e:
                logger.warning("delete_file_at_path failed path=%s: %s", path, e)
                return False
        return False

    # ─── 聊天记录文件 ─────────────────────────────────────

    def save_chat_history(self, user_id: int, session_id: str, data: dict) -> str:
        """保存会话的完整消息历史及元信息到 JSON 文件"""
        import json as _json
        d = self._user_dir(user_id, "history")
        path = d / f"{session_id}.json"
        path.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    def load_chat_history(self, user_id: int, session_id: str) -> Optional[dict]:
        """读取会话的完整消息历史"""
        import json as _json
        d = self._user_dir(user_id, "history")
        path = d / f"{session_id}.json"
        if not path.exists():
            return None
        try:
            return _json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def delete_chat_history(self, user_id: int, session_id: str) -> bool:
        """删除单个会话的文件"""
        d = self._user_dir(user_id, "history")
        path = d / f"{session_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def list_chat_sessions(self, user_id: int) -> List[dict]:
        """列出用户所有历史会话（从文件名 + 文件内 meta 提取）"""
        import json as _json
        d = self._user_dir(user_id, "history")
        sessions = []
        for p in sorted(d.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                data = _json.loads(p.read_text(encoding="utf-8"))
                meta = data.get("meta") or {}
                messages = data.get("messages") or []
                message_count = meta.get("message_count")
                if message_count is None:
                    message_count = len(messages)
                # 清理旧格式 datetime（+00:00Z → +00:00）
                created_at = str(meta.get("created_at", "")).replace("+00:00Z", "+00:00")
                updated_at = str(meta.get("updated_at", "")).replace("+00:00Z", "+00:00")
                sessions.append({
                    "id": p.stem,
                    "title": meta.get("title", "会话"),
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "message_count": int(message_count),
                })
            except Exception:
                sessions.append({
                    "id": p.stem,
                    "title": "会话",
                    "created_at": "",
                    "updated_at": "",
                    "message_count": 0,
                })
        return sessions


class FileStorageService:
    """
    文件存储服务门面

    USE_OSS=False → LocalStorage
    USE_OSS=True  → OSSStorage（未实现）
    """

    def __init__(self):
        if USE_OSS:
            # TODO: 未来接入 OSS
            raise NotImplementedError("OSS 存储暂未实现，请设置 USE_OSS=false")
        self._backend = LocalStorage(LOCAL_STORAGE_DIR)
        logger.info(f"FileStorageService 初始化: 本地存储 ({LOCAL_STORAGE_DIR})")

    # ─── 原始文件 ──────────────────────────────────────

    def save_file(self, user_id: int, filename: str, content: bytes) -> str:
        return self._backend.save_file(user_id, filename, content)

    def get_file(self, user_id: int, filename: str) -> Optional[bytes]:
        return self._backend.get_file(user_id, filename)

    def delete_file(self, user_id: int, filename: str) -> bool:
        return self._backend.delete_file(user_id, filename)

    def list_user_files(self, user_id: int) -> List[dict]:
        return self._backend.list_user_files(user_id)

    def delete_user_storage(self, user_id: int) -> bool:
        return self._backend.delete_user_storage(user_id)

    # ─── 解析缓存 ─────────────────────────────────────

    def save_parsed(self, user_id: int, filename: str, content: str) -> str:
        return self._backend.save_text(user_id, filename, content)

    def get_parsed(self, user_id: int, filename: str) -> Optional[str]:
        return self._backend.get_parsed(user_id, filename)

    # ─── 聊天记录 ─────────────────────────────────────

    def save_chat_history(self, user_id: int, session_id: str, data: dict) -> str:
        return self._backend.save_chat_history(user_id, session_id, data)

    def load_chat_history(self, user_id: int, session_id: str) -> Optional[dict]:
        return self._backend.load_chat_history(user_id, session_id)

    def delete_chat_history(self, user_id: int, session_id: str) -> bool:
        return self._backend.delete_chat_history(user_id, session_id)

    def list_chat_sessions(self, user_id: int) -> List[dict]:
        return self._backend.list_chat_sessions(user_id)

    # ─── 全局去重存储 ─────────────────────────────────────

    def save_global_file(
        self, content_hash: str, content: bytes, suffix: str = ""
    ) -> str:
        return self._backend.save_global_file(content_hash, content, suffix)

    def save_global_parsed(self, content_hash: str, content: str) -> str:
        return self._backend.save_global_parsed(content_hash, content)

    def save_global_parsed_pages(
        self,
        content_hash: str,
        page_texts: list[str],
        *,
        original_filename: str = "",
        ocr_used: bool = True,
    ) -> str:
        return self._backend.save_global_parsed_pages(
            content_hash,
            page_texts,
            original_filename=original_filename,
            ocr_used=ocr_used,
        )

    def save_global_parsed_content(
        self,
        content_hash: str,
        content: str,
        *,
        page_texts: Optional[list[str]] = None,
        original_filename: str = "",
        ocr_used: bool = False,
    ) -> str:
        return self._backend.save_global_parsed_content(
            content_hash,
            content,
            page_texts=page_texts,
            original_filename=original_filename,
            ocr_used=ocr_used,
        )

    def is_parsed_pages_dir(self, path: str) -> bool:
        return self._backend.is_parsed_pages_dir(path)

    def read_parsed_manifest(self, parsed_path: str) -> Optional[dict]:
        return self._backend.read_parsed_manifest(parsed_path)

    def read_page_at_path(self, parsed_path: str, page_number: int) -> Optional[str]:
        return self._backend.read_page_at_path(parsed_path, page_number)

    def list_parsed_pages(
        self, parsed_path: str, *, include_content: bool = True
    ) -> List[dict]:
        return self._backend.list_parsed_pages(
            parsed_path, include_content=include_content
        )

    def read_file_at_path(self, path: str) -> Optional[bytes]:
        return self._backend.read_file_at_path(path)

    def read_text_at_path(self, path: str) -> Optional[str]:
        return self._backend.read_text_at_path(path)

    def delete_file_at_path(self, path: str) -> bool:
        return self._backend.delete_file_at_path(path)


# 全局单例
storage_service = FileStorageService()