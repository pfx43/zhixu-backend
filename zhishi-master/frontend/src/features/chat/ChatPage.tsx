import { useState, useRef, useEffect } from "react"
import {
  Sparkles,
  ArrowUp,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Trash2,
  ChevronRight,
  GraduationCap,
  Home,
} from "lucide-react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { AppShell } from "@/components/layout/AppShell"
import { ChatCitationSidebar } from "@/components/blocks/ChatCitationSidebar"
import { Button } from "@/components/ui/button"
import { ChatMessage as ChatMessageBlock } from "@/components/blocks/ChatMessage"
import { chatApi, kbApi, normalizeChatHistory } from "@/lib/api"
import { useAuth } from "@/context/AuthContext"
import type { ChatMessage, Citation, KbCollection } from "@/types"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cn } from "@/lib/utils"

interface SessionItem {
  id: string
  title: string
  updated_at?: string
  created_at?: string
}

const welcomeMessage: ChatMessage = {
  id: "welcome",
  role: "assistant",
  content: "你好！我是 Tina，你的知识管理助手。\n你可以问我课程知识、上传文档、整理笔记，或者让我帮你生成学习路径。",
  time: "刚刚",
}

const HISTORY_SIDEBAR_KEY = "zhishi_chat_history_sidebar"

function readHistorySidebarOpen(): boolean {
  try {
    return localStorage.getItem(HISTORY_SIDEBAR_KEY) === "open"
  } catch {
    return false
  }
}

function persistHistorySidebarOpen(open: boolean) {
  try {
    localStorage.setItem(HISTORY_SIDEBAR_KEY, open ? "open" : "closed")
  } catch {
    /* ignore */
  }
}

