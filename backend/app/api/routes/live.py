from __future__ import annotations

import json
import logging
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.live import LiveEnqueueRequest, LivePreviewRequest
from app.services.preprocessor import TechnicalPreprocessor
from app.services.tts.base import SynthRequest
from app.services.tts.factory import get_tts_engine

router = APIRouter(prefix='/live', tags=['live'])
preprocessor = TechnicalPreprocessor()
logger = logging.getLogger(__name__)


@router.post('/enqueue')
async def enqueue_live(request: Request, payload: LiveEnqueueRequest) -> dict[str, str]:
    manager = request.app.state.live_manager
    await manager.enqueue(
        payload.session_id,
        {
            'job_id': str(uuid4()),
            'text': payload.text,
            'dictionary_id': payload.dictionary_id,
            'voice_id': payload.voice_id,
            'lora_name': payload.lora_name,
            'language': payload.language,
        },
    )
    return {'status': 'queued'}


@router.post('/preview')
async def preview_live_audio(payload: LivePreviewRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    try:
        processed = preprocessor.process(db, payload.text, dictionary_id=payload.dictionary_id)
        engine = get_tts_engine()
        wav_bytes = await engine.synthesize_preview(
            SynthRequest(
                text=processed.processed_text,
                voice_id=payload.voice_id,
                lora_name=payload.lora_name,
                language=payload.language,
            )
        )
        processed_header = quote(processed.processed_text, safe='')
        return StreamingResponse(
            iter([wav_bytes]),
            media_type='audio/wav',
            headers={'X-Processed-Text': processed_header},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception('Preview synthesis failed')
        raise HTTPException(status_code=503, detail=f'TTS preview failed: {exc}') from exc


@router.websocket('/ws/{session_id}')
async def live_ws(websocket: WebSocket, session_id: str) -> None:
    manager = websocket.app.state.live_manager
    await manager.connect(session_id, websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            if data.get('type') == 'enqueue_text':
                await manager.enqueue(
                    session_id,
                    {
                        'job_id': data.get('job_id') or str(uuid4()),
                        'text': data['text'],
                        'dictionary_id': data.get('dictionary_id'),
                        'voice_id': data.get('voice_id'),
                        'lora_name': data.get('lora_name'),
                        'language': data.get('language', 'ru'),
                    },
                )
            elif data.get('type') == 'ping':
                await websocket.send_json({'type': 'pong'})
    except WebSocketDisconnect:
        await manager.disconnect(session_id)