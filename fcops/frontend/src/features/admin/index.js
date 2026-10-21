import { lazy } from 'react'

export const routes = [
  { path: '/admin', Component: lazy(() => import('./Admin.jsx')) },
]
