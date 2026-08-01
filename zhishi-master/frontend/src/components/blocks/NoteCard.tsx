import { NotebookPen, Sparkles, Clock } from "lucide-react"
import type { Note } from "@/types"
import { Chip } from "@/components/ui/chip"
import { cn } from "@/lib/utils"

interface NoteCardProps {
  note: Note
  onClick?: () => void
  className?: string
}

export function NoteCard({ note, onClick, className }: NoteCardProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "group text-left bg-surface border border-line-soft rounded-lg p-5 shadow-xs",
        "hover:-translate-y-0.5 hover:shadow-md hover:border-primary/30 transition-all duration-160",
        className
      )}
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <NotebookPen className="w-4 h-4 text-ink-tertiary shrink-0" strokeWidth={2} />
          <h3 className="text-card-title font-semibold text-ink-primary truncate-1 group-hover:text-primary transition-colors">
            {note.title}
          </h3>
        </div>
        {note.hasAISummary && (
          <span className="inline-flex items-center gap-0.5 h-5 px-1.5 rounded-full bg-primary-soft text-primary text-small font-medium shrink-0">
            <Sparkles className="w-3 h-3" strokeWidth={2} />
            AI 摘要
          </span>
        )}
      </div>

      <p className="text-caption text-ink-secondary leading-relaxed mb-3 truncate-2">{note.excerpt}</p>

      {note.tags.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap mb-3">
          {note.tags.slice(0, 4).map((tag) => (
            <Chip key={tag} variant="default" size="sm" className="cursor-default">
              {tag}
            </Chip>
          ))}
        </div>
      )}

      <div className="flex items-center gap-3 text-small text-ink-tertiary">
        <span className="inline-flex items-center gap-1">
          <Clock className="w-3 h-3" strokeWidth={2} />
          {note.updatedAt}
        </span>
        <span>·</span>
        <span>{note.wordCount} 字</span>
        {note.source === "doc" && (
          <>
            <span>·</span>
            <span>来自文档</span>
          </>
        )}
        {note.source === "ai" && (
          <>
            <span>·</span>
            <span>AI 生成</span>
          </>
        )}
      </div>
    </button>
  )
}
