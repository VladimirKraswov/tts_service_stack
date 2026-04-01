# Dictionary and Preprocessing Documentation

## Dictionary JSON Format

The system supports a standardized JSON format for importing and exporting dictionaries.

### Example Schema
```json
{
  "version": 1,
  "name": "Technical Russian",
  "slug": "tech-ru",
  "description": "Common technical terms and abbreviations",
  "domain": "technical",
  "language": "ru",
  "is_default": false,
  "entries": [
    {
      "source_text": "WebSocket",
      "spoken_text": "веб сокет",
      "note": "Technical term"
    },
    {
      "source_text": "API",
      "spoken_text": "эй пи ай",
      "priority": 10
    }
  ]
}
```

### Import Modes
When importing entries into an existing dictionary, the following conflict resolution modes are available:
- `merge` (default): Updates existing entries (by `source_text`) and creates new ones.
- `create_only`: Only adds entries that do not already exist. Existing entries are left untouched.
- `replace_existing_entries`: Deletes all current entries in the dictionary before importing the new ones.

## Preprocessing Profiles

The TTS service uses a staged preprocessing pipeline with three distinct profiles. Profiles can be explicitly requested in API calls or automatically selected based on the active dictionary's domain.

### 1. General (`general`)
- **Use Case:** Everyday conversation, news, mixed content.
- **Rules:** Handles common abbreviations (т.е., т.к.), units (кг, см, руб.), and standard Russian text normalization.

### 2. Technical (`technical`)
- **Use Case:** Documentation, code snippets, IT-related text.
- **Rules:**
    - Normalizes technical symbols (e.g., `==` to "равно", `!=` to "не равно").
    - Handles paths (e.g., `/api/v1`) and versions (`v1.2.3`).
    - Expanded dictionary of English IT terms with Russian phonetic equivalents.
    - Preserves camelCase and snake_case structure where appropriate for reading.

### 3. Literary (`literary`)
- **Use Case:** Books, long-form narratives, dialogues.
- **Rules:**
    - Improved dialogue handling (dash normalization).
    - Chapter heading normalization (e.g., "Глава I" to "Глава первая").
    - Handles initials (e.g., "А. С. Пушкин") without breaking sentences.
    - Sentence-aware chunking to preserve narrative flow.

## Dictionary Metadata
- **Domain:** Categorizes the dictionary (general, technical, literary, etc.).
- **Is System:** System dictionaries are protected and cannot be deleted or modified directly via the UI (though they can be updated via migrations or seeding).
- **Priority:** Higher priority dictionaries take precedence when multiple dictionaries are active (future feature).
