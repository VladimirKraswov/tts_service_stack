import { useRef, useState } from 'react'

export type AudioChunk = {
  audio_b64: string
  sample_rate: number
  is_last?: boolean
  seq_no: number
}

function decodeBase64Pcm16(audioB64: string): Float32Array {
  const binaryString = window.atob(audioB64)
  const len = binaryString.length
  const bytes = new Uint8Array(len)

  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i)
  }

  const sampleCount = Math.floor(bytes.byteLength / 2)
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  const floatData = new Float32Array(sampleCount)

  for (let i = 0; i < sampleCount; i++) {
    const value = view.getInt16(i * 2, true)
    floatData[i] = value / 32768
  }

  return floatData
}

export function useAudioPlayer() {
  const audioContextRef = useRef<AudioContext | null>(null)
  const scheduledTimeRef = useRef<number>(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [queueSize, setQueueSize] = useState(0)

  const initContext = async () => {
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)({
        sampleRate: 24000,
      })
      scheduledTimeRef.current = audioContextRef.current.currentTime
    }

    if (audioContextRef.current.state === 'suspended') {
      await audioContextRef.current.resume()
    }
  }

  const prepare = async () => {
    await initContext()
  }

  const addChunk = async (chunk: AudioChunk) => {
    await initContext()
    const ctx = audioContextRef.current!
    const floatData = decodeBase64Pcm16(chunk.audio_b64)

    const audioBuffer = ctx.createBuffer(1, floatData.length, chunk.sample_rate)
    audioBuffer.getChannelData(0).set(floatData)

    const source = ctx.createBufferSource()
    source.buffer = audioBuffer
    source.connect(ctx.destination)

    const now = ctx.currentTime
    if (scheduledTimeRef.current < now) {
      scheduledTimeRef.current = now + 0.05
    }

    source.start(scheduledTimeRef.current)
    scheduledTimeRef.current += audioBuffer.duration

    setQueueSize((prev) => prev + 1)
    setIsPlaying(true)

    source.onended = () => {
      setQueueSize((prev) => {
        const next = Math.max(0, prev - 1)
        if (next === 0) {
          setIsPlaying(false)
        }
        return next
      })
    }
  }

  const stop = () => {
    const ctx = audioContextRef.current
    audioContextRef.current = null
    scheduledTimeRef.current = 0
    setIsPlaying(false)
    setQueueSize(0)

    if (ctx) {
      void ctx.close()
    }
  }

  return { addChunk, stop, isPlaying, queueSize, prepare }
}

export function AudioPlayerStatus({ isPlaying, queueSize }: { isPlaying: boolean; queueSize: number }) {
  if (!isPlaying && queueSize === 0) return null

  return (
    <div className="audio-status-badge">
      <span className="dot pulse"></span>
      {isPlaying ? 'Воспроизведение...' : 'Буферизация...'} ({queueSize})
    </div>
  )
}