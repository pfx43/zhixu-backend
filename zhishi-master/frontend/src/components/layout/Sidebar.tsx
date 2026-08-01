import { NavLink } from "react-router-dom"
import { Sparkles, ChevronLeft } from "lucide-react"
import { navGroups } from "@/data/nav"
import { useUI } from "@/context/UIContext"
import { useAuth } from "@/context/AuthContext"
import { cn } from "@/lib/utils"

export function Sidebar() {
  const { sidebarCollapsed, toggleSidebar } = useUI()
  const { user } = useAuth()

  return (
    <aside
      className={cn(
        "bg-sidebar-glass border-r border-line-soft flex flex-col shrink-0 transition-all duration-220",
        sidebarCollapsed ? "w-[72px]" : "w-[248px]",
      )}
    >
      {/* Logo */}
      <div className="h-16 flex items-center px-5 shrink-0">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-9 h-9 rounded-xl bg-gradient-primary flex items-center justify-center shadow-primary shrink-0">
            <Sparkles className="w-5 h-5 text-white" strokeWidth={2} />
          </div>
          {!sidebarCollapsed && (
            <div className="min-w-0">
              <div className="text-card-title text-ink-primary leading-tight">知拾</div>
              <div className="text-small text-ink-tertiary leading-tight">AI 知识工作台</div>
            </div>
          )}
        </div>
      </div>

      {/* 导航 */}
      <nav className="flex-1 overflow-y-auto scroll-thin px-3 py-2 space-y-4">
        {navGroups.map((group, gi) => (
          <div key={gi} className="space-y-0.5">
            {group.title && !sidebarCollapsed && (
              <div className="px-3 pt-2 pb-1.5 text-small font-medium text-ink-tertiary uppercase tracking-wider">
                {group.title}
              </div>
            )}
            {group.title && sidebarCollapsed && (
              <div className="mx-3 my-2 border-t border-line-soft" />
            )}
            {group.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  cn(
                    "group relative flex items-center gap-3 rounded-md px-3 h-10 text-body transition-all duration-160",
                    sidebarCollapsed && "justify-center px-0",
                    isActive
                      ? "bg-primary-soft text-primary-active font-medium"
                      : "text-ink-secondary hover:bg-primary-subtle hover:text-ink-primary",
                  )
                }
                title={sidebarCollapsed ? item.label : undefined}
              >
                {({ isActive }) => (
                  <>
                    {isActive && !sidebarCollapsed && (
                      <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-full bg-primary" />
                    )}
                    <item.icon
                      className={cn(
                        "w-[18px] h-[18px] shrink-0",
                        isActive ? "text-primary" : "text-ink-tertiary group-hover:text-primary",
                      )}
                      strokeWidth={2}
                    />
                    {!sidebarCollapsed && <span className="truncate-1">{item.label}</span>}
                  </>
                )}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      {/* 底部用户区 */}
      <div className="border-t border-line-soft p-3 shrink-0">
        <div className={cn("flex items-center gap-2.5 rounded-md p-2", !sidebarCollapsed && "hover:bg-surface-soft cursor-pointer transition-colors")}>
          <div className="w-8 h-8 rounded-full bg-primary-soft text-primary-active flex items-center justify-center text-small font-semibold shrink-0">
            {user?.nickname?.charAt(0) || "?"}
          </div>
          {!sidebarCollapsed && (
            <div className="min-w-0 flex-1">
              <div className="text-body text-ink-primary leading-tight truncate-1">{user?.nickname || "未登录"}</div>
              <div className="text-small text-ink-tertiary leading-tight">个人学习画像</div>
            </div>
          )}
        </div>
      </div>

      {/* 折叠按钮 */}
      <button
        onClick={toggleSidebar}
        className="absolute top-7 -right-3 w-6 h-6 rounded-full bg-surface border border-line-soft shadow-sm flex items-center justify-center text-ink-tertiary hover:text-primary hover:border-primary/40 transition-colors"
        style={{ zIndex: 30 }}
        aria-label="折叠侧边栏"
      >
        <ChevronLeft className={cn("w-3.5 h-3.5 transition-transform duration-220", sidebarCollapsed && "rotate-180")} />
      </button>
    </aside>
  )
}
