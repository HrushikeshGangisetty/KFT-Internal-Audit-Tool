import { useCallback, useEffect, useRef, useState } from 'react'
import { api, listOf } from '../lib/api'
import { Banner, Empty, Loading } from './ui.jsx'

/* ---------------------------------------------------------------------------
   Paged lists with infinite scroll. Every list endpoint uses DRF page-number
   pagination (core.pagination, max 200), so the first page is fetched with
   `page_size` and later pages follow the server's `next` link. Changing
   `params` starts again from page 1; a late response for old params is dropped.
   ------------------------------------------------------------------------- */
const FIRST = { rows: null, next: null, count: 0, error: '', loadingMore: false }

export function usePaged(path, params = {}, pageSize = 25) {
  const query = JSON.stringify(params)
  const [state, setState] = useState(FIRST)
  const [tick, setTick] = useState(0)
  const generation = useRef(0)
  const busy = useRef(false)

  useEffect(() => {
    if (!path) return
    const g = ++generation.current
    busy.current = true
    setState(FIRST)
    api(path, { params: { ...JSON.parse(query), page_size: pageSize } })
      .then((d) => g === generation.current && setState({
        ...FIRST, rows: listOf(d), next: d?.next ?? null, count: d?.count ?? listOf(d).length,
      }))
      .catch((e) => g === generation.current && setState({ ...FIRST, rows: [], error: e.message }))
      .finally(() => { if (g === generation.current) busy.current = false })
  }, [path, query, pageSize, tick])

  const { next } = state
  const loadMore = useCallback(() => {
    if (busy.current || !next) return
    const g = generation.current
    busy.current = true
    setState((s) => ({ ...s, loadingMore: true }))
    api(next)
      .then((d) => g === generation.current && setState((s) => ({
        ...s, rows: [...s.rows, ...listOf(d)], next: d?.next ?? null, loadingMore: false,
      })))
      .catch((e) => g === generation.current && setState((s) => ({ ...s, error: e.message, loadingMore: false })))
      .finally(() => { if (g === generation.current) busy.current = false })
  }, [next])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  return { ...state, loadMore, reload }
}

/** Loads the next page when it scrolls into view; the button is the fallback. */
export function LoadMore({ page }) {
  const ref = useRef(null)
  const { next, loadMore, loadingMore, rows, count } = page
  useEffect(() => {
    if (!next || !ref.current || !('IntersectionObserver' in window)) return undefined
    const io = new IntersectionObserver(([e]) => e.isIntersecting && loadMore(), { rootMargin: '400px' })
    io.observe(ref.current)
    return () => io.disconnect()
  }, [next, loadMore])
  if (!rows?.length) return null
  return (
    <div ref={ref} className="load-more">
      <span className="small muted">Showing {rows.length} of {count}</span>
      {next ? (
        <button type="button" className="secondary sm" onClick={loadMore} disabled={loadingMore}>
          {loadingMore ? 'Loading…' : 'Load more'}
        </button>
      ) : null}
    </div>
  )
}

/**
 * Loading / error / empty / rows for a usePaged result, plus the scroll
 * sentinel. `children(rows)` renders the list itself.
 */
export function Paged({ page, what = 'records', cols, empty = 'Nothing here yet.', emptyIcon, children }) {
  if (page.rows === null) return <Loading what={what} cols={cols} />
  return (
    <>
      {page.error ? <div className="pad"><Banner>{page.error}</Banner></div> : null}
      {page.rows.length ? children(page.rows) : page.error ? null : <Empty icon={emptyIcon}>{empty}</Empty>}
      <LoadMore page={page} />
    </>
  )
}
