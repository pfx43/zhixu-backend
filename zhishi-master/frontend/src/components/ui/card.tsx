import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

/**
 * 知拾卡片 · 对应设计第 10.3 节
 * variant:
 *   - default   白底 + 浅边框 + 轻阴影 (默认)
 *   - soft      浅灰底，无边框
 *   - elevated  重点卡片，渐变底 + 紫色阴影
 */
const cardVariants = cva(
  "rounded-lg flex flex-col text-ink-primary",
  {
    variants: {
      variant: {
        default: "bg-surface border border-line-soft shadow-xs",
        soft: "bg-surface-soft border border-transparent",
        elevated: "bg-card-elevated border border-primary/15 shadow-primary",
        flat: "bg-surface border border-line-soft",
      },
    },
    defaultVariants: { variant: "default" },
  }
)

function Card({
  className,
  variant,
  ...props
}: React.ComponentProps<"div"> & VariantProps<typeof cardVariants>) {
  return (
    <div
      data-slot="card"
      className={cn(cardVariants({ variant }), className)}
      {...props}
    />
  )
}

function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-header"
      className={cn("px-6 pt-6 pb-2 flex flex-col gap-1.5", className)}
      {...props}
    />
  )
}

function CardTitle({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-title"
      className={cn("text-card-title font-semibold text-ink-primary", className)}
      {...props}
    />
  )
}

function CardDescription({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-description"
      className={cn("text-caption text-ink-secondary", className)}
      {...props}
    />
  )
}

function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="card-content" className={cn("px-6 pb-6", className)} {...props} />
}

function CardFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-footer"
      className={cn("px-6 pb-6 pt-2 flex items-center", className)}
      {...props}
    />
  )
}

function CardAction({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-action"
      className={cn("px-6 pt-6 self-end", className)}
      {...props}
    />
  )
}

export { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter, CardAction, cardVariants }
