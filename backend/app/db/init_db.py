from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.models.base import Base
from app.models.dictionary import Dictionary, DictionaryEntry
from app.models.synthesis import SynthesisJob  # noqa: F401
from app.models.training import TrainingDataset, TrainingJob  # noqa: F401
from app.models.voice import VoiceProfile


def _ensure_voice(
    session,
    name: str,
    display_name: str,
    backend: str,
    model_name: str,
    description: str,
    kind: str = "voice",
) -> None:
    existing = session.scalar(select(VoiceProfile).where(VoiceProfile.name == name))
    if existing is None:
        session.add(
            VoiceProfile(
                name=name,
                display_name=display_name,
                backend=backend,
                model_name=model_name,
                description=description,
                is_enabled=True,
                kind=kind,
            )
        )
        return

    existing.display_name = display_name
    existing.backend = backend
    existing.model_name = model_name
    existing.description = description
    existing.is_enabled = True
    existing.kind = kind


def _ensure_dictionary(
    session,
    *,
    name: str,
    slug: str,
    description: str,
    is_default: bool,
    domain: str = "general",
    language: str = "ru",
    is_system: bool = True,
    is_editable: bool = False,
    priority: int = 0,
    entries: list[tuple[str, str, str]],
) -> Dictionary:
    dictionary = session.scalar(select(Dictionary).where(Dictionary.slug == slug))
    if dictionary is None:
        dictionary = Dictionary(
            name=name,
            slug=slug,
            description=description,
            is_default=is_default,
            domain=domain,
            language=language,
            is_system=is_system,
            is_editable=is_editable,
            priority=priority,
        )
        session.add(dictionary)
        session.flush()
    else:
        dictionary.name = name
        dictionary.description = description
        dictionary.is_default = is_default
        dictionary.domain = domain
        dictionary.language = language
        dictionary.is_system = is_system
        dictionary.is_editable = is_editable
        dictionary.priority = priority
        session.flush()

    existing_entries = {
        entry.source_text: entry
        for entry in session.scalars(
            select(DictionaryEntry).where(DictionaryEntry.dictionary_id == dictionary.id)
        ).all()
    }

    for source_text, spoken_text, note in entries:
        row = existing_entries.get(source_text)
        if row is None:
            session.add(
                DictionaryEntry(
                    dictionary_id=dictionary.id,
                    source_text=source_text,
                    spoken_text=spoken_text,
                    note=note,
                    case_sensitive=False,
                    is_enabled=True,
                    priority=0,
                )
            )
        else:
            row.spoken_text = spoken_text
            row.note = note
            row.case_sensitive = False
            row.is_enabled = True

    return dictionary


