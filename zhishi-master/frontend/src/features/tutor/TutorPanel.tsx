import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react"
import { Loader2, Send, Sparkles, X } from "lucide-react"
import { tutorApi } from "@/lib/api"
import type { TutorMessage, TutorSession } from "@/types"
import { Button } from "@/components/ui/button"
import {
  MarkdownWithMath,
  markdownProseClass,
  markdownProseInvertClass,
} from "@/components/blocks/MarkdownWithMath"
import { cn } from "@/lib/utils"

const SCROLL_BOTTOM_THRESHOLD = 48

function TutorMessageBody({
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

export interface TutorPanelHandle {
  sendMessage: (text: string) => void
}

interface TutorPanelProps {
  questionId: string
  quizSessionId?: string
  onClose?: () => void
  className?: string
}

export const TutorPanel = forwardRef<TutorPanelHandle, TutorPanelProps>(function TutorPanel(
  { questionId, quizSessionId, onClose, className },
  ref,
) {
  const [session, setSession] = useState<TutorSession | null>(null)
  const [messages, setMessages] = useState<TutorMessage[]>([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const userScrolledUpRef = useRef(false)
  const pendingMessageRef = useRef<string | null>(null)
  const sessionRef = useRef<TutorSession | null>(null)
  const sendingRef = useRef(false)

  const isAtBottom = () => {
    const el = scrollContainerRef.current
    if (!el) return true
    return el.scrollHeight - el.scrollTop - el.clientHeight <= SCROLL_BOTTOM_THRESHOLD
  }

  const scrollToBottom = (behavior: ScrollBehavior = "auto") => {
    messagesEndRef.current?.scrollIntoView({ behavior, block: "end" })
  }

  const handleScroll = () => {
    userScrolledUpRef.current = !isAtBottom()
  }

  useEffect(() => {
    if (!userScrolledUpRef.current) {
      scrollToBottom(sending ? "auto" : "smooth")
    }
  }, [messages, sending])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    const createTutorSession = async () => {
      try {
        return await tutorApi.createSession({
          question_id: questionId,
          quiz_session_id: quizSessionId,
        })
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : ""
        if (quizSessionId && msg.includes("刷题会话不存在")) {
          return tutorApi.createSession({ question_id: questionId })
        }
        throw err
      }
    }

    createTutorSession()
      .then((res) => {
        if (cancelled) return
        const s = res as unknown as TutorSession
        setSession(s)
        setMessages(s.messages || [])
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message || "无法创建辅导会话")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [questionId, quizSessionId])

  const sendText = useCallback(async (text: string) => {
    const trimmed = text.trim()
    const activeSession = sessionRef.current
    if (!trimmed || !activeSession || sendingRef.current) return

    sendingRef.current = true
    setSending(true)

    const userMsg: TutorMessage = { role: "user", content: trimmed, created_at: new Date().toISOString() }
    setMessages((prev) => [...prev, userMsg])
    setInput("")

    const assistantMsg: TutorMessage = { role: "assistant", content: "", created_at: new Date().toISOString() }
    setMessages((prev) => [...prev, assistantMsg])

    try {
      await tutorApi.sendMessageStream(activeSession.id, trimmed, (chunk) => {
        if (typeof chunk.content === "string") {
          setMessages((prev) => {
            const next = [...prev]
            const last = next[next.length - 1]
            if (last?.role === "assistant") {
              next[next.length - 1] = { ...last, content: last.content + chunk.content }
            }
            return next
          })
        }
      })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "发送失败"
      setMessages((prev) => {
        const next = [...prev]
        const last = next[next.length - 1]
        if (last?.role === "assistant" && !last.content) {
          next[next.length - 1] = { ...last, content: `❌ ${msg}` }
        }
        return next
      })
    } finally {
      sendingRef.current = false
      setSending(false)
    }
  }, [])

  useEffect(() => {
    sessionRef.current = session
  }, [session])

  useEffect(() => {
    sendingRef.current = sending
  }, [sending])

  useEffect(() => {
    if (!session || loading || !pendingMessageRef.current) return
    const text = pendingMessageRef.current
    pendingMessageRef.current = null
    void sendText(text)
  }, [session, loading, sendText])

  useImperativeHandle(ref, () => ({
    sendMessage: (text: string) => {
      const trimmed = text.trim()
      if (!trimmed) return
      setInput(trimmed)
      if (!sessionRef.current || loading || sendingRef.current) {
        pendingMessageRef.current = trimmed
        return
      }
      void sendText(trimmed)
    },
  }), [loading, sendText])

  const handleSend = () => {
    void sendText(input)
  }

  return (
    <div
      className={cn(
        "flex flex-col h-full min-h-0 overflow-hidden bg-surface border border-line-soft rounded-lg",
        className,
      )}
    >
      <div className="flex items-center gap-2 px-4 py-3 border-b border-line-soft shrink-0">
        <div className="w-8 h-8 rounded-full bg-gradient-primary flex items-center justify-center shrink-0">
          <Sparkles className="w-4 h-4 text-white" strokeWidth={2} />
        </div>
        <div className="flex-1 min-w-0 text-card-title font-semibold text-ink-primary">
          AI辅导
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 rounded-md flex items-center justify-center text-ink-tertiary hover:text-ink-primary hover:bg-surface-soft"
          >
            <X className="w-4 h-4" strokeWidth={2} />
          </button>
        )}
      </div>

      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 min-h-0 overflow-y-auto scroll-thin p-4 space-y-3"
      >
        {loading ? (
          <div className="flex items-center justify-center py-8 text-ink-tertiary gap-2">
            <Loader2 className="w-5 h-5 animate-spin" />
            <span className="text-body">准备辅导中...</span>
          </div>
        ) : error ? (
          <div className="text-body text-danger">{error}</div>
        ) : messages.length === 0 ? (
          <div className="text-small text-ink-tertiary text-center py-6">
            说说哪里不懂，AI 辅导会结合原文引导你思考
          </div>
        ) : (
          messages.map((m, i) => (
            <div
              key={i}
              className={cn(
                "text-body leading-relaxed",
                m.role === "user"
                  ? "flex justify-end"
                  : "flex gap-2 mr-2"
              )}
            >
              {m.role === "assistant" && (
                <div className="w-7 h-7 rounded-full bg-gradient-primary flex items-center justify-center shrink-0 mt-0.5">
                  <Sparkles className="w-3.5 h-3.5 text-white" strokeWidth={2} />
                </div>
              )}
              <div
                className={cn(
                  "rounded-lg px-3 py-2 max-w-[85%]",
                  m.role === "user"
                    ? "bg-primary text-white rounded-tr-sm"
                    : "bg-surface border border-line-soft text-ink-primary rounded-tl-sm"
                )}
              >
                <TutorMessageBody
                  content={m.content}
                  role={m.role}
                  isStreamingPlaceholder={sending && i === messages.length - 1 && m.role === "assistant"}
                />
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} aria-hidden />
      </div>

      <div className="p-3 border-t border-line-soft shrink-0">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            placeholder="输入你的疑问..."
            rows={2}
            disabled={loading || !!error || sending}
            className="flex-1 resize-none rounded-md border border-line bg-surface px-3 py-2 text-body text-ink-primary placeholder:text-ink-tertiary focus:outline-none focus:border-primary/50"
          />
          <Button
            variant="primary"
            size="icon"
            onClick={handleSend}
            disabled={!input.trim() || loading || !!error || sending}
            aria-label="发送"
          >
            <Send className="w-4 h-4" strokeWidth={2} />
          </Button>
        </div>
      </div>
    </div>
  )
})
