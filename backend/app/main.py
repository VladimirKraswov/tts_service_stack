from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.dictionaries import router as dictionaries_router
from app.api.routes.health import router as health_router
from app.api.routes.live import router as live_router
from app.api.routes.training import router as training_router
from app.api.routes.voices import router as voices_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.init_db import init_db
from app.services.live.factory import get_live_engine
from app.services.live.manager import LiveSessionManager
from app.services.live.preprocessor import LiveTextPreprocessor
from app.services.preview.factory import get_preview_engine

settings = get_settings()
configure_logging()
logger = logging.getLogger(__name__)


async def _safe_warmup(app: FastAPI) -> None:
    try:
        logger.info('Background warmup: preview engine...')
        await app.state.preview_engine.warmup()
        logger.info('Background warmup: preview engine ready')
    except Exception:
        logger.exception('Background warmup failed for preview engine')

    try:
        logger.info('Background warmup: live engine...')
        await app.state.live_manager.startup()
        logger.info('Background warmup: live engine ready')
    except Exception:
        logger.exception('Background warmup failed for live engine')


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.getenv("TESTING"):
        init_db()

    preview_engine = get_preview_engine()
    live_engine = get_live_engine()
    live_preprocessor = LiveTextPreprocessor()
    live_manager = LiveSessionManager(
        live_engine=live_engine,
        preprocessor=live_preprocessor,
    )

    app.state.preview_engine = preview_engine
    app.state.live_engine = live_engine
    app.state.live_manager = live_manager
    app.state.warmup_task = None

    try:
        # ВАЖНО: не блокируем запуск API прогревом модели
        app.state.warmup_task = asyncio.create_task(_safe_warmup(app), name='tts-background-warmup')
        yield
    finally:
        warmup_task = getattr(app.state, 'warmup_task', None)
        if warmup_task is not None:
            warmup_task.cancel()
            try:
                await warmup_task
            except asyncio.CancelledError:
                pass

        await live_manager.shutdown()


app = FastAPI(title=settings.app_title, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_origin,
        'http://localhost:8080',
        'http://127.0.0.1:8080',
    ],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(dictionaries_router, prefix=settings.api_prefix)
app.include_router(voices_router, prefix=settings.api_prefix)
app.include_router(training_router, prefix=settings.api_prefix)
app.include_router(live_router, prefix=settings.api_prefix)