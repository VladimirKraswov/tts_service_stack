import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { ToastProvider } from './components/Toast'
import { DashboardPage } from './pages/DashboardPage'
import { DictionaryPage } from './pages/DictionaryPage'
import { SynthesisPage } from './pages/SynthesisPage'
import { TestingPage } from './pages/TestingPage'
import { TrainingPage } from './pages/TrainingPage'

export default function App() {
  return (
    <ToastProvider>
      <Layout>
        <Routes>
          <Route path="/" element={<Navigate to="/synthesis" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/synthesis" element={<SynthesisPage />} />
          <Route path="/testing" element={<TestingPage />} />
          <Route path="/dictionary" element={<DictionaryPage />} />
          <Route path="/training" element={<TrainingPage />} />
        </Routes>
      </Layout>
    </ToastProvider>
  )
}