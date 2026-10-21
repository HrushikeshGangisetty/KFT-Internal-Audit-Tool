import { lazy } from 'react'

export const routes = [
  { path: '/fcs', Component: lazy(() => import('./FcList.jsx')) },
  { path: '/fcs/new', Component: lazy(() => import('./FcCreate.jsx')) },
  { path: '/fcs/:id', Component: lazy(() => import('./FcDetail.jsx')) },
]
