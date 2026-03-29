import { useEffect, useState } from 'react'
import { client, type Dictionary } from '../api/client'

export function DictionaryPage() {
  const [dictionaries, setDictionaries] = useState<Dictionary[]>([])
  const [selectedId, setSelectedId] = useState<number | undefined>(undefined)
  const [newName, setNewName] = useState('Team Tech')
  const [newSlug, setNewSlug] = useState('team-tech')
  const [sourceText, setSourceText] = useState('WebSocket')
  const [spokenText, setSpokenText] = useState('Веб сокет')
  const [previewText, setPreviewText] = useState('Наш сервис использует WebSocket и FastAPI для live режима.')
  const [previewResult, setPreviewResult] = useState('')

  const load = async () => {
    const rows = await client.listDictionaries()
    setDictionaries(rows)
    setSelectedId((current) => current ?? rows[0]?.id)
  }

  useEffect(() => {
    void load()
  }, [])

  const selected = dictionaries.find((item) => item.id === selectedId)

  const createDictionary = async () => {
    await client.createDictionary({ name: newName, slug: newSlug })
    await load()
  }

  const addEntry = async () => {
    if (!selectedId) return
    await client.addDictionaryEntry(selectedId, { source_text: sourceText, spoken_text: spokenText })
    await load()
  }

  const removeEntry = async (entryId: number) => {
    if (!selectedId) return
    await client.deleteDictionaryEntry(selectedId, entryId)
    await load()
  }

  const preview = async () => {
    if (!selectedId) return
    const result = await client.previewDictionary(selectedId, previewText)
    setPreviewResult(result.processed_text)
  }

  return (
    <div className="page-grid">
      <section className="card">
        <h2>Создать словарь</h2>
        <label>Название</label>
        <input value={newName} onChange={(e) => setNewName(e.target.value)} />
        <label>Slug</label>
        <input value={newSlug} onChange={(e) => setNewSlug(e.target.value)} />
        <button onClick={createDictionary}>Создать</button>
      </section>

      <section className="card wide">
        <h2>Работа со словарем</h2>
        <label>Активный словарь</label>
        <select value={selectedId} onChange={(e) => setSelectedId(Number(e.target.value))}>
          {dictionaries.map((dictionary) => (
            <option key={dictionary.id} value={dictionary.id}>{dictionary.name}</option>
          ))}
        </select>
        <div className="grid two">
          <div>
            <label>Слово</label>
            <input value={sourceText} onChange={(e) => setSourceText(e.target.value)} />
          </div>
          <div>
            <label>Как читать</label>
            <input value={spokenText} onChange={(e) => setSpokenText(e.target.value)} />
          </div>
        </div>
        <button onClick={addEntry}>Добавить запись</button>

        <h3>Записи словаря</h3>
        <div className="table-like">
          {selected?.entries.map((entry) => (
            <div className="table-row" key={entry.id}>
              <span>{entry.source_text}</span>
              <span>{entry.spoken_text}</span>
              <button onClick={() => removeEntry(entry.id)}>Удалить</button>
            </div>
          ))}
        </div>
      </section>

      <section className="card wide">
        <h2>Быстрая проверка произношения</h2>
        <textarea rows={5} value={previewText} onChange={(e) => setPreviewText(e.target.value)} />
        <button onClick={preview}>Проверить</button>
        {previewResult && (
          <div className="preview-box">
            <strong>Результат препроцессинга</strong>
            <p>{previewResult}</p>
          </div>
        )}
      </section>
    </div>
  )
}
