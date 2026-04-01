import { useEffect, useMemo, useRef, useState } from 'react'
import { client, type Dictionary, type SynthesisJob, type Voice } from '../api/client'
import { useToast } from '../components/Toast'

function getErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message
  return 'Неизвестная ошибка'
}

const orderedStages = ['uploaded', 'preprocessing', 'synthesizing', 'encoding_mp3', 'completed']

function stageLabel(stage: string): string {
  switch (stage) {
    case 'uploaded':
      return 'Текст загружен'
    case 'preprocessing':
      return 'Обработка текста'
    case 'synthesizing':
      return 'Модель превращает текст в голос'
    case 'encoding_mp3':
      return 'Конвертация в MP3'
    case 'completed':
      return 'Готов к загрузке'
    case 'failed':
      return 'Ошибка'
    default:
      return stage
  }
}

function getStageIndex(stage: string): number {
  return orderedStages.indexOf(stage)
}

function pickDefaultDictionaryId(
  profile: 'literary' | 'technical',
  dictionaries: Dictionary[],
): number | undefined {
  if (profile === 'literary') {
    return (
      dictionaries.find((item) => item.slug === 'default-literary')?.id ??
      dictionaries.find((item) => item.is_default)?.id ??
      dictionaries[0]?.id
    )
  }

  return (
    dictionaries.find((item) => item.slug === 'default-tech')?.id ??
    dictionaries.find((item) => item.is_default)?.id ??
    dictionaries[0]?.id
  )
}

function pickDefaultLoraName(
  profile: 'literary' | 'technical',
  voices: Voice[],
): string {
  const loras = voices.filter((voice) => voice.kind === 'lora')

  if (profile === 'literary') {
    return (
      loras.find((voice) => voice.name === 'calm-lora-v1')?.name ??
      loras.find((voice) => voice.name === 'energetic-lora-v1')?.name ??
      loras[0]?.name ??
      ''
    )
  }

  return (
    loras.find((voice) => voice.name === 'tech-lora-v1')?.name ??
    loras[0]?.name ??
    ''
  )
}

function pickDefaultReadingMode(
  profile: 'literary' | 'technical',
): 'narration' | 'expressive' | 'dialogue' | 'technical' {
  return profile === 'technical' ? 'technical' : 'narration'
}

function pickDefaultParagraphPause(profile: 'literary' | 'technical'): number {
  return profile === 'technical' ? 350 : 700
}

