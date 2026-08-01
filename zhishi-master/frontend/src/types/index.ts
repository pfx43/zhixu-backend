// 知拾 Web 端 · 全局类型定义

import type { LucideIcon } from "lucide-react"

/** 导航项 */
export interface NavItem {
  label: string
  to: string
  icon: LucideIcon
  badge?: string | number
}

/** 导航分组 */
export interface NavGroup {
  title: string
  items: NavItem[]
}

/** 笔记 */
export interface Note {
  id: string
  title: string
  excerpt: string
  tags: string[]
  updatedAt: string
  wordCount: number
  source: "manual" | "doc" | "ai"
  hasAISummary: boolean
  organized: boolean
  category?: string
}

/** 知识库文档 */
export interface KnowledgeDoc {
  id: string
  name: string
  type: "pdf" | "txt" | "md" | "docx" | "image" | "ocr"
  tags: string[]
  status: "indexed" | "processing" | "failed" | "pending"
  segment_status?: string
  question_gen_status?: string
  ocr_status?: string
  ocr_current_page?: number
  ocr_total_pages?: number
  questionCount?: number
  zone?: string
  wordCount: number
  updatedAt: string
}

/** 学习技能掌握度 */
export interface SkillMastery {
  name: string
  mastery: number // 0-100
  status: "mastered" | "practicing" | "pending"
}

/** 学习路径任务 */
export interface PathTask {
  id: string
  order: number
  name: string
  priority: number
  estimatedMinutes: number
  readiness: "high" | "medium" | "low"
  currentMastery: number
  learningReadiness: number
  prerequisites: string[]
  reason: string
  suggestion: string[]
}

/** 智能提醒 */
export interface Reminder {
  id: string
  title: string
  type: "review" | "task" | "doc" | "longterm"
  time: string
  done: boolean
  repeat?: boolean
  related?: string
}

/** 图谱节点 */
export interface GraphNode {
  id: string
  label: string
  type: "tag" | "doc" | "knowledge" | "goal"
  x: number
  y: number
  size: number
  related: string[]
}

/** 图谱连线 */
export interface GraphEdge {
  from: string
  to: string
}

/** 引用片段（聊天 / 刷题 / 辅导） */
export interface Citation {
  doc_id: string
  segment_id?: string | null
  title?: string | null
  char_start?: number | null
  char_end?: number | null
  snippet?: string | null
}

/** 知识库分区 */
export interface KbCollection {
  id: string
  name: string
  zone: "study" | "life"
  description?: string | null
  dataset_id?: string | null
  is_default?: boolean
  created_at?: string
  updated_at?: string
}

/** 文档分段 */
export interface DocumentSegment {
  id: string
  document_id: string
  order_index: number
  title?: string | null
  content: string
  char_start: number
  char_end: number
  created_at?: string
}

/** 题目选项 */
export interface QuestionOption {
  key: string
  text: string
}

/** 题目 */
export interface Question {
  id: string
  stem: string
  question_type: string
  options?: QuestionOption[]
  answer?: string
  explanation?: string | null
  tags?: string[]
  source_type?: string
  document_id?: string | null
  collection_id?: string | null
  created_at?: string
  user_answer_status?: "correct" | "wrong" | "unknown" | null
  attempt_count?: number
}

/** 题目列表（含做题统计） */
export interface QuestionListResult {
  questions: Question[]
  total: number
  document_id?: string | null
  collection_id?: string | null
  answered_count?: number
  correct_count?: number
  wrong_count?: number
  unknown_count?: number
}
export interface QuizSessionQuestion {
  question_id: string
  order_index: number
  stem: string
  question_type: string
  options?: QuestionOption[]
}

/** 刷题会话 */
export interface QuizSession {
  id: string
  title?: string | null
  status: "active" | "completed" | string
  document_id?: string | null
  collection_id?: string | null
  total_questions: number
  answered_count: number
  started_at?: string | null
  finished_at?: string | null
  questions: QuizSessionQuestion[]
}

/** 单题作答结果 */
export interface QuizAnswerResult {
  question_id: string
  status: "correct" | "wrong" | "unknown" | string
  correct_answer?: string | null
  explanation?: string | null
  citation?: Citation | null
  answered_count: number
  total_questions: number
  session_status: string
}

/** 错题回顾项 */
export interface QuizReviewItem {
  question_id: string
  stem: string
  user_answer?: string | null
  status: "wrong" | "unknown" | string
  correct_answer: string
  explanation?: string | null
  citation?: Citation | null
}

