import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { ChevronRight, FileText, Sparkles, Target } from "lucide-react"
import { AppShell } from "@/components/layout/AppShell"
import { PageHeader } from "@/components/blocks/PageHeader"
import { SectionHeader } from "@/components/blocks/SectionHeader"
import { EmptyState } from "@/components/ui/empty-state"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { reportsApi } from "@/lib/api"
import type { LearningReport } from "@/types"

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

export function TargetedTrainingListPage() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [reports, setReports] = useState<LearningReport[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    reportsApi
      .list()
      .then((res) => setReports(res.reports || []))
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "加载失败")
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <AppShell maxWidth={1180}>
        <PageHeader title="针对训练" subtitle="基于 AI 学习报告生成专属练习">
          <Badge variant="primary" size="md">加载中</Badge>
        </PageHeader>
        <div className="bg-surface border border-line-soft rounded-lg shadow-xs p-12 flex items-center justify-center">
          <div className="w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
        </div>
      </AppShell>
    )
  }

  if (error) {
    return (
      <AppShell maxWidth={1180}>
        <PageHeader title="针对训练" subtitle="基于 AI 学习报告生成专属练习" />
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
        title="针对训练"
        subtitle="选择一份 AI 学习报告，生成针对薄弱知识点的专属练习"
      >
        <Button variant="secondary" size="md" onClick={() => navigate("/analytics")}>
          <Sparkles className="w-4 h-4" strokeWidth={2} />
          去生成报告
        </Button>
      </PageHeader>

      <SectionHeader
        title="AI 学习报告"
        subtitle="点击报告查看详情并开始针对训练"
      />

      {reports.length === 0 ? (
        <Card variant="elevated">
          <EmptyState
            icon={Target}
            title="还没有学习报告"
            description="请先在「学习分析」页生成 AI 学习报告，再基于报告开始针对训练。"
            primaryAction={{ label: "前往学习分析", onClick: () => navigate("/analytics") }}
          />
        </Card>
      ) : (
        <ul className="space-y-3">
          {reports.map((report) => (
            <li key={report.id}>
              <button
                type="button"
                onClick={() => navigate(`/training/targeted/report/${report.id}`)}
                className="w-full text-left rounded-lg border border-line-soft bg-surface hover:border-primary/30 hover:bg-surface-soft transition-colors p-4 flex items-center gap-4 group"
              >
                <div className="w-10 h-10 rounded-lg bg-primary-soft flex items-center justify-center shrink-0">
                  <FileText className="w-5 h-5 text-primary" strokeWidth={2} />
                </div>
                <div className="min-w-0 flex-1">
                  <h3 className="text-body font-medium text-ink-primary truncate">
                    {report.title}
                  </h3>
                  <p className="text-small text-ink-tertiary mt-0.5">
                    {formatDateTime(report.created_at)}
                  </p>
                </div>
                <ChevronRight className="w-5 h-5 text-ink-tertiary group-hover:text-primary shrink-0" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </AppShell>
  )
}
