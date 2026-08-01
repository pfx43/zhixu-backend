import type { ReactNode } from "react"
import { Sparkles, ArrowRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

/** 智能推荐重点卡片 · 对应设计 12.1 智能推荐模块 */
interface RecommendCardProps {
  title: string
  highlight: string
  description: string
  actionLabel?: string
  onAction?: () => void
  className?: string
  children?: ReactNode
}

export function RecommendCard({
  title,
  highlight,
  description,
  actionLabel = "查看推荐内容",
  onAction,
  className,
}: RecommendCardProps) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl bg-card-elevated border border-primary/15 shadow-primary p-6",
        className
      )}
    >
      {/* 装饰性背景图形 - 透明度 6-10% */}
      <svg
        className="absolute -right-8 -top-8 w-56 h-56 text-primary opacity-[0.08] pointer-events-none"
        viewBox="0 0 200 200"
        fill="none"
        aria-hidden
      >
        <circle cx="100" cy="100" r="80" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="100" cy="100" r="55" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="100" cy="100" r="30" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="100" cy="20" r="6" fill="currentColor" />
        <circle cx="180" cy="100" r="5" fill="currentColor" />
        <circle cx="100" cy="155" r="4" fill="currentColor" />
        <line x1="100" y1="20" x2="100" y2="100" stroke="currentColor" strokeWidth="1" />
        <line x1="180" y1="100" x2="100" y2="100" stroke="currentColor" strokeWidth="1" />
        <line x1="100" y1="155" x2="100" y2="100" stroke="currentColor" strokeWidth="1" />
      </svg>

      <div className="relative">
        <div className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full bg-primary/10 text-primary text-small font-medium mb-4">
          <Sparkles className="w-3.5 h-3.5" strokeWidth={2} />
          {title}
        </div>
        <div className="text-card-title font-semibold text-ink-primary mb-2 max-w-md">
          {highlight}
        </div>
        <p className="text-caption text-ink-secondary max-w-md leading-relaxed mb-5">{description}</p>
        <Button variant="primary" size="md" onClick={onAction}>
          {actionLabel}
          <ArrowRight className="w-4 h-4" strokeWidth={2} />
        </Button>
      </div>
    </div>
  )
}
