import { useEffect, useState } from 'react'
import { client } from '../api/client'

export function DashboardPage() {
  const [health, setHealth] = useState<string>('loading')
  const [meta, setMeta] = useState<Record<string, string>>({})

  useEffect(() => {
    client.health().then((data) => setHealth(data.status)).catch(() => setHealth('error'))
    client.meta().then(setMeta).catch(() => setMeta({ error: 'failed to load' }))
  }, [])

  return (
    <div className="page-grid">
      <section className="card">
        <h2>Состояние сервиса</h2>
        <p className="metric">{health}</p>
      </section>
      <section className="card">
        <h2>Backend meta</h2>
        <pre>{JSON.stringify(meta, null, 2)}</pre>
      </section>
      <section className="card wide">
        <h2>Что проверять после деплоя</h2>
        <ol>
          <li>health/meta</li>
          <li>WebSocket соединение</li>
          <li>enqueue текста и first audio latency</li>
          <li>preview произношения</li>
          <li>upload dataset и training jobs</li>
        </ol>
      </section>
    </div>
  )
}
