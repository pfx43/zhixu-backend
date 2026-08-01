import { cn } from "@/lib/utils"

interface ProgressMeterProps {
  label: string
  value: number // 0-100
  /** 阈值：低于此值显示警告色 */
  warningBelow?: number
  className?: string
  showValue?: boolean
}

/** 掌握度进度条 · 对应设计 12.7 可信度评分 */
export function ProgressMeter({ label, value, warningBelow = 50, className, showValue = true }: ProgressMeterProps) {
  const tone = value >= 70 ? "primary" : value >= warningBelow ? "info" : "warning"
  const barColor =
    tone === "primary" ? "bg-primary" : tone === "info" ? "bg-info" : "bg-warning"

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-caption text-ink-primary truncate-1">{label}</span>
        {showValue && (
          <span
            className={cn(
              "text-small font-semibold tabular-nums",
              tone === "primary" ? "text-primary" : tone === "info" ? "text-info" : "text-warning"
            )}
          >
            {value.toFixed(0)}%
          </span>
        )}
      </div>
      <div className="h-2 rounded-full bg-surface-soft overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all duration-500", barColor)}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  )
}
