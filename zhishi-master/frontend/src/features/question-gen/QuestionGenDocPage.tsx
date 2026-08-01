import { useCallback, useEffect, useMemo, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import {
  ArrowLeft,
  CheckSquare,
  FileQuestion,
  Loader2,
  Sparkles,
  Square,
} from "lucide-react"
import { AppShell } from "@/components/layout/AppShell"
import { PageHeader } from "@/components/blocks/PageHeader"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { DocumentPipelineBadge } from "@/components/blocks/DocumentPipelineBadge"
import { DocumentContentViewer } from "@/components/blocks/DocumentContentViewer"
import { kbApi, questionsApi } from "@/lib/api"
import { useKbDocuments } from "@/hooks/useKbDocuments"
import type { DocumentPage, DocumentPageDetail, PageQuestionResult } from "@/types"
import { cn } from "@/lib/utils"

export function QuestionGenDocPage() {
  const { documentId = "" } = useParams<{ documentId: string }>()
  const navigate = useNavigate()
  const { documents, refreshDocuments, updateDocument } = useKbDocuments({
    zoneFilter: "study",
    preferZone: "study",
  })

  const selectedDocument = documents.find((d) => d.id === documentId)

  const [pages, setPages] = useState<DocumentPage[]>([])
  const [hasPageMarkers, setHasPageMarkers] = useState(true)
  const [docPreviewMode, setDocPreviewMode] = useState<"pdf" | "markdown" | "text">("markdown")
  const [documentName, setDocumentName] = useState("")
  const [activePageNumber, setActivePageNumber] = useState<number | null>(null)
  const [pageDetail, setPageDetail] = useState<DocumentPageDetail | null>(null)
  const [selectedPages, setSelectedPages] = useState<Set<number>>(new Set())
  const [loadingPages, setLoadingPages] = useState(false)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<PageQuestionResult | null>(null)

  const selectedPageList = useMemo(
    () => pages.filter((p) => selectedPages.has(p.page_number)),
    [pages, selectedPages]
  )

  const hasBuiltinSelected = selectedPageList.some((p) => p.has_builtin_questions)
  const hasKeySelected = selectedPageList.some((p) => p.is_key_page)

  const loadPages = useCallback(async (docId: string) => {
    setLoadingPages(true)
    setError(null)
    setSelectedPages(new Set())
    setResult(null)
    setActivePageNumber(null)
    setPageDetail(null)
    try {
      const res = await kbApi.getDocumentPages(docId)
      const pageList = res.pages || []
      setPages(pageList)
      setHasPageMarkers(res.has_page_markers)
      setDocPreviewMode(res.preview_mode || "markdown")
      setDocumentName(res.document_name || selectedDocument?.name || "")
      if (pageList.length > 0) {
        setActivePageNumber(pageList[0].page_number)
      }
    } catch (e) {
      setPages([])
      setError(e instanceof Error ? e.message : "加载页面失败")
    } finally {
      setLoadingPages(false)
    }
  }, [selectedDocument?.name])

  useEffect(() => {
    if (documentId) void loadPages(documentId)
  }, [documentId, loadPages])

  useEffect(() => {
    if (!documentId || !activePageNumber) {
      setPageDetail(null)
      return
    }
    let cancelled = false
    setLoadingDetail(true)
    kbApi
      .getDocumentPage(documentId, activePageNumber)
      .then((detail) => {
        if (!cancelled) setPageDetail(detail)
      })
      .catch((e) => {
        if (!cancelled) {
          setPageDetail(null)
          setError(e instanceof Error ? e.message : "加载页内容失败")
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingDetail(false)
      })
    return () => {
      cancelled = true
    }
  }, [documentId, activePageNumber])

  useEffect(() => {
    if (!documentId || !working) return
    const timer = window.setInterval(async () => {
      try {
        const docs = await refreshDocuments(true)
        const doc = docs.find((d) => d.id === documentId)
        if (!doc) return
        updateDocument(documentId, { question_gen_status: doc.question_gen_status })
        if (doc.question_gen_status === "completed" || doc.question_gen_status === "failed") {
          setWorking(false)
          setResult((prev) =>
            prev ? { ...prev, question_gen_status: doc.question_gen_status } : prev
          )
        }
      } catch {
        /* ignore poll errors */
      }
    }, 2500)
    return () => window.clearInterval(timer)
  }, [documentId, working, refreshDocuments, updateDocument])

  const togglePage = (pageNumber: number, event?: React.MouseEvent) => {
    event?.stopPropagation()
    setSelectedPages((prev) => {
      const next = new Set(prev)
      if (next.has(pageNumber)) next.delete(pageNumber)
      else next.add(pageNumber)
      return next
    })
  }

  const handlePageClick = (pageNumber: number) => {
    setActivePageNumber(pageNumber)
  }

  const selectAll = () => setSelectedPages(new Set(pages.map((p) => p.page_number)))
  const clearSelection = () => setSelectedPages(new Set())

  const runGenerate = async () => {
    if (!documentId || selectedPages.size === 0) return
    setWorking(true)
    setError(null)
    setResult(null)
    try {
      const res = await questionsApi.generateFromPages({
        document_id: documentId,
        page_numbers: Array.from(selectedPages).sort((a, b) => a - b),
        questions_per_page: 1,
      })
      setResult(res)
      if (res.question_gen_status === "processing") {
        updateDocument(documentId, { question_gen_status: "processing" })
      } else {
        setWorking(false)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "批量出题失败")
      setWorking(false)
    }
  }

  const runExtract = async () => {
    if (!documentId || selectedPages.size === 0) return
    setWorking(true)
    setError(null)
    setResult(null)
    try {
      const res = await questionsApi.extractFromPages({
        document_id: documentId,
        page_numbers: Array.from(selectedPages).sort((a, b) => a - b),
      })
      setResult(res)
      if (res.question_gen_status === "processing") {
        updateDocument(documentId, { question_gen_status: "processing" })
      } else {
        setWorking(false)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "提取题目失败")
      setWorking(false)
    }
  }

  const displayName = selectedDocument?.name || documentName || "文档"

  return (
    <AppShell maxWidth={null} noPadding>
      <div className="flex flex-col h-full">
        <div className="px-8 pt-6 pb-4 border-b border-line-soft shrink-0">
          <PageHeader
            title={displayName}
            subtitle="按页浏览内容，选择页面后提取或 AI 生成题目"
          >
            <Button
              variant="ghost"
              size="md"
              onClick={() => navigate("/question-gen")}
            >
              <ArrowLeft className="h-4 w-4 mr-2" />
              返回文档列表
            </Button>
            <Button variant="secondary" size="md" onClick={() => navigate("/quiz")}>
              前往题库
            </Button>
          </PageHeader>

          {selectedDocument && (
            <div className="mt-2">
              <DocumentPipelineBadge
                segment_status={selectedDocument.segment_status}
                question_gen_status={selectedDocument.question_gen_status}
                zone={selectedDocument.zone}
              />
            </div>
          )}
        </div>

        {error && (
          <Alert className="mx-8 mt-4 border-danger/30 bg-danger-soft shrink-0">
            <AlertDescription className="text-danger">{error}</AlertDescription>
          </Alert>
        )}

        {!hasPageMarkers && pages.length > 0 && (
          <Alert className="mx-8 mt-4 border-line-soft bg-surface-soft shrink-0">
            <AlertDescription className="text-ink-secondary">
              该文档无「## 第 N 页」标记，已作为单页全文展示。扫描 PDF 经 OCR 后会自动带页码。
            </AlertDescription>
          </Alert>
        )}

        <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[200px_minmax(0,1fr)_280px] gap-0 overflow-hidden">
          {/* 左：页码列表 */}
          <div className="border-r border-line-soft bg-surface/60 flex flex-col min-h-0 overflow-hidden">
            <div className="px-3 py-3 border-b border-line-soft flex items-center justify-between shrink-0">
              <span className="text-small font-medium text-ink-primary">页码</span>
              {pages.length > 0 && (
                <div className="flex gap-1">
                  <button
                    type="button"
                    onClick={selectAll}
                    className="text-caption text-primary hover:underline"
                  >
                    全选
                  </button>
                  <span className="text-caption text-ink-tertiary">·</span>
                  <button
                    type="button"
                    onClick={clearSelection}
                    className="text-caption text-ink-tertiary hover:underline"
                  >
                    清空
                  </button>
                </div>
              )}
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto scroll-thin p-2">
              {loadingPages ? (
                <div className="flex items-center justify-center py-8 text-ink-tertiary">
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  加载中…
                </div>
              ) : pages.length === 0 ? (
                <div className="text-caption text-ink-tertiary text-center py-8">暂无页面</div>
              ) : (
                pages.map((page) => {
                  const isActive = activePageNumber === page.page_number
                  const isSelected = selectedPages.has(page.page_number)
                  return (
                    <div
                      key={page.page_number}
                      className={cn(
                        "rounded-md mb-0.5 transition-colors flex items-start gap-1",
                        isActive && "bg-primary-soft/60"
                      )}
                    >
                      <button
                        type="button"
                        onClick={(e) => togglePage(page.page_number, e)}
                        className="shrink-0 px-2 py-2.5 text-ink-tertiary hover:text-primary"
                        title={isSelected ? "取消选中" : "选中此页"}
                        aria-label={isSelected ? "取消选中" : "选中此页"}
                      >
                        {isSelected ? (
                          <CheckSquare className="h-4 w-4 text-primary" />
                        ) : (
                          <Square className="h-4 w-4" />
                        )}
                      </button>
                      <button
                        type="button"
                        onClick={() => handlePageClick(page.page_number)}
                        className={cn(
                          "flex-1 min-w-0 text-left px-1 py-2.5 text-small transition-colors",
                          isActive
                            ? "text-primary font-medium"
                            : "text-ink-secondary hover:bg-surface-soft"
                        )}
                      >
                        <div className="truncate">{page.title}</div>
                        {(page.has_builtin_questions || page.is_key_page) && (
                          <div className="flex flex-wrap gap-1 mt-1">
                            {page.has_builtin_questions && (
                              <Badge variant="neutral" size="sm">
                                含习题
                              </Badge>
                            )}
                            {page.is_key_page && (
                              <Badge variant="info" size="sm">
                                重点
                              </Badge>
                            )}
                          </div>
                        )}
                        {page.preview && (
                          <div className="text-caption text-ink-tertiary truncate mt-0.5">
                            {page.preview}
                          </div>
                        )}
                      </button>
                    </div>
                  )
                })
              )}
            </div>
          </div>

          {/* 中：页内容预览 */}
          <div className="flex flex-col min-h-0 overflow-hidden bg-surface">
            <div className="px-5 py-3 border-b border-line-soft shrink-0">
              <span className="text-body font-medium text-ink-primary">
                {pageDetail?.title || (activePageNumber ? `第 ${activePageNumber} 页` : "页内容预览")}
              </span>
              {pageDetail && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {pageDetail.has_builtin_questions && (
                    <Badge variant="neutral" size="sm">
                      含习题
                    </Badge>
                  )}
                  {pageDetail.is_key_page && (
                    <Badge variant="info" size="sm">
                      重点
                    </Badge>
                  )}
                </div>
              )}
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto scroll-thin p-5">
              {loadingDetail ? (
                <div className="flex items-center justify-center py-16 text-ink-tertiary">
                  <Loader2 className="h-5 w-5 animate-spin mr-2" />
                  加载页内容…
                </div>
              ) : !pageDetail ? (
                <EmptyState
                  icon={FileQuestion}
                  title="选择一页查看内容"
                  description="从左侧页码列表点击页面"
                  size="md"
                />
              ) : (
                <DocumentContentViewer
                  docId={documentId}
                  previewMode={
                    pageDetail.preview_mode === "pdf" || docPreviewMode === "pdf"
                      ? "pdf"
                      : "markdown"
                  }
                  content={pageDetail.content || ""}
                  pageNumber={pageDetail.page_number}
                />
              )}
            </div>
          </div>

          {/* 右：出题操作 */}
          <div className="border-l border-line-soft bg-surface/60 flex flex-col min-h-0 overflow-hidden">
            <div className="px-4 py-3 border-b border-line-soft shrink-0">
              <h3 className="text-body font-semibold text-ink-primary">出题模式</h3>
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto scroll-thin p-4 flex flex-col gap-3">
              <p className="text-caption text-ink-secondary">
                在左侧勾选要出题的页面。已选{" "}
                <span className="font-medium text-ink-primary">{selectedPages.size}</span> 页
              </p>

              {selectedPages.size > 0 && (
                <div className="text-caption text-ink-tertiary space-y-1">
                  {hasBuiltinSelected && <p>· 选中页含教材自带题目，可「提取题目」</p>}
                  {hasKeySelected && <p>· 选中页含重点内容，可「AI 批量出题」</p>}
                </div>
              )}

              <div className="flex flex-col gap-2 mt-auto">
                <Button
                  className="w-full justify-start"
                  variant="secondary"
                  size="md"
                  disabled={working || selectedPages.size === 0 || !hasBuiltinSelected}
                  onClick={runExtract}
                  title={!hasBuiltinSelected ? "选中页未检测到习题特征" : undefined}
                >
                  {working ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  ) : (
                    <FileQuestion className="h-4 w-4 mr-2" />
                  )}
                  提取教材题目（模式 A）
                </Button>

                <Button
                  className="w-full justify-start"
                  size="md"
                  disabled={working || selectedPages.size === 0}
                  onClick={runGenerate}
                >
                  {working ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  ) : (
                    <Sparkles className="h-4 w-4 mr-2" />
                  )}
                  AI 批量出题（模式 B）
                </Button>
              </div>

              {result && (
                <Alert
                  className={
                    result.question_gen_status === "processing"
                      ? "border-line-soft bg-surface-soft"
                      : "border-success/30 bg-success-soft"
                  }
                >
                  <AlertDescription className="text-caption text-ink-primary">
                    {result.question_gen_status === "processing" ? (
                      <>正在后台{result.mode === "extract" ? "提取" : "生成"}题目，请稍候…</>
                    ) : (
                      <>
                        {result.mode === "extract" ? "提取" : "生成"}完成：新建{" "}
                        {result.questions_created} 题，复用 {result.questions_reused} 题，共{" "}
                        {result.total_questions} 题。
                        <Link
                          to={`/quiz?document_id=${result.document_id}`}
                          className="ml-1 text-primary hover:underline"
                        >
                          去题库
                        </Link>
                      </>
                    )}
                  </AlertDescription>
                </Alert>
              )}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  )
}
