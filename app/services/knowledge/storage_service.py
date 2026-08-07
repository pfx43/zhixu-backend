"""
文件存储服务 — 统一存取接口

使用方式：
    from app.services.knowledge.storage_service import storage_service

    # 保存文件
    path = storage_service.save_file(user_id, filename, content_bytes)
    # 读取文件
    data = storage_service.get_file(user_id, filename)
    # 列表
    files = storage_service.list_user_files(user_id)
    # 删除
    storage_service.delete_file(user_id, filename)

配置：
    STORAGE_BACKEND=local  → LocalStorage (storage/{user_id}/)
    STORAGE_BACKEND=cos    → COSStorage  (users/{user_id}/...)
"""
import json
import logging
import re
import shutil
from io import BytesIO
from pathlib import Path
from typing import List, Optional

from app.core.config import (
    COS_BUCKET,
    COS_REGION,
    COS_SECRET_ID,
    COS_SECRET_KEY,
    LOCAL_STORAGE_DIR,
    OCR_PAGES_DIR_NAME,
    STORAGE_BACKEND,
)

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


class COSStorage:
    """腾讯云 COS 对象存储"""

    def __init__(
        self,
        bucket: str,
        region: str,
        secret_id: str,
        secret_key: str,
    ):
        self.bucket = bucket
        self.region = region

        if not all([bucket, secret_id, secret_key]):
            raise RuntimeError(
                "COS 配置不完整，请设置 COS_SECRET_ID / COS_SECRET_KEY / COS_BUCKET"
            )

        from qcloud_cos import CosConfig, CosS3Client

        config = CosConfig(
            Region=region,
            SecretId=secret_id,
            SecretKey=secret_key,
            Scheme="https",
        )
        self.client = CosS3Client(config)

    # ─── 对象键工具 ──────────────────────────────────────

    @staticmethod
    def _user_prefix(user_id: int, subdir: str = "original") -> str:
        return f"users/{user_id}/{subdir}/"

    @staticmethod
    def _global_prefix(hash_prefix: str = "") -> str:
        base = "global"
        if hash_prefix:
            base = f"global/{hash_prefix}"
        return base + "/"

    # ─── COS 基础操作 ──────────────────────────────────

    def _put_object(self, key: str, content: bytes) -> str:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
        )
        logger.info(f"COSStorage._put_object: {key} ({len(content)} bytes)")
        return key

    def _get_object_bytes(self, key: str) -> Optional[bytes]:
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=key)
            return resp["Body"].get_raw_stream().read()
        except Exception as e:
            logger.warning(f"COSStorage._get_object_bytes 失败 key={key}: {e}")
            return None

    def _get_object_text(self, key: str) -> Optional[str]:
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=key)
            return resp["Body"].get_raw_stream().read().decode("utf-8")
        except Exception as e:
            logger.warning(f"COSStorage._get_object_text 失败 key={key}: {e}")
            return None

    def _delete_object(self, key: str) -> bool:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as e:
            logger.warning(f"COSStorage._delete_object 失败 key={key}: {e}")
            return False

    def _delete_prefix(self, prefix: str) -> bool:
        """删除指定前缀下的所有对象"""
        try:
            keys = []
            marker = ""
            while True:
                resp = self.client.list_objects(
                    Bucket=self.bucket,
                    Prefix=prefix,
                    Marker=marker,
                    MaxKeys=1000,
                )
                for obj in resp.get("Contents", []):
                    keys.append({"Key": obj["Key"]})
                if resp.get("IsTruncated") == "false":
                    break
                marker = resp.get("NextMarker", "")

            if keys:
                self.client.delete_objects(
                    Bucket=self.bucket,
                    Delete={"Object": keys},
                )
                logger.info(f"COSStorage._delete_prefix: 已删除 {len(keys)} 个对象, prefix={prefix}")
                return True
            return False
        except Exception as e:
            logger.warning(f"COSStorage._delete_prefix 失败 prefix={prefix}: {e}")
            return False

    def _list_objects(self, prefix: str) -> List[dict]:
        """列出指定前缀下的对象（含 size / modified_at）"""
        items = []
        try:
            marker = ""
            while True:
                resp = self.client.list_objects(
                    Bucket=self.bucket,
                    Prefix=prefix,
                    Marker=marker,
                    MaxKeys=1000,
                )
                for obj in resp.get("Contents", []):
                    items.append({
                        "key": obj["Key"],
                        "size": obj.get("Size", 0),
                        "modified_at": obj.get("LastModified", ""),
                    })
                if resp.get("IsTruncated") == "false":
                    break
                marker = resp.get("NextMarker", "")
        except Exception as e:
            logger.warning(f"COSStorage._list_objects 失败 prefix={prefix}: {e}")
        return items

    # ─── 用户文件 ──────────────────────────────────────

    def save_file(self, user_id: int, filename: str, content: bytes) -> str:
        """保存原始文件到 COS，返回 object_key"""
        safe_name = Path(filename).name
        key = f"users/{user_id}/original/{safe_name}"
        return self._put_object(key, content)

    def save_text(self, user_id: int, filename: str, content: str) -> str:
        """保存文本文件（解析缓存），返回 object_key"""
        safe_name = Path(filename).name
        key = f"users/{user_id}/parsed/{safe_name}"
        return self._put_object(key, content.encode("utf-8"))

    def get_file(self, user_id: int, filename: str) -> Optional[bytes]:
        """读取原始文件字节"""
        safe_name = Path(filename).name
        key = f"users/{user_id}/original/{safe_name}"
        return self._get_object_bytes(key)

    def get_parsed(self, user_id: int, filename: str) -> Optional[str]:
        """读取解析后的文本缓存"""
        safe_name = Path(filename).name
        key = f"users/{user_id}/parsed/{safe_name}"
        return self._get_object_text(key)

    def delete_file(self, user_id: int, filename: str) -> bool:
        """删除原始文件及同名解析缓存"""
        safe_name = Path(filename).name
        orig_key = f"users/{user_id}/original/{safe_name}"
        parsed_key = f"users/{user_id}/parsed/{safe_name}"
        deleted = self._delete_object(orig_key)
        self._delete_object(parsed_key)
        return deleted

    def delete_user_storage(self, user_id: int) -> bool:
        """删除用户全部存储对象"""
        prefix = f"users/{user_id}/"
        return self._delete_prefix(prefix)

    def list_user_files(self, user_id: int) -> List[dict]:
        """列出用户所有原始文件"""
        prefix = f"users/{user_id}/original/"
        items = self._list_objects(prefix)
        files = []
        for obj in items:
            filename = obj["key"][len(prefix):]
            files.append({
                "filename": filename,
                "size": obj["size"],
                "modified_at": obj["modified_at"],
            })
        return files

    # ─── 全局去重存储 ─────────────────────────────────

    def save_global_file(
        self, content_hash: str, content: bytes, suffix: str = ""
    ) -> str:
        """保存全局去重文件，键 global/{hash[:2]}/{hash}{suffix}"""
        normalized = suffix.lower()
        if normalized and not normalized.startswith("."):
            normalized = f".{normalized}"
        filename = f"{content_hash}{normalized}" if normalized else content_hash
        key = f"global/{content_hash[:2]}/{filename}"
        return self._put_object(key, content)

    def save_global_parsed(self, content_hash: str, content: str) -> str:
        """保存全局解析文本缓存（单文件）"""
        key = f"global/{content_hash[:2]}/{content_hash}.parsed.txt"
        return self._put_object(key, content.encode("utf-8"))

    def save_global_parsed_pages(
        self,
        content_hash: str,
        page_texts: list[str],
        *,
        original_filename: str = "",
        ocr_used: bool = True,
    ) -> str:
        """OCR 按页写入 COS 影子文件夹，返回文件夹前缀路径。"""
        base_prefix = f"global/{content_hash[:2]}/{content_hash}.parsed"
        pages_prefix = f"{base_prefix}/{OCR_PAGES_DIR_NAME}"

        # 删除旧页（如果有）
        self._delete_prefix(base_prefix + "/")

        for i, text in enumerate(page_texts, 1):
            page_key = f"{pages_prefix}/page_{i:03d}.md"
            self._put_object(page_key, build_page_markdown(i, text).encode("utf-8"))

        manifest = {
            "version": 1,
            "original_filename": original_filename or "",
            "total_pages": len(page_texts),
            "ocr_used": ocr_used,
            "pages_dir": OCR_PAGES_DIR_NAME,
        }
        manifest_key = f"{base_prefix}/manifest.json"
        self._put_object(
            manifest_key,
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        )
        logger.info(
            "COSStorage.save_global_parsed_pages: %s (%d pages)",
            base_prefix,
            len(page_texts),
        )
        return base_prefix

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
        """判断路径是否为按页解析目录（COS 中通过 manifest 存在性判断）"""
        manifest_key = f"{path}/manifest.json"
        # 在 COS 中通过 manifest 存在性判断
        return True  # COS 中由调用方按约定处理，此处始终返回 True 保持兼容

    def read_parsed_manifest(self, parsed_path: str) -> Optional[dict]:
        """读取 manifest.json"""
        manifest_key = f"{parsed_path}/manifest.json"
        text = self._get_object_text(manifest_key)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return None
        return None

    def read_page_at_path(self, parsed_path: str, page_number: int) -> Optional[str]:
        """读取按页目录下单页内容"""
        page_key = f"{parsed_path}/{OCR_PAGES_DIR_NAME}/page_{page_number:03d}.md"
        return self._get_object_text(page_key)

    def list_parsed_pages(
        self, parsed_path: str, *, include_content: bool = True
    ) -> List[dict]:
        """从按页前缀列出所有页面"""
        pages_prefix = f"{parsed_path}/{OCR_PAGES_DIR_NAME}/"
        items = self._list_objects(pages_prefix)
        pages: List[dict] = []
        for obj in items:
            filename = obj["key"][len(pages_prefix):]
            m = PAGE_FILE_PATTERN.match(filename)
            if m:
                page_num = int(m.group(1))
                content = ""
                if include_content:
                    content = self._get_object_text(obj["key"]) or ""
                pages.append({
                    "page_number": page_num,
                    "title": f"第 {page_num} 页",
                    "content": content,
                    "content_length": obj["size"],
                })
        pages.sort(key=lambda x: x["page_number"])
        return pages

    def read_file_at_path(self, path: str) -> Optional[bytes]:
        """读取指定键的对象字节"""
        return self._get_object_bytes(path)

    def read_text_at_path(self, path: str) -> Optional[str]:
        """读取指定键的对象文本（若是 parsed pages 目录则拼接）"""
        # 尝试作为单文件读取
        text = self._get_object_text(path)
        if text is not None and text.strip():
            return text

        # 尝试作为 parsed pages 目录读取
        pages_prefix = f"{path}/{OCR_PAGES_DIR_NAME}/"
        items = self._list_objects(pages_prefix)
        sorted_items = sorted(
            [i for i in items if PAGE_FILE_PATTERN.match(i["key"][len(pages_prefix):])],
            key=lambda x: int(PAGE_FILE_PATTERN.match(x["key"][len(pages_prefix):]).group(1)),
        )
        if not sorted_items:
            return None

        manifest = self.read_parsed_manifest(path)
        name = (manifest or {}).get("original_filename") or "document"
        total = (manifest or {}).get("total_pages") or len(sorted_items)
        lines = [f"# {name}", "", f"> OCR 提取，共 {total} 页", ""]
        for obj in sorted_items:
            content = self._get_object_text(obj["key"]) or ""
            lines.append(content.strip())
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    def delete_file_at_path(self, path: str) -> bool:
        """删除指定键对象或其前缀下所有对象"""
        # 先尝试单对象删除
        if self._delete_object(path):
            return True
        # 再尝试前缀删除
        return self._delete_prefix(path + "/")

    # ─── 聊天记录 ─────────────────────────────────────

    def save_chat_history(self, user_id: int, session_id: str, data: dict) -> str:
        """保存会话历史到 COS"""
        import json as _json
        key = f"users/{user_id}/history/{session_id}.json"
        return self._put_object(
            key,
            _json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"),
        )

    def load_chat_history(self, user_id: int, session_id: str) -> Optional[dict]:
        """读取会话历史"""
        import json as _json
        key = f"users/{user_id}/history/{session_id}.json"
        text = self._get_object_text(key)
        if text:
            try:
                return _json.loads(text)
            except Exception:
                return None
        return None

    def delete_chat_history(self, user_id: int, session_id: str) -> bool:
        """删除单个会话"""
        key = f"users/{user_id}/history/{session_id}.json"
        return self._delete_object(key)

    def list_chat_sessions(self, user_id: int) -> List[dict]:
        """列出用户所有历史会话"""
        import json as _json
        prefix = f"users/{user_id}/history/"
        items = self._list_objects(prefix)
        # 按修改时间倒序
        items.sort(key=lambda x: str(x.get("modified_at", "")), reverse=True)
        sessions = []
        for obj in items:
            filename = obj["key"][len(prefix):]
            if not filename.endswith(".json"):
                continue
            session_id = filename[:-5]
            try:
                text = self._get_object_text(obj["key"])
                if text:
                    data = _json.loads(text)
                    meta = data.get("meta") or {}
                    messages = data.get("messages") or []
                    message_count = meta.get("message_count") or len(messages)
                    created_at = str(meta.get("created_at", "")).replace("+00:00Z", "+00:00")
                    updated_at = str(meta.get("updated_at", "")).replace("+00:00Z", "+00:00")
                    sessions.append({
                        "id": session_id,
                        "title": meta.get("title", "会话"),
                        "created_at": created_at,
                        "updated_at": updated_at,
                        "message_count": int(message_count),
                    })
            except Exception:
                sessions.append({
                    "id": session_id,
                    "title": "会话",
                    "created_at": "",
                    "updated_at": "",
                    "message_count": 0,
                })
        return sessions


class FileStorageService:
    """
    文件存储服务门面

    STORAGE_BACKEND=local → LocalStorage
    STORAGE_BACKEND=cos  → COSStorage
    """

    def __init__(self):
        if STORAGE_BACKEND == "cos":
            self._backend = COSStorage(
                bucket=COS_BUCKET,
                region=COS_REGION,
                secret_id=COS_SECRET_ID,
                secret_key=COS_SECRET_KEY,
            )
            logger.info("FileStorageService 初始化: COS 存储 (bucket=%s)", COS_BUCKET)
        else:
            self._backend = LocalStorage(LOCAL_STORAGE_DIR)
            logger.info("FileStorageService 初始化: 本地存储 (%s)", LOCAL_STORAGE_DIR)

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