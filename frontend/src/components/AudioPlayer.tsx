import { useEffect, useRef, useState } from 'react'

export type AudioChunk = {
  audio_b64: string
  sample_rate: number
  is_last?: boolean
  seq_no: number
}

export function useAudioPlayer() {
  const audioContextRef = useRef<AudioContext | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const scheduledTimeRef = useRef<number>(0)
  const [queueSize, setQueueSize] = useState(0)

  const initContext = () => {
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 24000 })
      scheduledTimeRef.current = audioContextRef.current.currentTime
    }
    if (audioContextRef.current.state === 'suspended') {
      void audioContextRef.current.resume()
    }
  }

  const addChunk = async (chunk: AudioChunk) => {
    initContext()
    const ctx = audioContextRef.current!

    // Convert base64 to ArrayBuffer
    const binaryString = window.atob(chunk.audio_b64)
    const len = binaryString.length
    const bytes = new Uint8Array(len)
    for (let i = 0; i < len; i++) {
      bytes[i] = binaryString.charCodeAt(i)
    }

    // PCM S16LE to Float32
    const pcmData = new Int16Array(bytes.buffer)
    const floatData = new Float32Array(pcmData.length)
    for (let i = 0; i < pcmData.length; i++) {
      floatData[i] = pcmData[i] / 32768.0
    }

    const audioBuffer = ctx.createBuffer(1, floatData.length, chunk.sample_rate)
    audioBuffer.getChannelData(0).set(floatData)

    const source = ctx.createBufferSource()
    source.buffer = audioBuffer
    source.connect(ctx.destination)

    const now = ctx.currentTime
    if (scheduledTimeRef.current < now) {
      scheduledTimeRef.current = now + 0.05 // Small buffer to prevent initial gap
    }

    source.start(scheduledTimeRef.current)
    scheduledTimeRef.current += audioBuffer.duration

    setQueueSize(prev => prev + 1)
    setIsPlaying(true)

    source.onended = () => {
      setQueueSize(prev => {
        const next = prev - 1
        if (next === 0) setIsPlaying(false)
        return next
      })
    }
  }

  const stop = () => {
    if (audioContextRef.current) {
      void audioContextRef.current.close()
      audioContextRef.current = null
    }
    scheduledTimeRef.current = 0
    setIsPlaying(false)
    setQueueSize(0)
  }

  return { addChunk, stop, isPlaying, queueSize }
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
