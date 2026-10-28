import { useEffect, useState } from 'react'
import { apiFetch } from '../config'

// Card search with a pause after typing and "Load more" paging.
//   const search = useCardSearch(query)
//   search.results, search.searching, search.hint, search.hasMore, search.loadMore(), search.loadingMore
// /poketrace-search understands name + set words ("absol magma"), card numbers ("96/95"), optional "ex",
// and returns next_cursor when PokeTrace has more pages.
export default function useCardSearch(query, minLength = 2) {
  const [state, setState] = useState({ for: '', results: [], hint: null, cursor: null })
  const [loadingMore, setLoadingMore] = useState(false)
  const q = query.trim()

  useEffect(() => {
    if (q.length < minLength) return
    let cancelled = false
    const timeout = setTimeout(() => {
      apiFetch(`/poketrace-search/${encodeURIComponent(q)}`)
        .then(res => res.json())
        .then(data => { if (!cancelled) setState({ for: q, results: data.results || [], hint: data.hint || null, cursor: data.next_cursor || null }) })
        .catch(() => { if (!cancelled) setState({ for: q, results: [], hint: null, cursor: null }) })
    }, 400)
    return () => { cancelled = true; clearTimeout(timeout) }
  }, [q, minLength])

  function loadMore() {
    if (!state.cursor || loadingMore) return
    setLoadingMore(true)
    apiFetch(`/poketrace-search/${encodeURIComponent(state.for)}?cursor=${encodeURIComponent(state.cursor)}`)
      .then(res => res.json())
      .then(data => setState(s => {
        if (s.for !== state.for) return s  // the query changed while this page was loading
        const seen = new Set(s.results.map(r => r.poketrace_id))
        return { ...s, results: [...s.results, ...(data.results || []).filter(r => !seen.has(r.poketrace_id))], cursor: data.next_cursor || null }
      }))
      .catch(() => {})
      .finally(() => setLoadingMore(false))
  }

  const current = q.length >= minLength && state.for === q
  return {
    results: current ? state.results : [],
    searching: q.length >= minLength && state.for !== q,
    hint: current ? state.hint : null,
    hasMore: current && !!state.cursor,
    loadMore,
    loadingMore,
  }
}
