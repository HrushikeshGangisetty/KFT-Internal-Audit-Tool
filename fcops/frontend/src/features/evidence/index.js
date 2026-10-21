import { lazy } from 'react'

export const routes = [
  { path: '/param-compare', Component: lazy(() => import('./ParamCompare.jsx')) },
]
