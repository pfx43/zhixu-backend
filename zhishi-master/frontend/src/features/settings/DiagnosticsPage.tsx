import { useState } from "react"
import {
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronRight,
} from "lucide-react"
import { AppShell } from "@/components/layout/AppShell"
import { PageHeader } from "@/components/blocks/PageHeader"
import { SectionHeader } from "@/components/blocks/SectionHeader"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { TimelineStep, type TimelineStatus } from "@/components/blocks/TimelineStep"

const permissions = [
  { name: "无障碍服务", status: "warning" as const, desc: "需要设置" },
  { name: "悬浮窗权限", status: "warning" as const, desc: "需要设置" },
  { name: "透明覆盖层", status: "success" as const, desc: "未发现问题" },
]

const diagnosticSteps: { title: string; status: TimelineStatus; desc?: string }[] = [
  { title: "正在检测系统信息", status: "success" },
  { title: "Android 版本", status: "neutral", desc: "Android 16" },
  { title: "ROM 类型", status: "neutral", desc: "MIUI" },
  { title: "设备制造商", status: "neutral", desc: "Xiaomi" },
  { title: "无障碍服务", status: "error", desc: "未启用" },
  { title: "悬浮窗权限", status: "error", desc: "未授予" },
  { title: "透明覆盖层", status: "success", desc: "正常" },
  { title: "系统响应正常", status: "success", desc: "100ms" },
]

export function DiagnosticsPage() {
  const [solutionOpen, setSolutionOpen] = useState(true)

  return (
    <AppShell maxWidth={860}>
      <PageHeader title="诊断与修复" subtitle="检查系统权限与连接状态" />

      {/* 顶部状态卡 */}
      <Card variant="elevated" className="mb-8">
        <div className="p-6 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-warning-soft text-warning flex items-center justify-center shrink-0">
            <ShieldCheck className="w-6 h-6" strokeWidth={2} />
          </div>
          <div className="flex-1">
            <h2 className="text-card-title font-semibold text-ink-primary mb-0.5">当前权限状态</h2>
            <p className="text-caption text-ink-secondary">
              发现 <span className="text-warning font-semibold">2 个问题</span>，需要进行修复
            </p>
          </div>
        </div>
      </Card>

      {/* 权限状态列表 */}
      <div className="mb-8">
        <SectionHeader title="权限状态" />
        <Card className="divide-y divide-line-soft overflow-hidden">
          {permissions.map((p) => (
            <div key={p.name} className="flex items-center gap-3 px-5 py-3.5">
              {p.status === "success" ? (
                <CheckCircle2 className="w-5 h-5 text-success shrink-0" strokeWidth={2} />
              ) : (
                <AlertTriangle className="w-5 h-5 text-warning shrink-0" strokeWidth={2} />
              )}
              <div className="flex-1">
                <div className="text-body text-ink-primary font-medium">{p.name}</div>
              </div>
              <Badge variant={p.status === "success" ? "success" : "warning"}>{p.desc}</Badge>
            </div>
          ))}
        </Card>
      </div>

      {/* 排查步骤 - 时间线 */}
      <div className="mb-8">
        <SectionHeader title="排查步骤" subtitle="系统检测结果" />
        <Card className="p-6">
          <div className="space-y-0">
            {diagnosticSteps.map((step, i) => (
              <TimelineStep
                key={i}
                index={i + 1}
                title={step.title}
                description={step.desc}
                status={step.status}
                isLast={i === diagnosticSteps.length - 1}
              />
            ))}
          </div>
        </Card>
      </div>

      {/* 解决方案 - 可展开卡片 */}
      <div>
        <SectionHeader title="解决方案" />
        <Card className="overflow-hidden">
          <button
            onClick={() => setSolutionOpen((v) => !v)}
            className="w-full flex items-center gap-3 px-5 py-4 hover:bg-surface-soft transition-colors"
          >
            <div className="w-8 h-8 rounded-md bg-warning-soft text-warning flex items-center justify-center">
              <AlertTriangle className="w-4 h-4" strokeWidth={2} />
            </div>
            <div className="text-left flex-1">
              <div className="text-body text-ink-primary font-medium">需要解决的问题</div>
              <div className="text-small text-ink-tertiary">2 项待修复</div>
            </div>
            {solutionOpen ? (
              <ChevronDown className="w-5 h-5 text-ink-tertiary" strokeWidth={2} />
            ) : (
              <ChevronRight className="w-5 h-5 text-ink-tertiary" strokeWidth={2} />
            )}
          </button>
          {solutionOpen && (
            <div className="border-t border-line-soft p-5 space-y-4">
              <div className="space-y-2">
                {["无障碍服务未启用", "悬浮窗权限未授予"].map((p) => (
                  <div key={p} className="flex items-center gap-2 text-caption text-ink-secondary">
                    <XCircle className="w-4 h-4 text-danger shrink-0" strokeWidth={2} />
                    {p}
                  </div>
                ))}
              </div>

              <div className="pt-3 border-t border-line-soft">
                <div className="text-small font-medium text-ink-primary mb-3">操作步骤</div>
                <ol className="space-y-2.5">
                  {[
                    "点击一键设置权限",
                    "按照引导完成授权",
                    "设置完成后重新运行诊断",
                  ].map((step, i) => (
                    <li key={i} className="flex items-start gap-2.5">
                      <span className="w-5 h-5 rounded-full bg-primary-soft text-primary text-small font-semibold flex items-center justify-center shrink-0">
                        {i + 1}
                      </span>
                      <span className="text-caption text-ink-primary leading-relaxed pt-0.5">{step}</span>
                    </li>
                  ))}
                </ol>
              </div>
            </div>
          )}
        </Card>
      </div>
    </AppShell>
  )
}
