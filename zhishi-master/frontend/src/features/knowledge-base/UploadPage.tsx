import { useState, useRef, useCallback, useEffect } from "react"
import {
  UploadCloud,
  FileText,
  Image,
  Camera,
  CheckCircle2,
  Loader2,
  FileUp,
  XCircle,
} from "lucide-react"
import { AppShell } from "@/components/layout/AppShell"
import { RightPanel } from "@/components/layout/RightPanel"
import { PageHeader } from "@/components/blocks/PageHeader"
import { SectionHeader } from "@/components/blocks/SectionHeader"
import { StatCard } from "@/components/ui/stat-card"
import { EmptyState } from "@/components/ui/empty-state"
import { TimelineStep } from "@/components/blocks/TimelineStep"
import { cn } from "@/lib/utils"
import { SegmentedTabs } from "@/components/ui/segmented-tabs"
import { kbApi } from "@/lib/api"
import type { KbCollection } from "@/types"

const SUPPORTED_EXTENSIONS = [".txt", ".md", ".csv", ".json", ".html", ".htm", ".pdf", ".docx"]
const SUPPORTED_LABEL = "TXT, MD, CSV, JSON, HTML, PDF, DOCX"

interface UploadTask {
  id: string // batch_id
  documentId: string
  fileName: string
  fileSize: number
  status: "uploading" | "ocr" | "indexing" | "completed" | "error" | "duplicate"
  errorMessage?: string
  completedSegments?: number
  totalSegments?: number
  ocrCurrentPage?: number
  ocrTotalPages?: number
}

const uploadMethods = [
  {
    id: "doc",
    icon: FileText,
    title: "上传文档",
    desc: "PDF、TXT、MD、DOCX",
    accept: ".pdf,.txt,.md,.docx,.csv,.json,.html,.htm",
  },
  {
    id: "image",
    icon: Image,
    title: "图片 OCR",
    desc: "从图片识别文字",
    accept: ".png,.jpg,.jpeg,.webp",
  },
  {
    id: "camera",
    icon: Camera,
    title: "拍照识别",
    desc: "拍照后整理成资料",
    accept: "image/*",
  },
]

