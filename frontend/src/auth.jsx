/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import api from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    const response = await api.get('/auth/me')
    setUser(response.data.user)
    setLoading(false)
    return response.data.user
  }, [])

  useEffect(() => {
    // The account state is loaded from the server once when the app starts.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh().catch(() => setLoading(false))
  }, [refresh])

  const value = useMemo(() => ({
    user,
    loading,
    async login(values) {
      const response = await api.post('/auth/login', values)
      setUser(response.data.user)
      return response.data.user
    },
    async register(values) {
      const response = await api.post('/auth/register', values)
      setUser(response.data.user)
      return response.data.user
    },
    async logout() {
      await api.post('/auth/logout')
      setUser(null)
    },
    refresh,
  }), [loading, refresh, user])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  return useContext(AuthContext)
}
