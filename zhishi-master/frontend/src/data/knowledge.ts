import type { KnowledgeDoc } from "@/types"

export const kbStats = {
  docs: 0,
  words: 0,
  status: "已连接",
  pending: 0,
}

export const docs: KnowledgeDoc[] = []

export const sampleDocs: KnowledgeDoc[] = [
  {
    id: "d1",
    name: "Flutter 官方文档 - State 管理.pdf",
    type: "pdf",
    tags: ["Flutter", "State"],
    status: "indexed",
    wordCount: 12400,
    updatedAt: "2 小时前",
  },
  {
    id: "d2",
    name: "Provider 与 Riverpod 对比.md",
    type: "md",
    tags: ["Flutter", "Riverpod"],
    status: "indexed",
    wordCount: 3200,
    updatedAt: "5 小时前",
  },
  {
    id: "d3",
    name: "Dart 异步编程.docx",
    type: "docx",
    tags: ["Dart", "异步"],
    status: "processing",
    wordCount: 5600,
    updatedAt: "10 分钟前",
  },
  {
    id: "d4",
    name: "HTTP 请求封装笔记.txt",
    type: "txt",
    tags: ["Flutter", "HTTP"],
    status: "pending",
    wordCount: 1800,
    updatedAt: "1 小时前",
  },
  {
    id: "d5",
    name: "课堂笔记扫描件.jpg",
    type: "image",
    tags: [],
    status: "failed",
    wordCount: 0,
    updatedAt: "3 小时前",
  },
  {
    id: "d6",
    name: "SQLite 数据库基础.pdf",
    type: "pdf",
    tags: ["Flutter", "数据库"],
    status: "indexed",
    wordCount: 8900,
    updatedAt: "昨天",
  },
]

export const kbConfigStatus = {
  difyConnected: true,
  datasetId: "002fc6f7...",
}
