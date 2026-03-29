import { useEffect, useMemo, useRef, useState } from 'react'
import { client, type Dictionary, type Voice } from '../api/client'
import { AudioPlayerStatus, useAudioPlayer } from '../components/AudioPlayer'
import { useToast } from '../components/Toast'

function randomSessionId() {
  return `session-${Math.random().toString(36).slice(2, 10)}`
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message
  return 'Неизвестная ошибка'
}

export function TestingPage() {
  const { show } = useToast()
  const { addChunk, stop: stopAudio, isPlaying, queueSize, prepare } = useAudioPlayer()

  const [sessionId, setSessionId] = useState(randomSessionId())
  const [dictionaries, setDictionaries] = useState<Dictionary[]>([])
  const [voices, setVoices] = useState<Voice[]>([])
  const [dictionaryId, setDictionaryId] = useState<number | undefined>(undefined)
  const [voiceId, setVoiceId] = useState<string | undefined>(undefined)
  const [loraName, setLoraName] = useState<string | undefined>(undefined)

  const [previewText, setPreviewText] = useState('В Python функция __init__ вызывается при создании объекта. В React часто используют useEffect.')
  const [previewUrl, setPreviewUrl] = useState('')
  const [previewProcessedText, setPreviewProcessedText] = useState('')
  const [isPreviewing, setIsPreviewing] = useState(false)

  const [liveDraft, setLiveDraft] = useState('Это live режим. Текст можно подавать в буфер порциями.')
  const [liveStatus, setLiveStatus] = useState('disconnected')
  const [pendingText, setPendingText] = useState('')
  const [pendingChars, setPendingChars] = useState(0)
  const [events, setEvents] = useState<string[]>([])

  const websocketRef = useRef<WebSocket | null>(null)
  const previewAudioRef = useRef<HTMLAudioElement | null>(null)

  const voiceOptions = useMemo(() => voices.filter((voice) => voice.kind === 'voice'), [voices])
  const loraOptions = useMemo(() => voices.filter((voice) => voice.kind === 'lora'), [voices])

  const log = (message: string) => setEvents((prev) => [message, ...prev].slice(0, 80))

  const refreshData = async () => {
    const [dicts, voiceRows] = await Promise.all([client.listDictionaries(), client.listVoices()])
    setDictionaries(dicts)
    setVoices(voiceRows)
    setDictionaryId((current) => current ?? dicts.find((item) => item.is_default)?.id ?? dicts[0]?.id)
    setVoiceId((current) => current ?? voiceRows.find((item) => item.kind === 'voice')?.name)
    setLoraName((current) => current ?? voiceRows.find((item) => item.kind === 'lora')?.name)
  }

  useEffect(() => {
    void refreshData()
    return () => {
      disconnect()
      if (previewUrl) URL.revokeObjectURL(previewUrl)
    }
  }, [])

  const connect = async () => {
    if (websocketRef.current) return

    try {
      await prepare()
    } catch (error) {
      show(getErrorMessage(error), 'error')
      return
    }

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${protocol}://${window.location.host}/api/v1/live/ws/${sessionId}`)
    websocketRef.current = ws
    setLiveStatus('connecting')

    ws.onopen = () => {
      setLiveStatus('connected')
      log(`WS connected: ${sessionId}`)
    }

    ws.onclose = () => {
      setLiveStatus('disconnected')
      websocketRef.current = null
      log('WS disconnected')
    }

    ws.onerror = () => {
      log('WS error')
    }

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data)
      log(`${message.type}: ${JSON.stringify(message)}`)

      if (message.type === 'buffer.updated') {
        setPendingText(message.pending_text || '')
        setPendingChars(Number(message.pending_chars || 0))
      } else if (message.type === 'audio.chunk' && message.audio_b64) {
        void addChunk(message).catch((error) => {
          show(getErrorMessage(error), 'error')
        })
      } else if (message.type === 'job.error') {
        show(message.error || 'Ошибка live synthesis', 'error')
      }
    }
  }

  const disconnect = () => {
    websocketRef.current?.close()
    websocketRef.current = null
    setLiveStatus('disconnected')
    setPendingText('')
    setPendingChars(0)
    stopAudio()
  }

  const sendLive = async (flush: boolean) => {
    if (!websocketRef.current || websocketRef.current.readyState !== WebSocket.OPEN) {
      show('Сначала подключи WebSocket', 'info')
      return
    }

    try {
      await prepare()
      websocketRef.current.send(
        JSON.stringify({
          type: 'append_text',
          text: liveDraft,
          flush,
          dictionary_id: dictionaryId,
          voice_id: voiceId,
          lora_name: loraName,
          language: 'ru',
        }),
      )
      log(flush ? 'append_text + flush sent' : 'append_text sent')
    } catch (error) {
      show(getErrorMessage(error), 'error')
    }
  }

  const speakOnce = async () => {
    if (!websocketRef.current || websocketRef.current.readyState !== WebSocket.OPEN) {
      show('Сначала подключи WebSocket', 'info')
      return
    }

    try {
      await prepare()
      websocketRef.current.send(
        JSON.stringify({
          type: 'enqueue_text',
          text: liveDraft,
          dictionary_id: dictionaryId,
          voice_id: voiceId,
          lora_name: loraName,
          language: 'ru',
        }),
      )
      log('enqueue_text sent')
    } catch (error) {
      show(getErrorMessage(error), 'error')
    }
  }

  const flushBuffer = () => {
    if (!websocketRef.current || websocketRef.current.readyState !== WebSocket.OPEN) {
      show('Сначала подключи WebSocket', 'info')
      return
    }
    websocketRef.current.send(JSON.stringify({ type: 'flush' }))
  }

  const clearBuffer = () => {
    if (!websocketRef.current || websocketRef.current.readyState !== WebSocket.OPEN) {
      show('Сначала подключи WebSocket', 'info')
      return
    }
    websocketRef.current.send(JSON.stringify({ type: 'clear_buffer' }))
  }

  const preview = async () => {
    if (isPreviewing) return
    setIsPreviewing(true)

    try {
      await prepare()
      const result = await client.previewLive({
        text: previewText,
        dictionary_id: dictionaryId,
        voice_id: voiceId,
        lora_name: loraName,
        language: 'ru',
      })

      if (previewUrl) URL.revokeObjectURL(previewUrl)

      const url = URL.createObjectURL(result.blob)
      setPreviewUrl(url)
      setPreviewProcessedText(result.processedText)

      window.setTimeout(() => {
        void previewAudioRef.current?.play().catch(() => {})
      }, 0)
    } catch (error) {
      show(getErrorMessage(error), 'error')
    } finally {
      setIsPreviewing(false)
    }
  }

  return (
    <div className="page-grid">
      <section className="card wide">
        <div className="row space-between">
          <h2>Общие настройки</h2>
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
              <button onClick={() => void connect()} disabled={liveStatus === 'connected'}>
                Connect
              </button>
              <button onClick={disconnect} disabled={liveStatus === 'disconnected'}>
                Disconnect
              </button>
              <span className={`badge badge-${liveStatus}`}>{liveStatus}</span>
            </div>
          </div>
        </div>

        <div className="grid two">
          <div>
            <label>Словарь</label>
            <select value={dictionaryId} onChange={(e) => setDictionaryId(Number(e.target.value))}>
              {dictionaries.map((dictionary) => (
                <option key={dictionary.id} value={dictionary.id}>
                  {dictionary.name}
                </option>
              ))}
            </select>
          </div>

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
        </div>
      </section>

      <section className="card wide">
        <h2>Preview mode — качественный оффлайн синтез</h2>
        <textarea rows={6} value={previewText} onChange={(e) => setPreviewText(e.target.value)} />
        <div className="row wrap" style={{ marginTop: '16px' }}>
          <button onClick={() => void preview()} disabled={isPreviewing}>
            Preview (WAV)
          </button>
        </div>

        {previewProcessedText && (
          <div className="preview-box">
            <strong>Processed text:</strong>
            <p>{previewProcessedText}</p>
          </div>
        )}

        {previewUrl && <audio ref={previewAudioRef} controls src={previewUrl} />}
      </section>

      <section className="card wide">
        <h2>Live mode — буфер, инкрементальная подача текста</h2>
        <textarea rows={6} value={liveDraft} onChange={(e) => setLiveDraft(e.target.value)} />
        <div className="row wrap" style={{ marginTop: '16px' }}>
          <button onClick={() => void sendLive(false)}>Append to buffer</button>
          <button onClick={() => void sendLive(true)}>Append + Flush</button>
          <button onClick={() => void speakOnce()}>Speak once</button>
          <button onClick={flushBuffer}>Flush buffer</button>
          <button onClick={clearBuffer}>Clear buffer</button>
          {isPlaying && (
            <button onClick={stopAudio} style={{ background: '#991b1b' }}>
              Stop Audio
            </button>
          )}
        </div>

        <div className="preview-box">
          <strong>Pending buffer:</strong>
          <p>{pendingText || 'Буфер пуст'}</p>
          <p>Chars: {pendingChars}</p>
        </div>
      </section>

      <section className="card wide">
        <h2>Live events</h2>
        <div className="log-box">
          {events.map((eventLine, index) => (
            <div key={`${eventLine}-${index}`}>{eventLine}</div>
          ))}
        </div>
      </section>
    </div>
  )
}