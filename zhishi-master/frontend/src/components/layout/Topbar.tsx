import { useState, useRef, useEffect } from "react"
import { Search, PanelRight, LogOut } from "lucide-react"
import { useLocation, useNavigate } from "react-router-dom"
import { useUI } from "@/context/UIContext"
import { useAuth } from "@/context/AuthContext"
import { cn } from "@/lib/utils"

const titleMap: Record<string, string> = {
  "/": "首页",
  "/chat": "AI 对话",
  "/notes": "笔记",
  "/knowledge": "知识库管理",
  "/knowledge/upload": "上传到知识库",
  "/graph": "知识图谱",
  "/analytics": "学习分析",
  "/path": "学习路径",
  "/reminders": "智能提醒",
  "/profile": "个人学习画像",
  "/settings": "设置",
  "/settings/diagnostics": "诊断与修复",
}

export function Topbar() {
  const location = useLocation()
  const navigate = useNavigate()
  const { rightPanelOpen, toggleRightPanel } = useUI()
  const { user, logout } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const title = titleMap[location.pathname] ?? "知拾"

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    if (menuOpen) {
      document.addEventListener("mousedown", handleClickOutside)
      return () => document.removeEventListener("mousedown", handleClickOutside)
    }
  }, [menuOpen])

  const handleLogout = () => {
    logout()
    navigate("/login")
  }

  return (
    <header className="h-16 shrink-0 border-b border-line-soft bg-surface/80 backdrop-blur-xl flex items-center gap-4 px-6">
      {/* 左侧：页面标题 */}
      <div className="text-card-title font-semibold text-ink-primary shrink-0 w-[140px]">
        {title}
      </div>

      {/* 中间：搜索框 */}
      <div className="flex-1 max-w-[560px] mx-auto">
        <div className="relative group">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-[18px] h-[18px] text-ink-tertiary group-focus-within:text-primary transition-colors" strokeWidth={2} />
          <input
            type="text"
            placeholder="搜索笔记、文档、标签或向 Tina 提问..."
            className="w-full h-10 pl-11 pr-16 rounded-md bg-bg-subtle border border-line-soft text-body text-ink-primary placeholder:text-ink-tertiary focus:outline-none focus:border-primary/50 focus:bg-surface focus:ring-2 focus:ring-primary/10 transition-all"
          />
          <kbd className="absolute right-3 top-1/2 -translate-y-1/2 hidden sm:flex items-center gap-0.5 px-1.5 h-5 rounded border border-line-soft bg-surface text-small text-ink-tertiary">
            ⌘ K
          </kbd>
        </div>
      </div>

      {/* 右侧：操作 */}
      <div className="flex items-center gap-2 shrink-0">
        <button
          onClick={toggleRightPanel}
          className={cn(
            "inline-flex items-center justify-center w-9 h-9 rounded-md transition-colors",
            rightPanelOpen ? "text-primary bg-primary-soft" : "text-ink-secondary hover:bg-primary-subtle hover:text-primary",
          )}
          aria-label="切换右侧面板"
        >
          <PanelRight className="w-[18px] h-[18px]" strokeWidth={2} />
        </button>

        <div className="w-px h-6 bg-line-soft mx-1" />

        <div ref={menuRef} className="relative">
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="w-9 h-9 rounded-full bg-primary-soft text-primary-active flex items-center justify-center text-small font-semibold cursor-pointer hover:ring-2 hover:ring-primary/20 transition-all"
          >
            {user?.nickname?.charAt(0) || "?"}
          </button>
          {menuOpen && (
            <div className="absolute right-0 top-11 w-48 bg-surface border border-line-soft rounded-lg shadow-md py-1 z-50 animate-in fade-in slide-in-from-top-1">
              <div className="px-3 py-2 border-b border-line-soft">
                <div className="text-small font-medium text-ink-primary">{user?.nickname || "用户"}</div>
                <div className="text-caption text-ink-tertiary truncate">{user?.email || ""}</div>
              </div>
              <button
                onClick={handleLogout}
                className="w-full flex items-center gap-2.5 px-3 py-2.5 text-small text-ink-secondary hover:text-danger hover:bg-danger-soft transition-colors"
              >
                <LogOut className="w-4 h-4" strokeWidth={2} />
                退出登录
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