export function SynthesisPage() {
  const { show } = useToast()

  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const [file, setFile] = useState<File | null>(null)
  const [voices, setVoices] = useState<Voice[]>([])
  const [dictionaries, setDictionaries] = useState<Dictionary[]>([])
  const [jobs, setJobs] = useState<SynthesisJob[]>([])

  const [voiceId, setVoiceId] = useState<string>('')
  const [loraName, setLoraName] = useState<string>('')
  const [dictionaryId, setDictionaryId] = useState<number | undefined>(undefined)
  const [preprocessProfile, setPreprocessProfile] = useState<'literary' | 'technical'>('literary')
  const [readingMode, setReadingMode] = useState<'narration' | 'expressive' | 'dialogue' | 'technical'>('narration')
  const [speakingRate, setSpeakingRate] = useState<'slow' | 'normal' | 'fast'>('normal')
  const [paragraphPauseMs, setParagraphPauseMs] = useState(700)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const voiceOptions = useMemo(() => voices.filter((voice) => voice.kind === 'voice'), [voices])
  const loraOptions = useMemo(() => voices.filter((voice) => voice.kind === 'lora'), [voices])

  const load = async () => {
    const [voiceRows, dictionaryRows, synthesisRows] = await Promise.all([
      client.listVoices(),
      client.listDictionaries(),
      client.listSynthesisJobs(),
    ])

    setVoices(voiceRows)
    setDictionaries(dictionaryRows)
    setJobs(synthesisRows)

    setVoiceId((current) => current || voiceRows.find((item) => item.kind === 'voice')?.name || '')
    setLoraName((current) => current || pickDefaultLoraName(preprocessProfile, voiceRows))
    setDictionaryId((current) => current ?? pickDefaultDictionaryId(preprocessProfile, dictionaryRows))
  }

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(), 2000)
    return () => window.clearInterval(timer)
  }, [])

  const handleProfileChange = (nextProfile: 'literary' | 'technical') => {
    setPreprocessProfile(nextProfile)
    setDictionaryId(pickDefaultDictionaryId(nextProfile, dictionaries))
    setLoraName(pickDefaultLoraName(nextProfile, voices))
    setReadingMode(pickDefaultReadingMode(nextProfile))
    setParagraphPauseMs(pickDefaultParagraphPause(nextProfile))
  }

  const clearSelectedFile = () => {
    setFile(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const submit = async () => {
    if (!file) {
      show('Сначала выбери текстовый файл', 'info')
      return
    }

    setIsSubmitting(true)
    try {
      await client.createSynthesisJob({
        file,
        voice_id: voiceId || undefined,
        lora_name: loraName || undefined,
        language: 'ru',
        preprocess_profile: preprocessProfile,
        reading_mode: readingMode,
        dictionary_id: dictionaryId,
        speaking_rate: speakingRate,
        paragraph_pause_ms: paragraphPauseMs,
      })

      await load()
      show('Задача синтеза создана', 'success')
    } catch (error) {
      show(getErrorMessage(error), 'error')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="page-grid">
      <section className="card wide">
        <h2>Text → MP3</h2>

        <div className="preview-box">
          <strong>Пользовательский сценарий</strong>
          <ol>
            <li>Загрузи текстовый файл</li>
            <li>Выбери профиль обработки, голос и стиль</li>
            <li>Запусти синтез</li>
            <li>Следи за этапами: загрузка, обработка, голос, MP3, скачивание</li>
          </ol>
        </div>

        <label>Файл текста (.txt, .md)</label>
        <input
          ref={fileInputRef}
          type="file"
          accept=".txt,.md,text/plain,text/markdown"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />

        {file && (
          <div className="preview-box">
            <strong>Выбранный файл</strong>
            <p>{file.name}</p>
            <div className="row wrap">
              <button type="button" onClick={clearSelectedFile}>
                Очистить файл
              </button>
            </div>
          </div>
        )}

        <div className="grid two">
          <div>
            <label>Голос</label>
            <select value={voiceId} onChange={(e) => setVoiceId(e.target.value)}>
              {voiceOptions.map((voice) => (
                <option key={voice.id} value={voice.name}>
                  {voice.display_name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label>Стиль</label>
            <select value={loraName} onChange={(e) => setLoraName(e.target.value)}>
              {loraOptions.map((voice) => (
                <option key={voice.id} value={voice.name}>
                  {voice.display_name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid two">
          <div>
            <label>Профиль препроцессинга</label>
            <select
              value={preprocessProfile}
              onChange={(e) => handleProfileChange(e.target.value as 'literary' | 'technical')}
            >
              <option value="literary">Художественная литература</option>
              <option value="technical">Технический текст</option>
            </select>
          </div>

          <div>
            <label>Словарь</label>
            <select
              value={dictionaryId ?? ''}
              onChange={(e) => setDictionaryId(e.target.value ? Number(e.target.value) : undefined)}
            >
              {dictionaries.map((dictionary) => (
                <option key={dictionary.id} value={dictionary.id}>
                  {dictionary.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid two">
          <div>
            <label>Режим чтения</label>
            <select
              value={readingMode}
              onChange={(e) => setReadingMode(e.target.value as 'narration' | 'expressive' | 'dialogue' | 'technical')}
            >
              <option value="narration">Ровное повествование</option>
              <option value="expressive">Выразительное чтение</option>
              <option value="dialogue">Акцент на диалогах</option>
              <option value="technical">Технический диктор</option>
            </select>
          </div>

          <div>
            <label>Темп речи</label>
            <select
              value={speakingRate}
              onChange={(e) => setSpeakingRate(e.target.value as 'slow' | 'normal' | 'fast')}
            >
              <option value="slow">Медленный</option>
              <option value="normal">Нормальный</option>
              <option value="fast">Быстрее среднего</option>
            </select>
          </div>
        </div>

        <label>Пауза между фрагментами, мс</label>
        <input
          type="number"
          min={0}
          max={5000}
          value={paragraphPauseMs}
          onChange={(e) => setParagraphPauseMs(Number(e.target.value) || 0)}
        />

        <div className="row wrap" style={{ marginTop: '16px' }}>
          <button onClick={() => void submit()} disabled={!file || isSubmitting}>
            {isSubmitting ? 'Создание...' : 'Запустить синтез'}
          </button>
        </div>
      </section>

      <section className="card wide">
        <h2>Задачи синтеза</h2>

        {jobs.length === 0 && <p>Пока нет задач синтеза.</p>}

        <div className="jobs-list">
          {jobs.map((job) => {
            const activeStageIndex = getStageIndex(job.stage)

            return (
              <article className="job-card" key={job.id}>
                <div className="row space-between">
                  <strong>{job.source_name}</strong>
                  <span className={`badge badge-${job.status}`}>{stageLabel(job.stage)}</span>
                </div>

                <p>Прогресс: {job.progress}%</p>
                <p>Голос: {job.voice_id || 'default'}</p>
                <p>Стиль: {job.lora_name || 'default'}</p>
                <p>Профиль: {job.preprocess_profile}</p>
                <p>Режим чтения: {job.reading_mode}</p>
                <p>Темп: {job.speaking_rate || 'normal'}</p>

                <div className="preview-box">
                  <strong>Этапы</strong>
                  <ol>
                    {orderedStages.map((stage, index) => {
                      const completed = job.status === 'completed' && index <= activeStageIndex
                      const active = job.stage === stage

                      return (
                        <li key={stage}>
                          <strong>{stageLabel(stage)}</strong>
                          {' — '}
                          {completed ? 'готово' : active ? 'в работе' : job.status === 'failed' ? 'прервано' : 'ожидание'}
                        </li>
                      )
                    })}
                  </ol>
                </div>

                {job.log && <pre>{job.log}</pre>}

                {job.error_message && <p style={{ color: '#ef4444' }}>{job.error_message}</p>}

                {job.status === 'completed' && (
                  <div className="row wrap">
                    <a href={`/api/v1/synthesis/${job.id}/download`} target="_blank" rel="noreferrer">
                      Скачать MP3
                    </a>
                  </div>
                )}
              </article>
            )
          })}
        </div>
      </section>
    </div>
  )
}