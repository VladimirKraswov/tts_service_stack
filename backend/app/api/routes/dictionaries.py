from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.dictionary import Dictionary, DictionaryEntry
from app.schemas.dictionary import (
    DictionaryCreate,
    DictionaryEntryCreate,
    DictionaryEntryPagination,
    DictionaryEntryRead,
    DictionaryEntryUpdate,
    DictionaryExport,
    DictionaryImportResponse,
    DictionaryRead,
    DictionaryUpdate,
    ImportConflictMode,
    PronunciationPreviewRequest,
    PronunciationPreviewResponse,
)
from app.services.preprocessor import TechnicalPreprocessor

router = APIRouter(prefix='/dictionaries', tags=['dictionaries'])
preprocessor = TechnicalPreprocessor()


@router.get('', response_model=list[DictionaryRead])
def list_dictionaries(db: Session = Depends(get_db)) -> list[Dictionary]:
    return list(db.scalars(select(Dictionary).order_by(Dictionary.priority.desc(), Dictionary.id)))


@router.post('', response_model=DictionaryRead)
def create_dictionary(payload: DictionaryCreate, db: Session = Depends(get_db)) -> Dictionary:
    dictionary = Dictionary(**payload.model_dump())
    db.add(dictionary)
    db.commit()
    db.refresh(dictionary)
    return dictionary


@router.get('/{dictionary_id}', response_model=DictionaryRead)
def get_dictionary(dictionary_id: int, db: Session = Depends(get_db)) -> Dictionary:
    dictionary = db.get(Dictionary, dictionary_id)
    if dictionary is None:
        raise HTTPException(status_code=404, detail='Dictionary not found')
    return dictionary


@router.patch('/{dictionary_id}', response_model=DictionaryRead)
def update_dictionary(dictionary_id: int, payload: DictionaryUpdate, db: Session = Depends(get_db)) -> Dictionary:
    dictionary = db.get(Dictionary, dictionary_id)
    if dictionary is None:
        raise HTTPException(status_code=404, detail='Dictionary not found')

    if not dictionary.is_editable and any(
        v is not None
        for k, v in payload.model_dump(exclude={'priority', 'is_default'}).items()
    ):
        raise HTTPException(status_code=403, detail='Dictionary is not editable')

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(dictionary, field, value)

    db.commit()
    db.refresh(dictionary)
    return dictionary


@router.delete('/{dictionary_id}', status_code=204)
def delete_dictionary(dictionary_id: int, db: Session = Depends(get_db)):
    dictionary = db.get(Dictionary, dictionary_id)
    if dictionary is None:
        raise HTTPException(status_code=404, detail='Dictionary not found')
    if not dictionary.is_editable:
        raise HTTPException(status_code=403, detail='System dictionaries cannot be deleted')

    db.delete(dictionary)
    db.commit()
    return


@router.post('/{dictionary_id}/entries', response_model=DictionaryEntryRead)
def add_entry(dictionary_id: int, payload: DictionaryEntryCreate, db: Session = Depends(get_db)) -> DictionaryEntry:
    dictionary = db.get(Dictionary, dictionary_id)
    if dictionary is None:
        raise HTTPException(status_code=404, detail='Dictionary not found')
    if not dictionary.is_editable:
        raise HTTPException(status_code=403, detail='Dictionary is not editable')

    entry = DictionaryEntry(dictionary_id=dictionary_id, **payload.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.patch('/{dictionary_id}/entries/{entry_id}', response_model=DictionaryEntryRead)
def update_entry(
    dictionary_id: int, entry_id: int, payload: DictionaryEntryUpdate, db: Session = Depends(get_db)
) -> DictionaryEntry:
    dictionary = db.get(Dictionary, dictionary_id)
    if dictionary is None:
        raise HTTPException(status_code=404, detail='Dictionary not found')
    if not dictionary.is_editable:
        raise HTTPException(status_code=403, detail='Dictionary is not editable')

    entry = db.get(DictionaryEntry, entry_id)
    if entry is None or entry.dictionary_id != dictionary_id:
        raise HTTPException(status_code=404, detail='Entry not found')

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)

    db.commit()
    db.refresh(entry)
    return entry


