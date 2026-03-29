# TTS Admin Stack

Полноценный skeleton-проект для удаленного сервера с GPU:

- FastAPI API для интеграции в сервисы.
- WebSocket live-режим с FIFO-буфером в Redis.
- Параллельная работа с несколькими пользователями.
- Административный Web UI: тестирование, словари, training.
- Docker Compose deployment.
- Подготовленная точка расширения для Qwen3-TTS / кастомных backend'ов.

## Что уже работает

- REST API для словарей, голосов, preview и training jobs.
- Live session WebSocket + enqueue через API.
- FIFO-буфер на Redis `RPUSH/BLPOP`.
- Расширяемый препроцессор технического текста.
- Mock TTS backend для сквозного теста пайплайна.
- Trainer service с очередью из БД и артефактами в `/data/artifacts`.
- React admin UI.

## Что остается заменить для production TTS

Сейчас проект запускается из коробки на `mock` backend, чтобы можно было проверить:

- сетевую схему,
- многопользовательскую работу,
- буферизацию,
- словари,
- очередь обучения,
- UI и API контракты.

Для production вам нужно реализовать файл `backend/app/services/tts/qwen.py` и переключить:

```env
TTS_BACKEND=qwen
```

## Быстрый старт

```bash
cp .env.example .env
mkdir -p data/datasets data/artifacts data/uploads data/models
docker compose up --build
```

UI будет доступен на `http://localhost:8080`, API — на `http://localhost:8000`.

## Reverse proxy через nginx / Nginx Proxy Manager

Проще всего публиковать только контейнер `web`, потому что он уже проксирует:

- `/api/*` -> `api:8000`
- `/ws/*` -> `api:8000`

То есть во внешнем reverse proxy достаточно направить домен на `web:80`.

## Архитектура

### Сервисы

- `api` — REST + WebSocket + live FIFO pipeline.
- `trainer` — фоновая обработка queued training jobs.
- `postgres` — метаданные.
- `redis` — live FIFO-буферы и временное состояние.
- `web` — admin UI + встроенный nginx proxy.

### Потоки данных

1. Клиент открывает WebSocket `/api/v1/live/ws/{session_id}`.
2. Текст кладется в Redis FIFO через REST или WS.
3. Background consumer читает буфер FIFO.
4. Препроцессор применяет словарь и правила чтения техтекста.
5. TTS backend генерирует аудио чанки.
6. UI получает события и может проигрывать аудио.

## Структура проекта

```text
backend/app/
  api/routes/        # независимые роуты
  core/              # конфиг и логирование
  db/                # engine/session
  models/            # SQLAlchemy модели
  schemas/           # pydantic схемы
  services/          # буфер, препроцессор, словари, storage, live sessions
  services/tts/      # backends TTS
  trainer/           # training worker
frontend/src/
  api/               # HTTP клиент
  components/        # shell/layout
  pages/             # Dashboard / Testing / Dictionary / Training
```

## Production рекомендации

- Держать live inference в одном процессе, чтобы не дублировать модель в памяти GPU.
- Масштабировать control-plane отдельно, если потребуется.
- Для production training выделить отдельный GPU-профиль или отдельный сервер.
- Для больших датасетов перейти с локальных volume на S3/MinIO.

## Почему именно так

FastAPI поддерживает несколько worker-процессов для увеличения пропускной способности, а Docker Compose позволяет явно резервировать GPU для контейнеров. В этом проекте live TTS оставлен в одном GPU-процессе ради минимальной задержки и чтобы не размножать модель в памяти, а параллельность достигается через async WebSocket sessions и отдельные FIFO-очереди на Redis. citeturn927635view2turn927635view1

Qwen3-TTS официально позиционируется как серия моделей со streaming speech generation, voice cloning и возможностью использовать Base-модель для fine-tuning. Поэтому слой `services/tts/qwen.py` и training runner подготовлены именно под такую интеграцию. citeturn927635view0


## Qwen GPU mode

For real speech generation on NVIDIA GPU:

1. Set `TTS_BACKEND=qwen` in `.env`.
2. Use `QWEN_MODEL_NAME=Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` for lower latency, or switch to the 1.7B model for higher quality.
3. Rebuild `api` after changing dependencies: `docker compose up --build -d api trainer web`.
4. The backend uses Qwen speakers exposed in the voices catalog and maps style profiles like `tech-lora-v1` to instruction prompts.

The current live mode keeps app-level low latency by chunking text early and synthesizing each chunk immediately.
