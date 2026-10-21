import { useEffect, useState } from 'react'

/** `value`, settled for `ms` — so typing in a search box sends one request, not one per key. */
export function useDebounced(value, ms = 300) {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setSettled(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return settled
}