@router.get('/{dictionary_id}/entries', response_model=DictionaryEntryPagination)
def list_entries(
    dictionary_id: int,
    q: str | None = Query(None, description='Search query for source_text, spoken_text, or note'),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> dict:
    dictionary = db.get(Dictionary, dictionary_id)
    if dictionary is None:
        raise HTTPException(status_code=404, detail='Dictionary not found')

    stmt = select(DictionaryEntry).where(DictionaryEntry.dictionary_id == dictionary_id)
    if q:
        search_filter = (
            DictionaryEntry.source_text.ilike(f'%{q}%')
            | DictionaryEntry.spoken_text.ilike(f'%{q}%')
            | DictionaryEntry.note.ilike(f'%{q}%')
        )
        stmt = stmt.where(search_filter)

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = list(
        db.scalars(
            stmt.order_by(DictionaryEntry.priority.desc(), DictionaryEntry.source_text)
            .offset((page - 1) * size)
            .limit(size)
        )
    )

    pages = (total + size - 1) // size if total > 0 else 1

    return {
        'items': items,
        'total': total,
        'page': page,
        'size': size,
        'pages': pages,
    }


@router.delete('/{dictionary_id}/entries/{entry_id}', status_code=204)
def delete_entry(dictionary_id: int, entry_id: int, db: Session = Depends(get_db)):
    dictionary = db.get(Dictionary, dictionary_id)
    if dictionary is None:
        raise HTTPException(status_code=404, detail='Dictionary not found')
    if not dictionary.is_editable:
        raise HTTPException(status_code=403, detail='Dictionary is not editable')

    entry = db.get(DictionaryEntry, entry_id)
    if entry is None or entry.dictionary_id != dictionary_id:
        raise HTTPException(status_code=404, detail='Entry not found')

    db.delete(entry)
    db.commit()
    return


@router.post('/{dictionary_id}/preview', response_model=PronunciationPreviewResponse)
def preview_pronunciation(
    dictionary_id: int, payload: PronunciationPreviewRequest, db: Session = Depends(get_db)
) -> PronunciationPreviewResponse:
    processed = preprocessor.process(db, payload.text, dictionary_id=dictionary_id)
    return PronunciationPreviewResponse(original_text=payload.text, processed_text=processed.processed_text)


@router.get('/{dictionary_id}/export', response_model=DictionaryExport)
def export_dictionary(dictionary_id: int, db: Session = Depends(get_db)) -> dict:
    dictionary = db.get(Dictionary, dictionary_id)
    if dictionary is None:
        raise HTTPException(status_code=404, detail='Dictionary not found')

    entries = list(db.scalars(select(DictionaryEntry).where(DictionaryEntry.dictionary_id == dictionary_id)))
    result = {
        'version': 1,
        'name': dictionary.name,
        'slug': dictionary.slug,
        'description': dictionary.description,
        'is_default': dictionary.is_default,
        'domain': dictionary.domain,
        'language': dictionary.language,
        'entries': entries,
    }
    return result


@router.post('/{dictionary_id}/import', response_model=DictionaryImportResponse)
def import_into_dictionary(
    dictionary_id: int,
    payload: DictionaryExport,
    mode: ImportConflictMode = Query(ImportConflictMode.MERGE),
    db: Session = Depends(get_db),
) -> dict:
    dictionary = db.get(Dictionary, dictionary_id)
    if dictionary is None:
        raise HTTPException(status_code=404, detail='Dictionary not found')
    if not dictionary.is_editable:
        raise HTTPException(status_code=403, detail='Dictionary is not editable')

    existing_entries = {
        entry.source_text: entry
        for entry in db.scalars(select(DictionaryEntry).where(DictionaryEntry.dictionary_id == dictionary_id))
    }

    created_count = 0
    updated_count = 0
    deleted_count = 0

    if mode == ImportConflictMode.REPLACE_EXISTING_ENTRIES:
        for entry in existing_entries.values():
            db.delete(entry)
            deleted_count += 1
        existing_entries = {}

    for entry_data in payload.entries:
        existing = existing_entries.get(entry_data.source_text)
        if existing:
            if mode == ImportConflictMode.MERGE:
                existing.spoken_text = entry_data.spoken_text
                existing.note = entry_data.note
                existing.case_sensitive = entry_data.case_sensitive
                existing.is_enabled = entry_data.is_enabled
                existing.priority = entry_data.priority
                updated_count += 1
        else:
            new_entry = DictionaryEntry(dictionary_id=dictionary_id, **entry_data.model_dump())
            db.add(new_entry)
            created_count += 1

    db.commit()
    return {
        'dictionary_id': dictionary_id,
        'entries_created': created_count,
        'entries_updated': updated_count,
        'entries_deleted': deleted_count,
    }


@router.post('/import', response_model=DictionaryImportResponse)
def import_full_dictionary(
    payload: DictionaryExport,
    mode: ImportConflictMode = Query(ImportConflictMode.MERGE),
    db: Session = Depends(get_db),
) -> dict:
    dictionary = db.scalar(select(Dictionary).where(Dictionary.slug == payload.slug))

    if dictionary:
        return import_into_dictionary(dictionary.id, payload, mode, db)

    dictionary = Dictionary(
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        is_default=payload.is_default,
        domain=payload.domain,
        language=payload.language,
        is_system=False,
        is_editable=True,
    )
    db.add(dictionary)
    db.flush()

    created_count = 0
    for entry_data in payload.entries:
        new_entry = DictionaryEntry(dictionary_id=dictionary.id, **entry_data.model_dump())
        db.add(new_entry)
        created_count += 1

    db.commit()
    return {
        'dictionary_id': dictionary.id,
        'entries_created': created_count,
        'entries_updated': 0,
        'entries_deleted': 0,
    }
