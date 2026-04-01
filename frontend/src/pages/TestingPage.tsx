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
  const [preprocessProfile, setPreprocessProfile] = useState<'literary' | 'technical' | 'general'>('technical')

  const [previewText, setPreviewText] = useState('В Python функция __init__ вызывается при создании объекта. В React часто используют useEffect.')
  const [previewUrl, setPreviewUrl] = useState('')
  const [previewProcessedText, setPreviewProcessedText] = useState('')
  const [isPreviewing, setIsPreviewing] = useState(false)

  const [liveDraft, setLiveDraft] = useState('Live через CosyVoice отключен. Сейчас используется mock backend для проверки буфера, событий и WebSocket.')
  const [liveStatus, setLiveStatus] = useState('disconnected')
  const [pendingText, setPendingText] = useState('')
  const [pendingChars, setPendingChars] = useState(0)
  const [events, setEvents] = useState<string[]>([])
  const [autoStream, setAutoStream] = useState(true)

  const websocketRef = useRef<WebSocket | null>(null)
  const previewAudioRef = useRef<HTMLAudioElement | null>(null)
  const liveSentRef = useRef('')
  const autoSendTimerRef = useRef<number | null>(null)

  const voiceOptions = useMemo(() => voices.filter((voice) => voice.kind === 'voice'), [voices])
  const loraOptions = useMemo(() => voices.filter((voice) => voice.kind === 'lora'), [voices])

  const log = (message: string) => setEvents((prev) => [message, ...prev].slice(0, 100))

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
      if (autoSendTimerRef.current !== null) {
        window.clearTimeout(autoSendTimerRef.current)
      }
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
      liveSentRef.current = ''
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
    liveSentRef.current = ''
    setLiveStatus('disconnected')
    setPendingText('')
    setPendingChars(0)
    stopAudio()
  }

  const sendWsMessage = async (payload: unknown) => {
    if (!websocketRef.current || websocketRef.current.readyState !== WebSocket.OPEN) {
      show('Сначала подключи WebSocket', 'info')
      return false
    }

    try {
      await prepare()
      websocketRef.current.send(JSON.stringify(payload))
      return true
    } catch (error) {
      show(getErrorMessage(error), 'error')
      return false
    }
  }

  const syncLiveDelta = async () => {
    if (!autoStream) return
    if (!websocketRef.current || websocketRef.current.readyState !== WebSocket.OPEN) return

    const sent = liveSentRef.current
    const current = liveDraft

    if (current === sent) return

    if (!current.startsWith(sent)) {
      const ok = await sendWsMessage({ type: 'clear_buffer' })
      if (!ok) return
      liveSentRef.current = ''
    }

    const delta = liveDraft.slice(liveSentRef.current.length)
    if (!delta) return

    const ok = await sendWsMessage({
      type: 'append_text',
      text: delta,
      flush: false,
      dictionary_id: dictionaryId,
      voice_id: voiceId,
      lora_name: loraName,
      language: 'ru',
    })

    if (ok) {
      liveSentRef.current += delta
      log(`delta sent: ${JSON.stringify(delta)}`)
    }
  }

  useEffect(() => {
    if (!autoStream) return
    if (liveStatus !== 'connected') return

    if (autoSendTimerRef.current !== null) {
      window.clearTimeout(autoSendTimerRef.current)
    }

    autoSendTimerRef.current = window.setTimeout(() => {
      void syncLiveDelta()
    }, 110)

    return () => {
      if (autoSendTimerRef.current !== null) {
        window.clearTimeout(autoSendTimerRef.current)
      }
    }
  }, [liveDraft, autoStream, liveStatus, dictionaryId, voiceId, loraName])

  const appendManual = async (flush: boolean) => {
    const ok = await sendWsMessage({
      type: 'append_text',
      text: liveDraft,
      flush,
      dictionary_id: dictionaryId,
      voice_id: voiceId,
      lora_name: loraName,
      language: 'ru',
    })
    if (ok) log(flush ? 'append_text + flush sent' : 'append_text sent')
  }

  const speakOnce = async () => {
    const ok = await sendWsMessage({
      type: 'enqueue_text',
      text: liveDraft,
      dictionary_id: dictionaryId,
      voice_id: voiceId,
      lora_name: loraName,
      language: 'ru',
    })
    if (ok) log('enqueue_text sent')
  }

  const flushBuffer = async () => {
    const ok = await sendWsMessage({ type: 'flush' })
    if (ok) log('flush sent')
  }

  const clearBuffer = async () => {
    const ok = await sendWsMessage({ type: 'clear_buffer' })
    if (ok) {
      liveSentRef.current = ''
      log('clear_buffer sent')
    }
  }

  const resyncLiveText = async () => {
    const ok = await sendWsMessage({ type: 'clear_buffer' })
    if (!ok) return

    liveSentRef.current = ''

    const ok2 = await sendWsMessage({
      type: 'append_text',
      text: liveDraft,
      flush: false,
      dictionary_id: dictionaryId,
      voice_id: voiceId,
      lora_name: loraName,
      language: 'ru',
    })

    if (ok2) {
      liveSentRef.current = liveDraft
      log('live text resynced')
    }
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
        preprocess_profile: preprocessProfile,
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

        <div className="grid two">
          <div>
            <label>Профиль препроцессинга</label>
            <select
              value={preprocessProfile}
              onChange={(e) => setPreprocessProfile(e.target.value as 'literary' | 'technical' | 'general')}
            >
              <option value="literary">Художественная литература</option>
              <option value="technical">Технический текст</option>
              <option value="general">Общий профиль</option>
            </select>
          </div>
        </div>

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
        <h2>Live mode — CosyVoice отключен, сейчас работает mock backend</h2>

        <label className="row" style={{ gap: '8px', alignItems: 'center' }}>
          <input
            type="checkbox"
            checked={autoStream}
            onChange={(e) => setAutoStream(e.target.checked)}
          />
          Auto stream delta while typing
        </label>

        <textarea rows={6} value={liveDraft} onChange={(e) => setLiveDraft(e.target.value)} />

        <div className="row wrap" style={{ marginTop: '16px' }}>
          <button onClick={() => void appendManual(false)}>Append full text</button>
          <button onClick={() => void appendManual(true)}>Append + Flush</button>
          <button onClick={() => void speakOnce()}>Speak once</button>
          <button onClick={() => void flushBuffer()}>Flush buffer</button>
          <button onClick={() => void clearBuffer()}>Clear buffer</button>
          <button onClick={() => void resyncLiveText()}>Resync draft</button>
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