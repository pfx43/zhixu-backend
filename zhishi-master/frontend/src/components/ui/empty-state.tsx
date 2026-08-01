import type { LucideIcon } from "lucide-react"
import { Button } from "./button"
import { cn } from "@/lib/utils"

/**
 * 知拾空状态 · 对应设计第 10.5 节
 * 全站空状态统一使用此组件，结构：图标容器 / 标题 / 说明 / 主操作 / 次操作。
 */
interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description?: string
  primaryAction?: { label: string; onClick?: () => void }
  secondaryAction?: { label: string; onClick?: () => void }
  className?: string
  size?: "sm" | "md" | "lg"
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  primaryAction,
  secondaryAction,
  className,
  size = "md",
}: EmptyStateProps) {
  const containerSize = size === "lg" ? "w-20 h-20" : size === "sm" ? "w-12 h-12" : "w-16 h-16"
  const iconSize = size === "lg" ? "w-9 h-9" : size === "sm" ? "w-5 h-5" : "w-7 h-7"
  const iconRadius = size === "lg" ? "rounded-xl" : "rounded-md"

  return (
    <div className={cn("flex flex-col items-center justify-center text-center py-14 px-6", className)}>
      <div className={cn("flex items-center justify-center bg-primary-soft text-primary mb-5", containerSize, iconRadius)}>
        <Icon className={iconSize} strokeWidth={2} />
      </div>
      <h3 className="text-card-title font-semibold text-ink-primary mb-1.5">{title}</h3>
      {description && (
        <p className="text-caption text-ink-secondary max-w-sm leading-relaxed mb-6">{description}</p>
      )}
      {(primaryAction || secondaryAction) && (
        <div className="flex items-center gap-3 flex-wrap justify-center">
          {primaryAction && (
            <Button variant="primary" onClick={primaryAction.onClick}>
              {primaryAction.label}
            </Button>
          )}
          {secondaryAction && (
            <Button variant="secondary" onClick={secondaryAction.onClick}>
              {secondaryAction.label}
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
