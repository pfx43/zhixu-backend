import { FileText } from "lucide-react"
import type { Citation } from "@/types"
import { CitationViewDocumentButton } from "@/components/blocks/DocumentPreviewModal"
import { cn } from "@/lib/utils"

interface CitationCardProps {
  citation: Citation
  variant?: "default" | "compact" | "inline"
  showIndex?: number
  className?: string
  /** 点击引用标题时回调（如展开聊天侧栏）；不会打开文档页 */
  onSelect?: (citation: Citation) => void
}

/** 统一引用卡片：snippet + 查看文档按钮 */
export function CitationCard({
  citation,
  variant = "default",
  showIndex,
  className,
  onSelect,
}: CitationCardProps) {
  if (!citation.doc_id && !citation.snippet) return null

  const displayTitle = citation.title || citation.snippet?.slice(0, 40) || "引用"

  if (variant === "inline") {
    return (
      <div className={cn("flex flex-wrap items-center gap-x-2 gap-y-1", className)}>
        {onSelect ? (
          <button
            type="button"
            onClick={() => onSelect(citation)}
            className="text-small text-ink-secondary hover:text-primary text-left transition-colors"
          >
            {displayTitle}
          </button>
        ) : (
          <span className="text-small text-ink-secondary">{displayTitle}</span>
        )}
        {citation.doc_id && (
          <CitationViewDocumentButton citation={citation} label="查看文档" />
        )}
      </div>
    )
  }

  return (
    <div
      className={cn(
        "rounded-lg border border-line-soft bg-surface-soft border-l-2 border-l-primary/40",
        variant === "compact" ? "p-2.5 space-y-1.5" : "p-3 space-y-2",
        className
      )}
    >
      <div className="flex items-center gap-1.5 min-w-0">
        <FileText className="w-3.5 h-3.5 text-primary shrink-0" strokeWidth={2} />
        <span className="text-small font-medium text-ink-primary truncate">
          {showIndex != null && `${showIndex}. `}
          {citation.title || "原文引用"}
        </span>
      </div>
      {citation.snippet && (
        <p
          className={cn(
            "text-ink-secondary line-clamp-3",
            variant === "compact" ? "text-caption" : "text-small"
          )}
        >
          {citation.snippet}
        </p>
      )}
      {citation.doc_id && (
        <CitationViewDocumentButton citation={citation} label="查看文档" />
      )}
    </div>
  )
}
