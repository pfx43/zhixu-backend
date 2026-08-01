import type { ReactNode } from "react"
import { ExternalLink } from "lucide-react"
import { useNavigate } from "react-router-dom"
import type { Citation } from "@/types"
import { cn } from "@/lib/utils"

export function getDocumentViewPath(
  docId: string,
  options?: {
    title?: string | null
    charStart?: number | null
    charEnd?: number | null
  }
): string {
  const params = new URLSearchParams()
  if (options?.title) params.set("title", options.title)
  if (options?.charStart != null) params.set("start", String(options.charStart))
  if (options?.charEnd != null) params.set("end", String(options.charEnd))
  const qs = params.toString()
  return `/knowledge/doc/${docId}${qs ? `?${qs}` : ""}`
}

/** 跳转到文档查看页 */
export function ViewDocumentButton({
  docId,
  title,
  charStart,
  charEnd,
  className,
  label = "查看文档",
  showIcon = false,
}: {
  docId: string
  title?: string | null
  charStart?: number | null
  charEnd?: number | null
  className?: string
  label?: string
  showIcon?: boolean
}) {
  const navigate = useNavigate()

  return (
    <button
      type="button"
      onClick={() =>
        navigate(getDocumentViewPath(docId, { title, charStart, charEnd }))
      }
      className={cn(
        "inline-flex items-center gap-1 text-small text-primary hover:underline",
        className
      )}
    >
      {showIcon && <ExternalLink className="w-3.5 h-3.5 shrink-0" strokeWidth={2} />}
      {label}
    </button>
  )
}

/** 从 citation 跳转到文档查看页 */
export function CitationViewDocumentButton({
  citation,
  className,
  label = "查看文档",
}: {
  citation: Citation
  className?: string
  label?: string
}) {
  if (!citation.doc_id) return null

  return (
    <ViewDocumentButton
      docId={citation.doc_id}
      title={citation.title}
      charStart={citation.char_start}
      charEnd={citation.char_end}
      className={className}
      label={label}
      showIcon
    />
  )
}

export function renderHighlightedContent(
  content: string,
  start?: number | null,
  end?: number | null
): ReactNode {
  if (
    start == null ||
    end == null ||
    start < 0 ||
    end <= start ||
    start >= content.length
  ) {
    return content
  }
  const safeEnd = Math.min(end, content.length)
  return (
    <>
      {content.slice(0, start)}
      <mark className="bg-warning-soft text-ink-primary rounded-sm px-0.5">
        {content.slice(start, safeEnd)}
      </mark>
      {content.slice(safeEnd)}
    </>
  )
}
