import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { api, getTokens, login as apiLogin, setTokens } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!getTokens()?.access) {
      setLoading(false)
      return
    }
    api('/api/users/me/')
      .then(setUser)
      .catch(() => setTokens(null))
      .finally(() => setLoading(false))
  }, [])

  const value = useMemo(
    () => ({
      user,
      loading,
      login: async (username, password) => {
        const me = await apiLogin(username, password)
        setUser(me)
        return me
      },
      logout: () => {
        setTokens(null)
        setUser(null)
      },
      can: (permission) => Boolean(user?.permissions?.[permission]),
    }),
    [user, loading],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
