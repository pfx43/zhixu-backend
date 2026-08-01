import { Sparkles } from "lucide-react"
import type { ChatMessage as ChatMessageType, Citation } from "@/types"
import { CitationCard } from "@/components/blocks/CitationCard"
import { MarkdownWithMath } from "@/components/blocks/MarkdownWithMath"
import { cn } from "@/lib/utils"

interface ChatMessageProps {
  message: ChatMessageType
  className?: string
  onCitationClick?: (citation: Citation) => void
}

export function ChatMessage({ message, className, onCitationClick }: ChatMessageProps) {
  const isUser = message.role === "user"

  if (isUser) {
    return (
      <div className={cn("flex justify-end animate-msg-in", className)}>
        <div className="max-w-[72%] bg-primary text-white rounded-lg rounded-tr-sm px-4 py-2.5 text-body leading-relaxed shadow-xs">
          {message.content}
        </div>
      </div>
    )
  }

  return (
    <div className={cn("flex gap-3 animate-msg-in", className)}>
      <div className="w-8 h-8 rounded-full bg-gradient-primary flex items-center justify-center shrink-0 shadow-primary mt-0.5">
        <Sparkles className="w-4 h-4 text-white" strokeWidth={2} />
      </div>
      <div className="flex-1 min-w-0 text-body text-ink-primary leading-relaxed">
        <div className="text-card-title font-semibold text-ink-primary mb-2 flex items-center gap-1.5">
          Tina
          <span className="text-small text-ink-tertiary font-normal">· 知识库助手</span>
        </div>
        <MarkdownWithMath>{message.content}</MarkdownWithMath>
        {message.citations && message.citations.length > 0 && (
          <div className="mt-4 pt-3 border-t border-line-soft space-y-2">
            <div className="text-small text-ink-tertiary">引用来源：</div>
            {message.citations.map((c, i) => (
              <CitationCard
                key={i}
                citation={c}
                variant="inline"
                onSelect={onCitationClick}
              />
            ))}
          </div>
        )}
        {message.refs && message.refs.length > 0 && (
          <div className="mt-4 pt-3 border-t border-line-soft space-y-1">
            <div className="text-small text-ink-tertiary">引用文档：</div>
            {message.refs.map((ref, i) => (
              <div key={i} className="text-small text-ink-secondary">📄 {ref}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
