import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { HomePage } from './pages/HomePage'
import { RecentTripsPage } from './pages/RecentTripsPage'
import { SavedTripPage } from './pages/SavedTripPage'
import { SettingsPage } from './pages/SettingsPage'
import { TripWorkspacePage } from './pages/TripWorkspacePage'

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/trips" element={<RecentTripsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/trips/:tripId" element={<TripWorkspacePage />} />
        <Route path="/runs/:runId" element={<SavedTripPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  )
}
