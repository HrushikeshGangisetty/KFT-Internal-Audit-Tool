import { lazy } from 'react'

export const routes = [
  { path: '/report', Component: lazy(() => import('./Report.jsx')) },
  { path: '/issues', Component: lazy(() => import('./IssueList.jsx')) },
  { path: '/issues/new', Component: lazy(() => import('./IssueCreate.jsx')) },
  { path: '/issues/:id', Component: lazy(() => import('./IssueDetail.jsx')) },
]
