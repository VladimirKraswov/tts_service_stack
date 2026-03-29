import pytest
from sqlalchemy.orm import Session
from app.services.preprocessor import TechnicalPreprocessor
from app.models.dictionary import Dictionary, DictionaryEntry

def test_normalize():
    tp = TechnicalPreprocessor()
    assert tp._normalize("  hello   world  ") == "hello world"
    assert tp._normalize("line1\n\n\nline2") == "line1\n\nline2"

def test_apply_regex():
    tp = TechnicalPreprocessor()
    assert "эй пи ай" in tp._apply_regex("Using the API today")
    assert "джейсон" in tp._apply_regex("Send JSON payload")
    assert "версия 1.2.3" in tp._apply_regex("Software v1.2.3")
    assert "ю ай ю икс" in tp._apply_regex("Great UI/UX design")

def test_speak_code():
    tp = TechnicalPreprocessor()
    spoken = tp._speak_code("my_function(arg)")
    assert "андерскор" in spoken
    assert "открывающая скобка" in spoken
    assert "закрывающая скобка" in spoken

def test_apply_dictionary(db_session: Session):
    # Setup dictionary
    dict_obj = Dictionary(name="Test Dict", slug="test-dict", is_default=True)
    db_session.add(dict_obj)
    db_session.commit()

    entry = DictionaryEntry(dictionary_id=dict_obj.id, source_text="React", spoken_text="Риэкт")
    db_session.add(entry)
    db_session.commit()

    tp = TechnicalPreprocessor()
    # Should replace React with Риэкт
    processed = tp._apply_dictionary(db_session, "Learning React is fun", dictionary_id=dict_obj.id)
    assert "Риэкт" in processed

    # Should NOT replace part of a word if it's alphanumeric (word boundary check)
    processed_partial = tp._apply_dictionary(db_session, "Reaction is different", dictionary_id=dict_obj.id)
    assert "Риэкт" not in processed_partial
    assert "Reaction" in processed_partial
