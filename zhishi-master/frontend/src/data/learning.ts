import type { SkillMastery, PathTask, Reminder, GraphNode, GraphEdge } from "@/types"

// 学习分析
export const learningOverview = {
  status: "已连续学习 5 天",
  mastery: 54.0,
  mastered: 1,
  practicing: 4,
  pending: 3,
  todayMinutes: 120,
  totalHours: 144,
}

export const skillMasteries: SkillMastery[] = [
  { name: "Dart 基础语法", mastery: 90, status: "mastered" },
  { name: "Flutter 核心组件", mastery: 70, status: "practicing" },
  { name: "State 管理", mastery: 50, status: "practicing" },
  { name: "HTTP 请求", mastery: 60, status: "practicing" },
  { name: "SQLite 数据库", mastery: 40, status: "pending" },
  { name: "异步编程", mastery: 30, status: "pending" },
  { name: "动画与手势", mastery: 20, status: "pending" },
  { name: "测试与调试", mastery: 15, status: "pending" },
]

export const logicConflicts = [
  {
    id: "c1",
    title: "HTTP 请求掌握度高于前置知识异步编程",
    suggestion: "建议先巩固异步编程，再深入学习 HTTP 请求。",
  },
  {
    id: "c2",
    title: "State 管理掌握度偏低，影响后续组件开发",
    suggestion: "建议优先补齐 State 管理相关知识点。",
  },
]

// 学习路径
export const pathRecommendation = {
  currentSkill: "当前需要补强「State 管理」",
  nextStep: "State 管理",
  readiness: "就绪度高，适合立即开始",
  score: 88.0,
}

export const pathTasks: PathTask[] = [
  {
    id: "t1",
    order: 1,
    name: "State 管理",
    priority: 95.0,
    estimatedMinutes: 30,
    readiness: "high",
    currentMastery: 50,
    learningReadiness: 85,
    prerequisites: ["Dart 基础语法", "Flutter 核心组件"],
    reason:
      "你已经具备 Dart 基础语法和 Flutter 核心组件基础，但 State 管理掌握度较低，会影响后续组件开发。",
    suggestion: [
      "先复习状态提升",
      "再练 Provider / Riverpod 基础",
      "最后完成一个小组件练习",
    ],
  },
  {
    id: "t2",
    order: 2,
    name: "异步编程",
    priority: 80.0,
    estimatedMinutes: 40,
    readiness: "medium",
    currentMastery: 30,
    learningReadiness: 60,
    prerequisites: ["Dart 基础语法"],
    reason: "异步编程是 HTTP 请求和数据库操作的基础，掌握度偏低需要补齐。",
    suggestion: ["理解 Future 和 async/await", "学习 Stream", "练习错误处理"],
  },
  {
    id: "t3",
    order: 3,
    name: "HTTP 请求",
    priority: 70.0,
    estimatedMinutes: 35,
    readiness: "medium",
    currentMastery: 60,
    learningReadiness: 55,
    prerequisites: ["异步编程", "Dart 基础语法"],
    reason: "HTTP 请求是后端通信的核心，需要结合异步编程巩固。",
    suggestion: ["使用 dio 封装请求", "处理拦截器", "统一错误处理"],
  },
]

// 智能提醒
export const reminderStats = {
  pending: 0,
  today: 0,
  done: 0,
}

export const sampleReminders: Reminder[] = [
  { id: "r1", title: "复习 State 管理笔记", type: "review", time: "今天 20:00", done: false, related: "Flutter State 管理笔记" },
  { id: "r2", title: "整理 Dart 异步编程要点", type: "doc", time: "今天 21:30", done: false, repeat: false },
  { id: "r3", title: "完成 HTTP 请求练习", type: "task", time: "明天 10:00", done: false, repeat: true },
  { id: "r4", title: "每周知识回顾", type: "longterm", time: "周日 09:00", done: false, repeat: true },
  { id: "r5", title: "上传课堂笔记", type: "doc", time: "昨天", done: true },
]

// 知识图谱
export const graphStats = {
  tags: 0,
  docs: 0,
  hotTag: "暂无",
  relations: 0,
}

export const sampleGraphNodes: GraphNode[] = [
  { id: "n1", label: "Flutter", type: "knowledge", x: 400, y: 240, size: 36, related: ["n2", "n3", "n4"] },
  { id: "n2", label: "State 管理", type: "tag", x: 220, y: 140, size: 28, related: ["n1", "n5"] },
  { id: "n3", label: "核心组件", type: "tag", x: 580, y: 140, size: 28, related: ["n1", "n6"] },
  { id: "n4", label: "Dart", type: "knowledge", x: 400, y: 80, size: 30, related: ["n1", "n7"] },
  { id: "n5", label: "Provider 笔记", type: "doc", x: 120, y: 320, size: 22, related: ["n2"] },
  { id: "n6", label: "组件实践", type: "doc", x: 660, y: 320, size: 22, related: ["n3"] },
  { id: "n7", label: "异步编程", type: "tag", x: 280, y: 60, size: 24, related: ["n4"] },
  { id: "n8", label: "掌握 Flutter", type: "goal", x: 540, y: 380, size: 26, related: ["n1"] },
]

export const sampleGraphEdges: GraphEdge[] = [
  { from: "n1", to: "n2" },
  { from: "n1", to: "n3" },
  { from: "n1", to: "n4" },
  { from: "n2", to: "n5" },
  { from: "n3", to: "n6" },
  { from: "n4", to: "n7" },
  { from: "n1", to: "n8" },
]
