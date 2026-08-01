import { useState, useEffect } from "react"
import {
  Target,
  Sparkles,
  CheckCircle2,
  ArrowRight,
  Clock,
  Flame,
} from "lucide-react"
import { AppShell } from "@/components/layout/AppShell"
import { RightPanel } from "@/components/layout/RightPanel"
import { PageHeader } from "@/components/blocks/PageHeader"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ProgressMeter } from "@/components/blocks/ProgressMeter"
import { ktApi } from "@/lib/api"
import type { PathTask } from "@/types"
import { cn } from "@/lib/utils"

export function LearningPathPage() {
  const [loading, setLoading] = useState(true)
  const [tasks, setTasks] = useState<PathTask[]>([])
  const [selected, setSelected] = useState<PathTask | null>(null)

  useEffect(() => {
    const defaultStates = [
      { skill_name: "加法", value: 95 },
      { skill_name: "减法", value: 90 },
      { skill_name: "乘法", value: 75 },
      { skill_name: "除法", value: 60 },
      { skill_name: "一元一次方程", value: 40 },
      { skill_name: "函数基础", value: 25 },
      { skill_name: "微积分入门", value: 10 },
    ]

    ktApi.recommendLearningPath(defaultStates, 7)
      .then((res) => {
        const recs = res.recommendations || res.data || []
        const pathTasks: PathTask[] = recs.map((r: any, i: number) => ({
          id: `p${i + 1}`,
          order: i + 1,
          name: r.skill_name || r.name || "未知技能",
          priority: (r.priority || r.score || 50),
          estimatedMinutes: r.estimated_minutes || 30,
          readiness: (r.readiness === "high" ? "high" : r.readiness === "medium" ? "medium" : "low") as PathTask["readiness"],
          currentMastery: r.current_mastery || r.value || 0,
          learningReadiness: r.learning_readiness || r.readiness_score || 50,
          prerequisites: r.prerequisites || [],
          reason: r.reason || "建议按顺序学习",
          suggestion: r.suggestions || ["复习相关概念", "完成练习"],
        }))
        setTasks(pathTasks)
        if (pathTasks.length > 0) setSelected(pathTasks[0])
      })
      .catch(() => setTasks([]))
      .finally(() => setLoading(false))
  }, [])

  const recommendation = tasks.length > 0
    ? {
        currentSkill: `当前需要补强「${tasks[0].name}」`,
        nextStep: tasks[0].name,
        readiness: tasks[0].readiness === "high" ? "就绪度高，适合立即开始" : "建议先复习前置知识",
        score: tasks[0].priority,
      }
    : {
        currentSkill: "暂无推荐",
        nextStep: "—",
        readiness: "—",
        score: 0,
      }

  if (loading) {
    return (
      <AppShell maxWidth={1180}>
        <PageHeader title="学习路径" subtitle="下一步学什么的决策页" />
        <div className="bg-surface border border-line-soft rounded-lg shadow-xs p-12 flex items-center justify-center">
          <div className="flex items-center gap-2 text-ink-tertiary">
            <div className="w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
            <span className="text-body">正在分析学习路径…</span>
          </div>
        </div>
      </AppShell>
    )
  }

  return (
    <AppShell maxWidth={1180}>
      <PageHeader title="学习路径" subtitle="LEKT 推荐下一步学习内容" />

      {/* 顶部推荐卡 */}
      <Card variant="elevated" className="mb-8">
        <div className="p-6">
          <div className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full bg-primary/10 text-primary text-small font-medium mb-4">
            <Sparkles className="w-3.5 h-3.5" strokeWidth={2} />
            下一步学习建议
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <div>
              <div className="text-small text-ink-tertiary mb-1">当前技能</div>
              <div className="text-body text-ink-primary font-medium">{recommendation.currentSkill}</div>
            </div>
            <div>
              <div className="text-small text-ink-tertiary mb-1">推荐下一步</div>
              <div className="text-body text-primary font-semibold">{recommendation.nextStep}</div>
            </div>
            <div>
              <div className="text-small text-ink-tertiary mb-1">练习建议</div>
              <div className="text-body text-ink-primary font-medium">{recommendation.readiness}</div>
            </div>
            <div>
              <div className="text-small text-ink-tertiary mb-1">推荐指数</div>
              <div className="text-body text-ink-primary font-semibold">{recommendation.score.toFixed(1)}%</div>
            </div>
          </div>
        </div>
      </Card>

      {/* 路径列表 */}
      {tasks.length === 0 ? (
        <div className="text-body text-ink-tertiary py-12 text-center">
          暂无学习路径推荐，请先完善技能数据
        </div>
      ) : (
        <div className="space-y-4">
          {tasks.map((task) => (
            <PathCard
              key={task.id}
              task={task}
              selected={selected?.id === task.id}
              onSelect={() => setSelected(task)}
            />
          ))}
        </div>
      )}

      {/* 右侧详情 */}
      {selected && (
        <RightPanel title="任务详情">
          <TaskDetail task={selected} />
        </RightPanel>
      )}
    </AppShell>
  )
}

