"""
S2 基本逻辑验证 — 不启动 HTTP 服务
运行: cd backend && python test_s2_kb.py
"""
import hashlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.crud import kb as kb_crud
from app.models import User
from app.services.storage_service import FileStorageService


def test_imports():
    from app.schemas import kb as kb_schemas  # noqa: F401
    from app.services import kb_service  # noqa: F401
    from app.crud import kb as kb_crud_mod  # noqa: F401
    print("OK imports")


def test_seed_collections():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user = User(
        email="s2@test.local",
        password_hash="x",
        username="s2user",
        nickname="S2",
        is_active=True,
        plan_level=0,
        dataset_id="test-dataset",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    cols = kb_crud.seed_default_collections(db, user.id, user.dataset_id)
    db.commit()
    assert len(cols) == 2
    names = {c.name for c in kb_crud.list_collections(db, user.id)}
    assert names == {"学习区", "生活区"}
    default = kb_crud.get_default_study_collection(db, user.id)
    assert default is not None
    assert default.zone == "study"
    print("OK seed_collections")
    db.close()


def test_global_storage_dedup():
    with tempfile.TemporaryDirectory() as tmp:
        svc = FileStorageService.__new__(FileStorageService)
        from app.services.storage_service import LocalStorage
        svc._backend = LocalStorage(tmp)

        content = b"hello dedup"
        h = hashlib.sha256(content).hexdigest()
        p1 = svc.save_global_file(h, content)
        p2 = svc.save_global_file(h, content)
        assert p1 == p2
        assert Path(p1).exists()
        assert svc.read_file_at_path(p1) == content

        parsed = svc.save_global_parsed(h, "hello text")
        assert svc.read_text_at_path(parsed) == "hello text"
        print("OK global_storage_dedup")


def test_user_duplicate_constraint():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user = User(
        email="dup@test.local",
        password_hash="x",
        username="dup",
        nickname="Dup",
        is_active=True,
        plan_level=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    cols = kb_crud.seed_default_collections(db, user.id, None)
    db.commit()
    coll = cols[0]
    h = "abc123"

    g = kb_crud.create_global_document(
        db,
        content_hash=h,
        original_filename="a.txt",
        file_size=3,
        storage_path="/tmp/a",
    )
    kb_crud.create_document(
        db,
        user_id=user.id,
        collection_id=coll.id,
        zone=coll.zone,
        display_name="a.txt",
        content_hash=h,
        global_document_id=g.id,
    )
    db.commit()

    dup = kb_crud.get_document_by_user_hash(db, user.id, h)
    assert dup is not None
    print("OK user_duplicate_constraint")
    db.close()


if __name__ == "__main__":
    test_imports()
    test_seed_collections()
    test_global_storage_dedup()
    test_user_duplicate_constraint()
    print("\nAll S2 checks passed.")
