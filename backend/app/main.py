from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.api.routes.dictionaries import router as dictionaries_router
from app.api.routes.health import router as health_router
from app.api.routes.live import router as live_router
from app.api.routes.training import router as training_router
from app.api.routes.voices import router as voices_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.init_db import init_db
from app.services.live_sessions import LiveSessionManager
from app.services.preprocessor import TechnicalPreprocessor
from app.services.tts.factory import get_tts_engine
import os

settings = get_settings()
configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.getenv("TESTING"):
        init_db()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    preprocessor = TechnicalPreprocessor()
    tts_engine = get_tts_engine()

    app.state.redis = redis
    app.state.tts_engine = tts_engine
    app.state.live_manager = LiveSessionManager(
        redis=redis,
        tts_engine=tts_engine,
        preprocessor=preprocessor,
    )

    try:
        yield
    finally:
        await redis.close()


app = FastAPI(title=settings.app_title, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_origin,
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(dictionaries_router, prefix=settings.api_prefix)
app.include_router(voices_router, prefix=settings.api_prefix)
app.include_router(training_router, prefix=settings.api_prefix)
app.include_router(live_router, prefix=settings.api_prefix)
