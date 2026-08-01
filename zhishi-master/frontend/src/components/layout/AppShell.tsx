import type { ReactNode } from "react"
import { Sidebar } from "./Sidebar"
import { Topbar } from "./Topbar"
import { cn } from "@/lib/utils"

interface AppShellProps {
  children: ReactNode
  /** 主内容区最大宽度 px，null 表示全宽 */
  maxWidth?: number | null
  /** 是否禁用横向内边距（如全宽对话页） */
  noPadding?: boolean
}

/**
 * 三栏布局容器：Sidebar + Topbar + Main。
 * 右侧面板由各页面自行通过 <RightPanel /> 注入（按需出现）。
 */
export function AppShell({ children, maxWidth = 1180, noPadding = false }: AppShellProps) {
  return (
    <div className="relative flex h-screen overflow-hidden bg-bg">
      <Sidebar />
      <div className="relative flex-1 flex flex-col min-w-0">
        <Topbar />
        <main
          className={cn(
            "flex-1 bg-bg",
            noPadding ? "overflow-hidden" : "overflow-y-auto scroll-thin p-8",
          )}
        >
          <div
            className={cn("mx-auto w-full animate-page-in", noPadding && "h-full")}
            style={maxWidth ? { maxWidth } : undefined}
          >
            {children}
          </div>
        </main>
      </div>
    </div>
  )
}
