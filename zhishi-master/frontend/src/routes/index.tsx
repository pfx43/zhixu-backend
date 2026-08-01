import { Routes, Route, Navigate } from "react-router-dom"
import { useAuth } from "@/context/AuthContext"
import { DashboardPage } from "@/features/dashboard/DashboardPage"
import { ChatPage } from "@/features/chat/ChatPage"
import { NotesPage } from "@/features/notes/NotesPage"
import { KnowledgeBasePage } from "@/features/knowledge-base/KnowledgeBasePage"
import { DocumentViewPage } from "@/features/knowledge-base/DocumentViewPage"
import { UploadPage } from "@/features/knowledge-base/UploadPage"
import { KnowledgeGraphPage } from "@/features/knowledge-graph/KnowledgeGraphPage"
import { LearningAnalyticsPage } from "@/features/learning/LearningAnalyticsPage"
import { TargetedTrainingPage } from "@/features/learning/TargetedTrainingPage"
import { LearningPathPage } from "@/features/learning/LearningPathPage"
import { RemindersPage } from "@/features/learning/RemindersPage"
import { ProfilePage } from "@/features/profile/ProfilePage"
import { SettingsPage } from "@/features/settings/SettingsPage"
import { DiagnosticsPage } from "@/features/settings/DiagnosticsPage"
import { LoginPage } from "@/features/auth/LoginPage"
import { QuizPage } from "@/features/quiz/QuizPage"
import { QuestionGenPage } from "@/features/question-gen/QuestionGenPage"
import { QuestionGenDocPage } from "@/features/question-gen/QuestionGenDocPage"

function RequireAuth({ children }: { children: React.ReactElement }) {
  const { user, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center bg-bg">
        <div className="text-body text-ink-tertiary">加载中...</div>
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  return children
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<RequireAuth><DashboardPage /></RequireAuth>} />
      <Route path="/chat" element={<RequireAuth><ChatPage /></RequireAuth>} />
      <Route path="/notes" element={<RequireAuth><NotesPage /></RequireAuth>} />
      <Route path="/knowledge" element={<RequireAuth><KnowledgeBasePage /></RequireAuth>} />
      <Route path="/knowledge/doc/:docId" element={<RequireAuth><DocumentViewPage /></RequireAuth>} />
      <Route path="/knowledge/upload" element={<RequireAuth><UploadPage /></RequireAuth>} />
      <Route path="/graph" element={<RequireAuth><KnowledgeGraphPage /></RequireAuth>} />
      <Route path="/analytics" element={<RequireAuth><LearningAnalyticsPage /></RequireAuth>} />
      <Route path="/training/targeted/*" element={<RequireAuth><TargetedTrainingPage /></RequireAuth>} />
      <Route path="/path" element={<RequireAuth><LearningPathPage /></RequireAuth>} />
      <Route path="/reminders" element={<RequireAuth><RemindersPage /></RequireAuth>} />
      <Route path="/profile" element={<RequireAuth><ProfilePage /></RequireAuth>} />
      <Route path="/settings" element={<RequireAuth><SettingsPage /></RequireAuth>} />
      <Route path="/quiz" element={<RequireAuth><QuizPage /></RequireAuth>} />
      <Route path="/question-gen" element={<RequireAuth><QuestionGenPage /></RequireAuth>} />
      <Route path="/question-gen/doc/:documentId" element={<RequireAuth><QuestionGenDocPage /></RequireAuth>} />
      <Route path="/settings/diagnostics" element={<RequireAuth><DiagnosticsPage /></RequireAuth>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
