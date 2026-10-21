import { lazy } from 'react'

export const routes = [
  { path: '/firmware/builds', Component: lazy(() => import('./ManageFirmware.jsx')) },
]
