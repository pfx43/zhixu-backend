import * as React from "react"
import { cn } from "@/lib/utils"

/** 模块标题区 · 模块标题 + 可选副标题 + 可选右侧操作 */
interface SectionHeaderProps {
  title: string
  subtitle?: string
  children?: React.ReactNode
  className?: string
}

export function SectionHeader({ title, subtitle, children, className }: SectionHeaderProps) {
  return (
    <div className={cn("flex items-center justify-between gap-4 mb-4", className)}>
      <div className="min-w-0">
        <h2 className="text-section-title text-ink-primary leading-tight">{title}</h2>
        {subtitle && <p className="text-caption text-ink-tertiary mt-0.5">{subtitle}</p>}
      </div>
      {children && <div className="flex items-center gap-2 shrink-0">{children}</div>}
    </div>
  )
}
