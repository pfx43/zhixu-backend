import type { Note } from "@/types"

export const noteFilters = [
  { label: "全部", value: "all" },
  { label: "最近", value: "recent" },
  { label: "待整理", value: "pending" },
  { label: "AI 摘要", value: "ai" },
  { label: "有标签", value: "tagged" },
  { label: "未分类", value: "uncategorized" },
]

export const notesStats = {
  total: 0,
  pending: 0,
  aiSummary: 0,
}

// 空状态用：返回空数组表示无数据
export const notes: Note[] = []

// 有数据示例（用于演示列表/卡片视图，可切换使用）
export const sampleNotes: Note[] = [
  {
    id: "n1",
    title: "Flutter State 管理笔记",
    excerpt: "Flutter 的状态管理方案从简到繁依次是 setState、InheritedWidget、Provider、Riverpod、Bloc。setState 适合局部简单状态，Provider 是官方推荐的基础方案……",
    tags: ["Flutter", "State 管理", "前端"],
    updatedAt: "6 小时前",
    wordCount: 1280,
    source: "manual",
    hasAISummary: true,
    organized: true,
    category: "前端开发",
  },
  {
    id: "n2",
    title: "Provider 与 Riverpod 对比",
    excerpt: "Provider 依赖 BuildContext，Riverpod 不依赖；Riverpod 编译时类型安全，Provider 运行时才能发现错误；Riverpod 可测试性更强……",
    tags: ["Flutter", "Riverpod", "Provider"],
    updatedAt: "昨天",
    wordCount: 860,
    source: "ai",
    hasAISummary: true,
    organized: true,
    category: "前端开发",
  },
  {
    id: "n3",
    title: "Dart 异步编程要点",
    excerpt: "Dart 是单线程事件驱动模型，通过 Future、async/await 和 Stream 处理异步。async/await 是 Future 的语法糖，让异步代码读起来像同步……",
    tags: ["Dart", "异步"],
    updatedAt: "2 天前",
    wordCount: 540,
    source: "doc",
    hasAISummary: false,
    organized: false,
  },
  {
    id: "n4",
    title: "HTTP 请求封装实践",
    excerpt: "在 Flutter 中封装 HTTP 请求，通常使用 dio 或 http 包。推荐 dio，支持拦截器、全局配置、表单上传等。封装要点：统一错误处理、loading 状态、token 注入……",
    tags: ["Flutter", "HTTP"],
    updatedAt: "3 天前",
    wordCount: 720,
    source: "manual",
    hasAISummary: true,
    organized: true,
  },
  {
    id: "n5",
    title: "SQLite 数据库基础",
    excerpt: "Flutter 中使用 SQLite 通常配合 sqflite 包。基本流程：打开数据库、创建表、增删改查。注意事务的使用和异步处理……",
    tags: ["Flutter", "数据库"],
    updatedAt: "5 天前",
    wordCount: 460,
    source: "doc",
    hasAISummary: false,
    organized: false,
  },
  {
    id: "n6",
    title: "今日灵感",
    excerpt: "拍照识别纸质资料这个功能很实用，OCR 自动识别并整理后可以直接生成笔记。考虑加入批量处理和自动分类标签的能力……",
    tags: ["灵感", "OCR"],
    updatedAt: "1 周前",
    wordCount: 180,
    source: "manual",
    hasAISummary: false,
    organized: true,
    category: "灵感",
  },
]

export const tagSuggestions = [
  "Flutter",
  "Dart",
  "State 管理",
  "HTTP",
  "数据库",
  "异步",
  "前端",
  "后端",
  "AI",
  "灵感",
]

export const organizeSuggestions = [
  { id: "o1", title: "「Dart 异步编程要点」建议添加标签", action: "添加标签" },
  { id: "o2", title: "「SQLite 数据库基础」待整理", action: "去整理" },
  { id: "o3", title: "3 篇笔记未分类，建议归类", action: "批量分类" },
]
