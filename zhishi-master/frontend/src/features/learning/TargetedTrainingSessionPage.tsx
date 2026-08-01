import { useCallback, useEffect, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import {
  Brain,
  CheckCircle2,
  ChevronRight,
  HelpCircle,
  LogOut,
  Sparkles,
  Target,
  XCircle,
} from "lucide-react"
import { MarkdownWithMath } from "@/components/blocks/MarkdownWithMath"
import { CitationCard } from "@/components/blocks/CitationCard"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { analyticsApi, quizApi, trainingApi } from "@/lib/api"
import { TutorPanel } from "@/features/tutor/TutorPanel"
import { TrainingTutorPanel } from "@/features/learning/TrainingTutorPanel"
import type {
  QuizAnswerResult,
  QuizSession,
  QuizSessionQuestion,
  TagStats,
  TargetedTrainingResult,
  WeakTag,
} from "@/types"
import { cn } from "@/lib/utils"

type Phase = "loading" | "quiz" | "done"

const QUESTION_TYPE_LABEL: Record<string, string> = {
  single_choice: "选择题",
  short_answer: "简答题",
  application: "应用题",
}

export function TargetedTrainingSessionPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const [phase, setPhase] = useState<Phase>("loading")
  const [error, setError] = useState<string | null>(null)
  const [trainingMeta, setTrainingMeta] = useState<TargetedTrainingResult | null>(null)
  const [tagStats, setTagStats] = useState<TagStats[]>([])
  const [session, setSession] = useState<QuizSession | null>(null)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [selectedOption, setSelectedOption] = useState<string | null>(null)
  const [textAnswer, setTextAnswer] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [lastResult, setLastResult] = useState<QuizAnswerResult | null>(null)
  const [questionStartTime, setQuestionStartTime] = useState(Date.now())
  const initRef = useRef(false)

  const currentQuestion: QuizSessionQuestion | undefined = session?.questions[currentIndex]
  const reportId = trainingMeta?.report_id

  const exitToReport = useCallback(() => {
    if (reportId) {
      navigate(`/training/targeted/report/${reportId}`)
    } else {
      navigate("/training/targeted")
    }
  }, [navigate, reportId])

  const loadSession = useCallback(async () => {
    if (!sessionId) return
    setPhase("loading")
    setError(null)
    try {
      const [training, tags] = await Promise.all([
        trainingApi.resumeSession(sessionId),
        analyticsApi.getTagStats(),
      ])
      setTrainingMeta(training)
      setSession(training.session)
      setTagStats(tags.by_tag)

      const resumeIndex = Math.min(
        training.session.answered_count,
        Math.max(0, training.session.total_questions - 1)
      )
      setCurrentIndex(resumeIndex)
      setSelectedOption(null)
      setTextAnswer("")
      setLastResult(null)
      setQuestionStartTime(Date.now())

      if (training.session.status === "completed") {
        setPhase("done")
      } else if (training.session.answered_count >= training.session.total_questions) {
        setPhase("done")
      } else {
        setPhase("quiz")
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "加载训练会话失败")
      setPhase("loading")
    }
  }, [sessionId])

  useEffect(() => {
    if (initRef.current) return
    initRef.current = true
    loadSession()
  }, [loadSession])

  const advanceOrFinish = async (result: QuizAnswerResult) => {
    setLastResult(null)
    setSelectedOption(null)
    setTextAnswer("")
    if (currentIndex + 1 >= (session?.total_questions ?? 0)) {
      setPhase("done")
      return
    }
    setCurrentIndex((i) => i + 1)
    setQuestionStartTime(Date.now())
    if (result.session_status === "completed") {
      setPhase("done")
    }
  }

  const handleSubmit = async () => {
    if (!session || !currentQuestion) return
    const qtype = currentQuestion.question_type || "single_choice"
    const isChoice = qtype === "single_choice"
    if (isChoice && !selectedOption) return
    if (!isChoice && !textAnswer.trim()) return

    setSubmitting(true)
    try {
      const timeSpent = Math.round((Date.now() - questionStartTime) / 1000)
      const res = await quizApi.submitAnswer(session.id, {
        question_id: currentQuestion.question_id,
        user_answer: isChoice ? selectedOption! : textAnswer.trim(),
        time_spent_seconds: timeSpent,
      })
      const result = res as unknown as QuizAnswerResult
      setLastResult(result)
      setSession((prev) =>
        prev
          ? {
              ...prev,
              answered_count: result.answered_count,
              status: result.session_status,
            }
          : prev
      )
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "提交失败")
    } finally {
      setSubmitting(false)
    }
  }

  const handleUnknown = async () => {
    if (!session || !currentQuestion) return
    setSubmitting(true)
    try {
      const timeSpent = Math.round((Date.now() - questionStartTime) / 1000)
      const res = await quizApi.submitAnswer(session.id, {
        question_id: currentQuestion.question_id,
        status: "unknown",
        time_spent_seconds: timeSpent,
      })
      const result = res as unknown as QuizAnswerResult
      setLastResult(result)
      setSession((prev) =>
        prev
          ? {
              ...prev,
              answered_count: result.answered_count,
              status: result.session_status,
            }
          : prev
      )
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "提交失败")
    } finally {
      setSubmitting(false)
    }
  }

  const weakTags: WeakTag[] = trainingMeta?.weak_tags ?? []
  const isChoice =
    !currentQuestion?.question_type || currentQuestion.question_type === "single_choice"

  if (phase === "loading" && !error) {
    return (
      <div className="h-full min-h-[calc(100vh-3rem)] flex flex-col items-center justify-center bg-bg gap-4">
        <div className="w-12 h-12 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
        <p className="text-body text-ink-primary font-medium">加载训练会话…</p>
      </div>
    )
  }

  if (error && !session) {
    return (
      <div className="h-full min-h-[calc(100vh-3rem)] flex flex-col items-center justify-center bg-bg gap-4 px-6">
        <p className="text-body text-danger text-center max-w-md">{error}</p>
        <div className="flex gap-3">
          <Button variant="secondary" onClick={exitToReport}>
            返回
          </Button>
          <Button
            variant="primary"
            onClick={() => {
              initRef.current = false
              loadSession()
            }}
          >
            重试
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full min-h-[calc(100vh-3rem)] flex flex-col bg-bg">
      <header className="shrink-0 border-b border-line-soft bg-surface px-4 py-3 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <Target className="w-5 h-5 text-primary" strokeWidth={2} />
          <h1 className="text-body font-semibold text-ink-primary">针对训练</h1>
          {session && phase === "quiz" && (
            <Badge variant="primary" size="sm">
              {session.answered_count}/{session.total_questions}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          {phase === "quiz" && (
            <Button variant="ghost" size="sm" onClick={exitToReport}>
              <LogOut className="w-4 h-4" />
              退出
            </Button>
          )}
          {phase === "done" && reportId && (
            <Button variant="ghost" size="sm" onClick={exitToReport}>
              返回报告
            </Button>
          )}
        </div>
      </header>

      {error && (
        <div className="mx-4 mt-3 rounded-lg border border-danger/30 bg-danger-soft px-4 py-2 text-small text-danger">
          {error}
        </div>
      )}

      {phase === "done" ? (
        <div className="flex-1 flex items-center justify-center p-8">
          <Card className="p-8 text-center max-w-md">
            <CheckCircle2 className="w-12 h-12 text-success mx-auto mb-3" />
            <h2 className="text-card-title font-semibold mb-2">本轮针对训练完成</h2>
            <p className="text-body text-ink-secondary mb-4">
              共完成 {session?.total_questions ?? 0} 题，继续巩固薄弱知识点吧。
            </p>
            <div className="flex flex-wrap gap-3 justify-center">
              {reportId && (
                <Button variant="secondary" onClick={exitToReport}>
                  返回报告
                </Button>
              )}
              <Button
                variant="primary"
                onClick={() => {
                  if (reportId) {
                    navigate(`/training/targeted/report/${reportId}`)
                  }
                }}
              >
                <Sparkles className="w-4 h-4" />
                再来一轮
              </Button>
            </div>
          </Card>
        </div>
      ) : (
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-[280px_minmax(0,1fr)_320px] gap-0 min-h-0 overflow-hidden">
          <aside className="border-r border-line-soft bg-surface overflow-y-auto scroll-thin p-4 hidden lg:block">
            <h2 className="text-small font-semibold text-ink-primary mb-3">薄弱知识点</h2>
            {weakTags.length === 0 ? (
              <p className="text-small text-ink-tertiary">暂无 tag 统计</p>
            ) : (
              <ul className="space-y-2 mb-6">
                {weakTags.map((t) => (
                  <li
                    key={t.tag}
                    className="rounded-lg border border-line-soft px-3 py-2 text-small"
                  >
                    <div className="font-medium text-ink-primary truncate">{t.tag}</div>
                    <div className="text-ink-tertiary mt-0.5">
                      错 {t.wrong_count} · 对 {t.correct_count}
                      {t.accuracy_rate != null && ` · ${t.accuracy_rate}%`}
                    </div>
                  </li>
                ))}
              </ul>
            )}

            <h2 className="text-small font-semibold text-ink-primary mb-3">全部 Tag 统计</h2>
            <ul className="space-y-1.5">
              {tagStats.slice(0, 12).map((t) => (
                <li key={t.tag} className="flex justify-between text-caption text-ink-secondary">
                  <span className="truncate mr-2">{t.tag}</span>
                  <span className="shrink-0 text-danger">{t.wrong_count} 错</span>
                </li>
              ))}
            </ul>
          </aside>

          <main className="overflow-y-auto scroll-thin p-4 lg:p-6 min-h-0">
            {session && currentQuestion ? (
              <div className="max-w-2xl mx-auto">
                <div className="flex flex-wrap items-center gap-2 mb-4">
                  <Badge variant="neutral">
                    第 {currentIndex + 1} / {session.total_questions} 题
                  </Badge>
                  <Badge variant="primary" size="sm">
                    {QUESTION_TYPE_LABEL[currentQuestion.question_type] ||
                      currentQuestion.question_type}
                  </Badge>
                </div>

                <MarkdownWithMath className="text-card-title font-semibold mb-6 leading-relaxed">
                  {currentQuestion.stem}
                </MarkdownWithMath>

                {isChoice ? (
                  <div className="space-y-2.5 mb-6">
                    {(currentQuestion.options || []).map((opt) => (
                      <button
                        key={opt.key}
                        type="button"
                        disabled={!!lastResult || submitting}
                        onClick={() => setSelectedOption(opt.key)}
                        className={cn(
                          "w-full text-left rounded-lg border px-4 py-3 text-body transition-colors",
                          selectedOption === opt.key
                            ? "border-primary bg-primary-soft"
                            : "border-line-soft hover:border-primary/30",
                          lastResult?.correct_answer === opt.key && "border-success bg-success-soft"
                        )}
                      >
                        <span className="font-medium mr-2">{opt.key}.</span>
                        <MarkdownWithMath
                          proseClass="prose prose-sm max-w-none inline prose-p:inline prose-p:my-0"
                          className="inline"
                        >
                          {opt.text}
                        </MarkdownWithMath>
                      </button>
                    ))}
                  </div>
                ) : (
                  <textarea
                    className="w-full min-h-[140px] rounded-lg border border-line-soft bg-surface px-4 py-3 text-body mb-6 focus:outline-none focus:ring-2 focus:ring-primary/30"
                    placeholder="请输入你的答案…"
                    value={textAnswer}
                    onChange={(e) => setTextAnswer(e.target.value)}
                    disabled={!!lastResult || submitting}
                  />
                )}

                {!lastResult ? (
                  <div className="flex flex-wrap gap-3">
                    <Button
                      variant="primary"
                      onClick={handleSubmit}
                      disabled={
                        submitting || (isChoice ? !selectedOption : !textAnswer.trim())
                      }
                    >
                      {submitting ? "提交中…" : "提交答案"}
                    </Button>
                    <Button variant="secondary" onClick={handleUnknown} disabled={submitting}>
                      <HelpCircle className="w-4 h-4" />
                      我不会
                    </Button>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div
                      className={cn(
                        "flex items-center gap-2 font-medium",
                        lastResult.status === "correct" ? "text-success" : "text-warning"
                      )}
                    >
                      {lastResult.status === "correct" ? (
                        <>
                          <CheckCircle2 className="w-5 h-5" /> 回答正确
                        </>
                      ) : lastResult.status === "unknown" ? (
                        "已标记「我不会」"
                      ) : (
                        <>
                          <XCircle className="w-5 h-5" /> 回答错误，参考：{lastResult.correct_answer}
                        </>
                      )}
                    </div>
                    {lastResult.explanation && (
                      <div className="text-body bg-surface-soft rounded-md p-3 border border-line-soft">
                        <MarkdownWithMath>{lastResult.explanation}</MarkdownWithMath>
                      </div>
                    )}
                    {lastResult.citation && <CitationCard citation={lastResult.citation} />}
                    <Button variant="primary" onClick={() => advanceOrFinish(lastResult)}>
                      下一题
                      <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center justify-center h-full text-ink-tertiary gap-2">
                <Brain className="w-5 h-5" />
                暂无题目
              </div>
            )}
          </main>

          <aside className="border-l border-line-soft bg-surface min-h-[320px] lg:min-h-0 flex flex-col overflow-hidden">
            {trainingMeta?.agent_session_id ? (
              <TrainingTutorPanel
                agentSessionId={trainingMeta.agent_session_id}
                rationale={trainingMeta.rationale}
                className="flex-1 min-h-0"
              />
            ) : currentQuestion ? (
              <TutorPanel
                key={currentQuestion.question_id}
                questionId={currentQuestion.question_id}
                quizSessionId={session?.id}
                className="flex-1 min-h-0"
              />
            ) : (
              <div className="p-4 text-small text-ink-tertiary">AI 教练加载中…</div>
            )}
          </aside>
        </div>
      )}
    </div>
  )
}
