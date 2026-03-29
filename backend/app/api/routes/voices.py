from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.voice import VoiceProfile
from app.schemas.voice import VoiceRead

router = APIRouter(prefix='/voices', tags=['voices'])


@router.get('', response_model=list[VoiceRead])
def list_voices(db: Session = Depends(get_db)) -> list[VoiceProfile]:
    return list(db.scalars(select(VoiceProfile).order_by(VoiceProfile.kind, VoiceProfile.id)))
