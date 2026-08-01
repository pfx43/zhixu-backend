import * as React from "react"
import { cn } from "@/lib/utils"

/** 知拾输入框 · 对应设计第 10.2 节 */
const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type = "text", ...props }, ref) => {
    return (
      <input
        ref={ref}
        type={type}
        data-slot="input"
        className={cn(
          "h-10 w-full rounded-md bg-surface border border-line px-3.5 text-body text-ink-primary placeholder:text-ink-tertiary",
          "focus:outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/10 transition-all",
          "disabled:opacity-50 disabled:cursor-not-allowed",
          className
        )}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"

export { Input }
