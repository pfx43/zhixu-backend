import { Badge } from "@/components/ui/badge"
import type { VariantProps } from "class-variance-authority"
import { badgeVariants } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

export interface DocumentPipelineInfo {
  segment_status?: string
  question_gen_status?: string
  questionCount?: number
  zone?: string
}

type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>["variant"]>

export function getDocumentPipelineStatus(
  info: DocumentPipelineInfo
): { label: string; variant: BadgeVariant } | null {
  if (info.zone === "life") {
    return { label: "仅检索", variant: "neutral" }
  }

  const seg = info.segment_status || "not_started"
  const qgen = info.question_gen_status || "not_started"

  if (seg === "failed" || qgen === "failed") {
    return { label: "处理失败", variant: "danger" }
  }
  if (seg === "processing") {
    return { label: "分段中", variant: "warning" }
  }
  if (qgen === "processing") {
    return { label: "出题中", variant: "warning" }
  }
  if (qgen === "completed" && (info.questionCount ?? 0) > 0) {
    return { label: `题库 · ${info.questionCount} 题`, variant: "primary" }
  }
  if (qgen === "completed") {
    return { label: "已出题", variant: "primary" }
  }
  if (seg === "completed") {
    return { label: "已分段", variant: "success" }
  }
  if (seg === "not_started") {
    return { label: "待分段", variant: "neutral" }
  }

  return null
}

export function formatDocumentOptionLabel(
  name: string,
  info: DocumentPipelineInfo
): string {
  const status = getDocumentPipelineStatus(info)
  const parts = [name]
  if (status && info.zone !== "life") {
    parts.push(status.label)
  } else if (info.zone === "life") {
    parts.push("仅学习区可练习")
  }
  return parts.join(" · ")
}

interface DocumentPipelineBadgeProps extends DocumentPipelineInfo {
  className?: string
  size?: "sm" | "md"
}

/** 文档分段/出题进度徽章 */
export function DocumentPipelineBadge({
  className,
  size = "sm",
  ...info
}: DocumentPipelineBadgeProps) {
  const status = getDocumentPipelineStatus(info)
  if (!status) return null

  return (
    <Badge variant={status.variant} size={size} className={cn(className)}>
      {status.label}
    </Badge>
  )
}