/** 刷题结果汇总 */
export interface QuizResults {
  session_id: string
  status: string
  total_questions: number
  correct_count: number
  wrong_count: number
  unknown_count: number
  items: QuizReviewItem[]
}

/** 学习分析统计 */
export interface DocumentStats {
  total: number
  indexed: number
  processing: number
  failed: number
  study_zone: number
  with_questions: number
}

export interface QuestionStats {
  total: number
  answered: number
  correct: number
  wrong: number
  unknown: number
  accuracy_rate: number | null
}

export interface DocumentProgress {
  document_id: string
  document_name: string
  question_total: number
  answered_count: number
  correct_count: number
  wrong_count: number
  unknown_count: number
  accuracy_rate: number | null
}

export interface RecentSession {
  id: string
  document_id?: string | null
  document_name?: string | null
  status: string
  total_questions: number
  answered_count: number
  started_at?: string | null
  finished_at?: string | null
}

export interface RecentAnswer {
  question_id: string
  stem: string
  status: string
  document_id?: string | null
  document_name?: string | null
  answered_at?: string | null
}

export interface LearningStats {
  documents: DocumentStats
  questions: QuestionStats
  document_progress: DocumentProgress[]
  recent_sessions: RecentSession[]
  recent_answers: RecentAnswer[]
}

/** Tag 维度统计 */
export interface TagStats {
  tag: string
  question_type: string
  correct_count: number
  wrong_count: number
  unknown_count: number
  total_attempts: number
  accuracy_rate: number | null
}

export interface TagStatsResult {
  by_tag: TagStats[]
  by_question_type: TagStats[]
}

/** 学习报告 */
export interface LearningReport {
  id: string
  title: string
  content_md: string
  collection_id?: string | null
  note_type?: string
  created_at?: string | null
}

export interface LearningReportList {
  reports: LearningReport[]
  total: number
}

/** 针对训练 */
export interface WeakTag {
  tag: string
  wrong_count: number
  correct_count: number
  accuracy_rate: number | null
}

export interface TargetedTrainingResult {
  session: QuizSession
  weak_tags: WeakTag[]
  question_ids: string[]
  report_id?: string | null
  rationale?: string | null
  agent_session_id?: string | null
}

export interface TargetedTrainingActiveSession {
  session_id: string
  report_id?: string | null
  answered_count: number
  total_questions: number
  agent_session_id?: string | null
  status: string
}

/** 辅导消息 */
export interface TutorMessage {
  role: "user" | "assistant" | string
  content: string
  created_at?: string
}

/** 辅导会话 */
export interface TutorSession {
  id: string
  question_id: string
  document_id?: string | null
  segment_id?: string | null
  quiz_answer_id?: string | null
  status: string
  question_stem?: string | null
  segment_context?: {
    segment_id?: string
    title?: string
    snippet?: string
  } | null
  messages: TutorMessage[]
  created_at?: string
  updated_at?: string
}

/** 文档页（出题页） */
export interface DocumentPage {
  page_number: number
  title: string
  preview: string
  char_start: number
  char_end: number
  content_length: number
  has_builtin_questions: boolean
  is_key_page: boolean
  segment_id?: string | null
  preview_mode?: "pdf" | "markdown" | "text"
  file_type?: string | null
}

export interface DocumentPageList {
  document_id: string
  document_name: string
  total_pages: number
  has_page_markers: boolean
  preview_mode?: "pdf" | "markdown" | "text"
  file_type?: string | null
  has_raw_file?: boolean
  pages: DocumentPage[]
}

export interface DocumentPageDetail extends DocumentPage {
  content: string
}

export interface DocumentContentMeta {
  doc_id: string
  file_name?: string
  content: string
  file_type?: string
  preview_mode?: "pdf" | "text" | "markdown"
  has_raw_file?: boolean
  mock?: boolean
}

export interface PageQuestionResult {
  document_id: string
  page_numbers: number[]
  mode: string
  question_gen_status?: string
  questions_created: number
  questions_reused: number
  total_questions: number
}

/** 对话消息 */
export interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  time: string
  refs?: string[]
  citations?: Citation[]
}

/** 页面布局配置 */
export interface PageLayout {
  /** 主内容区最大宽度，px。null 表示全宽 */
  maxWidth?: number | null
  /** 是否显示右侧面板 */
  showRightPanel?: boolean
  /** 右侧面板标题 */
  rightPanelTitle?: string
}
