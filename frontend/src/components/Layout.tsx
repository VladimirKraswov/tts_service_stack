import { NavLink } from 'react-router-dom'
import type { PropsWithChildren } from 'react'

const links = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/testing', label: 'Тестирование' },
  { to: '/dictionary', label: 'Словари' },
  { to: '/training', label: 'Fine-tuning' },
]

export function Layout({ children }: PropsWithChildren) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <h1>TTS Admin</h1>
        <p className="subtitle">Тестирование, словари и обучение</p>
        <nav className="nav">
          {links.map((link) => (
            <NavLink key={link.to} to={link.to} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              {link.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="content">{children}</main>
    </div>
  )
}
