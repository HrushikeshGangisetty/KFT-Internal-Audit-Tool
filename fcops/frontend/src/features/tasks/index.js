import { lazy } from 'react'

export const routes = [
  { path: '/tasks', Component: lazy(() => import('./Tasks.jsx')) },
]
