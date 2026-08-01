import type { KnowledgeDoc } from "@/types"
import { Trash2, Eye } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { DocumentPipelineBadge } from "@/components/blocks/DocumentPipelineBadge"
import { cn } from "@/lib/utils"

const typeLabels: Record<KnowledgeDoc["type"], string> = {
  pdf: "PDF",
  txt: "TXT",
  md: "MD",
  docx: "DOCX",
  image: "图片",
  ocr: "OCR",
}

const statusConfig: Record<
  KnowledgeDoc["status"],
  { label: string; variant: "success" | "warning" | "danger" | "neutral" }
> = {
  indexed: { label: "已入库", variant: "success" },
  processing: { label: "处理中", variant: "warning" },
  failed: { label: "解析失败", variant: "danger" },
  pending: { label: "待整理", variant: "neutral" },
}

function statusLabel(doc: KnowledgeDoc): string {
  if (doc.ocr_status === "processing") {
    const total = doc.ocr_total_pages
    const current = doc.ocr_current_page ?? 0
    return total ? `OCR 第 ${current}/${total} 页` : "OCR 识别中"
  }
  return statusConfig[doc.status].label
}

interface DocRowProps {
  doc: KnowledgeDoc
  className?: string
  onDelete?: (e: React.MouseEvent) => void
  onView?: (e: React.MouseEvent) => void
}

/** 知识库文档行 · 表格风格要轻，不像传统后台厚重表格 */
export function DocRow({ doc, className, onDelete, onView }: DocRowProps) {
  const status = statusConfig[doc.status]
  return (
    <div
      className={cn(
        "grid grid-cols-[1fr_auto] sm:grid-cols-[minmax(0,2fr)_auto_auto_auto_auto_auto] gap-x-4 gap-y-2 items-center px-5 py-3.5 hover:bg-surface-soft transition-colors group",
        className
      )}
    >
      {/* 文档名 + 标签 */}
      <div className="min-w-0">
        <div className="text-body text-ink-primary font-medium truncate-1">
          {doc.name}
        </div>
        {doc.tags.length > 0 && (
          <div className="flex items-center gap-1 mt-1 flex-wrap">
            {doc.tags.map((t) => (
              <span key={t} className="text-small text-ink-tertiary">
                #{t}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* 类型 */}
      <div className="hidden sm:block">
        <span className="inline-flex items-center justify-center min-w-[44px] h-6 px-2 rounded-sm bg-surface-soft text-small text-ink-secondary font-medium">
          {typeLabels[doc.type]}
        </span>
      </div>

      {/* 字数 */}
      <div className="hidden sm:block text-small text-ink-tertiary tabular-nums">{doc.wordCount}</div>

      {/* 更新时间 */}
      <div className="hidden sm:block text-small text-ink-tertiary">{doc.updatedAt}</div>

      {/* 状态 */}
      <div className="flex items-center gap-2 justify-self-end flex-wrap justify-end">
        {(doc.segment_status || doc.question_gen_status) && (
          <DocumentPipelineBadge
            segment_status={doc.segment_status}
            question_gen_status={doc.question_gen_status}
            questionCount={doc.questionCount}
            zone={doc.zone}
          />
        )}
        <Badge variant={status.variant}>{statusLabel(doc)}</Badge>
      </div>

      {/* 操作 */}
      <div className="flex items-center justify-end sm:justify-center gap-0.5">
        {onView && (
          <button
            type="button"
            onClick={onView}
            className="w-8 h-8 rounded-md flex items-center justify-center text-ink-tertiary opacity-100 sm:opacity-0 sm:group-hover:opacity-100 hover:bg-primary-soft hover:text-primary transition-all"
            title="查看文档"
            aria-label={`查看 ${doc.name}`}
          >
            <Eye className="w-4 h-4" strokeWidth={2} />
          </button>
        )}
        {onDelete && (
          <button
            type="button"
            onClick={onDelete}
            className="w-8 h-8 rounded-md flex items-center justify-center text-ink-tertiary opacity-100 sm:opacity-0 sm:group-hover:opacity-100 hover:bg-danger-soft hover:text-danger transition-all"
            title="删除文档"
            aria-label={`删除 ${doc.name}`}
          >
            <Trash2 className="w-4 h-4" strokeWidth={2} />
          </button>
        )}
      </div>
    </div>
  )
}
