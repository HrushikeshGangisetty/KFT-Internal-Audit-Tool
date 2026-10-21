import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useAuth } from './lib/auth.jsx'
import { Empty, PageSkeleton } from './components/ui.jsx'
import Shell from './app/Shell.jsx'

// Each feature owns its routes (features/<name>/index.js). Pages are loaded
// on first visit, so adding a feature does not grow the initial download.
import { routes as home } from './features/home/index.js'
import { routes as work } from './features/work/index.js'
import { routes as issues } from './features/issues/index.js'
import { routes as tasks } from './features/tasks/index.js'
import { routes as releases } from './features/releases/index.js'
import { routes as fc } from './features/fc/index.js'
import { routes as evidence } from './features/evidence/index.js'
import { routes as firmware } from './features/firmware/index.js'
import { routes as knowledge } from './features/knowledge/index.js'
import { routes as config } from './features/config/index.js'
import { routes as admin } from './features/admin/index.js'
import { routes as customers } from './features/customers/index.js'

const ROUTES = [
  ...home, ...work, ...issues, ...tasks, ...releases, ...fc, ...evidence, ...firmware,
  ...customers, ...knowledge, ...config, ...admin,
]
const Login = lazy(() => import('./features/auth/Login.jsx'))

export default function App() {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="content"><PageSkeleton stats={4} /></div>
  if (!user) {
    return (
      <Suspense fallback={null}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </Suspense>
    )
  }
  return (
    <Shell>
      <Suspense fallback={<PageSkeleton split />}>
        {/* Keyed by path so each page mounts fresh and plays its entrance. */}
        <div className="page" key={location.pathname}>
          <Routes location={location}>
            {ROUTES.map(({ path, Component, redirect }) => (
              <Route key={path} path={path}
                     element={redirect ? <Navigate to={redirect} replace /> : <Component />} />
            ))}
            <Route path="/login" element={<Navigate to="/" replace />} />
            <Route path="*" element={<Empty title="Page not found">That page doesn't exist.</Empty>} />
          </Routes>
        </div>
      </Suspense>
    </Shell>
  )
}
