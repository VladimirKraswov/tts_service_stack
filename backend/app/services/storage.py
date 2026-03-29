import shutil
from pathlib import Path

from fastapi import UploadFile

from app.core.config import get_settings

settings = get_settings()


def save_upload(upload: UploadFile, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / upload.filename
    with target_path.open('wb') as buffer:
        shutil.copyfileobj(upload.file, buffer)
    return target_path
