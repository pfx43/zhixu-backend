import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

/**
 * 知拾状态标签 · 用于文档状态、学习状态等
 * 仅用于状态提示，不作为页面主视觉。
 */
const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full font-medium whitespace-nowrap",
  {
    variants: {
      variant: {
        neutral: "bg-surface-soft text-ink-secondary border border-line-soft",
        primary: "bg-primary-soft text-primary-active border border-primary/20",
        success: "bg-success-soft text-success border border-success/20",
        warning: "bg-warning-soft text-warning border border-warning/20",
        danger: "bg-danger-soft text-danger border border-danger/20",
        info: "bg-info-soft text-info border border-info/20",
      },
      size: {
        sm: "h-5 px-2 text-small",
        md: "h-6 px-2.5 text-small",
      },
    },
    defaultVariants: { variant: "neutral", size: "sm" },
  }
)

function Badge({
  className,
  variant,
  size,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span data-slot="badge" className={cn(badgeVariants({ variant, size }), className)} {...props} />
}

export { Badge, badgeVariants }
