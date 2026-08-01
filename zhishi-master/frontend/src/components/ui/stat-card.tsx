import * as React from "react"
import type { LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"

/**
 * 知拾统计卡片 · 用于概览数字展示
 * 浅色图标容器 + 标签 + 数值 + 可选副标题。
 */
interface StatCardProps {
  icon: LucideIcon
  label: string
  value: React.ReactNode
  hint?: string
  trend?: "up" | "down" | "flat"
  className?: string
  /** 图标容器色调 */
  tone?: "primary" | "success" | "warning" | "info" | "neutral"
}

const toneMap = {
  primary: "bg-primary-soft text-primary",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  info: "bg-info-soft text-info",
  neutral: "bg-surface-soft text-ink-secondary",
}

export function StatCard({ icon: Icon, label, value, hint, className, tone = "neutral" }: StatCardProps) {
  return (
    <div className={cn("bg-surface border border-line-soft rounded-lg p-5 flex items-start gap-4 shadow-xs", className)}>
      <div className={cn("w-10 h-10 rounded-md flex items-center justify-center shrink-0", toneMap[tone])}>
        <Icon className="w-5 h-5" strokeWidth={2} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-small text-ink-tertiary mb-1">{label}</div>
        <div className="text-section-title font-semibold text-ink-primary leading-tight truncate-1">{value}</div>
        {hint && <div className="text-small text-ink-tertiary mt-1 truncate-1">{hint}</div>}
      </div>
    </div>
  )
}
