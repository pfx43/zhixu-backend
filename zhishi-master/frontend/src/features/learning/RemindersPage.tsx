import { useState } from "react"
import {
  Bell,
  CheckCircle2,
  Calendar,
  Clock,
} from "lucide-react"
import { AppShell } from "@/components/layout/AppShell"
import { PageHeader } from "@/components/blocks/PageHeader"
import { StatCard } from "@/components/ui/stat-card"
import { EmptyState } from "@/components/ui/empty-state"
import { Chip } from "@/components/ui/chip"

const filters = [
  { label: "今天", value: "today" },
  { label: "本周", value: "week" },
  { label: "全部", value: "all" },
  { label: "已完成", value: "done" },
]

export function RemindersPage() {
  const [filter, setFilter] = useState("all")

  return (
    <AppShell maxWidth={1180}>
      <PageHeader title="智能提醒" subtitle="Tina 会帮你安排复习和任务提醒" />

      {/* 统计 */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <StatCard icon={Clock} label="待处理" value={0} tone="warning" />
        <StatCard icon={Calendar} label="今天" value={0} tone="primary" />
        <StatCard icon={CheckCircle2} label="已完成" value={0} tone="success" />
      </div>

      {/* 筛选 */}
      <div className="flex items-center gap-2 mb-5">
        {filters.map((f) => (
          <Chip key={f.value} variant={filter === f.value ? "selected" : "filter"} onClick={() => setFilter(f.value)}>
            {f.label}
          </Chip>
        ))}
      </div>

      {/* 列表 */}
      <div className="bg-surface border border-line-soft rounded-lg shadow-xs">
        <EmptyState
          icon={Bell}
          title="暂无提醒"
          description="你可以为复习、作业、文档整理设置提醒。"
          size="lg"
        />
      </div>
    </AppShell>
  )
}