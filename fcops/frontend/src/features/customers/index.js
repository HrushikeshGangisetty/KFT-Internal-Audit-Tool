import { lazy } from 'react'

export const routes = [
  { path: '/customers', Component: lazy(() => import('./CustomerList.jsx')) },
  { path: '/customers/:id', Component: lazy(() => import('./CustomerDetail.jsx')) },
]
