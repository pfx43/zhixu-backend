import { Navigate, Route, Routes } from "react-router-dom"
import { TargetedTrainingListPage } from "@/features/learning/TargetedTrainingListPage"
import { TargetedTrainingReportPage } from "@/features/learning/TargetedTrainingReportPage"
import { TargetedTrainingSessionPage } from "@/features/learning/TargetedTrainingSessionPage"

/** 针对训练路由容器：列表 → 报告详情 → 全屏训练会话 */
export function TargetedTrainingPage() {
  return (
    <Routes>
      <Route index element={<TargetedTrainingListPage />} />
      <Route path="report/:reportId" element={<TargetedTrainingReportPage />} />
      <Route path="session/:sessionId" element={<TargetedTrainingSessionPage />} />
      <Route path="*" element={<Navigate to="/training/targeted" replace />} />
    </Routes>
  )
}
