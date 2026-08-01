import type { ReactNode } from "react"
import { Check, X, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

export type TimelineStatus = "success" | "warning" | "error" | "loading" | "neutral"

interface TimelineStepProps {
  index?: number
  title: string
  description?: ReactNode
  status?: TimelineStatus
  isLast?: boolean
  className?: string
}

const statusConfig: Record<TimelineStatus, { dot: string; icon: typeof Check }> = {
  success: { dot: "bg-success text-white", icon: Check },
  warning: { dot: "bg-warning text-white", icon: X },
  error: { dot: "bg-danger text-white", icon: X },
  loading: { dot: "bg-primary text-white", icon: Loader2 },
  neutral: { dot: "bg-surface-soft text-ink-tertiary border border-line", icon: Check },
}

/** 时间线项 · 用于诊断排查、学习路径 */
export function TimelineStep({ index, title, description, status = "neutral", isLast, className }: TimelineStepProps) {
  const cfg = statusConfig[status]
  const Icon = cfg.icon
  return (
    <div className={cn("flex gap-3", className)}>
      <div className="flex flex-col items-center">
        <div
          className={cn(
            "w-6 h-6 rounded-full flex items-center justify-center shrink-0 text-small font-semibold",
            cfg.dot
          )}
        >
          {status === "loading" ? (
            <Icon className="w-3.5 h-3.5 animate-spin" strokeWidth={2.5} />
          ) : status === "success" || status === "warning" || status === "error" ? (
            <Icon className="w-3.5 h-3.5" strokeWidth={2.5} />
          ) : (
            <span>{index}</span>
          )}
        </div>
        {!isLast && <div className="w-px flex-1 bg-line-soft mt-1 min-h-[20px]" />}
      </div>
      <div className={cn("flex-1 pb-5", isLast && "pb-0")}>
        <div className="text-body text-ink-primary font-medium leading-tight">{title}</div>
        {description && <div className="text-small text-ink-secondary mt-1 leading-relaxed">{description}</div>}
      </div>
    </div>
  )
}
