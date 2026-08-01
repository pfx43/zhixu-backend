import * as React from "react"
import { cn } from "@/lib/utils"

/** 骨架屏 · 对应设计第 16.2 节加载态 */
function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("animate-pulse rounded-md bg-surface-soft", className)}
      {...props}
    />
  )
}

export { Skeleton }
