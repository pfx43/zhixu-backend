import { useEffect, useState } from "react"
import { Loader2 } from "lucide-react"
import { MarkdownWithMath } from "@/components/blocks/MarkdownWithMath"
import { renderHighlightedContent } from "@/components/blocks/DocumentPreviewModal"
import { kbApi } from "@/lib/api"
import { cn } from "@/lib/utils"

interface DocumentContentViewerProps {
  docId: string
  previewMode?: "pdf" | "text" | "markdown"
  content?: string
  pageNumber?: number | null
  charStart?: number | null
  charEnd?: number | null
  className?: string
}

export function DocumentContentViewer({
  docId,
  previewMode = "text",
  content = "",
  pageNumber = null,
  charStart = null,
  charEnd = null,
  className,
}: DocumentContentViewerProps) {
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)
  const [loadingPdf, setLoadingPdf] = useState(false)
  const [pdfError, setPdfError] = useState<string | null>(null)

  const showPdf = previewMode === "pdf"

  useEffect(() => {
    if (!showPdf || !docId) {
      setPdfUrl(null)
      return
    }

    let cancelled = false
    let objectUrl: string | null = null
    setLoadingPdf(true)
    setPdfError(null)

    kbApi
      .fetchDocumentFile(docId)
      .then((blob) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setPdfUrl(objectUrl)
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setPdfUrl(null)
          setPdfError(err.message || "PDF 加载失败")
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingPdf(false)
      })

    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [docId, showPdf, pageNumber])

  if (showPdf) {
    if (loadingPdf) {
      return (
        <div className={cn("flex items-center justify-center py-16 text-ink-tertiary", className)}>
          <Loader2 className="h-5 w-5 animate-spin mr-2" />
          加载 PDF…
        </div>
      )
    }
    if (pdfError) {
      return <div className={cn("p-5 text-body text-danger", className)}>{pdfError}</div>
    }
    if (!pdfUrl) {
      return (
        <div className={cn("p-5 text-body text-ink-tertiary", className)}>
          原始 PDF 不可用
        </div>
      )
    }

    const pdfSrc = pageNumber != null ? `${pdfUrl}#page=${pageNumber}` : pdfUrl

    return (
      <div className={cn("flex flex-col gap-4 min-h-0", className)}>
        <iframe
          key={pageNumber ?? "all"}
          title="PDF 预览"
          src={pdfSrc}
          className="w-full min-h-[560px] flex-1 border-0 bg-surface-soft rounded-md"
        />
        {content.trim() ? (
          <div className="border-t border-line-soft pt-4">
            <p className="text-caption text-ink-tertiary mb-2">OCR / 解析文本</p>
            <MarkdownWithMath className="text-body leading-relaxed">
              {content}
            </MarkdownWithMath>
          </div>
        ) : null}
      </div>
    )
  }

  if (previewMode === "markdown") {
    return (
      <MarkdownWithMath className={cn("text-body leading-relaxed", className)}>
        {content || "（空白页）"}
      </MarkdownWithMath>
    )
  }

  return (
    <pre className={cn("text-body text-ink-primary whitespace-pre-wrap font-sans leading-relaxed", className)}>
      {renderHighlightedContent(content, charStart, charEnd)}
    </pre>
  )
}
