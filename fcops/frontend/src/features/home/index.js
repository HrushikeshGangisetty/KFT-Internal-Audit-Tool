import { lazy } from 'react'

export const routes = [
  { path: '/', Component: lazy(() => import('./Home.jsx')) },
]
