import { useNavigate } from "react-router-dom"
import { BookOpen, Loader2 } from "lucide-react"
import { AppShell } from "@/components/layout/AppShell"
import { PageHeader } from "@/components/blocks/PageHeader"
import { KbDocBrowser } from "@/components/blocks/KbDocBrowser"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { useKbDocuments } from "@/hooks/useKbDocuments"
import type { KnowledgeDoc } from "@/types"

export function QuestionGenPage() {
  const navigate = useNavigate()
  const {
    collections,
    selectedCollectionId,
    setSelectedCollectionId,
    documents,
    loadingCollections,
    loadingDocuments,
  } = useKbDocuments({
    zoneFilter: "study",
    preferZone: "study",
  })

  const handleDocumentSelect = (doc: KnowledgeDoc) => {
    navigate(`/question-gen/doc/${doc.id}`)
  }

  const handleCollectionChange = (id: string) => {
    setSelectedCollectionId(id)
  }

  return (
    <AppShell maxWidth={960}>
      <PageHeader
        title="出题页"
        subtitle="选择知识库文档，进入按页浏览与批量出题"
      >
        <Button variant="secondary" size="md" onClick={() => navigate("/quiz")}>
          前往题库
        </Button>
      </PageHeader>

      {loadingCollections ? (
        <div className="flex items-center justify-center py-16 text-ink-tertiary gap-2">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span>加载分区...</span>
        </div>
      ) : collections.length === 0 ? (
        <EmptyState
          icon={BookOpen}
          title="暂无学习区知识库"
          description="请先在知识库上传学习区文档"
          primaryAction={{ label: "去知识库", onClick: () => navigate("/knowledge") }}
        />
      ) : (
        <div className="bg-surface border border-line-soft rounded-lg shadow-xs min-h-[480px] lg:h-[calc(100vh-12rem)]">
          <KbDocBrowser
            className="h-full min-h-0"
            collections={collections}
            selectedCollectionId={selectedCollectionId}
            onCollectionChange={handleCollectionChange}
            documents={documents}
            loading={loadingDocuments}
            selectedDocumentId=""
            onDocumentSelect={handleDocumentSelect}
            showZoneHint={false}
            emptyTitle="该分区还没有文档"
            emptyDescription="上传资料并完成解析后，可在此按页出题"
            emptyAction={{ label: "去知识库", onClick: () => navigate("/knowledge") }}
          />
        </div>
      )}
    </AppShell>
  )
}
