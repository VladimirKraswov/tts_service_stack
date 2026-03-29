import { useEffect, useMemo, useRef, useState } from 'react'
import { client, type Dictionary, type Voice } from '../api/client'
import { AudioPlayerStatus, useAudioPlayer } from '../components/AudioPlayer'
import { useToast } from '../components/Toast'

function randomSessionId() {
  return `session-${Math.random().toString(36).slice(2, 10)}`
}

export function TestingPage() {
  const { show } = useToast()
  const { addChunk, stop: stopAudio, isPlaying, queueSize } = useAudioPlayer()
  const [sessionId, setSessionId] = useState(randomSessionId())
  const [text, setText] = useState('В Python функция __init__ вызывается при создании объекта. В React часто используют useEffect.')
  const [dictionaries, setDictionaries] = useState<Dictionary[]>([])
  const [voices, setVoices] = useState<Voice[]>([])
  const [dictionaryId, setDictionaryId] = useState<number | undefined>(undefined)
  const [voiceId, setVoiceId] = useState<string | undefined>(undefined)
  const [loraName, setLoraName] = useState<string | undefined>(undefined)
  const [events, setEvents] = useState<string[]>([])
  const [previewUrl, setPreviewUrl] = useState<string>('')
  const [previewProcessedText, setPreviewProcessedText] = useState<string>('')
  const [quickSource, setQuickSource] = useState('FastAPI')
  const [quickSpoken, setQuickSpoken] = useState('Фаст Эй Пи Ай')
  const [status, setStatus] = useState('disconnected')
  const [isEnqueuing, setIsEnqueuing] = useState(false)
  const [isPreviewing, setIsPreviewing] = useState(false)
  const websocketRef = useRef<WebSocket | null>(null)

  const voiceOptions = useMemo(() => voices.filter((voice) => voice.kind === 'voice'), [voices])
  const loraOptions = useMemo(() => voices.filter((voice) => voice.kind === 'lora'), [voices])

  useEffect(() => {
    refreshData()
    return () => disconnect()
  }, [])

  const refreshData = async () => {
    const [dicts, voiceRows] = await Promise.all([client.listDictionaries(), client.listVoices()])
    setDictionaries(dicts)
    setVoices(voiceRows)
    setDictionaryId((current) => current ?? dicts.find((item) => item.is_default)?.id ?? dicts[0]?.id)
    setVoiceId((current) => current ?? voiceRows.find((item) => item.kind === 'voice')?.name)
    setLoraName((current) => current ?? voiceRows.find((item) => item.kind === 'lora')?.name)
  }

  const log = (message: string) => setEvents((prev) => [message, ...prev].slice(0, 60))

  const connect = () => {
    if (websocketRef.current) return
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${protocol}://${window.location.host}/api/v1/live/ws/${sessionId}`)
    websocketRef.current = ws
    setStatus('connecting')
    ws.onopen = () => {
      setStatus('connected')
      log(`WS connected: ${sessionId}`)
    }
    ws.onclose = () => {
      setStatus('disconnected')
      websocketRef.current = null
      log('WS disconnected')
    }
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data)
      log(`${message.type}: ${JSON.stringify(message)}`)
      if (message.type === 'audio.chunk' && message.audio_b64) {
        void addChunk(message)
      } else if (message.type === 'job.error') {
        show(message.error || 'Ошибка синтеза', 'error')
      }
    }
  }

  const disconnect = () => {
    websocketRef.current?.close()
    websocketRef.current = null
    setStatus('disconnected')
    stopAudio()
  }

  const sendViaRest = async () => {
    if (isEnqueuing) return
    setIsEnqueuing(true)
    try {
      await client.enqueueLive({
        session_id: sessionId,
        text,
        dictionary_id: dictionaryId,
        voice_id: voiceId,
        lora_name: loraName,
        language: 'ru',
      })
      log('REST enqueue success')
    } catch (e) {
      show('Ошибка enqueue через API', 'error')
    } finally {
      setIsEnqueuing(false)
    }
  }

  const sendViaWs = () => {
    if (!websocketRef.current || websocketRef.current.readyState !== WebSocket.OPEN) {
      show('WebSocket не подключен', 'info')
      return
    }
    websocketRef.current.send(
      JSON.stringify({
        type: 'enqueue_text',
        text,
        dictionary_id: dictionaryId,
        voice_id: voiceId,
        lora_name: loraName,
        language: 'ru',
      }),
    )
    log('WS enqueue success')
  }

  const quickAddToDictionary = async () => {
    if (!dictionaryId) return
    try {
      await client.addDictionaryEntry(dictionaryId, { source_text: quickSource, spoken_text: quickSpoken })
      await refreshData()
      show('Запись добавлена в словарь', 'success')
      log(`Added entry ${quickSource} -> ${quickSpoken}`)
    } catch (e) {
      show('Ошибка добавления в словарь', 'error')
    }
  }

  const preview = async () => {
    if (isPreviewing) return
    setIsPreviewing(true)
    try {
      const result = await client.previewLive({ text, dictionary_id: dictionaryId, voice_id: voiceId, lora_name: loraName })
      const url = URL.createObjectURL(result.blob)
      setPreviewUrl(url)
      setPreviewProcessedText(result.processedText)
    } catch (e) {
      show('Ошибка превью', 'error')
    } finally {
      setIsPreviewing(false)
    }
  }

  return (
    <div className="page-grid">
      <section className="card wide">
        <div className="row space-between">
          <h2>Модуль тестирования</h2>
          <AudioPlayerStatus isPlaying={isPlaying} queueSize={queueSize} />
        </div>

        <div className="grid two">
          <div>
            <label>Session ID</label>
            <div className="row">
              <input value={sessionId} onChange={(e) => setSessionId(e.target.value)} />
              <button onClick={() => setSessionId(randomSessionId())}>New</button>
            </div>
          </div>
          <div>
            <label>Live Connection</label>
            <div className="row">
              <button onClick={connect} disabled={status === 'connected'}>Connect</button>
              <button onClick={disconnect} disabled={status === 'disconnected'}>Disconnect</button>
              <span className={`badge badge-${status}`}>{status}</span>
            </div>
          </div>
        </div>

        <label>Текст / буфер</label>
        <textarea rows={8} value={text} onChange={(e) => setText(e.target.value)} />

        <div className="grid two">
          <div className="card" style={{ background: 'rgba(255,255,255,0.02)', padding: '15px' }}>
            <label>Словарь</label>
            <select value={dictionaryId} onChange={(e) => setDictionaryId(Number(e.target.value))}>
              {dictionaries.map((dictionary) => (
                <option key={dictionary.id} value={dictionary.id}>{dictionary.name}</option>
              ))}
            </select>
          </div>
          <div className="card" style={{ background: 'rgba(255,255,255,0.02)', padding: '15px' }}>
            <div className="grid two">
              <div>
                <label>Голос</label>
                <select value={voiceId} onChange={(e) => setVoiceId(e.target.value)}>
                  {voiceOptions.map((voice) => (
                    <option key={voice.id} value={voice.name}>{voice.display_name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label>LoRA / Стиль</label>
                <select value={loraName} onChange={(e) => setLoraName(e.target.value)}>
                  {loraOptions.map((voice) => (
                    <option key={voice.id} value={voice.name}>{voice.display_name}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        </div>

        <div className="row wrap" style={{ marginTop: '20px' }}>
          <button onClick={sendViaRest} disabled={isEnqueuing}>Enqueue (REST)</button>
          <button onClick={sendViaWs}>Enqueue (WebSocket)</button>
          <button onClick={preview} disabled={isPreviewing}>Preview (WAV)</button>
          {isPlaying && <button onClick={stopAudio} style={{ background: '#991b1b' }}>Stop Audio</button>}
        </div>
        {previewProcessedText && (
          <div className="preview-box">
            <strong>Processed text:</strong>
            <p>{previewProcessedText}</p>
          </div>
        )}
        {previewUrl && <audio controls src={previewUrl} />}
      </section>

      <section className="card">
        <h2>Быстро добавить слово в словарь</h2>
        <label>Исходная форма</label>
        <input value={quickSource} onChange={(e) => setQuickSource(e.target.value)} />
        <label>Как читать</label>
        <input value={quickSpoken} onChange={(e) => setQuickSpoken(e.target.value)} />
        <button onClick={quickAddToDictionary}>Добавить в активный словарь</button>
      </section>

      <section className="card">
        <h2>Лог live событий</h2>
        <div className="log-box">
          {events.map((eventLine, index) => (
            <div key={`${eventLine}-${index}`}>{eventLine}</div>
          ))}
        </div>
      </section>
    </div>
  )
}
