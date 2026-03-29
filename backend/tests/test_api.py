import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.models.base import Base
from app.api.deps import get_db

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_api.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="module")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_list_voices(client):
    response = client.get("/api/v1/voices")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_meta(client):
    response = client.get("/api/v1/meta")
    assert response.status_code == 200
    assert "app_title" in response.json()
    assert "tts_backend" in response.json()

def test_dataset_upload_path_traversal(client):
    # Prepare a fake zip file
    import io
    file_content = b"fake zip content"
    file = io.BytesIO(file_content)

    # Try with malicious speaker_name
    response = client.post(
        "/api/v1/training/datasets",
        data={
            "name": "Traversal Test",
            "speaker_name": "../../etc/passwd",
            "language": "ru",
            "note": "testing path traversal"
        },
        files={"file": ("test.zip", file, "application/zip")}
    )

    assert response.status_code == 200
    data = response.json()
    # The saved file_path should NOT contain ../../etc/passwd
    # Our sanitizer should have converted it to something safe like "etcpasswd" or similar
    assert "../../" not in data["file_path"]
    assert "etcpasswd" in data["file_path"] or "etc_passwd" in data["file_path"]

def test_dataset_upload_invalid_extension(client):
    import io
    file = io.BytesIO(b"not a zip")
    response = client.post(
        "/api/v1/training/datasets",
        data={"name": "Invalid Ext", "speaker_name": "ivan", "language": "ru"},
        files={"file": ("test.txt", file, "text/plain")}
    )
    assert response.status_code == 400
    assert "Invalid file format" in response.json()["detail"]
