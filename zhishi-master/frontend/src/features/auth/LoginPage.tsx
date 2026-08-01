import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useAuth } from "@/context/AuthContext"
import { Button } from "@/components/ui/button"
import { Sparkles, Mail, Lock, User, ArrowRight } from "lucide-react"
import { cn } from "@/lib/utils"

export function LoginPage() {
  const { login, register } = useAuth()
  const navigate = useNavigate()

  const [isRegister, setIsRegister] = useState(false)
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [nickname, setNickname] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)

    try {
      if (isRegister) {
        await register(email, password, nickname || email.split("@")[0])
      } else {
        await login(email, password)
      }
      navigate("/chat")
    } catch (err: any) {
      setError(err.message || "操作失败，请重试")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="h-full flex items-center justify-center bg-bg">
      <div className="w-full max-w-[440px] mx-auto animate-page-in">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="w-14 h-14 rounded-full bg-gradient-primary flex items-center justify-center mx-auto mb-4 shadow-primary">
            <Sparkles className="w-7 h-7 text-white" strokeWidth={2} />
          </div>
          <h1 className="text-page-title text-ink-primary">知拾</h1>
          <p className="text-body text-ink-tertiary mt-1.5">知识管理，从 Tina 开始</p>
        </div>

        {/* Card */}
        <div className="bg-surface rounded-xl border border-line-soft shadow-sm p-8">
          <h2 className="text-card-title font-semibold text-ink-primary mb-5">
            {isRegister ? "创建账号" : "欢迎回来"}
          </h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            {isRegister && (
              <div className="space-y-1.5">
                <label className="text-small text-ink-secondary">昵称</label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-tertiary" strokeWidth={2} />
                  <input
                    type="text"
                    value={nickname}
                    onChange={e => setNickname(e.target.value)}
                    placeholder="你的昵称"
                    required
                    className={cn(
                      "w-full h-10 pl-10 pr-3 rounded-md border border-line bg-surface-soft",
                      "text-body text-ink-primary placeholder:text-ink-tertiary",
                      "focus:border-primary/50 focus:ring-2 focus:ring-primary/10 outline-none transition-all"
                    )}
                  />
                </div>
              </div>
            )}

            <div className="space-y-1.5">
              <label className="text-small text-ink-secondary">邮箱</label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-tertiary" strokeWidth={2} />
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="your@email.com"
                  required
                  className={cn(
                    "w-full h-10 pl-10 pr-3 rounded-md border border-line bg-surface-soft",
                    "text-body text-ink-primary placeholder:text-ink-tertiary",
                    "focus:border-primary/50 focus:ring-2 focus:ring-primary/10 outline-none transition-all"
                  )}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-small text-ink-secondary">密码</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-tertiary" strokeWidth={2} />
                <input
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="至少 6 位"
                  required
                  minLength={6}
                  className={cn(
                    "w-full h-10 pl-10 pr-3 rounded-md border border-line bg-surface-soft",
                    "text-body text-ink-primary placeholder:text-ink-tertiary",
                    "focus:border-primary/50 focus:ring-2 focus:ring-primary/10 outline-none transition-all"
                  )}
                />
              </div>
            </div>

            {error && (
              <div className="text-small text-danger bg-danger-soft px-3 py-2.5 rounded-md border border-danger/20">
                {error}
              </div>
            )}

            <Button
              type="submit"
              className="w-full h-11"
              variant="primary"
              disabled={loading}
            >
            {loading ? (
                isRegister ? "正在创建专属知识空间..." : "登录中..."
              ) : (
                <>
                  {isRegister ? "注册" : "登录"}
                  <ArrowRight className="w-4 h-4" strokeWidth={2} />
                </>
              )}
            </Button>

            <div className="text-center text-small text-ink-tertiary pt-1">
              {isRegister ? "已有账号？" : "还没有账号？"}
              <button
                type="button"
                onClick={() => { setIsRegister(!isRegister); setError("") }}
                className="text-primary hover:underline ml-1 font-medium"
              >
                {isRegister ? "去登录" : "去注册"}
              </button>
            </div>
          </form>
        </div>

        <p className="text-center text-small text-ink-tertiary mt-5">
          注册即自动为你创建专属知识库
        </p>
      </div>
    </div>
  )
}