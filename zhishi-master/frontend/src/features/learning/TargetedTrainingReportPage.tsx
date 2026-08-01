import { useEffect, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { ArrowLeft, Loader2, Play, RotateCcw, Target } from "lucide-react"
import { AppShell } from "@/components/layout/AppShell"
import { PageHeader } from "@/components/blocks/PageHeader"
import { MarkdownWithMath } from "@/components/blocks/MarkdownWithMath"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { reportsApi, trainingApi } from "@/lib/api"
import type { LearningReport, TargetedTrainingActiveSession } from "@/types"

function formatDateTime(value?: string | null): string {
  if (!value) return "—"
  try {
    const d = new Date(value)
    if (Number.isNaN(d.getTime())) return value
    return d.toLocaleString("zh-CN", {
      year: "numeric",
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    return value
  }
}

export function TargetedTrainingReportPage() {
  const { reportId } = useParams<{ reportId: string }>()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [report, setReport] = useState<LearningReport | null>(null)
  const [activeSession, setActiveSession] = useState<TargetedTrainingActiveSession | null>(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!reportId) return
    setLoading(true)
    setError(null)
    Promise.all([reportsApi.get(reportId), trainingApi.getActiveSession(reportId)])
      .then(([r, active]) => {
        setReport(r)
        setActiveSession(active)
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "加载失败")
      })
      .finally(() => setLoading(false))
  }, [reportId])

  const handleStart = async (forceNew = false) => {
    if (!reportId) return
    setStarting(true)
    setError(null)
    try {
      const result = await trainingApi.startTargeted({
        report_id: reportId,
        force_new: forceNew,
      })
      navigate(`/training/targeted/session/${result.session.id}`)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "启动训练失败")
    } finally {
      setStarting(false)
    }
  }

  const handleContinue = () => {
    if (activeSession?.session_id) {
      navigate(`/training/targeted/session/${activeSession.session_id}`)
    }
  }

  if (loading) {
    return (
      <AppShell maxWidth={900}>
        <div className="flex items-center justify-center py-24 gap-2 text-ink-tertiary">
          <Loader2 className="w-5 h-5 animate-spin" />
          加载报告…
        </div>
      </AppShell>
    )
  }

  if (error && !report) {
    return (
      <AppShell maxWidth={900}>
        <Card className="p-8 text-center">
          <p className="text-body text-danger mb-4">{error}</p>
          <Button variant="secondary" onClick={() => navigate("/training/targeted")}>
            返回列表
          </Button>
        </Card>
      </AppShell>
    )
  }

  return (
    <AppShell maxWidth={900}>
      <PageHeader
        title={report?.title ?? "学习报告"}
        subtitle={formatDateTime(report?.created_at)}
      >
        <Button
          variant="ghost"
          size="md"
          onClick={() => navigate("/training/targeted")}
        >
          <ArrowLeft className="w-4 h-4" />
          返回列表
        </Button>
      </PageHeader>

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertTitle>操作失败</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {activeSession && activeSession.status === "active" && (
        <Card className="p-4 mb-4 border-primary/30 bg-primary-soft/30">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-body font-medium text-ink-primary">你有未完成的针对训练</p>
              <p className="text-small text-ink-secondary mt-0.5">
                进度 {activeSession.answered_count}/{activeSession.total_questions} 题，退出后进度已保留
              </p>
            </div>
            <Button variant="primary" onClick={handleContinue}>
              <Play className="w-4 h-4" />
              继续训练
            </Button>
          </div>
        </Card>
      )}

      <Card className="p-6 mb-6">
        <div className="max-h-[480px] overflow-y-auto scroll-thin text-body text-ink-secondary">
          {report && <MarkdownWithMath>{report.content_md}</MarkdownWithMath>}
        </div>
      </Card>

      <div className="flex flex-wrap gap-3">
        {activeSession && activeSession.status === "active" ? (
          <>
            <Button variant="primary" size="lg" onClick={handleContinue} disabled={starting}>
              <Play className="w-4 h-4" />
              继续训练
            </Button>
            <Button
              variant="secondary"
              size="lg"
              onClick={() => handleStart(true)}
              disabled={starting}
            >
              {starting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  生成中…
                </>
              ) : (
                <>
                  <RotateCcw className="w-4 h-4" />
                  重新开始
                </>
              )}
            </Button>
          </>
        ) : (
          <Button variant="primary" size="lg" onClick={() => handleStart(false)} disabled={starting}>
            {starting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                AI 正在生成训练…
              </>
            ) : (
              <>
                <Target className="w-4 h-4" />
                开始针对训练
              </>
            )}
          </Button>
        )}
      </div>

      {starting && (
        <p className="text-small text-ink-tertiary mt-3">
          分析学习报告与薄弱知识点，从题库匹配题目…
        </p>
      )}
    </AppShell>
  )
}
