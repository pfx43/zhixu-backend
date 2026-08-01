// 首页 mock 数据

export const greeting = {
  text: "晚上好，啊噗",
  subtitle: "持续学习，成就更好的自己。",
  stats: [
    { label: "连续学习", value: "5 天" },
    { label: "知识库", value: "12 篇" },
    { label: "待整理", value: "3 项" },
  ],
}

export const quickActions = [
  { id: "note", title: "新建笔记", description: "记录想法、整理资料", to: "/notes" },
  { id: "chat", title: "AI 对话", description: "向 Tina 提问、整理文档", to: "/chat" },
  { id: "upload", title: "上传资料", description: "PDF、TXT、MD、DOCX", to: "/knowledge/upload" },
  { id: "graph", title: "知识图谱", description: "查看标签与知识关系", to: "/graph" },
]

export const recommendation = {
  title: "智能推荐",
  highlight: "上次学习 Flutter 核心组件，建议复习 State 管理相关知识点。",
  description: "根据你的学习记录和掌握度，State 管理是影响后续组件开发的关键，建议优先巩固。",
  actionLabel: "查看推荐内容",
}

export const recentItems = [
  {
    id: "1",
    title: "知拾食用指南",
    meta: "Markdown · 软件说明 · 2 小时前",
  },
  {
    id: "2",
    title: "今日灵感",
    meta: "拍照识别纸质资料，OCR 自动识别并整理 · 3 小时前",
  },
  {
    id: "3",
    title: "Flutter State 管理笔记",
    meta: "学习笔记 · 6 小时前",
  },
  {
    id: "4",
    title: "Provider 与 Riverpod 对比",
    meta: "AI 摘要 · 昨天",
  },
]

export const todayStatus = {
  studyMinutes: 120,
  pendingReview: 3,
  pendingDocs: 2,
}

export const tinaSuggestions = [
  "今天适合补 State 管理",
  "有 1 份文档建议添加标签",
  "Dart 基础语法可以开始复习",
]

export const rightPanelShortcuts = [
  { label: "上传资料", to: "/knowledge/upload" },
  { label: "创建提醒", to: "/reminders" },
  { label: "查看学习路径", to: "/path" },
]