def init_db() -> None:
    settings = get_settings()

    # Создаёт схему с нуля по актуальным моделям.
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        _ensure_dictionary(
            session,
            name="Default Tech",
            slug="default-tech",
            description="Базовый словарь произношения технических терминов.",
            is_default=True,
            domain="technical",
            language="ru",
            is_system=True,
            is_editable=False,
            priority=100,
            entries=[
                ("WebSocket", "веб сокет", "Технический термин"),
                ("FastAPI", "фаст эй пи ай", "Фреймворк"),
                ("REST", "рест", "Архитектурный стиль"),
                ("REST API", "рест эй пи ай", "Технический термин"),
                ("HTTP", "эйч ти ти пи", "Протокол"),
                ("HTTPS", "эйч ти ти пи эс", "Протокол"),
                ("JSON", "джейсон", "Формат данных"),
                ("SQL", "эс кью эл", "Язык запросов"),
                ("CLI", "си эл ай", "Интерфейс"),
                ("UI", "ю ай", "Интерфейс"),
                ("UX", "ю икс", "Опыт"),
                ("UI/UX", "ю ай ю икс", "Дизайн"),
                ("CI/CD", "си ай си ди", "Процесс"),
                ("CPU", "си пи ю", "Процессор"),
                ("GPU", "джи пи ю", "Видеокарта"),
                ("backend", "бэкэнд", "Технический термин"),
                ("frontend", "фронтэнд", "Технический термин"),
                ("Docker", "докер", "Контейнеризация"),
                ("Docker Compose", "докер компоуз", "Инструмент"),
                ("Redis", "редис", "Хранилище"),
                ("PostgreSQL", "постгрес", "База данных"),
                ("React", "ре акт", "Библиотека"),
                ("TypeScript", "тайп скрипт", "Язык программирования"),
                ("JavaScript", "джава скрипт", "Язык программирования"),
                ("Python", "пайтон", "Язык программирования"),
                ("Golang", "гоу лэнг", "Язык программирования"),
                ("API Gateway", "эй пи ай гейтвей", "Архитектура"),
                ("JWT", "джи дабл ю ти", "Токен"),
                ("OAuth", "о аус", "Авторизация"),
                ("protobuf", "протобаф", "Сериализация"),
                ("nginx", "энджиикс", "Сервер"),
            ],
        )

        _ensure_dictionary(
            session,
            name="Default Literary",
            slug="default-literary",
            description="Базовый словарь для художественного чтения.",
            is_default=False,
            domain="literary",
            language="ru",
            is_system=True,
            is_editable=False,
            priority=90,
            entries=[
                ("гл.", "глава", "Сокращение"),
                ("стр.", "страница", "Сокращение"),
                ("рис.", "рисунок", "Сокращение"),
                ("табл.", "таблица", "Сокращение"),
                ("А. С. Пушкин", "Александр Сергеевич Пушкин", "Имя"),
                ("Л. Н. Толстой", "Лев Николаевич Толстой", "Имя"),
                ("Ф. М. Достоевский", "Фёдор Михайлович Достоевский", "Имя"),
            ],
        )

        _ensure_dictionary(
            session,
            name="Default General RU",
            slug="default-general-ru",
            description="Общий словарь сокращений русского языка.",
            is_default=False,
            domain="general",
            language="ru",
            is_system=True,
            is_editable=False,
            priority=80,
            entries=[
                ("т.е.", "то есть", "Сокращение"),
                ("т.к.", "так как", "Сокращение"),
                ("т.д.", "так далее", "Сокращение"),
                ("т.п.", "тому подобное", "Сокращение"),
                ("и т.д.", "и так далее", "Сокращение"),
                ("и т.п.", "и тому подобное", "Сокращение"),
                ("др.", "другие", "Сокращение"),
                ("кв.", "квартира", "Сокращение"),
                ("д.", "дом", "Сокращение"),
                ("ул.", "улица", "Сокращение"),
                ("просп.", "проспект", "Сокращение"),
                ("пер.", "переулок", "Сокращение"),
                ("пос.", "посёлок", "Сокращение"),
                ("обл.", "область", "Сокращение"),
                ("им.", "имени", "Сокращение"),
                ("гг.", "годы", "Сокращение"),
                ("г.", "город", "Сокращение"),
                ("№", "номер", "Знак номера"),
                ("млн", "миллионов", "Числительное"),
                ("млрд", "миллиардов", "Числительное"),
                ("тыс.", "тысяч", "Числительное"),
                ("руб.", "рублей", "Валюта"),
                ("коп.", "копеек", "Валюта"),
            ],
        )

        if settings.effective_preview_backend == "qwen":
            qwen_model = settings.qwen_model_name
            qwen_voices = [
                ("qwen-vivian", "Qwen Vivian", "Vivian", "Яркий молодой женский голос."),
                ("qwen-serena", "Qwen Serena", "Serena", "Теплый мягкий женский голос."),
                ("qwen-uncle-fu", "Qwen Uncle Fu", "Uncle_Fu", "Низкий спокойный мужской голос."),
                ("qwen-dylan", "Qwen Dylan", "Dylan", "Молодой мужской голос с четкой дикцией."),
                ("qwen-eric", "Qwen Eric", "Eric", "Живой мужской голос с легкой хрипотцой."),
                ("qwen-ryan", "Qwen Ryan", "Ryan", "Динамичный английский мужской голос."),
                ("qwen-aiden", "Qwen Aiden", "Aiden", "Солнечный американский мужской голос."),
                ("qwen-ono-anna", "Qwen Ono Anna", "Ono_Anna", "Легкий японский женский голос."),
                ("qwen-sohee", "Qwen Sohee", "Sohee", "Теплый корейский женский голос."),
                ("system-neutral", "System Neutral", "Ryan", "Совместимый системный alias для нейтрального голоса."),
                ("system-warm", "System Warm", "Serena", "Совместимый системный alias для теплого голоса."),
            ]

            for name, display_name, speaker, description in qwen_voices:
                _ensure_voice(
                    session,
                    name=name,
                    display_name=display_name,
                    backend="qwen",
                    model_name=qwen_model,
                    description=f"{description} Speaker={speaker}",
                )

            _ensure_voice(
                session,
                "tech-lora-v1",
                "Tech Style v1",
                "qwen",
                qwen_model,
                "Стиль тех-диктора через instruction prompt.",
                kind="lora",
            )
            _ensure_voice(
                session,
                "calm-lora-v1",
                "Calm Style v1",
                "qwen",
                qwen_model,
                "Спокойный стиль через instruction prompt.",
                kind="lora",
            )
            _ensure_voice(
                session,
                "energetic-lora-v1",
                "Energetic Style v1",
                "qwen",
                qwen_model,
                "Энергичный стиль через instruction prompt.",
                kind="lora",
            )
        else:
            _ensure_voice(
                session,
                "system-neutral",
                "System Neutral",
                "mock",
                "mock://neutral",
                "Базовый нейтральный голос",
            )
            _ensure_voice(
                session,
                "system-warm",
                "System Warm",
                "mock",
                "mock://warm",
                "Теплый голос для тестов",
            )
            _ensure_voice(
                session,
                "tech-lora-v1",
                "Tech LoRA v1",
                "mock",
                "mock://tech-lora-v1",
                "LoRA для техтекста",
                kind="lora",
            )

        session.commit()


if __name__ == "__main__":
    init_db()