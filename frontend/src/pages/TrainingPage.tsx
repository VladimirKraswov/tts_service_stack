import { useEffect, useMemo, useState } from 'react'
import { client, type TrainingDataset, type TrainingJob } from '../api/client'

export function TrainingPage() {
  const [datasets, setDatasets] = useState<TrainingDataset[]>([])
  const [jobs, setJobs] = useState<TrainingJob[]>([])
  const [name, setName] = useState('Ivan voice dataset')
  const [speakerName, setSpeakerName] = useState('Ivan')
  const [language, setLanguage] = useState('ru')
  const [note, setNote] = useState('16k+ wav/flac + transcripts recommended.')
  const [file, setFile] = useState<File | null>(null)
  const [datasetId, setDatasetId] = useState<number | undefined>(undefined)
  const [baseModel, setBaseModel] = useState('Qwen/Qwen3-TTS-12Hz-1.7B-Base')
  const [outputName, setOutputName] = useState('ivan-tech-voice')

  const refresh = async () => {
    const [datasetRows, jobRows] = await Promise.all([client.listDatasets(), client.listJobs()])
    setDatasets(datasetRows)
    setJobs(jobRows)
    setDatasetId((current) => current ?? datasetRows[0]?.id)
  }

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => void refresh(), 5000)
    return () => window.clearInterval(timer)
  }, [])

  const upload = async () => {
    if (!file) return
    const formData = new FormData()
    formData.append('name', name)
    formData.append('speaker_name', speakerName)
    formData.append('language', language)
    formData.append('note', note)
    formData.append('file', file)
    await client.uploadDataset(formData)
    setFile(null)
    await refresh()
  }

  const createJob = async () => {
    if (!datasetId) return
    await client.createTrainingJob({ dataset_id: datasetId, base_model: baseModel, output_name: outputName })
    await refresh()
  }

  return (
    <div className="page-grid">
      <section className="card wide">
        <h2>Инструкция по fine-tuning</h2>
        <ol>
          <li>Подготовьте архив датасета с аудио и транскриптами.</li>
          <li>Загрузите датасет через форму ниже.</li>
          <li>Создайте training job с выбранной base model.</li>
          <li>Наблюдайте статус и артефакты в таблице jobs.</li>
          <li>Замените trainer stub на реальный recipe для Qwen/CosyVoice.</li>
        </ol>
      </section>

      <section className="card">
        <h2>Добавить датасет</h2>
        <label>Название</label>
        <input value={name} onChange={(e) => setName(e.target.value)} />
        <label>Имя спикера</label>
        <input value={speakerName} onChange={(e) => setSpeakerName(e.target.value)} />
        <label>Язык</label>
        <input value={language} onChange={(e) => setLanguage(e.target.value)} />
        <label>Комментарий</label>
        <textarea rows={4} value={note} onChange={(e) => setNote(e.target.value)} />
        <label>Файл архива</label>
        <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <button onClick={upload}>Загрузить датасет</button>
      </section>

      <section className="card">
        <h2>Запустить обучение</h2>
        <label>Датасет</label>
        <select value={datasetId} onChange={(e) => setDatasetId(Number(e.target.value))}>
          {datasets.map((dataset) => (
            <option key={dataset.id} value={dataset.id}>{dataset.name}</option>
          ))}
        </select>
        <label>Base model</label>
        <input value={baseModel} onChange={(e) => setBaseModel(e.target.value)} />
        <label>Имя результата</label>
        <input value={outputName} onChange={(e) => setOutputName(e.target.value)} />
        <button onClick={createJob}>Создать training job</button>
      </section>

      <section className="card wide">
        <h2>Datasets</h2>
        <div className="table-like">
          {datasets.map((dataset) => (
            <div className="table-row" key={dataset.id}>
              <span>#{dataset.id}</span>
              <span>{dataset.name}</span>
              <span>{dataset.speaker_name}</span>
              <span>{dataset.language}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="card wide">
        <h2>Training jobs</h2>
        <div className="jobs-list">
          {jobs.map((job) => (
            <article className="job-card" key={job.id}>
              <div className="row space-between">
                <strong>Job #{job.id}</strong>
                <span className={`badge badge-${job.status}`}>{job.status}</span>
              </div>
              <p>Dataset: {job.dataset_id}</p>
              <p>Model: {job.base_model}</p>
              <p>Output: {job.output_name}</p>
              <p>Progress: {job.progress}%</p>
              <pre>{job.log}</pre>
              {job.artifact_path && <p>Artifacts: {job.artifact_path}</p>}
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}
