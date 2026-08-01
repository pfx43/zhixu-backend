import { useState } from "react"
import {
  Moon,
  BarChart3,
  Sparkles,
  Cpu,
  Database,
  ScanLine,
  Bell,
  Accessibility,
  Stethoscope,
  ChevronDown,
  ChevronRight,
  Wrench,
  Plug,
} from "lucide-react"
import { AppShell } from "@/components/layout/AppShell"
import { PageHeader } from "@/components/blocks/PageHeader"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

export function SettingsPage() {
  const [advancedOpen, setAdvancedOpen] = useState(false)

  return (
    <AppShell maxWidth={860}>
      <PageHeader title="设置中心" subtitle="管理画像、AI 助手、知识库、提醒和高级连接" />

      <div className="space-y-5">
        <SettingsGroup
          icon={Moon}
          title="账号与画像"
          items={[
            {
              icon: Moon,
              title: "深色模式",
              desc: "跟随系统",
              control: <ThemeSelector />,
            },
            {
              icon: BarChart3,
              title: "用户画像分析",
              desc: "启用学习分析、掌握度评估和学习路径推荐",
              control: <Toggle defaultOn />,
            },
          ]}
        />

        <SettingsGroup
          icon={Sparkles}
          title="AI 助手"
          items={[
            {
              icon: Sparkles,
              title: "主动智能推荐",
              desc: "启用后会消耗更多 Token",
              control: <Toggle />,
            },
          ]}
        />

        <SettingsGroup
          icon={Cpu}
          title="AI 连接概况"
          items={[
            { icon: Cpu, title: "当前模型", desc: "deepseek-chat", control: <Badge variant="neutral">已配置</Badge> },
            { icon: Plug, title: "API 连接", desc: "已配置", control: <Badge variant="success">已配置</Badge> },
            { icon: Plug, title: "密钥状态", desc: "已配置", control: <Badge variant="success">已配置</Badge> },
            { icon: Cpu, title: "温度", desc: "1.0", control: <Badge variant="neutral">1.0</Badge> },
          ]}
        />

        <SettingsGroup
          icon={Database}
          title="知识库与上传"
          items={[
            { icon: Database, title: "Dify 连接", desc: "已配置", control: <Badge variant="success">已配置</Badge> },
            { icon: Plug, title: "Dify 密钥状态", desc: "已配置", control: <Badge variant="success">已配置</Badge> },
            { icon: Database, title: "数据集 ID", desc: "002fc6f7...", control: <Badge variant="neutral">已配置</Badge> },
          ]}
        />

        <SettingsGroup
          icon={ScanLine}
          title="OCR"
          items={[
            { icon: ScanLine, title: "OCR App ID", desc: "已配置", control: <Badge variant="success">已配置</Badge> },
            { icon: Plug, title: "OCR 密钥状态", desc: "已配置", control: <Badge variant="success">已配置</Badge> },
            { icon: Plug, title: "OCR 连接", desc: "已配置", control: <Badge variant="success">已配置</Badge> },
            { icon: Sparkles, title: "OCR 文字智能优化", desc: "关闭", control: <Toggle /> },
          ]}
        />

        <SettingsGroup
          icon={Bell}
          title="提醒与通知"
          items={[
            { icon: Accessibility, title: "无障碍访问", desc: "辅助功能设置", control: <ChevronRight className="w-4 h-4 text-ink-tertiary" strokeWidth={2} /> },
            { icon: Stethoscope, title: "诊断与修复", desc: "检查权限与连接状态", control: <ChevronRight className="w-4 h-4 text-ink-tertiary" strokeWidth={2} /> },
          ]}
        />

        {/* 高级设置 - 默认折叠 */}
        <Card className="overflow-hidden">
          <button
            onClick={() => setAdvancedOpen((v) => !v)}
            className="w-full flex items-center gap-3 px-5 py-4 hover:bg-surface-soft transition-colors"
          >
            <div className="w-9 h-9 rounded-md bg-surface-soft text-ink-secondary flex items-center justify-center">
              <Wrench className="w-5 h-5" strokeWidth={2} />
            </div>
            <div className="text-left flex-1">
              <div className="text-card-title font-semibold text-ink-primary">高级设置</div>
              <div className="text-small text-ink-tertiary">API、URL、后端连接、开发检查项</div>
            </div>
            {advancedOpen ? (
              <ChevronDown className="w-5 h-5 text-ink-tertiary" strokeWidth={2} />
            ) : (
              <ChevronRight className="w-5 h-5 text-ink-tertiary" strokeWidth={2} />
            )}
          </button>
          {advancedOpen && (
            <div className="border-t border-line-soft divide-y divide-line-soft">
              {[
                { title: "API", desc: "后端接口地址与密钥" },
                { title: "URL", desc: "服务端点配置" },
                { title: "后端连接", desc: "KT 后端连接状态" },
                { title: "开发检查项", desc: "调试与日志" },
              ].map((item) => (
                <div key={item.title} className="flex items-center justify-between gap-3 px-5 py-3.5">
                  <div>
                    <div className="text-body text-ink-primary font-medium">{item.title}</div>
                    <div className="text-small text-ink-tertiary">{item.desc}</div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-ink-tertiary" strokeWidth={2} />
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </AppShell>
  )
}

function SettingsGroup({
  icon: Icon,
  title,
  items,
}: {
  icon: typeof Moon
  title: string
  items: { icon: typeof Moon; title: string; desc: string; control: React.ReactNode }[]
}) {
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center gap-3 px-5 py-3.5 border-b border-line-soft bg-surface-soft/50">
        <div className="w-8 h-8 rounded-md bg-primary-soft text-primary flex items-center justify-center">
          <Icon className="w-4 h-4" strokeWidth={2} />
        </div>
        <h3 className="text-card-title font-semibold text-ink-primary">{title}</h3>
      </div>
      <div className="divide-y divide-line-soft">
        {items.map((item) => (
          <div key={item.title} className="flex items-center gap-3 px-5 py-3.5">
            <item.icon className="w-[18px] h-[18px] text-ink-tertiary shrink-0" strokeWidth={2} />
            <div className="flex-1 min-w-0">
              <div className="text-body text-ink-primary font-medium">{item.title}</div>
              <div className="text-small text-ink-tertiary truncate-1">{item.desc}</div>
            </div>
            {item.control}
          </div>
        ))}
      </div>
    </Card>
  )
}

function Toggle({ defaultOn = false }: { defaultOn?: boolean }) {
  const [on, setOn] = useState(defaultOn)
  return (
    <button
      onClick={() => setOn((v) => !v)}
      className={cn(
        "w-10 h-6 rounded-full p-0.5 transition-colors shrink-0",
        on ? "bg-primary" : "bg-line"
      )}
    >
      <span
        className={cn(
          "block w-5 h-5 rounded-full bg-white shadow-sm transition-transform",
          on && "translate-x-4"
        )}
      />
    </button>
  )
}

function ThemeSelector() {
  const [theme, setTheme] = useState("system")
  return (
    <div className="flex gap-1.5">
      {[
        { label: "跟随系统", value: "system" },
        { label: "浅色", value: "light" },
        { label: "深色", value: "dark" },
      ].map((t) => (
        <button
          key={t.value}
          onClick={() => setTheme(t.value)}
          className={cn(
            "h-7 px-2.5 rounded-md text-small font-medium transition-colors",
            theme === t.value ? "bg-primary-soft text-primary-active" : "text-ink-tertiary hover:bg-surface-soft"
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}
