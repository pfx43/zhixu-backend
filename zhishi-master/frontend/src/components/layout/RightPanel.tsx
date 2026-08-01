import type { ReactNode } from "react"
import { X } from "lucide-react"
import { useUI } from "@/context/UIContext"
import { cn } from "@/lib/utils"

interface RightPanelProps {
  title?: string
  children?: ReactNode
}

/** 右侧辅助栏。无 children 时不渲染。 */
export function RightPanel({ title, children }: RightPanelProps) {
  const { rightPanelOpen, setRightPanelOpen } = useUI()

  if (!children) return null

  return (
    <>
      {/* 移动端遮罩 */}
      {rightPanelOpen && (
        <div
          className="fixed inset-0 bg-ink-primary/20 backdrop-blur-[2px] xl:hidden z-40"
          onClick={() => setRightPanelOpen(false)}
        />
      )}
      <aside
        className={cn(
          "shrink-0 border-l border-line-soft bg-surface overflow-y-auto scroll-thin transition-all duration-220",
          "fixed xl:static right-0 top-16 bottom-0 z-40 xl:z-auto",
          rightPanelOpen ? "w-[340px] translate-x-0" : "w-[340px] translate-x-full xl:hidden",
        )}
      >
        <div className="sticky top-0 bg-surface/90 backdrop-blur-md border-b border-line-soft px-5 h-14 flex items-center justify-between">
          <div className="text-card-title font-semibold text-ink-primary">{title ?? "上下文"}</div>
          <button
            onClick={() => setRightPanelOpen(false)}
            className="w-7 h-7 rounded-md flex items-center justify-center text-ink-tertiary hover:bg-surface-soft hover:text-ink-primary transition-colors xl:hidden"
            aria-label="关闭面板"
          >
            <X className="w-4 h-4" strokeWidth={2} />
          </button>
        </div>
        <div className="p-5 animate-panel-in">{children}</div>
      </aside>
    </>
  )
}
