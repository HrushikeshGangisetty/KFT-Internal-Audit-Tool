import { lazy } from 'react'

export const routes = [
  { path: '/known-issues', Component: lazy(() => import('./KnownIssues.jsx')) },
  { path: '/search', Component: lazy(() => import('./Search.jsx')) },
  { path: '/audit', Component: lazy(() => import('./AuditLog.jsx')) },
]
