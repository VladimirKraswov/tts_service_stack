export type DictionaryEntry = {
  id: number
  source_text: string
  spoken_text: string
  note?: string | null
}

export type Dictionary = {
  id: number
  name: string
  slug: string
  description?: string | null
  is_default: boolean
  entries: DictionaryEntry[]
}

export type Voice = {
  id: number
  name: string
  display_name: string
  backend: string
  model_name: string
  description?: string | null
  is_enabled: boolean
  kind: string
}

export type TrainingDataset = {
  id: number
  name: string
  speaker_name: string
  language: string
  file_path: string
  note?: string | null
  created_at: string
}

export type TrainingJob = {
  id: number
  dataset_id: number
  base_model: string
  output_name: string
  status: string
  progress: number
  log?: string | null
  artifact_path?: string | null
  created_at: string
  updated_at: string
}

export type SynthesisJob = {
  id: number
  source_name: string
  status: string
  stage: string
  progress: number

  voice_id?: string | null
  lora_name?: string | null
  language: string
  preprocess_profile: string
  reading_mode: string
  dictionary_id?: number | null
  speaking_rate?: string | null
  paragraph_pause_ms: number

  original_text_path?: string | null
  processed_text_path?: string | null
  wav_path?: string | null
  mp3_path?: string | null

  error_message?: string | null
  log?: string | null

  created_at: string
  updated_at: string
}

async function readError(response: Response): Promise<string> {
  const contentType = response.headers.get('content-type') || ''
  try {
    if (contentType.includes('application/json')) {
      const data = await response.json()
      if (typeof data?.detail === 'string') return data.detail
      return JSON.stringify(data)
    }
    return (await response.text()) || `${response.status} ${response.statusText}`
  } catch {
    return `${response.status} ${response.statusText}`
  }
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      ...(init?.headers || {}),
    },
    ...init,
  })

  if (!response.ok) {
    throw new Error(await readError(response))
  }

  return response.json() as Promise<T>
}

export const client = {
  health: () => api<{ status: string }>('/api/v1/health'),
  meta: () => api<Record<string, unknown>>('/api/v1/meta'),

  listDictionaries: () => api<Dictionary[]>('/api/v1/dictionaries'),
  createDictionary: (payload: { name: string; slug: string; description?: string; is_default?: boolean }) =>
    api<Dictionary>('/api/v1/dictionaries', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  addDictionaryEntry: (dictionaryId: number, payload: { source_text: string; spoken_text: string; note?: string }) =>
    api<Dictionary>(`/api/v1/dictionaries/${dictionaryId}/entries`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  deleteDictionaryEntry: (dictionaryId: number, entryId: number) =>
    api<Dictionary>(`/api/v1/dictionaries/${dictionaryId}/entries/${entryId}`, { method: 'DELETE' }),
  previewDictionary: (dictionaryId: number, text: string) =>
    api<{ original_text: string; processed_text: string }>(`/api/v1/dictionaries/${dictionaryId}/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    }),

  listVoices: () => api<Voice[]>('/api/v1/voices'),

  enqueueLive: (payload: { session_id: string; text: string; dictionary_id?: number; voice_id?: string; lora_name?: string; language?: string }) =>
    api<{ status: string }>('/api/v1/live/enqueue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  previewLive: async (payload: {
    text: string
    dictionary_id?: number
    voice_id?: string
    lora_name?: string
    language?: string
    reading_mode?: string
    speaking_rate?: string
    paragraph_pause_ms?: number
  }) => {
    const body = JSON.stringify(payload)

    const [audioResponse, meta] = await Promise.all([
      fetch('/api/v1/live/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      }),
      api<{ original_text: string; processed_text: string }>('/api/v1/live/preview-meta', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      }),
    ])

    if (!audioResponse.ok) {
      throw new Error(await readError(audioResponse))
    }

    return {
      blob: await audioResponse.blob(),
      processedText: meta.processed_text,
    }
  },

  listDatasets: () => api<TrainingDataset[]>('/api/v1/training/datasets'),
  uploadDataset: async (formData: FormData) => {
    const response = await fetch('/api/v1/training/datasets', { method: 'POST', body: formData })
    if (!response.ok) throw new Error(await readError(response))
    return response.json() as Promise<TrainingDataset>
  },
  listJobs: () => api<TrainingJob[]>('/api/v1/training/jobs'),
  createTrainingJob: (payload: { dataset_id: number; base_model: string; output_name: string }) =>
    api<TrainingJob>('/api/v1/training/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  listSynthesisJobs: () => api<SynthesisJob[]>('/api/v1/synthesis'),

  getSynthesisJob: (jobId: number) => api<SynthesisJob>(`/api/v1/synthesis/${jobId}`),

  createSynthesisJob: async (payload: {
    file: File
    voice_id?: string
    lora_name?: string
    language?: string
    preprocess_profile?: string
    reading_mode?: string
    dictionary_id?: number
    speaking_rate?: string
    paragraph_pause_ms?: number
  }) => {
    const formData = new FormData()
    formData.append('file', payload.file)
    if (payload.voice_id) formData.append('voice_id', payload.voice_id)
    if (payload.lora_name) formData.append('lora_name', payload.lora_name)
    if (payload.language) formData.append('language', payload.language)
    if (payload.preprocess_profile) formData.append('preprocess_profile', payload.preprocess_profile)
    if (payload.reading_mode) formData.append('reading_mode', payload.reading_mode)
    if (payload.dictionary_id !== undefined) formData.append('dictionary_id', String(payload.dictionary_id))
    if (payload.speaking_rate) formData.append('speaking_rate', payload.speaking_rate)
    if (payload.paragraph_pause_ms !== undefined) formData.append('paragraph_pause_ms', String(payload.paragraph_pause_ms))

    const response = await fetch('/api/v1/synthesis', {
      method: 'POST',
      body: formData,
    })

    if (!response.ok) {
      throw new Error(await readError(response))
    }

    return response.json() as Promise<{ id: number; status: string; stage: string; progress: number }>
  },
}