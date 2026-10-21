import { lazy } from 'react'

export const routes = [
  { path: '/queue', Component: lazy(() => import('./Queue.jsx')) },
]
