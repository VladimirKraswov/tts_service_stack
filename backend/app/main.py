from __future__ import annotations

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
from app.services.preprocessor import TechnicalPreprocessor
from app.services.preview.factory import get_preview_engine

settings = get_settings()
configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.getenv("TESTING"):
        init_db()

    preprocessor = TechnicalPreprocessor()
    preview_engine = get_preview_engine()
    live_engine = get_live_engine()
    live_manager = LiveSessionManager(
        live_engine=live_engine,
        preprocessor=preprocessor,
    )

    app.state.preview_engine = preview_engine
    app.state.live_engine = live_engine
    app.state.live_manager = live_manager

    try:
        logger.info('Warming up preview engine...')
        await preview_engine.warmup()
        logger.info('Preview engine warmup completed')

        logger.info('Warming up live engine...')
        await live_manager.startup()
        logger.info('Live engine warmup completed')

        yield
    finally:
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