import re
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

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


def _normalize_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _ensure_single_default(db: Session, dictionary_id: int, domain: str, language: str) -> None:
    db.execute(
        update(Dictionary)
        .where(
            Dictionary.id != dictionary_id,
            Dictionary.domain == domain,
            Dictionary.language == language,
            Dictionary.is_default == True
        )
        .values(is_default=False)
    )


@router.get('', response_model=list[DictionaryRead])
def list_dictionaries(db: Session = Depends(get_db)) -> list[Dictionary]:
    return list(
        db.scalars(
            select(Dictionary).order_by(Dictionary.priority.desc(), Dictionary.is_default.desc(), Dictionary.id)
        )
    )


@router.post('', response_model=DictionaryRead)
def create_dictionary(payload: DictionaryCreate, db: Session = Depends(get_db)) -> Dictionary:
    try:
        # Prevent creating system dictionaries via API
        data = payload.model_dump()
        data['is_system'] = False
        data['is_editable'] = True

        dictionary = Dictionary(**data)
        db.add(dictionary)
        db.flush()

        if dictionary.is_default:
            _ensure_single_default(db, dictionary.id, dictionary.domain, dictionary.language)

        db.commit()
        db.refresh(dictionary)
        return dictionary
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Dictionary with this slug or name already exists')


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

    requested = payload.model_dump(exclude_unset=True)

    # Restricted fields for system dictionaries
    if not dictionary.is_editable:
        restricted_fields = {'name', 'slug', 'description', 'domain', 'language', 'is_system', 'is_editable'}
        if any(field in requested for field in restricted_fields):
            raise HTTPException(status_code=403, detail='System fields of this dictionary are not editable')

    # Security: never allow changing is_system/is_editable via PATCH
    requested.pop('is_system', None)
    requested.pop('is_editable', None)

    for field, value in requested.items():
        setattr(dictionary, field, value)

    try:
        db.flush()
        if dictionary.is_default:
            _ensure_single_default(db, dictionary.id, dictionary.domain, dictionary.language)
        db.commit()
        db.refresh(dictionary)
        return dictionary
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Conflict: Name or slug already exists')


@router.delete('/{dictionary_id}', status_code=204)
def delete_dictionary(dictionary_id: int, db: Session = Depends(get_db)) -> Response:
    dictionary = db.get(Dictionary, dictionary_id)
    if dictionary is None:
        raise HTTPException(status_code=404, detail='Dictionary not found')
    if not dictionary.is_editable:
        raise HTTPException(status_code=403, detail='System dictionaries cannot be deleted')

    db.delete(dictionary)
    db.commit()
    return Response(status_code=204)


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

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
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


@router.post('/{dictionary_id}/entries', response_model=DictionaryEntryRead)
def add_entry(dictionary_id: int, payload: DictionaryEntryCreate, db: Session = Depends(get_db)) -> DictionaryEntry:
    dictionary = db.get(Dictionary, dictionary_id)
    if dictionary is None:
        raise HTTPException(status_code=404, detail='Dictionary not found')
    if not dictionary.is_editable:
        raise HTTPException(status_code=403, detail='Dictionary is not editable')

    data = payload.model_dump()
    data['source_text'] = _normalize_text(data['source_text'])
    data['spoken_text'] = _normalize_text(data['spoken_text'])

    try:
        entry = DictionaryEntry(dictionary_id=dictionary_id, **data)
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f'Entry with source text "{data["source_text"]}" already exists')


@router.patch('/{dictionary_id}/entries/{entry_id}', response_model=DictionaryEntryRead)
def update_entry(
    dictionary_id: int,
    entry_id: int,
    payload: DictionaryEntryUpdate,
    db: Session = Depends(get_db),
) -> DictionaryEntry:
    dictionary = db.get(Dictionary, dictionary_id)
    if dictionary is None:
        raise HTTPException(status_code=404, detail='Dictionary not found')
    if not dictionary.is_editable:
        raise HTTPException(status_code=403, detail='Dictionary is not editable')

    entry = db.get(DictionaryEntry, entry_id)
    if entry is None or entry.dictionary_id != dictionary_id:
        raise HTTPException(status_code=404, detail='Entry not found')

    requested = payload.model_dump(exclude_unset=True)
    if 'source_text' in requested:
        requested['source_text'] = _normalize_text(requested['source_text'])
    if 'spoken_text' in requested:
        requested['spoken_text'] = _normalize_text(requested['spoken_text'])

    for field, value in requested.items():
        setattr(entry, field, value)

    try:
        db.commit()
        db.refresh(entry)
        return entry
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Conflict: Another entry with this source text already exists')


