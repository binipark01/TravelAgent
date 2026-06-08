import type { ReactNode } from 'react'
import { Header } from './Header'

interface AppShellProps {
  children: ReactNode
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="app-shell">
      <Header />
      <main className="app-main">{children}</main>
    </div>
  )
}
