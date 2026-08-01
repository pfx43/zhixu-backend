from typing import List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Document, GlobalDocument, KbCollection


DEFAULT_COLLECTIONS = (
    {"name": "学习区", "zone": "study", "is_default": True},
    {"name": "生活区", "zone": "life", "is_default": False},
)


def seed_default_collections(
    db: Session, user_id: int, dataset_id: Optional[str] = None
) -> List[KbCollection]:
    existing = (
        db.query(KbCollection).filter(KbCollection.user_id == user_id).count()
    )
    if existing:
        return list_collections(db, user_id)

    created: List[KbCollection] = []
    for item in DEFAULT_COLLECTIONS:
        coll = KbCollection(
            user_id=user_id,
            name=item["name"],
            zone=item["zone"],
            is_default=item["is_default"],
            dataset_id=dataset_id if item["is_default"] else None,
        )
        db.add(coll)
        created.append(coll)
    db.flush()
    return created


def list_collections(db: Session, user_id: int) -> List[KbCollection]:
    return (
        db.query(KbCollection)
        .filter(KbCollection.user_id == user_id)
        .order_by(KbCollection.is_default.desc(), KbCollection.created_at.asc())
        .all()
    )


def get_collection(
    db: Session, user_id: int, collection_id: str
) -> Optional[KbCollection]:
    return (
        db.query(KbCollection)
        .filter(
            KbCollection.id == collection_id,
            KbCollection.user_id == user_id,
        )
        .first()
    )


def get_default_study_collection(
    db: Session, user_id: int
) -> Optional[KbCollection]:
    return (
        db.query(KbCollection)
        .filter(
            KbCollection.user_id == user_id,
            KbCollection.zone == "study",
            KbCollection.is_default.is_(True),
        )
        .first()
    )


def get_default_life_collection(
    db: Session, user_id: int
) -> Optional[KbCollection]:
    return (
        db.query(KbCollection)
        .filter(
            KbCollection.user_id == user_id,
            KbCollection.zone == "life",
        )
        .order_by(KbCollection.created_at.asc())
        .first()
    )


def create_collection(
    db: Session,
    user_id: int,
    name: str,
    zone: str,
    description: Optional[str] = None,
    dataset_id: Optional[str] = None,
) -> KbCollection:
    coll = KbCollection(
        user_id=user_id,
        name=name,
        zone=zone,
        description=description,
        dataset_id=dataset_id,
        is_default=False,
    )
    db.add(coll)
    db.flush()
    return coll


def delete_collection(
    db: Session, user_id: int, collection_id: str
) -> bool:
    collection = db.query(KbCollection).filter(
        KbCollection.id == collection_id,
        KbCollection.user_id == user_id,
    ).first()
    if not collection:
        return False
    db.delete(collection)
    db.flush()
    return True