export function UploadPage() {
  const [active, setActive] = useState("doc")
  const [dragging, setDragging] = useState(false)
  const [tasks, setTasks] = useState<UploadTask[]>([])
  const [uploading, setUploading] = useState(false)
  const [maxUploadSize, setMaxUploadSize] = useState("")
  const [showDemoWarning, setShowDemoWarning] = useState(false)
  const [collections, setCollections] = useState<KbCollection[]>([])
  const [selectedCollectionId, setSelectedCollectionId] = useState("")
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    kbApi.getConfig()
      .then((res) => {
        setMaxUploadSize(res.max_upload_size_display || "")
        setShowDemoWarning(!res.use_oss && (res.max_upload_size ?? 0) > 0)
      })
      .catch(() => {})
    kbApi
      .listCollections()
      .then((res) => {
        const cols = (res.collections || []) as KbCollection[]
        setCollections(cols)
        const defaultCol = cols.find((c) => c.is_default) || cols[0]
        if (defaultCol) setSelectedCollectionId(defaultCol.id)
      })
      .catch(() => {})
  }, [])

  // 当前选中方式对应的 accept
  const currentAccept =
    uploadMethods.find((m) => m.id === active)?.accept ?? ".pdf,.txt,.md,.docx,.csv,.json,.html,.htm"

  const pollStatus = useCallback(async (task: UploadTask) => {
    const maxPolls = 60 // 最多轮询 60 次（约 2 分钟）
    let polls = 0

    const poll = async () => {
      if (polls >= maxPolls) {
        setTasks((prev) =>
          prev.map((t) => (t.id === task.id ? { ...t, status: "error" as const, errorMessage: "索引超时" } : t))
        )
        return
      }
      polls++

      try {
        const res = await kbApi.getDocumentStatus(task.id)
        const status = res.status
        const ocrStatus = res.ocr_status as string | undefined

        if (ocrStatus === "processing") {
          setTasks((prev) =>
            prev.map((t) =>
              t.id === task.id
                ? {
                    ...t,
                    status: "ocr",
                    ocrCurrentPage: Number(res.ocr_current_page ?? 0),
                    ocrTotalPages: Number(res.ocr_total_pages ?? 0),
                  }
                : t
            )
          )
          setTimeout(poll, 2000)
          return
        }

        if (status === "completed" || status === "indexed") {
          setTasks((prev) =>
            prev.map((t) =>
              t.id === task.id
                ? { ...t, status: "completed", completedSegments: res.completed_segments ?? res.total_segments, totalSegments: res.total_segments }
                : t
            )
          )
          return
        }
        if (status === "error") {
          setTasks((prev) =>
            prev.map((t) => (t.id === task.id ? { ...t, status: "error", errorMessage: res.error_message || "索引失败" } : t))
          )
          return
        }
        // still indexing
        setTasks((prev) =>
          prev.map((t) =>
            t.id === task.id
              ? {
                  ...t,
                  status: "indexing",
                  completedSegments: res.completed_segments ?? 0,
                  totalSegments: res.total_segments ?? 0,
                }
              : t
          )
        )
        setTimeout(poll, 2000)
      } catch {
        setTimeout(poll, 3000)
      }
    }

    setTimeout(poll, 2000) // 等待 2 秒后开始轮询
  }, [])

  // 页面加载时恢复仍在处理中的上传任务（刷新/返回页面后继续轮询）
  useEffect(() => {
    if (!selectedCollectionId) return
    kbApi
      .listDocuments(1, 50, selectedCollectionId)
      .then((res) => {
        const items = (res.documents || []) as Array<Record<string, unknown>>
        const processing = items.filter((d) => {
          const ocr = String(d.ocr_status || "") === "processing"
          const indexing = String(d.indexing_status || "") === "processing"
          const segment = String(d.segment_status || "") === "processing"
          return ocr || indexing || segment
        })
        if (processing.length === 0) return

        const restored: UploadTask[] = processing.map((d) => {
          const batchId = String(d.dify_batch_id || d.id)
          const ocr = String(d.ocr_status || "") === "processing"
          return {
            id: batchId,
            documentId: String(d.id),
            fileName: String(d.name || "文档"),
            fileSize: Number(d.file_size || 0),
            status: ocr ? "ocr" : "indexing",
            ocrCurrentPage: Number(d.ocr_current_page ?? 0),
            ocrTotalPages: Number(d.ocr_total_pages ?? 0),
          }
        })

        setTasks((prev) => {
          const existing = new Set(prev.map((t) => t.id))
          const merged = restored.filter((t) => !existing.has(t.id))
          if (merged.length) {
            window.setTimeout(() => merged.forEach((task) => pollStatus(task)), 0)
          }
          return merged.length ? [...merged, ...prev] : prev
        })
      })
      .catch(() => {})
  }, [selectedCollectionId, pollStatus])

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      setUploading(true)
      const fileArray = Array.from(files)

      for (const file of fileArray) {
        // 检查扩展名（仅文档模式）
        if (active === "doc") {
          const ext = "." + file.name.split(".").pop()?.toLowerCase()
          if (!SUPPORTED_EXTENSIONS.includes(ext)) {
            setTasks((prev) => [
              {
                id: `err-${Date.now()}-${file.name}`,
                documentId: "",
                fileName: file.name,
                fileSize: file.size,
                status: "error",
                errorMessage: `不支持的文件类型: ${ext}`,
              },
              ...prev,
            ])
            continue
          }
        }

        // 判断是否为图片（需要 OCR）
        const isImage = /\.(png|jpg|jpeg|webp|bmp)$/i.test(file.name)

        // 添加临时任务
        const tempId = `uploading-${Date.now()}-${file.name}`
        setTasks((prev) => [
          { id: tempId, documentId: "", fileName: file.name, fileSize: file.size, status: "uploading" },
          ...prev,
        ])

        // 如果是图片，立即切到 OCR 状态（后端会持续处理）
        if (isImage) {
          setTasks((prev) =>
            prev.map((t) => (t.id === tempId ? { ...t, status: "ocr" } : t))
          )
        }

        try {
          const res = await kbApi.upload(file, selectedCollectionId || undefined)

          if (res.status === "duplicate") {
            setTasks((prev) =>
              prev.map((t) =>
                t.id === tempId
                  ? {
                      ...t,
                      id: res.batch_id,
                      documentId: res.document_id,
                      status: "duplicate",
                    }
                  : t
              )
            )
            continue
          }

          const newTask: UploadTask = {
            id: res.batch_id,
            documentId: res.document_id,
            fileName: res.file_name || file.name,
            fileSize: file.size,
            status: res.ocr_status === "processing" ? "ocr" : "indexing",
            ocrCurrentPage: Number(res.ocr_current_page ?? 0),
            ocrTotalPages: Number(res.ocr_total_pages ?? 0),
          }
          setTasks((prev) => prev.map((t) => (t.id === tempId ? newTask : t)))
          pollStatus(newTask)
        } catch (err: any) {
          setTasks((prev) =>
            prev.map((t) =>
              t.id === tempId
                ? { ...t, id: `err-${tempId}`, status: "error", errorMessage: err?.message || "上传失败" }
                : t
            )
          )
        }
      }

      setUploading(false)
    },
    [active, pollStatus, selectedCollectionId]
  )

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragging(false)
      if (e.dataTransfer.files?.length) {
        handleFiles(e.dataTransfer.files)
      }
    },
    [handleFiles]
  )

  const onFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files?.length) {
        handleFiles(e.target.files)
        e.target.value = "" // 重置以允许重复选择同一文件
      }
    },
    [handleFiles]
  )

  const completedCount = tasks.filter((t) => t.status === "completed").length
  const processingCount = tasks.filter((t) => t.status === "uploading" || t.status === "ocr" || t.status === "indexing").length
  const errorCount = tasks.filter((t) => t.status === "error").length
  const duplicateCount = tasks.filter((t) => t.status === "duplicate").length

  return (
    <AppShell maxWidth={1180}>
      <PageHeader title="上传到知识库" subtitle="把文档、图片或拍照资料交给 Tina 整理" />

      {collections.length > 0 && (
        <div className="mb-6">
          <div className="text-small text-ink-tertiary mb-2">上传到分区</div>
          <SegmentedTabs
            tabs={collections.map((c) => ({
              label: `${c.name}${c.zone === "life" ? " · 生活" : " · 学习"}`,
              value: c.id,
            }))}
            value={selectedCollectionId}
            onChange={setSelectedCollectionId}
          />
        </div>
      )}

      {/* 流程条 */}
      <div className="bg-surface border border-line-soft rounded-lg shadow-xs p-5 mb-8">
        <div className="flex items-center justify-between max-w-2xl mx-auto">
          {[
            { label: "上传", icon: UploadCloud, done: tasks.length > 0 },
            { label: "解析/索引", icon: Loader2, done: processingCount === 0 && tasks.length > 0, active: processingCount > 0 },
            { label: "摘要/标签", icon: FileText, done: completedCount > 0 },
            { label: "加入知识库", icon: CheckCircle2, done: completedCount > 0 },
          ].map((step, i, arr) => (
            <div key={step.label} className="flex items-center flex-1 last:flex-none">
              <div className="flex flex-col items-center gap-2">
                <div
                  className={cn(
                    "w-10 h-10 rounded-full flex items-center justify-center transition-colors",
                    step.done
                      ? "bg-success text-white"
                      : step.active
                        ? "bg-primary text-white"
                        : "bg-surface-soft text-ink-tertiary border border-line-soft"
                  )}
                >
                  <step.icon
                    className={cn("w-5 h-5", step.active && "animate-spin")}
                    strokeWidth={2}
                  />
                </div>
                <span
                  className={cn(
                    "text-small font-medium",
                    step.done ? "text-success" : step.active ? "text-primary" : "text-ink-tertiary"
                  )}
                >
                  {step.label}
                </span>
              </div>
              {i < arr.length - 1 && (
                <div
                  className={cn(
                    "flex-1 h-0.5 mx-3 mb-6 rounded-full",
                    step.done ? "bg-success" : "bg-line-soft"
                  )}
                />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* 上传方式卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        {uploadMethods.map((m) => (
          <button
            key={m.id}
            onClick={() => setActive(m.id)}
            className={cn(
              "text-left bg-surface border rounded-lg p-5 transition-all duration-160",
              active === m.id
                ? "border-primary/40 shadow-primary bg-card-elevated"
                : "border-line-soft shadow-xs hover:-translate-y-0.5 hover:shadow-md hover:border-primary/30"
            )}
          >
            <div
              className={cn(
                "w-11 h-11 rounded-md flex items-center justify-center mb-3 transition-colors",
                active === m.id ? "bg-primary text-white" : "bg-primary-soft text-primary"
              )}
            >
              <m.icon className="w-5 h-5" strokeWidth={2} />
            </div>
            <div className="text-card-title font-semibold text-ink-primary mb-1">{m.title}</div>
            <div className="text-small text-ink-tertiary">{m.desc}</div>
          </button>
        ))}
      </div>

      {/* 隐藏的文件选择器 */}
      <input
        ref={fileInputRef}
        type="file"
        accept={currentAccept}
        multiple
        className="hidden"
        onChange={onFileInputChange}
      />

      {/* 拖拽上传区 */}
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => fileInputRef.current?.click()}
        className={cn(
          "border-2 border-dashed rounded-lg p-10 text-center transition-all duration-160 cursor-pointer",
          dragging
            ? "border-primary bg-primary-soft/50 scale-[1.01]"
            : "border-line bg-surface hover:border-primary/40 hover:bg-surface-soft/50"
        )}
      >
        {uploading ? (
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="w-8 h-8 text-primary animate-spin" strokeWidth={2} />
            <div className="text-card-title font-semibold text-ink-primary">正在上传...</div>
          </div>
        ) : (
          <>
            <div className="w-16 h-16 rounded-xl bg-primary-soft text-primary flex items-center justify-center mx-auto mb-4">
              <UploadCloud className="w-8 h-8" strokeWidth={2} />
            </div>
            <div className="text-card-title font-semibold text-ink-primary mb-1">
              拖拽文件到这里，或点击选择文件
            </div>
            <div className="text-caption text-ink-tertiary">
              支持 {SUPPORTED_LABEL}
            </div>
            {showDemoWarning && (
              <div className="mt-3 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-warning-soft text-warning text-caption">
                <svg className="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <path d="M12 9v4M12 17h.01" />
                  <circle cx="12" cy="12" r="10" />
                </svg>
                演示环境限制：单个文件不超过 {maxUploadSize}
              </div>
            )}
          </>
        )}
      </div>

      {/* 任务区 */}
      <div className="mt-8">
        <SectionHeader title="上传任务">
          {tasks.length > 0 && (
            <button
              onClick={() => setTasks((prev) => prev.filter((t) => t.status === "uploading" || t.status === "indexing"))}
              className="text-small text-ink-tertiary hover:text-ink-primary transition-colors"
            >
              清空已完成
            </button>
          )}
        </SectionHeader>
        {tasks.length > 0 ? (
          <div className="bg-surface border border-line-soft rounded-lg shadow-xs p-5">
            {tasks.map((task, i) => (
              <TimelineStep
                key={task.id}
                index={i + 1}
                title={task.fileName}
                description={
                  task.status === "uploading"
                    ? "正在上传到服务器..."
                    : task.status === "ocr"
                      ? task.ocrTotalPages
                        ? `OCR 识别中：第 ${task.ocrCurrentPage ?? 0}/${task.ocrTotalPages} 页`
                        : "OCR 识别中..."
                      : task.status === "indexing"
                      ? `正在索引 ${task.completedSegments ?? 0}/${task.totalSegments ?? "?"} 段`
                      : task.status === "completed"
                        ? "已入库 · 索引完成"
                        : task.status === "duplicate"
                          ? "该文件已上传过，跳过"
                          : task.status === "error"
                            ? task.errorMessage || "处理失败"
                            : ""
                }
                status={
                  task.status === "uploading" || task.status === "ocr" || task.status === "indexing"
                    ? "loading"
                    : task.status === "completed"
                      ? "success"
                      : task.status === "duplicate"
                        ? "success"
                        : "error"
                }
                isLast={i === tasks.length - 1}
              />
            ))}
          </div>
        ) : (
          <div className="bg-surface border border-line-soft rounded-lg shadow-xs">
            <EmptyState
              icon={FileUp}
              title="还没有上传任务"
              description="选择上方的上传方式或拖拽文件开始上传"
              size="md"
            />
          </div>
        )}
      </div>

      {/* 右侧统计 */}
      <RightPanel title="上传统计">
        <div className="space-y-4">
          <StatCard icon={FileText} label="总数" value={tasks.length} tone="neutral" />
          <StatCard icon={Loader2} label="处理中" value={processingCount} tone="warning" />
          <StatCard icon={CheckCircle2} label="完成" value={completedCount + duplicateCount} tone="success" />
          <StatCard icon={XCircle} label="失败" value={errorCount} tone="warning" />

          <div className="pt-4 border-t border-line-soft">
            <div className="text-small text-ink-tertiary leading-relaxed">
              上传后 Tina 会自动：
              <ul className="mt-2 space-y-1.5">
                <li>• 解析文档内容</li>
                <li>• 生成 AI 摘要</li>
                <li>• 智能打标签</li>
                <li>• 建立知识关系</li>
              </ul>
            </div>
          </div>
        </div>
      </RightPanel>
    </AppShell>
  )
}