import type { LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"

interface SegmentedTabsProps {
  tabs: { label: string; value: string; icon?: LucideIcon }[]
  value: string
  onChange: (v: string) => void
  className?: string
  size?: "sm" | "md"
}

/** 分段切换 · 用于 Tab 视图切换、模式切换 */
export function SegmentedTabs({ tabs, value, onChange, className, size = "md" }: SegmentedTabsProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-1 p-1 rounded-md bg-surface-soft border border-line-soft",
        className
      )}
      role="tablist"
    >
      {tabs.map((tab) => {
        const active = tab.value === value
        const Icon = tab.icon
        return (
          <button
            key={tab.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(tab.value)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-sm font-medium transition-all duration-160",
              size === "sm" ? "h-7 px-3 text-small" : "h-8 px-3.5 text-caption",
              active
                ? "bg-surface text-ink-primary shadow-xs"
                : "text-ink-secondary hover:text-ink-primary"
            )}
          >
            {Icon && <Icon className="w-4 h-4" strokeWidth={2} />}
            {tab.label}
          </button>
        )
      })}
    </div>
  )
}
