import { useState, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import {
  BarChart3,
  FileText,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Library,
  Brain,
  Activity,
  ArrowRight,
  Upload,
  PenLine,
  Sparkles,
  Target,
  Loader2,
} from "lucide-react"
import { AppShell } from "@/components/layout/AppShell"
import { PageHeader } from "@/components/blocks/PageHeader"
import { SectionHeader } from "@/components/blocks/SectionHeader"
import { StatCard } from "@/components/ui/stat-card"
import { EmptyState } from "@/components/ui/empty-state"
import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { ProgressMeter } from "@/components/blocks/ProgressMeter"
import { MarkdownWithMath } from "@/components/blocks/MarkdownWithMath"
import { analyticsApi, reportsApi } from "@/lib/api"
import type { LearningReport, LearningStats, TagStatsResult } from "@/types"

function formatDateTime(value?: string | null): string {
  if (!value) return "—"
  try {
    const d = new Date(value)
    if (Number.isNaN(d.getTime())) return value
    return d.toLocaleString("zh-CN", {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    return value
  }
}

function answerStatusBadge(status: string) {
  if (status === "correct") return { label: "正确", variant: "success" as const }
  if (status === "wrong") return { label: "错误", variant: "danger" as const }
  if (status === "unknown") return { label: "不会", variant: "warning" as const }
  return { label: status, variant: "neutral" as const }
}

function sessionStatusLabel(status: string) {
  if (status === "completed") return "已完成"
  if (status === "active") return "进行中"
  return status
}

export function LearningAnalyticsPage() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [stats, setStats] = useState<LearningStats | null>(null)
  const [tagStats, setTagStats] = useState<TagStatsResult | null>(null)
  const [reports, setReports] = useState<LearningReport[]>([])
  const [latestReport, setLatestReport] = useState<LearningReport | null>(null)
  const [generatingReport, setGeneratingReport] = useState(false)
  const [reportError, setReportError] = useState<string | null>(null)

  const loadReports = () => {
    reportsApi
      .list()
      .then((res) => setReports(res.reports || []))
      .catch(() => setReports([]))
    reportsApi
      .getLatest()
      .then(setLatestReport)
      .catch(() => setLatestReport(null))
  }

  useEffect(() => {
    Promise.all([analyticsApi.getStats(), analyticsApi.getTagStats()])
      .then(([s, tags]) => {
        setStats(s)
        setTagStats(tags)
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "加载失败")
      })
      .finally(() => setLoading(false))
    loadReports()
  }, [])

  const handleGenerateReport = async () => {
    setGeneratingReport(true)
    setReportError(null)
    try {
      const res = await reportsApi.generate()
      setLatestReport(res.report)
      loadReports()
    } catch (err: unknown) {
      setReportError(err instanceof Error ? err.message : "生成失败")
    } finally {
      setGeneratingReport(false)
    }
  }

  const docs = stats?.documents
  const questions = stats?.questions
  const hasDocuments = (docs?.total ?? 0) > 0
  const hasQuestions = (questions?.total ?? 0) > 0
  const hasPractice = (questions?.answered ?? 0) > 0

  const accuracyDisplay =
    questions?.accuracy_rate != null ? `${questions.accuracy_rate}%` : "—"

  if (loading) {
    return (
      <AppShell maxWidth={1180}>
        <PageHeader title="学习分析" subtitle="汇总知识库与刷题数据">
          <Badge variant="primary" size="md">加载中</Badge>
        </PageHeader>
        <div className="bg-surface border border-line-soft rounded-lg shadow-xs p-12 flex items-center justify-center">
          <div className="flex items-center gap-2 text-ink-tertiary">
            <div className="w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
            <span className="text-body">加载中...</span>
          </div>
        </div>
      </AppShell>
    )
  }

  if (error) {
    return (
      <AppShell maxWidth={1180}>
        <PageHeader title="学习分析" subtitle="汇总知识库与刷题数据" />
        <Card className="p-8 text-center">
          <p className="text-body text-danger mb-4">{error}</p>
          <Button variant="secondary" onClick={() => window.location.reload()}>
            重试
          </Button>
        </Card>
      </AppShell>
    )
  }

  return (
    <AppShell maxWidth={1180}>
      <PageHeader
        title="学习分析"
        subtitle="基于你的知识库文档、题库与刷题记录"
      >
        <Button variant="secondary" size="md" onClick={() => navigate("/training/targeted")}>
          <Target className="w-4 h-4" strokeWidth={2} />
          针对训练
        </Button>
        <Button variant="secondary" size="md" onClick={() => navigate("/quiz")}>
          去刷题
        </Button>
      </PageHeader>

      <div className="mb-8">
        <SectionHeader title="学习报告" subtitle="AI 分析薄弱知识点，自动保存到生活区笔记">
          <Button
            variant="primary"
            size="sm"
            onClick={handleGenerateReport}
            disabled={generatingReport}
          >
            {generatingReport ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                生成中…
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" strokeWidth={2} />
                生成学习报告
              </>
            )}
          </Button>
        </SectionHeader>

        {reportError && (
          <Card className="p-4 mb-4 border-danger/30 text-danger text-body">{reportError}</Card>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card className="p-5">
            <h3 className="text-card-title font-semibold text-ink-primary mb-3">最新报告预览</h3>
            {!latestReport ? (
              <p className="text-body text-ink-tertiary py-4">
                暂无报告，点击「生成学习报告」获取 AI 分析与建议。
              </p>
            ) : (
              <>
                <p className="text-small text-ink-tertiary mb-3">
                  {latestReport.title} · {formatDateTime(latestReport.created_at)}
                </p>
                <div className="max-h-64 overflow-y-auto scroll-thin text-body text-ink-secondary border border-line-soft rounded-md p-3">
                  <MarkdownWithMath>{latestReport.content_md.slice(0, 2000)}</MarkdownWithMath>
                  {latestReport.content_md.length > 2000 && (
                    <p className="text-caption text-ink-tertiary mt-2">（内容已截断，完整版见笔记）</p>
                  )}
                </div>
              </>
            )}
          </Card>

          <Card className="p-5">
            <h3 className="text-card-title font-semibold text-ink-primary mb-3">历史报告</h3>
            {reports.length === 0 ? (
              <p className="text-body text-ink-tertiary py-4">暂无历史报告</p>
            ) : (
              <ul className="space-y-2 max-h-64 overflow-y-auto scroll-thin">
                {reports.map((r) => (
                  <li
                    key={r.id}
                    className="flex items-center justify-between gap-2 py-2 border-b border-line-soft last:border-0 text-small"
                  >
                    <span className="text-ink-primary truncate">{r.title}</span>
                    <span className="text-ink-tertiary shrink-0">{formatDateTime(r.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      {(tagStats?.by_tag.length ?? 0) > 0 && (
        <div className="mb-8">
          <SectionHeader title="知识点 Tag 统计" subtitle="按 tag 聚合对错次数" />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {tagStats?.by_tag.slice(0, 9).map((t) => (
              <Card key={t.tag} className="p-4">
                <div className="font-medium text-ink-primary truncate mb-1">{t.tag}</div>
                <div className="text-small text-ink-tertiary">
                  对 {t.correct_count} · 错 {t.wrong_count} · 不会 {t.unknown_count}
                  {t.accuracy_rate != null && ` · 正确率 ${t.accuracy_rate}%`}
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}

      {!hasDocuments && !hasQuestions ? (
        <Card variant="elevated">
          <EmptyState
            icon={BarChart3}
            title="还没有学习数据"
            description="上传学习区文档并完成出题后，这里会展示文档处理进度、题库规模与刷题表现。"
            primaryAction={{ label: "上传资料", onClick: () => navigate("/knowledge/upload") }}
            secondaryAction={{ label: "前往出题", onClick: () => navigate("/question-gen") }}
          />
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <StatCard
              icon={Library}
              label="知识库文档"
              value={docs?.total ?? 0}
              hint={`学习区 ${docs?.study_zone ?? 0} 份 · 已索引 ${docs?.indexed ?? 0}`}
              tone="primary"
            />
            <StatCard
              icon={FileText}
              label="已出题文档"
              value={docs?.with_questions ?? 0}
              hint={
                (docs?.processing ?? 0) > 0
                  ? `${docs?.processing} 份处理中`
                  : undefined
              }
              tone="info"
            />
            <StatCard
              icon={Brain}
              label="题库题目"
              value={questions?.total ?? 0}
              hint={`已作答 ${questions?.answered ?? 0} 题`}
              tone="neutral"
            />
            <StatCard
              icon={CheckCircle2}
              label="正确率"
              value={accuracyDisplay}
              hint={
                hasPractice
                  ? `正确 ${questions?.correct ?? 0} · 错误 ${questions?.wrong ?? 0}`
                  : "完成刷题后显示"
              }
              tone="success"
            />
          </div>

          {hasPractice && (
            <div className="grid grid-cols-3 gap-4 mb-8">
              <StatCard icon={CheckCircle2} label="答对" value={questions?.correct ?? 0} tone="success" />
              <StatCard icon={XCircle} label="答错" value={questions?.wrong ?? 0} tone="warning" />
              <StatCard icon={HelpCircle} label="标记不会" value={questions?.unknown ?? 0} tone="neutral" />
            </div>
          )}

          <div className="mb-8">
            <SectionHeader
              title="按文档刷题进度"
              subtitle={hasQuestions ? "每份文档的题库规模与作答情况" : "暂无题目，请先在出题页生成题目"}
            >
              {hasQuestions && (
                <Button variant="ghost" size="sm" onClick={() => navigate("/question-gen")}>
                  前往出题
                  <ArrowRight className="w-4 h-4" strokeWidth={2} />
                </Button>
              )}
            </SectionHeader>

            {!hasQuestions ? (
              <Card>
                <EmptyState
                  icon={PenLine}
                  title="还没有题目"
                  description="在出题页选择文档与页码，AI 生成题目后即可开始练习。"
                  primaryAction={{ label: "前往出题", onClick: () => navigate("/question-gen") }}
                  size="sm"
                />
              </Card>
            ) : stats?.document_progress.length === 0 ? (
              <Card className="p-8 text-center text-body text-ink-tertiary">
                题目已生成，但尚未关联到具体文档
              </Card>
            ) : (
              <div className="space-y-3">
                {stats?.document_progress.map((doc) => {
                  const progressPct =
                    doc.question_total > 0
                      ? Math.round((doc.answered_count / doc.question_total) * 100)
                      : 0
                  return (
                    <Card key={doc.document_id} className="p-5">
                      <div className="flex items-start justify-between gap-4 mb-4">
                        <div className="min-w-0">
                          <h3 className="text-body font-medium text-ink-primary truncate">
                            {doc.document_name}
                          </h3>
                          <p className="text-small text-ink-tertiary mt-0.5">
                            {doc.question_total} 题 · 已做 {doc.answered_count} 题
                            {doc.accuracy_rate != null && ` · 正确率 ${doc.accuracy_rate}%`}
                          </p>
                        </div>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => navigate(`/quiz?document_id=${doc.document_id}`)}
                        >
                          去练习
                        </Button>
                      </div>
                      <ProgressMeter label="完成进度" value={progressPct} />
                    </Card>
                  )
                })}
              </div>
            )}
          </div>

          <div className="mb-4">
            <SectionHeader title="最近练习" subtitle="最近的刷题会话与作答记录">
              {!hasPractice && hasDocuments && (
                <Button variant="ghost" size="sm" onClick={() => navigate("/quiz")}>
                  开始刷题
                  <ArrowRight className="w-4 h-4" strokeWidth={2} />
                </Button>
              )}
            </SectionHeader>

            {!hasPractice ? (
              <Card>
                <EmptyState
                  icon={Activity}
                  title="还没有练习记录"
                  description={
                    hasQuestions
                      ? "前往题库页选择文档，开始你的第一次练习。"
                      : "先上传文档并出题，再开始刷题。"
                  }
                  primaryAction={
                    hasQuestions
                      ? { label: "去刷题", onClick: () => navigate("/quiz") }
                      : { label: "上传资料", onClick: () => navigate("/knowledge/upload") }
                  }
                  secondaryAction={
                    !hasQuestions
                      ? { label: "前往出题", onClick: () => navigate("/question-gen") }
                      : undefined
                  }
                  size="sm"
                />
              </Card>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <Card className="p-5">
                  <h3 className="text-card-title font-semibold text-ink-primary mb-4">刷题会话</h3>
                  {(stats?.recent_sessions.length ?? 0) === 0 ? (
                    <p className="text-body text-ink-tertiary py-4 text-center">暂无会话记录</p>
                  ) : (
                    <div className="space-y-3">
                      {stats?.recent_sessions.map((session) => (
                        <div
                          key={session.id}
                          className="flex items-center justify-between gap-3 py-2 border-b border-line-soft last:border-0"
                        >
                          <div className="min-w-0">
                            <p className="text-body text-ink-primary truncate">
                              {session.document_name || "未关联文档"}
                            </p>
                            <p className="text-small text-ink-tertiary">
                              {formatDateTime(session.started_at)} · {session.answered_count}/{session.total_questions} 题
                            </p>
                          </div>
                          <Badge
                            variant={session.status === "completed" ? "success" : "primary"}
                            size="sm"
                          >
                            {sessionStatusLabel(session.status)}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  )}
                </Card>

                <Card className="p-5">
                  <h3 className="text-card-title font-semibold text-ink-primary mb-4">最近作答</h3>
                  {(stats?.recent_answers.length ?? 0) === 0 ? (
                    <p className="text-body text-ink-tertiary py-4 text-center">暂无作答记录</p>
                  ) : (
                    <div className="space-y-3">
                      {stats?.recent_answers.map((answer) => {
                        const badge = answerStatusBadge(answer.status)
                        return (
                          <div
                            key={`${answer.question_id}-${answer.answered_at}`}
                            className="flex items-start justify-between gap-3 py-2 border-b border-line-soft last:border-0"
                          >
                            <div className="min-w-0">
                              <p className="text-body text-ink-primary line-clamp-2">{answer.stem}</p>
                              <p className="text-small text-ink-tertiary mt-0.5">
                                {answer.document_name || "未知文档"} · {formatDateTime(answer.answered_at)}
                              </p>
                            </div>
                            <Badge variant={badge.variant} size="sm" className="shrink-0">
                              {badge.label}
                            </Badge>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </Card>
              </div>
            )}
          </div>

          {hasDocuments && !hasQuestions && (
            <Card variant="elevated" className="mt-6">
              <EmptyState
                icon={Upload}
                title="文档已就绪，下一步：出题"
                description="学习区文档分段完成后，可在出题页按页 AI 生成题目。"
                primaryAction={{ label: "前往出题", onClick: () => navigate("/question-gen") }}
                size="sm"
              />
            </Card>
          )}
        </>
      )}
    </AppShell>
  )
}