def update_collection(
    db: Session,
    collection: KbCollection,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> KbCollection:
    if name is not None:
        collection.name = name
    if description is not None:
        collection.description = description
    db.flush()
    return collection


def get_document_by_user_hash(
    db: Session, user_id: int, content_hash: str
) -> Optional[Document]:
    return (
        db.query(Document)
        .filter(
            Document.user_id == user_id,
            Document.content_hash == content_hash,
        )
        .first()
    )


def get_global_document_by_hash(
    db: Session, content_hash: str
) -> Optional[GlobalDocument]:
    return (
        db.query(GlobalDocument)
        .filter(GlobalDocument.content_hash == content_hash)
        .first()
    )


def create_global_document(
    db: Session,
    content_hash: str,
    original_filename: str,
    file_size: int,
    storage_path: str,
    mime_type: Optional[str] = None,
    parsed_text_path: Optional[str] = None,
) -> GlobalDocument:
    global_doc = GlobalDocument(
        content_hash=content_hash,
        original_filename=original_filename,
        mime_type=mime_type,
        file_size=file_size,
        storage_path=storage_path,
        parsed_text_path=parsed_text_path,
    )
    db.add(global_doc)
    db.flush()
    return global_doc


def create_document(
    db: Session,
    user_id: int,
    collection_id: str,
    zone: str,
    display_name: str,
    content_hash: str,
    global_document_id: Optional[str] = None,
    dify_document_id: Optional[str] = None,
    dify_batch_id: Optional[str] = None,
    parsed_cache_key: Optional[str] = None,
    indexing_status: str = "processing",
) -> Document:
    doc = Document(
        user_id=user_id,
        collection_id=collection_id,
        global_document_id=global_document_id,
        dify_document_id=dify_document_id,
        dify_batch_id=dify_batch_id,
        display_name=display_name,
        zone=zone,
        content_hash=content_hash,
        parsed_cache_key=parsed_cache_key,
        indexing_status=indexing_status,
    )
    db.add(doc)
    db.flush()
    return doc


def list_documents(
    db: Session,
    user_id: int,
    collection_id: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
) -> Tuple[List[Document], int]:
    query = db.query(Document).filter(Document.user_id == user_id)
    if collection_id:
        query = query.filter(Document.collection_id == collection_id)
    total = query.count()
    docs = (
        query.order_by(Document.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return docs, total


def get_document_by_id_or_dify(
    db: Session, user_id: int, doc_id: str
) -> Optional[Document]:
    return (
        db.query(Document)
        .filter(
            Document.user_id == user_id,
            (Document.id == doc_id) | (Document.dify_document_id == doc_id),
        )
        .first()
    )


def get_document_by_id_internal(db: Session, document_id: str) -> Optional[Document]:
    return db.query(Document).filter(Document.id == document_id).first()


def get_document_by_batch_id(
    db: Session, user_id: int, batch_id: str
) -> Optional[Document]:
    return (
        db.query(Document)
        .filter(
            Document.user_id == user_id,
            Document.dify_batch_id == batch_id,
        )
        .first()
    )


def delete_related_for_document(db: Session, document_id: str) -> None:
    """删除文档前清理 segments、题目关联、辅导会话等外键引用。"""
    from app.models import (
        DocumentSegment,
        QuestionProvenance,
        QuizSession,
        TutorSession,
        UserQuestionRef,
    )

    segment_ids = [
        row[0]
        for row in db.query(DocumentSegment.id)
        .filter(DocumentSegment.document_id == document_id)
        .all()
    ]

    db.query(TutorSession).filter(TutorSession.document_id == document_id).delete(
        synchronize_session=False
    )
    db.query(UserQuestionRef).filter(UserQuestionRef.document_id == document_id).delete(
        synchronize_session=False
    )

    prov_query = db.query(QuestionProvenance).filter(
        QuestionProvenance.document_id == document_id
    )
    if segment_ids:
        prov_query = db.query(QuestionProvenance).filter(
            or_(
                QuestionProvenance.document_id == document_id,
                QuestionProvenance.segment_id.in_(segment_ids),
            )
        )
    prov_query.delete(synchronize_session=False)

    db.query(DocumentSegment).filter(DocumentSegment.document_id == document_id).delete(
        synchronize_session=False
    )
    db.query(QuizSession).filter(QuizSession.document_id == document_id).update(
        {QuizSession.document_id: None},
        synchronize_session=False,
    )
    db.flush()


def delete_provenance_for_global(db: Session, global_document_id: str) -> None:
    from app.models import QuestionProvenance

    db.query(QuestionProvenance).filter(
        QuestionProvenance.global_document_id == global_document_id
    ).delete(synchronize_session=False)
    db.flush()


def delete_document_row(db: Session, document: Document) -> Optional[str]:
    global_document_id = document.global_document_id
    db.delete(document)
    db.flush()
    return global_document_id


def count_documents_for_global(db: Session, global_document_id: str) -> int:
    return (
        db.query(Document)
        .filter(Document.global_document_id == global_document_id)
        .count()
    )


def delete_global_document(db: Session, global_doc: GlobalDocument) -> None:
    db.delete(global_doc)
    db.flush()
