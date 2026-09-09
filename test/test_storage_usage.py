"""每用户资料占用：写入 users.storage_used_bytes。"""
from pgutil import make_sessionmaker

from app.models import (
    Document,
    GlobalDocument,
    KbCollection,
    NoteAttachment,
    User,
    UserNote,
)
from app.services.storage_usage import compute_user_storage_bytes, refresh_user_storage


def test_storage_usage_sums_docs_and_unique_attachments():
    engine, Session = make_sessionmaker()
    try:
        with Session() as db:
            owner = User(
                email="storage-owner@example.com",
                password_hash="hash",
                nickname="Owner",
                is_active=True,
            )
            other = User(
                email="storage-other@example.com",
                password_hash="hash",
                nickname="Other",
                is_active=True,
            )
            db.add_all([owner, other])
            db.commit()
            db.refresh(owner)
            db.refresh(other)

            coll = KbCollection(
                user_id=owner.id, name="学习区", zone="study", is_default=True
            )
            db.add(coll)
            db.commit()
            db.refresh(coll)

            gdoc = GlobalDocument(
                content_hash="hash-store-1",
                original_filename="a.pdf",
                file_size=1000,
                storage_path="/tmp/a.pdf",
            )
            db.add(gdoc)
            db.flush()
            doc = Document(
                user_id=owner.id,
                collection_id=coll.id,
                global_document_id=gdoc.id,
                display_name="a.pdf",
                zone="study",
                content_hash="hash-store-1",
            )
            db.add(doc)
            db.flush()

            note = UserNote(
                user_id=owner.id,
                title="n",
                content_md="x",
            )
            db.add(note)
            db.flush()
            db.add(
                NoteAttachment(
                    note_id=note.id,
                    user_id=owner.id,
                    media_type="image",
                    mime_type="image/png",
                    file_size=250,
                    checksum="aaa",
                    storage_path="notes/1/a.png",
                    original_filename="a.png",
                )
            )
            db.add(
                NoteAttachment(
                    note_id=note.id,
                    user_id=owner.id,
                    media_type="image",
                    mime_type="image/png",
                    file_size=250,
                    checksum="aaa",
                    storage_path="notes/1/a.png",
                    original_filename="a-copy.png",
                )
            )
            db.flush()

            assert compute_user_storage_bytes(db, owner.id) == 1250
            assert compute_user_storage_bytes(db, other.id) == 0
            assert refresh_user_storage(db, owner.id) == 1250
            db.commit()
            db.refresh(owner)
            assert owner.storage_used_bytes == 1250
    finally:
        engine.dispose()


def test_storage_usage_drops_after_document_removed():
    engine, Session = make_sessionmaker()
    try:
        with Session() as db:
            owner = User(
                email="storage-del@example.com",
                password_hash="hash",
                nickname="Owner",
                is_active=True,
            )
            db.add(owner)
            db.commit()
            db.refresh(owner)
            coll = KbCollection(
                user_id=owner.id, name="学习区", zone="study", is_default=True
            )
            db.add(coll)
            db.commit()
            db.refresh(coll)
            gdoc = GlobalDocument(
                content_hash="hash-store-2",
                original_filename="b.pdf",
                file_size=4000,
                storage_path="/tmp/b.pdf",
            )
            db.add(gdoc)
            db.flush()
            doc = Document(
                user_id=owner.id,
                collection_id=coll.id,
                global_document_id=gdoc.id,
                display_name="b.pdf",
                zone="study",
                content_hash="hash-store-2",
            )
            db.add(doc)
            db.commit()
            assert refresh_user_storage(db, owner.id) == 4000
            db.delete(doc)
            db.flush()
            assert refresh_user_storage(db, owner.id) == 0
            db.commit()
            db.refresh(owner)
            assert owner.storage_used_bytes == 0
    finally:
        engine.dispose()
