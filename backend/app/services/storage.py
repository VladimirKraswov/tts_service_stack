import re
import shutil
from pathlib import Path

from fastapi import UploadFile


def _safe_filename(filename: str | None) -> str:
    raw = Path(filename or 'upload.bin').name
    safe = re.sub(r'[^0-9A-Za-zА-Яа-я._-]+', '_', raw).strip('._')
    return safe or 'upload.bin'


def save_upload(upload: UploadFile, target_dir: Path) -> Path:
    target_dir = target_dir.resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = _safe_filename(upload.filename)
    target_path = (target_dir / safe_name).resolve()

    if target_path.parent != target_dir:
        raise ValueError('Unsafe upload path')

    with target_path.open('wb') as buffer:
        shutil.copyfileobj(upload.file, buffer)

    return target_path