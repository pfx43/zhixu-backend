import { useState } from "react"
import {
  Sparkles,
  Plus,
  X,
  Check,
  Network,
} from "lucide-react"
import { AppShell } from "@/components/layout/AppShell"
import { PageHeader } from "@/components/blocks/PageHeader"
import { SectionHeader } from "@/components/blocks/SectionHeader"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Chip } from "@/components/ui/chip"
import { Badge } from "@/components/ui/badge"
import { useAuth } from "@/context/AuthContext"

const tinaUsage = [
  "调整回答深度",
  "推荐更适合你的学习路径",
  "优先整理与你目标相关的知识",
  "生成更贴合你的复习提醒",
]

export function ProfilePage() {
  const { user } = useAuth()
  const [name, setName] = useState(user?.nickname || "")
  const [goal, setGoal] = useState("")
  const [tags, setTags] = useState<string[]>([])
  const [newTag, setNewTag] = useState("")

  const addTag = () => {
    const t = newTag.trim()
    if (t && !tags.includes(t)) {
      setTags([...tags, t])
    }
    setNewTag("")
  }

  return (
    <AppShell maxWidth={960}>
      <PageHeader title="个人学习画像" subtitle="维护昵称、学习目标和常用知识标签" />

      {/* 顶部大卡片 */}
      <Card variant="elevated" className="mb-8">
        <div className="p-6 flex items-center gap-5">
          <div className="w-20 h-20 rounded-full bg-gradient-primary text-white text-section-title font-semibold flex items-center justify-center shadow-primary shrink-0">
            {user?.nickname?.charAt(0) || "?"}
          </div>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h2 className="text-section-title font-semibold text-ink-primary">{name || user?.nickname || "未设置"}</h2>
              <Badge variant="primary" size="md">用户</Badge>
            </div>
            <p className="text-caption text-ink-secondary">{goal || "设置学习目标，让 Tina 更好地帮助你"}</p>
          </div>
        </div>
      </Card>

      {/* 主体双栏 */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-6">
        {/* 左侧：画像编辑 */}
        <div className="space-y-6">
          <Card className="p-6">
            <SectionHeader title="基础信息" />

            <div className="space-y-5">
              <Field label="昵称">
                <Input value={name} onChange={(e) => setName(e.target.value)} />
              </Field>

              <Field label="可选资料 · 性别">
                <div className="flex gap-2">
                  <Chip variant="default">男</Chip>
                  <Chip variant="default">女</Chip>
                  <Chip variant="default">不公开</Chip>
                </div>
              </Field>
            </div>
          </Card>

          <Card className="p-6">
            <SectionHeader title="学习目标与偏好" />
            <textarea
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              rows={3}
              className="w-full resize-none rounded-md bg-surface border border-line px-3.5 py-2.5 text-body text-ink-primary placeholder:text-ink-tertiary focus:outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/10 transition-all"
              placeholder="描述你的学习目标..."
            />
          </Card>

          <Card className="p-6">
            <SectionHeader title="学习标签" subtitle="Tina 会基于标签为你推荐内容" />
            <div className="flex items-center gap-2 flex-wrap mb-4">
              {tags.map((tag) => (
                <span
                  key={tag}
                  className="inline-flex items-center gap-1 h-8 px-3 rounded-full bg-primary-soft text-primary-active border border-primary/20 text-caption font-medium"
                >
                  {tag}
                  <button
                    onClick={() => setTags(tags.filter((t) => t !== tag))}
                    className="hover:bg-primary/20 rounded-full p-0.5 transition-colors"
                  >
                    <X className="w-3 h-3" strokeWidth={2.5} />
                  </button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <Input
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addTag()}
                placeholder="添加新标签..."
              />
              <Button variant="secondary" size="md" onClick={addTag}>
                <Plus className="w-4 h-4" strokeWidth={2} />
                添加
              </Button>
            </div>
          </Card>
        </div>

        {/* 右侧：Tina 使用说明 */}
        <div>
          <Card className="p-6 sticky top-0">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-9 h-9 rounded-md bg-gradient-primary flex items-center justify-center shadow-primary">
                <Sparkles className="w-5 h-5 text-white" strokeWidth={2} />
              </div>
              <h3 className="text-card-title font-semibold text-ink-primary">Tina 会如何使用你的画像？</h3>
            </div>
            <ul className="space-y-3">
              {tinaUsage.map((u) => (
                <li key={u} className="flex items-start gap-2.5">
                  <span className="w-5 h-5 rounded-full bg-primary-soft text-primary flex items-center justify-center shrink-0 mt-0.5">
                    <Check className="w-3 h-3" strokeWidth={2.5} />
                  </span>
                  <span className="text-caption text-ink-secondary leading-relaxed">{u}</span>
                </li>
              ))}
            </ul>

            <div className="mt-6 pt-5 border-t border-line-soft">
              <div className="flex items-center gap-2 text-small text-ink-tertiary mb-2">
                <Network className="w-4 h-4" strokeWidth={2} />
                知识图谱预览
              </div>
              <div className="flex flex-wrap gap-1.5">
                {["Flutter", "Dart", "后端", "AI", "数据库"].map((t) => (
                  <span key={t} className="inline-flex items-center h-6 px-2 rounded-full bg-surface-soft text-small text-ink-secondary">
                    {t}
                  </span>
                ))}
              </div>
            </div>
          </Card>
        </div>
      </div>

      {/* 右侧辅助栏：画像页右侧说明已内嵌在主体双栏中，不重复渲染 */}
    </AppShell>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-small text-ink-secondary mb-1.5 font-medium">{label}</label>
      {children}
    </div>
  )
}
