import io
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ['TESTING'] = '1'
os.environ['INIT_DB'] = 'false'
os.environ['TTS_BACKEND'] = 'mock'
os.environ['PREVIEW_BACKEND'] = 'mock'
os.environ['LIVE_BACKEND'] = 'mock'

from app.api.deps import get_db
from app.main import app
from app.models.base import Base

TEST_DB_PATH = Path(__file__).with_name('test_api.db')
SQLALCHEMY_DATABASE_URL = f'sqlite:///{TEST_DB_PATH}'
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={'check_same_thread': False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope='module')
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()


@pytest.fixture(scope='module')
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
    response = client.get('/api/v1/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_list_voices(client):
    response = client.get('/api/v1/voices')
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_meta(client):
    response = client.get('/api/v1/meta')
    assert response.status_code == 200
    assert 'app_title' in response.json()
    assert 'tts_backend' in response.json()


def test_dataset_upload_path_traversal(client):
    file_content = b'fake zip content'
    file = io.BytesIO(file_content)

    response = client.post(
        '/api/v1/training/datasets',
        data={
            'name': 'Traversal Test',
            'speaker_name': '../../etc/passwd',
            'language': 'ru',
            'note': 'testing path traversal',
        },
        files={'file': ('../../evil.zip', file, 'application/zip')},
    )

    assert response.status_code == 200
    data = response.json()
    assert '../../' not in data['file_path']
    assert '..' not in Path(data['file_path']).name
    assert Path(data['file_path']).name == 'evil.zip'


def test_dataset_upload_invalid_extension(client):
    file = io.BytesIO(b'not a zip')
    response = client.post(
        '/api/v1/training/datasets',
        data={'name': 'Invalid Ext', 'speaker_name': 'ivan', 'language': 'ru'},
        files={'file': ('test.txt', file, 'text/plain')},
    )
    assert response.status_code == 400
    assert 'Invalid file format' in response.json()['detail']