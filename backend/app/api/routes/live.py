from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.live import (
    LiveBufferAppendRequest,
    LiveEnqueueRequest,
    LiveFlushRequest,
    LivePreviewMetaResponse,
    LivePreviewRequest,
)
from app.services.preview.base import PreviewRequest
from app.services.preprocessor import TechnicalPreprocessor

router = APIRouter(prefix='/live', tags=['live'])
preprocessor = TechnicalPreprocessor()

MAX_PREVIEW_CHARS = 400


def _validate_preview_text(text: str) -> None:
    if len(text.strip()) > MAX_PREVIEW_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f'Preview text is too long. Max {MAX_PREVIEW_CHARS} characters.',
        )


@router.post('/preview-meta', response_model=LivePreviewMetaResponse)
async def preview_audio_meta(
    payload: LivePreviewRequest,
    db: Session = Depends(get_db),
) -> LivePreviewMetaResponse:
    _validate_preview_text(payload.text)
    processed = preprocessor.process(db, payload.text, dictionary_id=payload.dictionary_id)
    return LivePreviewMetaResponse(
        original_text=payload.text,
        processed_text=processed.processed_text,
    )


@router.post('/preview')
async def preview_audio(
    request: Request,
    payload: LivePreviewRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    _validate_preview_text(payload.text)

    try:
        processed = preprocessor.process(db, payload.text, dictionary_id=payload.dictionary_id)
        engine = request.app.state.preview_engine
        wav_bytes = await engine.synthesize(
            PreviewRequest(
                text=processed.processed_text,
                voice_id=payload.voice_id,
                lora_name=payload.lora_name,
                language=payload.language,
            )
        )
        return StreamingResponse(
            iter([wav_bytes]),
            media_type='audio/wav',
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f'Preview synthesis failed: {exc}') from exc


@router.post('/enqueue')
async def enqueue_live(request: Request, payload: LiveEnqueueRequest) -> dict[str, str]:
    manager = request.app.state.live_manager
    try:
        await manager.enqueue_once(
            payload.session_id,
            payload.text,
            dictionary_id=payload.dictionary_id,
            voice_id=payload.voice_id,
            lora_name=payload.lora_name,
            language=payload.language,
        )
    except KeyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f'Live enqueue failed: {exc}') from exc

    return {'status': 'queued'}


@router.post('/buffer/append')
async def append_buffer(request: Request, payload: LiveBufferAppendRequest) -> dict[str, str]:
    manager = request.app.state.live_manager
    try:
        await manager.append_text(
            payload.session_id,
            payload.text,
            dictionary_id=payload.dictionary_id,
            voice_id=payload.voice_id,
            lora_name=payload.lora_name,
            language=payload.language,
            flush=payload.flush,
        )
    except KeyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f'Live buffer append failed: {exc}') from exc

    return {'status': 'buffered'}


@router.post('/buffer/flush')
async def flush_buffer(request: Request, payload: LiveFlushRequest) -> dict[str, str]:
    manager = request.app.state.live_manager
    try:
        await manager.flush(payload.session_id)
    except KeyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f'Live buffer flush failed: {exc}') from exc

    return {'status': 'flushed'}


@router.websocket('/ws/{session_id}')
async def live_ws(websocket: WebSocket, session_id: str) -> None:
    manager = websocket.app.state.live_manager

    try:
        await manager.connect(session_id, websocket)
    except Exception as exc:
        await websocket.accept()
        await websocket.send_json({
            'type': 'job.error',
            'error': f'Live session init failed: {exc}',
        })
        await websocket.close()
        return

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            msg_type = data.get('type')

            if msg_type == 'append_text':
                await manager.append_text(
                    session_id,
                    data.get('text', ''),
                    dictionary_id=data.get('dictionary_id'),
                    voice_id=data.get('voice_id'),
                    lora_name=data.get('lora_name'),
                    language=data.get('language', 'ru'),
                    flush=bool(data.get('flush', False)),
                )

            elif msg_type == 'enqueue_text':
                await manager.enqueue_once(
                    session_id,
                    data.get('text', ''),
                    dictionary_id=data.get('dictionary_id'),
                    voice_id=data.get('voice_id'),
                    lora_name=data.get('lora_name'),
                    language=data.get('language', 'ru'),
                )

            elif msg_type == 'flush':
                await manager.flush(session_id)

            elif msg_type == 'clear_buffer':
                await manager.clear_buffer(session_id)

            elif msg_type == 'ping':
                await websocket.send_json({'type': 'pong'})

    except WebSocketDisconnect:
        await manager.disconnect(session_id)
    except Exception as exc:
        try:
            await websocket.send_json({'type': 'job.error', 'error': str(exc)})
        except Exception:
            pass
        await manager.disconnect(session_id)