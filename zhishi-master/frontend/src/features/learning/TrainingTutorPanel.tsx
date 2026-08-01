import { useCallback, useEffect, useRef, useState } from "react"
import { Loader2, Send, Sparkles } from "lucide-react"
import { trainingApi } from "@/lib/api"
import type { TutorMessage } from "@/types"
import { Button } from "@/components/ui/button"
import {
  MarkdownWithMath,
  markdownProseClass,
  markdownProseInvertClass,
} from "@/components/blocks/MarkdownWithMath"
import { cn } from "@/lib/utils"

interface TrainingTutorPanelProps {
  agentSessionId: string
  rationale?: string | null
  className?: string
}

function MessageBody({
  content,
  role,
  isStreamingPlaceholder,
}: {
  content: string
  role: TutorMessage["role"]
  isStreamingPlaceholder?: boolean
}) {
  if (!content) {
    return <span>{isStreamingPlaceholder ? "..." : ""}</span>
  }
  return (
    <MarkdownWithMath
      proseClass={role === "user" ? markdownProseInvertClass : markdownProseClass}
    >
      {content}
    </MarkdownWithMath>
  )
}

export function TrainingTutorPanel({
  agentSessionId,
  rationale,
  className,
}: TrainingTutorPanelProps) {
  const [messages, setMessages] = useState<TutorMessage[]>([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const sendingRef = useRef(false)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" })
  }, [messages, sending])

  const sendText = useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || !agentSessionId || sendingRef.current) return

      sendingRef.current = true
      setSending(true)
      setError(null)

      const userMsg: TutorMessage = { role: "user", content: trimmed }
      setMessages((prev) => [...prev, userMsg])
      setInput("")

      const assistantPlaceholder: TutorMessage = { role: "assistant", content: "" }
      setMessages((prev) => [...prev, assistantPlaceholder])

      try {
        await trainingApi.tutorStream(agentSessionId, trimmed, (chunk) => {
          const content = String(chunk.content ?? "")
          if (!content) return
          setMessages((prev) => {
            const next = [...prev]
            const last = next[next.length - 1]
            if (last?.role === "assistant") {
              next[next.length - 1] = { ...last, content: last.content + content }
            }
            return next
          })
        })
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "发送失败")
        setMessages((prev) => prev.slice(0, -1))
      } finally {
        sendingRef.current = false
        setSending(false)
      }
    },
    [agentSessionId]
  )

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    sendText(input)
  }

  return (
    <div className={cn("flex flex-col h-full min-h-0", className)}>
      <div className="shrink-0 px-4 py-3 border-b border-line-soft">
        <div className="flex items-center gap-2 mb-1">
          <Sparkles className="w-4 h-4 text-primary" />
          <h2 className="text-small font-semibold text-ink-primary">AI 学习教练</h2>
        </div>
        {rationale && (
          <div className="mt-2 rounded-lg bg-primary-soft/50 border border-primary/20 px-3 py-2">
            <p className="text-caption font-medium text-primary mb-1">本次训练说明</p>
            <MarkdownWithMath proseClass="prose prose-sm max-w-none text-ink-secondary">
              {rationale}
            </MarkdownWithMath>
          </div>
        )}
      </div>

      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto scroll-thin px-4 py-3 space-y-3 min-h-0"
      >
        {messages.length === 0 && !rationale && (
          <p className="text-small text-ink-tertiary">
            可向教练询问：为什么选这些题？薄弱点在哪？如何复习？
          </p>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={cn(
              "rounded-lg px-3 py-2 text-small max-w-[95%]",
              msg.role === "user"
                ? "ml-auto bg-primary text-white"
                : "mr-auto bg-surface-soft border border-line-soft"
            )}
          >
            <MessageBody
              content={msg.content}
              role={msg.role}
              isStreamingPlaceholder={sending && i === messages.length - 1 && msg.role === "assistant"}
            />
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {error && (
        <div className="mx-4 mb-2 text-caption text-danger">{error}</div>
      )}

      <form
        onSubmit={handleSubmit}
        className="shrink-0 border-t border-line-soft p-3 flex gap-2"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="问教练…"
          disabled={sending}
          className="flex-1 rounded-lg border border-line-soft bg-surface px-3 py-2 text-small focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
        <Button type="submit" variant="primary" size="sm" disabled={sending || !input.trim()}>
          {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
        </Button>
      </form>
    </div>
  )
}
