"""
旧书补页脚本 — 对存量学习区文档回填段页码与章节目录。

用法：
    python -m app.services.knowledge.doc_backfill

幂等：重复执行只更新有变化的段；目录每次按最新解析重写。
"""
import logging
import sys

from app.core.database import SessionLocal
from app.crud import kb as kb_crud
from app.models import Document
from app.services.knowledge.segment_service import recompute_document_structure

logger = logging.getLogger(__name__)


def backfill_all(db) -> dict:
    docs = (
        db.query(Document)
        .filter(
            Document.zone == "study",
            Document.segment_status == "completed",
        )
        .all()
    )

    result = {
        "total_documents": len(docs),
        "updated_segment_documents": 0,
        "updated_segments": 0,
        "failed_documents": 0,
        "errors": [],
    }

    for doc in docs:
        try:
            updated = recompute_document_structure(doc.id, db)
            if updated:
                result["updated_segment_documents"] += 1
                result["updated_segments"] += updated
        except Exception:
            logger.exception("backfill failed: document_id=%s", doc.id)
            result["failed_documents"] += 1
            result["errors"].append(doc.id)
            db.rollback()
        else:
            db.commit()

    return result


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    db = SessionLocal()
    try:
        result = backfill_all(db)
    finally:
        db.close()

    print(
        "backfill 完成: "
        f"文档 {result['total_documents']} 个，"
        f"更新段页码文档 {result['updated_segment_documents']} 个，"
        f"更新段 {result['updated_segments']} 条，"
        f"失败 {result['failed_documents']} 个"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())