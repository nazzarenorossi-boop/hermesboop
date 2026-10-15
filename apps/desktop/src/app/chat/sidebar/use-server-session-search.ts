import { useEffect, useMemo, useState } from 'react'

import { useHermesConfigRecord } from '@/app/hooks/use-config-record'
import { searchSessions, type SessionSearchResult } from '@/hermes'
import { configuredExcludeSources } from '@/lib/session-source'
import { ALL_PROFILES, normalizeProfileKey } from '@/store/profile'

const SEARCH_DEBOUNCE_MS = 200

export interface ServerSessionSearch {
  serverMatches: SessionSearchResult[]
  searchPending: boolean
}

/**
 * Debounced full-text search across *all* sessions (not just the loaded page)
 * so old sessions stay findable. Hits come from the profile the sidebar shows:
 * an unscoped request searches the primary backend's launch profile, whatever
 * profile is on screen. "All profiles" asks the primary as before.
 */
export function useServerSessionSearch(query: string, profileScope: string): ServerSessionSearch {
  const [serverMatches, setServerMatches] = useState<SessionSearchResult[]>([])
  const [searchPending, setSearchPending] = useState(false)
  const profile = profileScope === ALL_PROFILES ? null : normalizeProfileKey(profileScope)
  // The same exclusions the recents slice uses, so a term that lives inside an
  // excluded source cannot resurface a row the list itself hides
  // (`sessions.exclude_sources`, `a2a` by default).
  const { data: configRecord } = useHermesConfigRecord()
  const excludeSources = useMemo(() => configuredExcludeSources(configRecord), [configRecord])

  useEffect(() => {
    if (!query) {
      setServerMatches([])
      setSearchPending(false)

      return
    }

    let cancelled = false

    setSearchPending(true)

    const id = window.setTimeout(() => {
      void searchSessions(query, profile, excludeSources)
        .then(res => {
          if (!cancelled) {
            setServerMatches(res.results)
          }
        })
        .catch(() => undefined)
        .finally(() => {
          if (!cancelled) {
            setSearchPending(false)
          }
        })
    }, SEARCH_DEBOUNCE_MS)

    return () => {
      cancelled = true
      window.clearTimeout(id)
    }
  }, [query, profile, excludeSources])

  return { searchPending, serverMatches }
}
