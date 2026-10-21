import { lazy } from 'react'

export const routes = [
  { path: '/releases', Component: lazy(() => import('./ReleaseList.jsx')) },
  { path: '/releases/:id', Component: lazy(() => import('./ReleaseDetail.jsx')) },
  { path: '/software/push-update', redirect: '/releases' },
]
