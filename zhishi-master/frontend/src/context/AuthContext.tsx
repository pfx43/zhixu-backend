import { createContext, useContext, useState, useEffect, type ReactNode } from "react"
import { setToken, getToken, authApi } from "@/lib/api"

interface User {
  id: number
  email: string
  nickname: string
  username?: string
  is_active: boolean
}

interface AuthState {
  user: User | null
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, nickname: string) => Promise<void>
  logout: () => void
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  // 页面刷新时从 localStorage 恢复 token，尝试获取用户信息
  useEffect(() => {
    const token = getToken()
    if (token) {
      authApi.getMe()
        .then(u => setUser({ id: u.id, email: u.email, nickname: u.nickname, username: u.username, is_active: u.is_active }))
        .catch(() => { setToken(null); setUser(null) })
        .finally(() => setIsLoading(false))
    } else {
      setIsLoading(false)
    }
  }, [])

  const login = async (email: string, password: string) => {
    const res = await authApi.login(email, password)
    setToken(res.access_token)
    const me = await authApi.getMe()
    setUser({ id: me.id, email: me.email, nickname: me.nickname, username: me.username, is_active: me.is_active })
  }

  const register = async (email: string, password: string, nickname: string) => {
    const res = await authApi.register(email, password, nickname)
    if (res.access_token) {
      setToken(res.access_token)
      const me = await authApi.getMe()
      setUser({ id: me.id, email: me.email, nickname: me.nickname, username: me.username, is_active: me.is_active })
    } else {
      // 注册成功但 Redis 不可用，需手动登录
      throw new Error(res.message || "注册成功，请登录")
    }
  }

  const logout = () => {
    setToken(null)
    setUser(null)
  }

  const refresh = async () => {
    if (!getToken()) return
    try {
      const me = await authApi.getMe()
      setUser({ id: me.id, email: me.email, nickname: me.nickname, username: me.username, is_active: me.is_active })
    } catch {
      logout()
    }
  }

  return (
    <AuthContext.Provider value={{ user, isLoading, login, register, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}