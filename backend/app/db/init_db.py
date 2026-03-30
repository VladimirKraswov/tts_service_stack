from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.models.base import Base
from app.models.dictionary import Dictionary, DictionaryEntry
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


def init_db() -> None:
    settings = get_settings()
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        default_dictionary = session.scalar(select(Dictionary).where(Dictionary.slug == 'default-tech'))
        if default_dictionary is None:
            default_dictionary = Dictionary(
                name='Default Tech',
                slug='default-tech',
                description='Базовый словарь произношения технических терминов.',
                is_default=True,
            )
            session.add(default_dictionary)
            session.flush()
            entries = [
                ('Python', 'Пайтон', 'Название языка Python'),
                ('Java', 'Джава', 'Название языка Java'),
                ('React', 'Реакт', 'Название фреймворка React'),
                ('Golang', 'Гоу лэнг', 'Название языка Go'),
                ('useEffect', 'юз эффект', 'Хук React'),
                ('useState', 'юз стейт', 'Хук React'),
                ('goroutine', 'горутина', 'Go concurrency primitive'),
                ('__init__', 'андерскор андерскор инит андерскор андерскор', 'Python magic method'),
            ]
            for source, spoken, note in entries:
                session.add(
                    DictionaryEntry(
                        dictionary_id=default_dictionary.id,
                        source_text=source,
                        spoken_text=spoken,
                        note=note,
                    )
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