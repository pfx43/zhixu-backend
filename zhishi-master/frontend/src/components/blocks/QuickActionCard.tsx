import type { LucideIcon } from "lucide-react"
import { ChevronRight } from "lucide-react"
import { cn } from "@/lib/utils"

/** 快捷操作卡片 · 首页横向 4 卡片 */
interface QuickActionCardProps {
  icon: LucideIcon
  title: string
  description: string
  onClick?: () => void
  className?: string
}

export function QuickActionCard({ icon: Icon, title, description, onClick, className }: QuickActionCardProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "group text-left bg-surface border border-line-soft rounded-lg p-5 shadow-xs",
        "hover:-translate-y-0.5 hover:shadow-md hover:border-primary/30 transition-all duration-160",
        className
      )}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="w-10 h-10 rounded-md bg-primary-soft text-primary flex items-center justify-center group-hover:bg-primary group-hover:text-white transition-colors">
          <Icon className="w-5 h-5" strokeWidth={2} />
        </div>
        <ChevronRight className="w-4 h-4 text-ink-tertiary group-hover:text-primary group-hover:translate-x-0.5 transition-all" strokeWidth={2} />
      </div>
      <div className="text-card-title font-semibold text-ink-primary mb-1">{title}</div>
      <div className="text-small text-ink-tertiary leading-relaxed truncate-2">{description}</div>
    </button>
  )
}
