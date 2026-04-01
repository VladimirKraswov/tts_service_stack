from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.models.base import Base
from app.models.dictionary import Dictionary, DictionaryEntry
from app.models.synthesis import SynthesisJob
from app.models.voice import VoiceProfile


def _ensure_voice(
    session,
    name: str,
    display_name: str,
    backend: str,
    model_name: str,
    description: str,
    kind: str = 'voice',
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
    entries: list[tuple[str, str, str]],
) -> Dictionary:
    dictionary = session.scalar(select(Dictionary).where(Dictionary.slug == slug))
    if dictionary is None:
        dictionary = Dictionary(
            name=name,
            slug=slug,
            description=description,
            is_default=is_default,
        )
        session.add(dictionary)
        session.flush()
    else:
        dictionary.name = name
        dictionary.description = description
        dictionary.is_default = is_default
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
                )
            )
        else:
            row.spoken_text = spoken_text
            row.note = note

    return dictionary


def init_db() -> None:
    settings = get_settings()
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        _ensure_dictionary(
            session,
            name='Default Tech',
            slug='default-tech',
            description='Базовый словарь произношения технических терминов.',
            is_default=True,
            entries=[
                ('Python', 'Пайтон', 'Название языка Python'),
                ('Java', 'Джава', 'Название языка Java'),
                ('React', 'Реакт', 'Название фреймворка React'),
                ('Golang', 'Гоу лэнг', 'Название языка Go'),
                ('useEffect', 'юз эффект', 'Хук React'),
                ('useState', 'юз стейт', 'Хук React'),
                ('goroutine', 'горутина', 'Go concurrency primitive'),
                ('__init__', 'андерскор андерскор инит андерскор андерскор', 'Python magic method'),
                ('WebSocket', 'веб сокет', 'Сетевой термин'),
                ('FastAPI', 'фаст эй пи ай', 'Название фреймворка'),
                ('GPU', 'джи пи ю', 'Графический процессор'),
                ('CPU', 'си пи ю', 'Центральный процессор'),
            ],
        )

        _ensure_dictionary(
            session,
            name='Default Literary',
            slug='default-literary',
            description='Базовый словарь и подстановки для чтения художественной литературы.',
            is_default=False,
            entries=[
                ('г.', 'город', 'Сокращение'),
                ('ул.', 'улица', 'Сокращение'),
                ('им.', 'имени', 'Сокращение'),
                ('гл.', 'глава', 'Сокращение'),
                ('стр.', 'страница', 'Сокращение'),
                ('рис.', 'рисунок', 'Сокращение'),
                ('кв.', 'квартира', 'Сокращение'),
                ('пос.', 'посёлок', 'Сокращение'),
                ('д.', 'дом', 'Сокращение'),
                ('др.', 'другие', 'Сокращение'),
                ('т.е.', 'то есть', 'Сокращение'),
                ('т.к.', 'так как', 'Сокращение'),
                ('т.д.', 'так далее', 'Сокращение'),
                ('т.п.', 'тому подобное', 'Сокращение'),
                ('и т.д.', 'и так далее', 'Сокращение'),
                ('и т.п.', 'и тому подобное', 'Сокращение'),
                ('гг.', 'годы', 'Сокращение'),
                ('№', 'номер', 'Знак номера'),
            ],
        )

        if settings.effective_preview_backend == 'qwen':
            qwen_model = settings.qwen_model_name
            qwen_voices = [
                ('qwen-vivian', 'Qwen Vivian', 'Vivian', 'Яркий молодой женский голос.'),
                ('qwen-serena', 'Qwen Serena', 'Serena', 'Теплый мягкий женский голос.'),
                ('qwen-uncle-fu', 'Qwen Uncle Fu', 'Uncle_Fu', 'Низкий спокойный мужской голос.'),
                ('qwen-dylan', 'Qwen Dylan', 'Dylan', 'Молодой мужской голос с четкой дикцией.'),
                ('qwen-eric', 'Qwen Eric', 'Eric', 'Живой мужской голос с легкой хрипотцой.'),
                ('qwen-ryan', 'Qwen Ryan', 'Ryan', 'Динамичный английский мужской голос.'),
                ('qwen-aiden', 'Qwen Aiden', 'Aiden', 'Солнечный американский мужской голос.'),
                ('qwen-ono-anna', 'Qwen Ono Anna', 'Ono_Anna', 'Легкий японский женский голос.'),
                ('qwen-sohee', 'Qwen Sohee', 'Sohee', 'Теплый корейский женский голос.'),
                ('system-neutral', 'System Neutral', 'Ryan', 'Совместимый системный alias для нейтрального голоса.'),
                ('system-warm', 'System Warm', 'Serena', 'Совместимый системный alias для теплого голоса.'),
            ]
            for name, display_name, speaker, description in qwen_voices:
                _ensure_voice(session, name, display_name, 'qwen', qwen_model, f'{description} Speaker={speaker}')

            _ensure_voice(
                session,
                'tech-lora-v1',
                'Tech Style v1',
                'qwen',
                qwen_model,
                'Стиль тех-диктора через instruction prompt.',
                kind='lora',
            )
            _ensure_voice(
                session,
                'calm-lora-v1',
                'Calm Style v1',
                'qwen',
                qwen_model,
                'Спокойный стиль через instruction prompt.',
                kind='lora',
            )
            _ensure_voice(
                session,
                'energetic-lora-v1',
                'Energetic Style v1',
                'qwen',
                qwen_model,
                'Энергичный стиль через instruction prompt.',
                kind='lora',
            )
        else:
            _ensure_voice(session, 'system-neutral', 'System Neutral', 'mock', 'mock://neutral', 'Базовый нейтральный голос')
            _ensure_voice(session, 'system-warm', 'System Warm', 'mock', 'mock://warm', 'Теплый голос для тестов')
            _ensure_voice(
                session,
                'tech-lora-v1',
                'Tech LoRA v1',
                'mock',
                'mock://tech-lora-v1',
                'LoRA для техтекста',
                kind='lora',
            )

        session.commit()