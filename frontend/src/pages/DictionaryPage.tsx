import { useEffect, useState, useCallback, useRef } from 'react'
import { client, type Dictionary, type DictionaryEntry } from '../api/client'

export function DictionaryPage() {
  const [dictionaries, setDictionaries] = useState<Dictionary[]>([])
  const [selectedId, setSelectedId] = useState<number | undefined>(undefined)
  const [selectedDictionary, setSelectedDictionary] = useState<Dictionary | null>(null)

  // Entries state
  const [entries, setEntries] = useState<DictionaryEntry[]>([])
  const [totalEntries, setTotalEntries] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [loadingEntries, setLoadingEntries] = useState(false)

  // Edit/Create Dictionary state
  const [isEditingDict, setIsEditingDict] = useState(false)
  const [dictForm, setDictForm] = useState({
    name: '',
    slug: '',
    description: '',
    domain: 'general',
    is_default: false,
    priority: 0,
  })

  // Edit/Create Entry state
  const [editingEntryId, setEditingEntryId] = useState<number | null>(null)
  const [entryForm, setEntryForm] = useState({
    source_text: '',
    spoken_text: '',
    note: '',
    priority: 0,
    case_sensitive: false,
    is_enabled: true,
  })

  // Preview state
  const [previewText, setPreviewText] = useState('Наш сервис использует WebSocket и FastAPI для live режима.')
  const [previewResult, setPreviewResult] = useState('')

  // Import state
  const fileInputRef = useRef<HTMLInputElement>(null)

  const loadDictionaries = async () => {
    const rows = await client.listDictionaries()
    setDictionaries(rows)
    if (!selectedId && rows.length > 0) {
      setSelectedId(rows[0].id)
    }
  }

  const loadDictionaryDetails = useCallback(async (id: number) => {
    const dict = await client.getDictionary(id)
    setSelectedDictionary(dict)
    setDictForm({
      name: dict.name,
      slug: dict.slug,
      description: dict.description || '',
      domain: dict.domain,
      is_default: dict.is_default,
      priority: dict.priority,
    })
  }, [])

  const loadEntries = useCallback(async (id: number, p: number, q: string) => {
    setLoadingEntries(true)
    try {
      const resp = await client.listDictionaryEntries(id, { page: p, q, size: 20 })
      setEntries(resp.items)
      setTotalEntries(resp.total)
    } finally {
      setLoadingEntries(false)
    }
  }, [])

  useEffect(() => {
    void loadDictionaries()
  }, [])

  useEffect(() => {
    if (selectedId) {
      void loadDictionaryDetails(selectedId)
      void loadEntries(selectedId, 1, search)
      setPage(1)
    }
  }, [selectedId, loadDictionaryDetails, loadEntries])

  useEffect(() => {
    if (selectedId) {
      void loadEntries(selectedId, page, search)
    }
  }, [page, search, selectedId, loadEntries])

  const handleCreateDictionary = async () => {
    const timestamp = Date.now()
    const newDict = await client.createDictionary({
      name: `Новый словарь ${timestamp}`,
      slug: `new-dict-${timestamp}`,
    })
    await loadDictionaries()
    setSelectedId(newDict.id)
    setIsEditingDict(true)
  }

  const handleUpdateDictionary = async () => {
    if (!selectedId) return
    await client.updateDictionary(selectedId, dictForm)
    await loadDictionaries()
    await loadDictionaryDetails(selectedId)
    setIsEditingDict(false)
  }

  const handleDeleteDictionary = async () => {
    if (!selectedId || !window.confirm('Вы уверены, что хотите удалить этот словарь?')) return
    await client.deleteDictionary(selectedId)
    setSelectedId(undefined)
    setSelectedDictionary(null)
    await loadDictionaries()
  }

  const handleAddEntry = async () => {
    if (!selectedId) return
    await client.addDictionaryEntry(selectedId, entryForm)
    setEntryForm({
      source_text: '',
      spoken_text: '',
      note: '',
      priority: 0,
      case_sensitive: false,
      is_enabled: true,
    })
    void loadEntries(selectedId, page, search)
  }

  const handleUpdateEntry = async (entryId: number) => {
    if (!selectedId) return
    await client.updateDictionaryEntry(selectedId, entryId, entryForm)
    setEditingEntryId(null)
    void loadEntries(selectedId, page, search)
  }

  const handleEditEntry = (entry: DictionaryEntry) => {
    setEditingEntryId(entry.id)
    setEntryForm({
      source_text: entry.source_text,
      spoken_text: entry.spoken_text,
      note: entry.note || '',
      priority: entry.priority,
      case_sensitive: entry.case_sensitive,
      is_enabled: entry.is_enabled,
    })
  }

  const handleRemoveEntry = async (entryId: number) => {
    if (!selectedId || !window.confirm('Удалить запись?')) return
    await client.deleteDictionaryEntry(selectedId, entryId)
    void loadEntries(selectedId, page, search)
  }

  const handlePreview = async () => {
    if (!selectedId) return
    const result = await client.previewDictionary(selectedId, previewText)
    setPreviewResult(result.processed_text)
  }

  const handleExport = async () => {
    if (!selectedId) return
    const data = await client.exportDictionary(selectedId)
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${data.slug}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    const text = await file.text()
    try {
      const data = JSON.parse(text)
      if (selectedId) {
        if (window.confirm('Импортировать в текущий словарь?')) {
          await client.importIntoDictionary(selectedId, data, 'merge')
          void loadEntries(selectedId, page, search)
        }
      } else {
        await client.importFullDictionary(data, 'merge')
        await loadDictionaries()
      }
    } catch (err) {
      alert('Ошибка при разборе JSON: ' + (err instanceof Error ? err.message : String(err)))
    }

    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  return (
    <div className="page-grid">
      <section className="card">
        <h2>Словари</h2>
        <div className="form-group">
          <label>Активный словарь</label>
          <select
            value={selectedId || ''}
            onChange={(e) => setSelectedId(Number(e.target.value))}
            className="full-width"
            data-testid="dictionary-select"
          >
            <option value="" disabled>Выберите словарь</option>
            {dictionaries.map((dict) => (
              <option key={dict.id} value={dict.id}>
                {dict.name} {dict.is_system ? '(системный)' : ''}
              </option>
            ))}
          </select>
        </div>
        <div className="button-group" style={{ marginTop: '1rem' }}>
          <button className="secondary" onClick={handleCreateDictionary}>Создать новый</button>
          <button className="secondary" onClick={() => fileInputRef.current?.click()}>Импорт JSON</button>
          <input
            type="file"
            ref={fileInputRef}
            style={{ display: 'none' }}
            accept=".json"
            onChange={handleImport}
          />
        </div>

        {selectedDictionary && (
          <div style={{ marginTop: '2rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3>Свойства словаря</h3>
              {!isEditingDict && selectedDictionary.is_editable && (
                <button className="small" onClick={() => setIsEditingDict(true)}>Изменить</button>
              )}
            </div>

            {isEditingDict ? (
              <div className="form">
                <label>Название</label>
                <input value={dictForm.name} onChange={(e) => setDictForm({ ...dictForm, name: e.target.value })} />
                <label>Slug</label>
                <input value={dictForm.slug} onChange={(e) => setDictForm({ ...dictForm, slug: e.target.value })} />
                <label>Описание</label>
                <textarea value={dictForm.description} onChange={(e) => setDictForm({ ...dictForm, description: e.target.value })} />
                <label>Домен</label>
                <select value={dictForm.domain} onChange={(e) => setDictForm({ ...dictForm, domain: e.target.value })}>
                  <option value="general">Общий</option>
                  <option value="technical">Технический</option>
                  <option value="literary">Литературный</option>
                </select>
                <div className="checkbox-group">
                  <input
                    type="checkbox"
                    id="is_default"
                    checked={dictForm.is_default}
                    onChange={(e) => setDictForm({ ...dictForm, is_default: e.target.checked })}
                  />
                  <label htmlFor="is_default">По умолчанию</label>
                </div>
                <div className="button-group">
                  <button onClick={handleUpdateDictionary}>Сохранить</button>
                  <button className="secondary" onClick={() => setIsEditingDict(false)}>Отмена</button>
                </div>
              </div>
            ) : (
              <div className="details-list">
                <div><strong>Slug:</strong> {selectedDictionary.slug}</div>
                <div><strong>Домен:</strong> {selectedDictionary.domain}</div>
                <div><strong>По умолчанию:</strong> {selectedDictionary.is_default ? 'Да' : 'Нет'}</div>
                {selectedDictionary.description && (
                  <div style={{ marginTop: '0.5rem', fontStyle: 'italic' }}>{selectedDictionary.description}</div>
                )}
                <div className="button-group" style={{ marginTop: '1rem' }}>
                  <button className="secondary small" onClick={handleExport}>Экспорт в JSON</button>
                  {selectedDictionary.is_editable && (
                    <button className="danger small" onClick={handleDeleteDictionary}>Удалить словарь</button>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="card wide">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2>Записи словаря</h2>
          <div className="search-box">
            <input
              placeholder="Поиск..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        {selectedDictionary?.is_editable ? (
          <div className="add-entry-form" style={{ backgroundColor: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px', marginBottom: '1rem' }}>
            <h4>{editingEntryId ? 'Редактировать запись' : 'Добавить новую запись'}</h4>
            <div className="grid three">
              <div>
                <label htmlFor="source-text">Слово (source)</label>
                <input
                  id="source-text"
                  value={entryForm.source_text}
                  onChange={(e) => setEntryForm({ ...entryForm, source_text: e.target.value })}
                />
              </div>
              <div>
                <label htmlFor="spoken-text">Как читать (spoken)</label>
                <input
                  id="spoken-text"
                  value={entryForm.spoken_text}
                  onChange={(e) => setEntryForm({ ...entryForm, spoken_text: e.target.value })}
                />
              </div>
              <div>
                <label htmlFor="note">Заметка</label>
                <input
                  id="note"
                  value={entryForm.note}
                  onChange={(e) => setEntryForm({ ...entryForm, note: e.target.value })}
                />
              </div>
            </div>
            <div className="grid three" style={{ marginTop: '0.5rem', alignItems: 'center' }}>
              <div className="checkbox-group">
                <input
                  type="checkbox"
                  id="case_sensitive"
                  checked={entryForm.case_sensitive}
                  onChange={(e) => setEntryForm({ ...entryForm, case_sensitive: e.target.checked })}
                />
                <label htmlFor="case_sensitive">Регистрозависимо</label>
              </div>
              <div>
                <label>Приоритет</label>
                <input
                  type="number"
                  value={entryForm.priority}
                  onChange={(e) => setEntryForm({ ...entryForm, priority: Number(e.target.value) })}
                />
              </div>
              <div className="button-group" style={{ justifyContent: 'flex-end' }}>
                {editingEntryId ? (
                  <>
                    <button onClick={() => handleUpdateEntry(editingEntryId)}>Обновить</button>
                    <button className="secondary" onClick={() => {
                      setEditingEntryId(null)
                      setEntryForm({ source_text: '', spoken_text: '', note: '', priority: 0, case_sensitive: false, is_enabled: true })
                    }}>Отмена</button>
                  </>
                ) : (
                  <button onClick={handleAddEntry}>Добавить</button>
                )}
              </div>
            </div>
          </div>
        ) : selectedId && (
          <div className="info-box" style={{ marginBottom: '1rem' }}>
            Этот словарь системный и не может быть изменен напрямую.
          </div>
        )}

        <div className="table-container">
          <table className="full-width">
            <thead>
              <tr>
                <th>Слово</th>
                <th>Произношение</th>
                <th>Приоритет</th>
                <th>Заметка</th>
                <th style={{ width: '120px' }}>Действия</th>
              </tr>
            </thead>
            <tbody>
              {loadingEntries ? (
                <tr><td colSpan={5} style={{ textAlign: 'center' }}>Загрузка...</td></tr>
              ) : entries.length === 0 ? (
                <tr><td colSpan={5} style={{ textAlign: 'center' }}>Записей не найдено</td></tr>
              ) : (
                entries.map((entry) => (
                  <tr key={entry.id} className={!entry.is_enabled ? 'dimmed' : ''}>
                    <td>
                      <span className={entry.case_sensitive ? 'tag-cs' : ''}>{entry.source_text}</span>
                    </td>
                    <td>{entry.spoken_text}</td>
                    <td>{entry.priority}</td>
                    <td><small>{entry.note}</small></td>
                    <td>
                      <div className="button-group compact">
                        {selectedDictionary?.is_editable && (
                          <>
                            <button className="small secondary" onClick={() => handleEditEntry(entry)}>✎</button>
                            <button className="small danger" onClick={() => handleRemoveEntry(entry.id)}>×</button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {totalEntries > 20 && (
          <div className="pagination" style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem', justifyContent: 'center' }}>
            <button
              className="small secondary"
              disabled={page === 1}
              onClick={() => setPage(p => p - 1)}
            >
              Назад
            </button>
            <span style={{ alignSelf: 'center' }}>Страница {page} из {Math.ceil(totalEntries / 20)}</span>
            <button
              className="small secondary"
              disabled={page >= Math.ceil(totalEntries / 20)}
              onClick={() => setPage(p => p + 1)}
            >
              Вперед
            </button>
          </div>
        )}
      </section>

      <section className="card wide">
        <h2>Проверка произношения</h2>
        <div className="form">
          <textarea
            rows={4}
            value={previewText}
            onChange={(e) => setPreviewText(e.target.value)}
            placeholder="Введите текст для проверки..."
          />
          <button onClick={handlePreview} disabled={!selectedId}>Проверить препроцессинг</button>
        </div>
        {previewResult && (
          <div className="preview-box" style={{ marginTop: '1rem', backgroundColor: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px' }}>
            <strong>Результат:</strong>
            <p style={{ marginTop: '0.5rem', whiteSpace: 'pre-wrap' }}>{previewResult}</p>
          </div>
        )}
      </section>

      <style>{`
        .details-list div { margin-bottom: 0.25rem; }
        .grid.three { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; }
        .full-width { width: 100%; }
        .compact { gap: 0.25rem; }
        .dimmed { opacity: 0.5; }
        .tag-cs { border-bottom: 2px dotted var(--primary); }
        .table-container { overflow-x: auto; margin-top: 1rem; }
        table { border-collapse: collapse; }
        th, td { text-align: left; padding: 0.75rem; border-bottom: 1px solid var(--border-color); }
        th { background-color: var(--bg-secondary); }
        .info-box { padding: 0.75rem; background-color: #e3f2fd; color: #1976d2; border-radius: 4px; }
      `}</style>
    </div>
  )
}
