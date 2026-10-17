import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { currentUser, login as apiLogin, logout as apiLogout } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // The session cookie is HttpOnly, so ask the server who we are.
    currentUser()
      .then((me) => setUser(me || null))
      .catch(() => setUser(null))
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
      logout: async () => {
        await apiLogout()
        setUser(null)
      },
      can: (permission) => Boolean(user?.permissions?.[permission]),
    }),
    [user, loading],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