export function ChatPage() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const [input, setInput] = useState("")
  const [messages, setMessages] = useState<ChatMessage[]>([welcomeMessage])
  const [isStreaming, setIsStreaming] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sessions, setSessions] = useState<SessionItem[]>([])
  const [sidebarOpen, setSidebarOpen] = useState(readHistorySidebarOpen)
  const [citationSidebarOpen, setCitationSidebarOpen] = useState(false)
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null)
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [collections, setCollections] = useState<KbCollection[]>([])
  const [collectionId, setCollectionId] = useState<string>("")
  const scrollRef = useRef<HTMLDivElement>(null)

  // ─── 会话列表 ──────────────────────────────────────

  const loadSessions = async () => {
    try {
      const res = await chatApi.getSessions()
      const items = res.sessions || res.data || []
      setSessions(items)
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    loadSessions()
    kbApi
      .listCollections()
      .then((res) => {
        const cols = (res.collections || []) as KbCollection[]
        setCollections(cols)
        const defaultCol = cols.find((c) => c.is_default) || cols[0]
        if (defaultCol) setCollectionId(defaultCol.id)
      })
      .catch(() => {})
  }, [])

  // ─── 从 Dashboard 跳转过来的自动搜索 ─────────────────

  useEffect(() => {
    const q = searchParams.get("q")
    if (q?.trim()) {
      // 等组件完全加载后再发送
      const t = setTimeout(() => {
        setInput(q.trim())
        handleSend()
      }, 300)
      return () => clearTimeout(t)
    }
  }, [])

  // ─── 滚动到底 ──────────────────────────────────────

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
  }, [messages])

  // ─── 切换会话 ──────────────────────────────────────

  const handleSelectSession = async (s: SessionItem) => {
    if (s.id === sessionId) return
    setSessionId(s.id)
    setLoadingHistory(true)
    try {
      const res = await chatApi.getHistory(s.id)
      const items = normalizeChatHistory(res)
      const msgs: ChatMessage[] = items.map((m, i) => ({
        id: String(m.id || `h-${i}`),
        role: (m.role as ChatMessage["role"]) || "user",
        content: String(m.content || ""),
        time: String(m.time || m.created_at || "—"),
        citations: (m.citations as Citation[]) || undefined,
      }))
      if (msgs.length === 0) {
        setMessages([welcomeMessage])
      } else {
        setMessages(msgs)
      }
    } catch {
      setMessages([welcomeMessage])
    } finally {
      setLoadingHistory(false)
    }
  }

  // ─── 新建会话 ──────────────────────────────────────

  const handleNewSession = () => {
    setSessionId(null)
    setMessages([welcomeMessage])
  }

  // ─── 删除会话 ──────────────────────────────────────

  const handleDeleteSession = async (s: SessionItem, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await chatApi.deleteSession(s.id)
      setSessions(prev => prev.filter(x => x.id !== s.id))
      if (s.id === sessionId) {
        handleNewSession()
      }
    } catch {
      // ignore
    }
  }

  // ─── 发送消息 ──────────────────────────────────────

  const handleSend = async () => {
    const text = input.trim()
    if (!text || isStreaming) return

    const now = new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })
    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      content: text,
      time: now,
    }

    const assistantId = `a-${Date.now()}`
    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      time: now,
    }

    setMessages(prev => [...prev, userMsg, assistantMsg])
    setInput("")
    setIsStreaming(true)

    try {
      let messageCitations: Citation[] = []
      await chatApi.sendStream({
        content: text,
        session_id: sessionId ?? undefined,
        collection_id: collectionId || undefined,
        onChunk: (chunk) => {
          if (typeof chunk.content === "string") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, content: m.content + chunk.content } : m
              )
            )
          }
          if (chunk.session_id && !sessionId) {
            setSessionId(String(chunk.session_id))
            loadSessions()
          }
          if (Array.isArray(chunk.citations) && chunk.citations.length > 0) {
            messageCitations = chunk.citations as Citation[]
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, citations: messageCitations } : m
              )
            )
          }
        },
      })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "请稍后重试"
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId ? { ...m, content: `❌ 发送失败：${msg}` } : m
        )
      )
    } finally {
      setIsStreaming(false)
    }
  }

  const handleCitationClick = (citation: Citation) => {
    setActiveCitation(citation)
    setCitationSidebarOpen(true)
  }

  const toggleHistorySidebar = () => {
    setSidebarOpen((prev) => {
      const next = !prev
      persistHistorySidebarOpen(next)
      return next
    })
  }

  const selectedCollection = collections.find((c) => c.id === collectionId)
  const zoneLabel = selectedCollection?.zone === "life" ? "生活区" : "学习区"

  const handleLogout = () => {
    logout()
    navigate("/login")
  }

  // ─── 格式化时间 ────────────────────────────────────

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return "—"
    try {
      const d = new Date(dateStr)
      const now = new Date()
      const diff = now.getTime() - d.getTime()
      if (diff < 86400000) {
        return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })
      }
      if (diff < 604800000) {
        const days = ["日", "一", "二", "三", "四", "五", "六"]
        return `周${days[d.getDay()]}`
      }
      return `${d.getMonth() + 1}/${d.getDate()}`
    } catch {
      return "—"
    }
  }

  return (
    <AppShell maxWidth={null} noPadding>
      <div className="flex h-full">
        {/* ────── 左侧可折叠历史侧栏 ────── */}
        <div className={cn(
          "shrink-0 border-r border-line-soft bg-surface/60 flex flex-col transition-all duration-200",
          sidebarOpen ? "w-[260px]" : "w-[44px]",
        )}>
          <div className={cn("flex items-center gap-2 px-3 py-3 border-b border-line-soft", !sidebarOpen && "justify-center px-0")}>
            {sidebarOpen && (
              <>
                <span className="text-card-title font-semibold text-ink-primary flex-1">历史会话</span>
                <button
                  onClick={handleNewSession}
                  className="w-7 h-7 rounded-md flex items-center justify-center text-ink-tertiary hover:text-primary hover:bg-primary-soft transition-colors"
                  title="新建会话"
                >
                  <Plus className="w-4 h-4" strokeWidth={2} />
                </button>
              </>
            )}
            <button
              onClick={toggleHistorySidebar}
              className="w-7 h-7 rounded-md flex items-center justify-center text-ink-tertiary hover:text-ink-primary hover:bg-surface-soft transition-colors shrink-0"
              title={sidebarOpen ? "折叠历史" : "展开历史"}
            >
              {sidebarOpen
                ? <PanelLeftClose className="w-4 h-4" strokeWidth={2} />
                : <PanelLeftOpen className="w-4 h-4" strokeWidth={2} />
              }
            </button>
          </div>

          {sidebarOpen && (
            <div className="flex-1 overflow-y-auto scroll-thin px-2 py-2">
              {sessions.length === 0 ? (
                <div className="text-caption text-ink-tertiary text-center py-8">暂无历史会话</div>
              ) : (
                sessions.map(s => (
                  <div
                    key={s.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => handleSelectSession(s)}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') handleSelectSession(s) }}
                    className={cn(
                      "w-full text-left px-3 py-2.5 rounded-md flex items-center gap-2 group transition-colors mb-0.5 cursor-pointer",
                      s.id === sessionId
                        ? "bg-primary-soft text-primary"
                        : "hover:bg-surface-soft text-ink-secondary",
                    )}
                  >
                    <span className="flex-1 truncate text-small">
                      {s.title || "新对话"}
                    </span>
                    <div className="flex items-center gap-1 shrink-0">
                      <span className="text-caption text-ink-tertiary">
                        {formatDate(s.updated_at || s.created_at)}
                      </span>
                      <button
                        onClick={(e) => handleDeleteSession(s, e)}
                        className="w-5 h-5 rounded flex items-center justify-center opacity-0 group-hover:opacity-100 hover:bg-danger-soft hover:text-danger transition-all"
                        title="删除会话"
                      >
                        <Trash2 className="w-3 h-3" strokeWidth={2} />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {!sidebarOpen && (
            <div className="flex-1 flex items-center justify-center">
              <button
                onClick={() => {
                  setSidebarOpen(true)
                  persistHistorySidebarOpen(true)
                }}
                className="flex flex-col items-center gap-1.5 text-ink-tertiary hover:text-primary transition-colors py-8"
              >
                <ChevronRight className="w-4 h-4" strokeWidth={2} />
                <span className="text-caption font-medium [writing-mode:vertical-rl] tracking-wider">历史</span>
              </button>
            </div>
          )}
        </div>

        {/* ────── 对话主区域 ────── */}
        <div className="flex-1 flex flex-col min-w-0">
          <div className="px-8 pt-6 pb-4 border-b border-line-soft">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-gradient-primary flex items-center justify-center shadow-primary shrink-0">
                  <Sparkles className="w-5 h-5 text-white" strokeWidth={2} />
                </div>
                <div>
                  <div className="text-card-title font-semibold text-ink-primary leading-tight">Tina</div>
                  <div className="text-small text-ink-tertiary">
                    知识库助手 · {user?.nickname || ""}
                  </div>
                </div>
              </div>
              <button
                onClick={handleLogout}
                title="退出登录"
                className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md text-small text-ink-tertiary hover:text-danger hover:bg-danger-soft transition-colors"
              >
                <LogOut className="w-4 h-4" strokeWidth={2} />
                <span className="hidden lg:inline">退出</span>
              </button>
            </div>
          </div>

          <div ref={scrollRef} className="flex-1 overflow-y-auto scroll-thin px-8 py-6">
            <div className="max-w-[860px] mx-auto space-y-5">
              {loadingHistory ? (
                <div className="flex items-center justify-center py-12">
                  <div className="flex items-center gap-2 text-ink-tertiary">
                    <div className="w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
                    <span className="text-body">加载历史消息...</span>
                  </div>
                </div>
              ) : (
                <>
                  {messages.map((m) => (
                    <ChatMessageBlock
                      key={m.id}
                      message={m}
                      onCitationClick={handleCitationClick}
                    />
                  ))}
                  {isStreaming && messages.length > 0 && messages[messages.length - 1].role === "assistant" && !messages[messages.length - 1].content && (
                    <div className="flex gap-3 animate-msg-in">
                      <div className="w-8 h-8 rounded-full bg-gradient-primary flex items-center justify-center shrink-0 shadow-primary mt-0.5">
                        <Sparkles className="w-4 h-4 text-white" strokeWidth={2} />
                      </div>
                      <div className="flex items-center gap-1.5 pt-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
                        <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse [animation-delay:150ms]" />
                        <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse [animation-delay:300ms]" />
                      </div>
                    </div>
                  )}
                  {messages.length <= 1 && (
                    <div className="pt-2">
                      <div className="text-small text-ink-tertiary mb-2">开始对话吧</div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>

          <div className="border-t border-line-soft bg-surface px-8 py-4">
            <div className="max-w-[860px] mx-auto">
              <div className="flex flex-wrap items-center gap-2 mb-3">
                <span className="text-small text-ink-tertiary">检索分区</span>
                <Select value={collectionId} onValueChange={setCollectionId}>
                  <SelectTrigger className="h-8 min-w-[180px] border-line bg-surface text-small text-ink-primary">
                    <SelectValue placeholder="选择分区" />
                  </SelectTrigger>
                  <SelectContent>
                    {collections.map((c) => (
                      <SelectItem key={c.id} value={c.id}>
                        {c.name} · {c.zone === "life" ? "生活区" : "学习区"}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {selectedCollection && (
                  <Badge variant={selectedCollection.zone === "life" ? "neutral" : "info"}>
                    {selectedCollection.zone === "life" ? (
                      <Home className="w-3 h-3 mr-1 inline" strokeWidth={2} />
                    ) : (
                      <GraduationCap className="w-3 h-3 mr-1 inline" strokeWidth={2} />
                    )}
                    当前对话将检索 {zoneLabel}
                  </Badge>
                )}
              </div>
              <div className="relative rounded-lg border border-line bg-surface shadow-xs focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-primary/10 transition-all">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault()
                      handleSend()
                    }
                  }}
                  placeholder="随便问点什么，或粘贴一段资料让 Tina 整理..."
                  rows={3}
                  className="w-full resize-none bg-transparent px-4 pt-3.5 pb-12 text-body text-ink-primary placeholder:text-ink-tertiary focus:outline-none"
                  style={{ maxHeight: "240px", minHeight: "88px" }}
                  disabled={isStreaming || loadingHistory}
                />
                <div className="absolute bottom-0 left-0 right-0 flex items-center justify-end px-3 py-2">
                  <Button
                    variant={input.trim() && !isStreaming ? "primary" : "secondary"}
                    size="icon"
                    onClick={handleSend}
                    disabled={!input.trim() || isStreaming || loadingHistory}
                    aria-label="发送"
                  >
                    <ArrowUp className="w-[18px] h-[18px]" strokeWidth={2} />
                  </Button>
                </div>
              </div>
              <div className="text-small text-ink-tertiary mt-2 text-center">
                Enter 发送 · Shift + Enter 换行 · Tina 可能会出错，请核实重要信息
              </div>
            </div>
          </div>
        </div>

        {/* ────── 右侧可折叠引用侧栏 ────── */}
        <ChatCitationSidebar
          open={citationSidebarOpen}
          onOpenChange={setCitationSidebarOpen}
          citation={activeCitation}
        />
      </div>
    </AppShell>
  )
}