@router.delete('/{dictionary_id}/entries/{entry_id}', status_code=204)
def delete_entry(dictionary_id: int, entry_id: int, db: Session = Depends(get_db)) -> Response:
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
    return Response(status_code=204)


@router.post('/{dictionary_id}/preview', response_model=PronunciationPreviewResponse)
def preview_pronunciation(
    dictionary_id: int,
    payload: PronunciationPreviewRequest,
    db: Session = Depends(get_db),
) -> PronunciationPreviewResponse:
    processed = preprocessor.process(db, payload.text, dictionary_id=dictionary_id, profile='general')
    return PronunciationPreviewResponse(original_text=payload.text, processed_text=processed.processed_text)


@router.get('/{dictionary_id}/export', response_model=DictionaryExport)
def export_dictionary(dictionary_id: int, db: Session = Depends(get_db)) -> DictionaryExport:
    dictionary = db.get(Dictionary, dictionary_id)
    if dictionary is None:
        raise HTTPException(status_code=404, detail='Dictionary not found')

    entries = list(
        db.scalars(
            select(DictionaryEntry)
            .where(DictionaryEntry.dictionary_id == dictionary_id)
            .order_by(DictionaryEntry.priority.desc(), DictionaryEntry.source_text)
        )
    )

    return DictionaryExport(
        version=1,
        name=dictionary.name,
        slug=dictionary.slug,
        description=dictionary.description,
        is_default=dictionary.is_default,
        domain=dictionary.domain,
        language=dictionary.language,
        entries=[
            DictionaryEntryCreate(
                source_text=entry.source_text,
                spoken_text=entry.spoken_text,
                note=entry.note,
                case_sensitive=entry.case_sensitive,
                is_enabled=entry.is_enabled,
                priority=entry.priority,
            )
            for entry in entries
        ],
    )


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
        for entry in db.scalars(select(DictionaryEntry).where(DictionaryEntry.dictionary_id == dictionary_id)).all()
    }

    created_count = 0
    updated_count = 0
    deleted_count = 0

    if mode == ImportConflictMode.REPLACE_EXISTING_ENTRIES:
        for entry in existing_entries.values():
            db.delete(entry)
            deleted_count += 1
        db.flush()
        existing_entries = {}

    for entry_data in payload.entries:
        source_text = _normalize_text(entry_data.source_text)
        existing = existing_entries.get(source_text)

        if existing is not None:
            if mode == ImportConflictMode.MERGE:
                existing.spoken_text = _normalize_text(entry_data.spoken_text)
                existing.note = entry_data.note
                existing.case_sensitive = entry_data.case_sensitive
                existing.is_enabled = entry_data.is_enabled
                existing.priority = entry_data.priority
                updated_count += 1
            continue

        if mode == ImportConflictMode.CREATE_ONLY or mode == ImportConflictMode.MERGE or mode == ImportConflictMode.REPLACE_EXISTING_ENTRIES:
            new_entry = DictionaryEntry(
                dictionary_id=dictionary_id,
                source_text=source_text,
                spoken_text=_normalize_text(entry_data.spoken_text),
                note=entry_data.note,
                case_sensitive=entry_data.case_sensitive,
                is_enabled=entry_data.is_enabled,
                priority=entry_data.priority
            )
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
    existing_dictionary = db.scalar(select(Dictionary).where(Dictionary.slug == payload.slug))

    if existing_dictionary is not None:
        return import_into_dictionary(existing_dictionary.id, payload, mode, db)

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

    if dictionary.is_default:
        _ensure_single_default(db, dictionary.id, dictionary.domain, dictionary.language)

    created_count = 0
    for entry_data in payload.entries:
        db.add(DictionaryEntry(
            dictionary_id=dictionary.id,
            source_text=_normalize_text(entry_data.source_text),
            spoken_text=_normalize_text(entry_data.spoken_text),
            note=entry_data.note,
            case_sensitive=entry_data.case_sensitive,
            is_enabled=entry_data.is_enabled,
            priority=entry_data.priority
        ))
        created_count += 1

    db.commit()
    return {
        'dictionary_id': dictionary.id,
        'entries_created': created_count,
        'entries_updated': 0,
        'entries_deleted': 0,
    }
