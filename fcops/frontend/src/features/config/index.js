import { lazy } from 'react'

export const routes = [
  { path: '/manager/test-configuration', Component: lazy(() => import('./TestConfiguration.jsx')) },
  { path: '/manager/fc-models', Component: lazy(() => import('./FcModels.jsx')) },
]
