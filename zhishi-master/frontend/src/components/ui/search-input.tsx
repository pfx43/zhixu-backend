import * as React from "react"
import { Search } from "lucide-react"
import { cn } from "@/lib/utils"

/** 搜索输入框，左侧带搜索图标 */
const SearchInput = React.forwardRef<
  HTMLInputElement,
  React.ComponentProps<"input"> & { icon?: React.ReactNode }
>(({ className, placeholder = "搜索...", icon, ...props }, ref) => {
  return (
    <div className="relative group">
      <Search
        className="absolute left-3.5 top-1/2 -translate-y-1/2 w-[18px] h-[18px] text-ink-tertiary group-focus-within:text-primary transition-colors"
        strokeWidth={2}
      />
      <input
        ref={ref}
        type="text"
        placeholder={placeholder}
        data-slot="search-input"
        className={cn(
          "w-full h-10 pl-11 pr-4 rounded-md bg-surface border border-line text-body text-ink-primary placeholder:text-ink-tertiary",
          "focus:outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/10 transition-all",
          className
        )}
        {...props}
      />
      {icon && <div className="absolute right-3 top-1/2 -translate-y-1/2">{icon}</div>}
    </div>
  )
})
SearchInput.displayName = "SearchInput"

export { SearchInput }
