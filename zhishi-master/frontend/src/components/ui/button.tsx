import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

/**
 * 知拾按钮 · 对应设计第 10.1 节
 * variant:
 *   - primary   纯紫主按钮
 *   - gradient  渐变主 CTA / AI 按钮
 *   - secondary 白底浅边框
 *   - ghost     透明，hover 浅灰
 *   - danger    危险操作
 * size: sm(36) / md(40) / lg(44) / xl(48)
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap font-medium transition-all duration-160 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-[18px] shrink-0 [&_svg]:shrink-0 outline-none focus-visible:ring-2 focus-visible:ring-primary/30 active:scale-[0.98]",
  {
    variants: {
      variant: {
        primary: "bg-primary text-white hover:bg-primary-hover shadow-xs hover:shadow-primary",
        gradient: "bg-gradient-primary text-white shadow-primary hover:shadow-lg hover:-translate-y-0.5",
        secondary: "bg-surface text-ink-primary border border-line hover:bg-surface-soft hover:border-line",
        outline: "bg-surface text-ink-primary border border-line hover:bg-surface-soft hover:border-line",
        ghost: "text-ink-secondary hover:bg-surface-soft hover:text-ink-primary",
        danger: "bg-danger text-white hover:bg-danger/90 shadow-xs",
      },
      size: {
        sm: "h-9 px-3 rounded-md text-caption gap-1.5",
        md: "h-10 px-4 rounded-md text-body",
        default: "h-10 px-4 rounded-md text-body",
        lg: "h-11 px-5 rounded-md text-body",
        xl: "h-12 px-6 rounded-md text-body",
        icon: "h-10 w-10 rounded-md",
        "icon-sm": "h-9 w-9 rounded-md",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  }
)

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<"button"> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "button"
  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
