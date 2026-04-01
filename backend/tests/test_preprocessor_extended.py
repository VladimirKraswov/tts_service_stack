import pytest
from sqlalchemy.orm import Session
from app.services.preprocessor import TechnicalPreprocessor
from app.models.dictionary import Dictionary, DictionaryEntry

def test_literary_preprocessing():
    tp = TechnicalPreprocessor()
    # Chapter headings
    text = "Глава I. В начале было слово."
    processed = tp._apply_literary_rules(text)
    assert "Глава первая" in processed

    text = "Часть II. Путь домой."
    processed = tp._apply_literary_rules(text)
    assert "Часть вторая" in processed

    # Initials
    text = "А. С. Пушкин написал много сказок."
    processed = tp._apply_literary_rules(text)
    assert "А. С. Пушкин" in processed

def test_technical_preprocessing():
    tp = TechnicalPreprocessor()
    # Path handling
    text = "The file is at /home/user/data.txt"
    processed = tp._apply_technical_rules(text)
    assert " слэш home слэш user слэш data.txt" in processed

    # Code snippets
    text = "Use `result = a + b` for calculations."
    processed = tp._rewrite_code(text)
    assert "result = a + b" in processed
    # check if spaces added
    assert " result = a + b " in processed

def test_general_preprocessing():
    tp = TechnicalPreprocessor()
    # Units
    text = "Вес составляет 5 кг, длина 10 см."
    processed = tp._apply_general_rules(text)
    assert "килограмм" in processed
    assert "сантиметр" in processed

    # Money
    text = "Цена 100 руб. или 1000 ₽."
    processed = tp._apply_general_rules(text)
    assert "рубль" in processed
    assert processed.count("рубль") == 2

def test_staged_pipeline(db_session: Session):
    tp = TechnicalPreprocessor()
    # Setup a dictionary entry
    dict_obj = Dictionary(name="Test Pipeline", slug="test-pipeline-unique", is_default=True)
    db_session.add(dict_obj)
    db_session.flush()
    entry = DictionaryEntry(dictionary_id=dict_obj.id, source_text="MyCustomWord", spoken_text="кастомное слово")
    db_session.add(entry)
    db_session.commit()

    text = "Service uses MyCustomWord.\n\nMore info at /api/v1."
    payload = tp.process(db_session, text, profile="technical")

    # Check dictionary application
    assert "кастомное слово" in payload.processed_text
    # Check tech rules (path)
    # Note: API was replaced by эй пи ай, then path rules replaced / by слэш
    assert " слэш эй пи ай слэш v1" in payload.processed_text or "/эй пи ай слэш v1" in payload.processed_text
    # Check normalization (double newline)
    assert "\n\n" in payload.processed_text

def test_chunking():
    tp = TechnicalPreprocessor()
    # Test paragraph respecting
    text = "First paragraph. End of first.\n\nSecond paragraph. Still second."
    chunks = tp._chunk(text, profile="literary")
    assert len(chunks) >= 1

    # Test long chunk splitting
    long_text = "слово " * 100 # ~ 600 chars
    chunks = tp._chunk(long_text, profile="literary")
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 400
