import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.models.dictionary import Dictionary, DictionaryEntry
from app.schemas.dictionary import ImportConflictMode
from app.api.deps import get_db
from app.main import app

@pytest.fixture(scope="function")
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

def test_dictionary_crud(client):
    # Create
    resp = client.post("/api/v1/dictionaries", json={"name": "Test Dict", "slug": "test-dict"})
    assert resp.status_code == 200
    dict_id = resp.json()["id"]

    # Read
    resp = client.get(f"/api/v1/dictionaries/{dict_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Test Dict"

    # Update
    resp = client.patch(f"/api/v1/dictionaries/{dict_id}", json={"description": "New description"})
    assert resp.status_code == 200
    assert resp.json()["description"] == "New description"

    # Delete
    resp = client.delete(f"/api/v1/dictionaries/{dict_id}")
    assert resp.status_code == 204
    resp = client.get(f"/api/v1/dictionaries/{dict_id}")
    assert resp.status_code == 404

def test_dictionary_entries_pagination_and_search(client, db_session: Session):
    # Setup
    dict_obj = Dictionary(name="Pagination Dict", slug="pagination-dict")
    db_session.add(dict_obj)
    db_session.flush()

    for i in range(15):
        entry = DictionaryEntry(
            dictionary_id=dict_obj.id,
            source_text=f"word{i}",
            spoken_text=f"spoken{i}",
            note="common note" if i < 5 else "other"
        )
        db_session.add(entry)
    db_session.commit()

    # Test pagination
    resp = client.get(f"/api/v1/dictionaries/{dict_obj.id}/entries", params={"size": 10, "page": 1})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 10
    assert data["total"] == 15
    assert data["pages"] == 2

    # Test search
    resp = client.get(f"/api/v1/dictionaries/{dict_obj.id}/entries", params={"q": "common note"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 5

def test_dictionary_import_modes(client, db_session: Session):
    # Setup
    dict_obj = Dictionary(name="Import Dict", slug="import-dict")
    db_session.add(dict_obj)
    db_session.flush()
    # Use direct DB insert for setup
    db_session.add(DictionaryEntry(dictionary_id=dict_obj.id, source_text="React", spoken_text="Old React"))
    db_session.commit()

    import_data = {
        "name": "Import Dict",
        "slug": "import-dict",
        "entries": [
            {"source_text": "React", "spoken_text": "New React"},
            {"source_text": "FastAPI", "spoken_text": "Фаст эй пи ай"}
        ]
    }

    # Test MERGE
    resp = client.post(f"/api/v1/dictionaries/{dict_obj.id}/import", json=import_data, params={"mode": "merge"})
    assert resp.status_code == 200
    # React should be updated, FastAPI should be created
    assert resp.json()["entries_created"] == 1
    assert resp.json()["entries_updated"] == 1

    # Test CREATE_ONLY
    import_data_2 = {
        "name": "Import Dict",
        "slug": "import-dict",
        "entries": [
            {"source_text": "React", "spoken_text": "Should not change"},
            {"source_text": "Docker", "spoken_text": "Докер"}
        ]
    }
    resp = client.post(f"/api/v1/dictionaries/{dict_obj.id}/import", json=import_data_2, params={"mode": "create_only"})
    assert resp.status_code == 200
    # React exists, so skip. Docker created.
    assert resp.json()["entries_created"] == 1
    assert resp.json()["entries_updated"] == 0

    # Test REPLACE
    # We clear the session to avoid any lingering state that might cause IntegrityError on REPLACE if not careful
    db_session.commit()
    resp = client.post(f"/api/v1/dictionaries/{dict_obj.id}/import", json=import_data, params={"mode": "replace_existing_entries"})
    assert resp.status_code == 200
    # React, FastAPI, Docker were there. deleted 3. React, FastAPI from import_data created.
    assert resp.json()["entries_deleted"] == 3
    assert resp.json()["entries_created"] == 2
