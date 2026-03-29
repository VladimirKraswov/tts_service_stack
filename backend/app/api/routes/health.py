from fastapi import APIRouter

from app.services.meta import get_meta

router = APIRouter(tags=['health'])


@router.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


@router.get('/meta')
def meta() -> dict:
    return get_meta()
