import { GraduationCap, Home, Library } from "lucide-react"
import { DocRow } from "@/components/blocks/DocRow"
import { EmptyState } from "@/components/ui/empty-state"
import { SegmentedTabs } from "@/components/ui/segmented-tabs"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { KbCollection, KnowledgeDoc } from "@/types"

interface KbDocBrowserProps {
  collections: KbCollection[]
  selectedCollectionId: string
  onCollectionChange: (id: string) => void
  documents: KnowledgeDoc[]
  loading?: boolean
  selectedDocumentId?: string
  onDocumentSelect?: (doc: KnowledgeDoc) => void
  emptyTitle?: string
  emptyDescription?: string
  emptyAction?: { label: string; onClick: () => void }
  className?: string
  showZoneHint?: boolean
}

export function KbDocBrowser({
  collections,
  selectedCollectionId,
  onCollectionChange,
  documents,
  loading = false,
  selectedDocumentId,
  onDocumentSelect,
  emptyTitle = "该分区还没有文档",
  emptyDescription = "请先在知识库上传资料",
  emptyAction,
  className,
  showZoneHint = true,
}: KbDocBrowserProps) {
  const selectedCollection = collections.find((c) => c.id === selectedCollectionId)
  const isLifeZone = selectedCollection?.zone === "life"

  const zoneLabel = (zone?: string) => {
    if (zone === "life") return { text: "生活区", icon: Home }
    return { text: "学习区", icon: GraduationCap }
  }

  const zone = zoneLabel(selectedCollection?.zone)

  return (
    <div className={cn("flex flex-col min-h-0", className)}>
      {collections.length > 0 && (
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <SegmentedTabs
            tabs={collections.map((c) => ({
              label: c.name,
              value: c.id,
              icon: c.zone === "life" ? Home : GraduationCap,
            }))}
            value={selectedCollectionId}
            onChange={onCollectionChange}
          />
          {selectedCollection && (
            <Badge variant={selectedCollection.zone === "life" ? "neutral" : "info"}>
              <zone.icon className="w-3 h-3 mr-1 inline" strokeWidth={2} />
              {zone.text}
            </Badge>
          )}
        </div>
      )}

      {showZoneHint && isLifeZone && (
        <p className="text-caption text-ink-tertiary mb-3">
          生活区文档仅支持检索与对话，练习与出题请切换到学习区。
        </p>
      )}

      {loading ? (
        <div className="bg-surface border border-line-soft rounded-lg shadow-xs p-12 flex items-center justify-center flex-1">
          <div className="flex items-center gap-2 text-ink-tertiary">
            <div className="w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
            <span className="text-body">加载中...</span>
          </div>
        </div>
      ) : documents.length === 0 ? (
        <div className="bg-surface border border-line-soft rounded-lg shadow-xs flex-1">
          <EmptyState
            icon={Library}
            title={emptyTitle}
            description={emptyDescription}
            primaryAction={emptyAction}
            size="lg"
          />
        </div>
      ) : (
        <div className="bg-surface border border-line-soft rounded-lg shadow-xs overflow-hidden flex-1 min-h-0 flex flex-col">
          <div className="hidden sm:grid grid-cols-[minmax(0,2fr)_auto_auto_auto_auto] gap-x-4 px-5 py-3 border-b border-line-soft bg-surface-soft text-small text-ink-tertiary font-medium shrink-0">
            <div>文档名</div>
            <div className="min-w-[60px]">类型</div>
            <div className="min-w-[60px]">字数</div>
            <div className="min-w-[80px]">更新时间</div>
            <div className="min-w-[80px] text-right">状态</div>
          </div>
          <div className="divide-y divide-line-soft overflow-y-auto scroll-thin flex-1">
            {documents.map((doc) => (
              <div
                key={doc.id}
                onClick={() => onDocumentSelect?.(doc)}
                className={cn(
                  "cursor-pointer transition-colors",
                  selectedDocumentId === doc.id && "bg-primary-soft/40"
                )}
              >
                <DocRow doc={doc} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
