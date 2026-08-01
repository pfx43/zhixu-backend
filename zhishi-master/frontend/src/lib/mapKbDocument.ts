import type { KnowledgeDoc } from "@/types"

export function mapFileType(d: Record<string, unknown>): KnowledgeDoc["type"] {
  const name = String(d.name || d.file_name || "").toLowerCase()
  if (name.endsWith(".pdf")) return "pdf"
  if (name.endsWith(".txt")) return "txt"
  if (name.endsWith(".md")) return "md"
  if (name.endsWith(".docx") || name.endsWith(".doc")) return "docx"
  return "txt"
}

export function mapStatus(d: Record<string, unknown>): KnowledgeDoc["status"] {
  if (String(d.ocr_status || "").toLowerCase() === "processing") return "processing"
  const s = String(d.indexing_status || d.status || "").toLowerCase()
  if (s === "completed" || s === "indexed") return "indexed"
  if (s === "processing" || s === "parsing" || s === "splitting" || s === "indexing")
    return "processing"
  if (s === "error" || s === "failed") return "failed"
  return "pending"
}

export function mapKbDocument(d: Record<string, unknown>, zone?: string): KnowledgeDoc {
  return {
    id: String(d.id),
    name: String(d.name || d.file_name || d.id),
    type: mapFileType(d),
    tags: (d.tags as string[]) || [],
    status: mapStatus(d),
    segment_status: String(d.segment_status || "not_started"),
    question_gen_status: String(d.question_gen_status || "not_started"),
    ocr_status: d.ocr_status ? String(d.ocr_status) : undefined,
    ocr_current_page: d.ocr_current_page != null ? Number(d.ocr_current_page) : undefined,
    ocr_total_pages: d.ocr_total_pages != null ? Number(d.ocr_total_pages) : undefined,
    zone: zone || (d.zone ? String(d.zone) : undefined),
    wordCount: Number(d.word_count || d.wordCount || 0),
    updatedAt: String(d.updated_at || d.updatedAt || "—"),
  }
}
