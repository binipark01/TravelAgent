import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { HomePage } from './pages/HomePage'

// 보조 페이지는 필요할 때만 로드해 초기 번들을 줄인다(첫 화면 = HomePage만).
const RecentTripsPage = lazy(() =>
  import('./pages/RecentTripsPage').then((m) => ({ default: m.RecentTripsPage })),
)
const SettingsPage = lazy(() =>
  import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage })),
)
const TripWorkspacePage = lazy(() =>
  import('./pages/TripWorkspacePage').then((m) => ({ default: m.TripWorkspacePage })),
)
const SavedTripPage = lazy(() =>
  import('./pages/SavedTripPage').then((m) => ({ default: m.SavedTripPage })),
)

export default function App() {
  return (
    <AppShell>
      <Suspense fallback={<div className="route-loading">불러오는 중…</div>}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/trips" element={<RecentTripsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/trips/:tripId" element={<TripWorkspacePage />} />
          <Route path="/runs/:runId" element={<SavedTripPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </AppShell>
  )
}