function PathCard({
  task,
  selected,
  onSelect,
}: {
  task: PathTask
  selected: boolean
  onSelect: () => void
}) {
  const readinessTone =
    task.readiness === "high" ? "success" : task.readiness === "medium" ? "warning" : "neutral"
  const readinessLabel = task.readiness === "high" ? "就绪度高" : task.readiness === "medium" ? "就绪度中" : "就绪度低"

  return (
    <Card
      className={cn(
        "p-5 cursor-pointer transition-all duration-160",
        selected ? "border-primary/40 shadow-primary" : "hover:-translate-y-0.5 hover:shadow-md hover:border-primary/30"
      )}
      onClick={onSelect}
    >
      <div className="flex items-start gap-4">
        {/* 序号 */}
        <div
          className={cn(
            "w-10 h-10 rounded-full flex items-center justify-center shrink-0 text-card-title font-semibold",
            selected ? "bg-primary text-white" : "bg-primary-soft text-primary"
          )}
        >
          {task.order}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5 flex-wrap">
            <h3 className="text-card-title font-semibold text-ink-primary">{task.name}</h3>
            <Badge variant={readinessTone as "success"} size="sm">{readinessLabel}</Badge>
          </div>

          <div className="flex items-center gap-4 text-small text-ink-tertiary mb-4">
            <span className="inline-flex items-center gap-1">
              <Target className="w-3.5 h-3.5" strokeWidth={2} />
              优先级 {task.priority.toFixed(1)}%
            </span>
            <span className="inline-flex items-center gap-1">
              <Clock className="w-3.5 h-3.5" strokeWidth={2} />
              预计 {task.estimatedMinutes} 分钟
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-3 mb-4">
            <ProgressMeter label="当前掌握度" value={task.currentMastery} warningBelow={40} />
            <ProgressMeter label="学习就绪度" value={task.learningReadiness} warningBelow={40} />
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-small text-ink-tertiary">先修条件：</span>
            {task.prerequisites.length === 0 ? (
              <span className="text-small text-ink-tertiary">无</span>
            ) : (
              task.prerequisites.map((p) => (
                <span
                  key={p}
                  className="inline-flex items-center gap-1 h-6 px-2 rounded-full bg-success-soft text-success text-small font-medium"
                >
                  <CheckCircle2 className="w-3 h-3" strokeWidth={2} />
                  {p}
                </span>
              ))
            )}
          </div>
        </div>

        <div className="flex flex-col gap-2 shrink-0">
          <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); onSelect() }}>
            查看详情
            <ArrowRight className="w-3.5 h-3.5" strokeWidth={2} />
          </Button>
        </div>
      </div>
    </Card>
  )
}

function TaskDetail({ task }: { task: PathTask }) {
  return (
    <div className="space-y-5">
      <div>
        <div className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full bg-primary/10 text-primary text-small font-medium mb-3">
          <Sparkles className="w-3.5 h-3.5" strokeWidth={2} />
          推荐指数 {(task.priority).toFixed(1)}%
        </div>
        <h3 className="text-card-title font-semibold text-ink-primary">{task.name}</h3>
      </div>

      <section>
        <h4 className="text-small font-medium text-ink-tertiary mb-2 uppercase tracking-wider flex items-center gap-1.5">
          <Flame className="w-3.5 h-3.5" strokeWidth={2} />
          为什么推荐它？
        </h4>
        <p className="text-caption text-ink-secondary leading-relaxed">{task.reason}</p>
      </section>

      <section>
        <h4 className="text-small font-medium text-ink-tertiary mb-2 uppercase tracking-wider">学习建议</h4>
        <ol className="space-y-2">
          {task.suggestion.map((s, i) => (
            <li key={i} className="flex items-start gap-2.5">
              <span className="w-5 h-5 rounded-full bg-primary-soft text-primary text-small font-semibold flex items-center justify-center shrink-0">
                {i + 1}
              </span>
              <span className="text-caption text-ink-primary leading-relaxed pt-0.5">{s}</span>
            </li>
          ))}
        </ol>
      </section>

      <section>
        <h4 className="text-small font-medium text-ink-tertiary mb-2 uppercase tracking-wider">先修条件</h4>
        <div className="flex flex-wrap gap-1.5">
          {task.prerequisites.length === 0 ? (
            <span className="text-small text-ink-tertiary">无（可直接开始）</span>
          ) : (
            task.prerequisites.map((p) => (
              <Badge key={p} variant="success" size="md">
                <CheckCircle2 className="w-3 h-3" strokeWidth={2} />
                {p}
              </Badge>
            ))
          )}
        </div>
      </section>
    </div>
  )
}