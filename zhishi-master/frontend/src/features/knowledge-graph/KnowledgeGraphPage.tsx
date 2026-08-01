import { useState, useEffect } from "react"
import {
  Network,
  Tag,
  FileText,
  Target,
  Sparkles,
} from "lucide-react"
import { AppShell } from "@/components/layout/AppShell"
import { RightPanel } from "@/components/layout/RightPanel"
import { PageHeader } from "@/components/blocks/PageHeader"
import { StatCard } from "@/components/ui/stat-card"
import { SegmentedTabs } from "@/components/ui/segmented-tabs"
import { EmptyState } from "@/components/ui/empty-state"
import { Badge } from "@/components/ui/badge"
import { ktApi } from "@/lib/api"
import type { GraphNode } from "@/types"

const nodeTypeConfig = {
  knowledge: { color: "#6366F1", label: "知识点", icon: Network },
  tag: { color: "#7C3AED", label: "标签", icon: Tag },
  doc: { color: "#3B82F6", label: "文档", icon: FileText },
  goal: { color: "#F59E0B", label: "学习目标", icon: Target },
}

export function KnowledgeGraphPage() {
  const [tab, setTab] = useState("graph")
  const [nodes, setNodes] = useState<GraphNode[]>([])
  const [edges, setEdges] = useState<{ from: string; to: string }[]>([])
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [loading, setLoading] = useState(true)
  const [graphStats, setGraphStats] = useState({ tags: 0, docs: 0, hotTag: "暂无", relations: 0 })
  const [tagList, setTagList] = useState<string[]>([])

  useEffect(() => {
    ktApi.getSkillGraph()
      .then((res) => {
        // Map nodes
        const rawNodes = res.nodes || res.skills || []
        const gNodes = rawNodes.map((n: any, i: number) => ({
          id: String(n.id ?? `n${i}`),
          label: n.label || n.name || "—",
          type: (n.type as GraphNode["type"]) || "tag",
          x: n.x || 200 + (i % 4) * 150,
          y: n.y || 80 + Math.floor(i / 4) * 160,
          size: n.size || 24,
          related: n.related || n.prerequisites || [],
        }))
        setNodes(gNodes)
        if (gNodes.length > 0) setSelected(gNodes[0])

        // Build edges
        const gEdges: { from: string; to: string }[] = []
        gNodes.forEach((n: GraphNode) => {
          n.related.forEach((rid: string) => gEdges.push({ from: n.id, to: rid }))
        })
        if (res.edges) {
          res.edges.forEach((e: any) => gEdges.push({ from: e.from || e.source, to: e.to || e.target }))
        }
        setEdges(gEdges)

        // Tags for tag list view
        const allTags: string[] = []
        gNodes.forEach((n: GraphNode) => {
          if (n.type === "tag") allTags.push(n.label)
        })
        setTagList(allTags.length > 0 ? allTags : [])

        // Stats
        setGraphStats({
          tags: res.tags_count || gNodes.filter((n: GraphNode) => n.type === "tag").length || 0,
          docs: res.docs_count || 0,
          hotTag: res.hot_tag || (allTags[0] || "暂无"),
          relations: res.relations_count || gEdges.length || 0,
        })
      })
      .catch(() => { /* silently use empty graph */ })
      .finally(() => setLoading(false))
  }, [])

  return (
    <AppShell maxWidth={null} noPadding>
      <div className="p-8">
        <PageHeader title="知识图谱" subtitle="查看标签、文档、知识点之间的关系" />

        {/* 统计 */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <StatCard icon={Tag} label="标签总数" value={graphStats.tags} tone="primary" />
          <StatCard icon={FileText} label="文档总数" value={graphStats.docs} tone="info" />
          <StatCard icon={Sparkles} label="热门标签" value={graphStats.hotTag} tone="warning" />
          <StatCard icon={Network} label="知识关系" value={graphStats.relations} tone="neutral" />
        </div>

        {/* Tab 切换 */}
        <div className="mb-5">
          <SegmentedTabs
            value={tab}
            onChange={setTab}
            tabs={[
              { label: "图谱视图", value: "graph", icon: Network },
              { label: "标签列表", value: "tags", icon: Tag },
              { label: "文档关系", value: "docs", icon: FileText },
            ]}
          />
        </div>

        {/* 内容 */}
        {loading ? (
          <div className="bg-surface border border-line-soft rounded-lg shadow-xs p-12 flex items-center justify-center">
            <div className="flex items-center gap-2 text-ink-tertiary">
              <div className="w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
              <span className="text-body">加载中...</span>
            </div>
          </div>
        ) : nodes.length === 0 ? (
          <div className="bg-surface border border-line-soft rounded-lg shadow-xs">
            <EmptyState
              icon={Network}
              title="暂无知识关系"
              description="上传文档或给笔记添加标签后，系统会自动生成图谱关系。"
              primaryAction={{ label: "上传文档" }}
              size="lg"
            />
          </div>
        ) : tab === "graph" ? (
          <div className="bg-surface border border-line-soft rounded-lg shadow-xs overflow-hidden">
            <GraphCanvas
              nodes={nodes}
              edges={edges}
              selected={selected}
              onSelect={setSelected}
            />
          </div>
        ) : tab === "tags" ? (
          <TagListView tags={tagList} />
        ) : (
          <DocRelationView nodes={nodes} edges={edges} />
        )}
      </div>

      {/* 右侧节点详情 */}
      {selected && (
        <RightPanel title="节点详情">
          <NodeDetail node={selected} allNodes={nodes} />
        </RightPanel>
      )}
    </AppShell>
  )
}

/** 图谱画布 - 轻量 SVG 实现 */
function GraphCanvas({
  nodes,
  edges,
  selected,
  onSelect,
}: {
  nodes: GraphNode[]
  edges: { from: string; to: string }[]
  selected: GraphNode | null
  onSelect: (n: GraphNode) => void
}) {
  return (
    <div className="relative w-full" style={{ height: "500px" }}>
      <svg viewBox="0 0 760 480" className="w-full h-full" style={{ background: "#FAFAFC" }}>
        {/* 连线 */}
        {edges.map((edge, i) => {
          const from = nodes.find((n) => n.id === edge.from)
          const to = nodes.find((n) => n.id === edge.to)
          if (!from || !to) return null
          const isActive = selected && (selected.id === from.id || selected.id === to.id)
          return (
            <line
              key={i}
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              stroke={isActive ? "#6366F1" : "#C7C9D9"}
              strokeWidth={isActive ? 2 : 1.2}
              strokeOpacity={isActive ? 0.7 : 0.4}
            />
          )
        })}

        {/* 节点 */}
        {nodes.map((node) => {
          const cfg = nodeTypeConfig[node.type]
          const isSelected = selected?.id === node.id
          return (
            <g
              key={node.id}
              onClick={() => onSelect(node)}
              className="cursor-pointer"
              style={{ transition: "all 160ms ease" }}
            >
              {isSelected && (
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={node.size / 2 + 6}
                  fill={cfg.color}
                  fillOpacity={0.12}
                />
              )}
              <circle
                cx={node.x}
                cy={node.y}
                r={node.size / 2}
                fill={isSelected ? cfg.color : "#FFFFFF"}
                stroke={cfg.color}
                strokeWidth={isSelected ? 0 : 2}
                fillOpacity={isSelected ? 1 : 1}
              />
              <text
                x={node.x}
                y={node.y}
                textAnchor="middle"
                dominantBaseline="central"
                fill={isSelected ? "#FFFFFF" : cfg.color}
                fontSize={node.type === "knowledge" ? 13 : 11}
                fontWeight={600}
                style={{ pointerEvents: "none", userSelect: "none" }}
              >
                {node.label.length > 6 ? node.label.slice(0, 5) + "…" : node.label}
              </text>
            </g>
          )
        })}
      </svg>

      {/* 图例 */}
      <div className="absolute bottom-4 left-4 flex items-center gap-3 bg-surface/90 backdrop-blur-md border border-line-soft rounded-md px-3 py-2 shadow-xs">
        {(Object.entries(nodeTypeConfig) as [keyof typeof nodeTypeConfig, typeof nodeTypeConfig[keyof typeof nodeTypeConfig]][]).map(
          ([type, cfg]) => (
            <div key={type} className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded-full" style={{ background: cfg.color }} />
              <span className="text-small text-ink-secondary">{cfg.label}</span>
            </div>
          )
        )}
      </div>
    </div>
  )
}

function NodeDetail({ node, allNodes }: { node: GraphNode; allNodes: GraphNode[] }) {
  const cfg = nodeTypeConfig[node.type]
  const related = node.related
    .map((id) => allNodes.find((n) => n.id === id))
    .filter(Boolean) as GraphNode[]

  return (
    <div className="space-y-5">
      <div>
        <div className="flex items-center gap-2 mb-2">
          <div
            className="w-9 h-9 rounded-md flex items-center justify-center"
            style={{ background: cfg.color + "20", color: cfg.color }}
          >
            <cfg.icon className="w-5 h-5" strokeWidth={2} />
          </div>
          <div>
            <div className="text-card-title font-semibold text-ink-primary">{node.label}</div>
            <Badge variant="primary" size="sm" className="mt-0.5">{cfg.label}</Badge>
          </div>
        </div>
      </div>

      <section>
        <h4 className="text-small font-medium text-ink-tertiary mb-2 uppercase tracking-wider">关联节点</h4>
        <div className="space-y-1.5">
          {related.length === 0 ? (
            <div className="text-small text-ink-tertiary">暂无关联</div>
          ) : (
            related.map((r) => {
              const rCfg = nodeTypeConfig[r.type]
              return (
                <div
                  key={r.id}
                  className="flex items-center gap-2 px-3 py-2 rounded-md bg-surface-soft border border-line-soft hover:border-primary/30 cursor-pointer transition-all"
                >
                  <span className="w-2 h-2 rounded-full" style={{ background: rCfg.color }} />
                  <span className="text-caption text-ink-primary truncate-1">{r.label}</span>
                  <span className="text-small text-ink-tertiary ml-auto shrink-0">{rCfg.label}</span>
                </div>
              )
            })
          )}
        </div>
      </section>

      <section>
        <h4 className="text-small font-medium text-ink-tertiary mb-2 uppercase tracking-wider">最近更新</h4>
        <div className="text-caption text-ink-secondary">—</div>
      </section>
    </div>
  )
}

function TagListView({ tags }: { tags: string[] }) {
  if (tags.length === 0) {
    return (
      <div className="bg-surface border border-line-soft rounded-lg shadow-xs p-6">
        <span className="text-body text-ink-tertiary">暂无标签</span>
      </div>
    )
  }
  return (
    <div className="bg-surface border border-line-soft rounded-lg shadow-xs p-6">
      <div className="flex flex-wrap gap-2">
        {tags.map((t) => (
          <span
            key={t}
            className="inline-flex items-center gap-1.5 h-8 px-3.5 rounded-full bg-surface-soft border border-line-soft text-caption text-ink-secondary hover:border-primary/40 hover:text-primary cursor-pointer transition-all"
          >
            <Tag className="w-3.5 h-3.5" strokeWidth={2} />
            {t}
          </span>
        ))}
      </div>
    </div>
  )
}

function DocRelationView({ nodes, edges }: { nodes: GraphNode[]; edges: { from: string; to: string }[] }) {
  const docNodes = nodes.filter((n) => n.type === "doc")
  if (docNodes.length === 0) {
    return (
      <div className="bg-surface border border-line-soft rounded-lg shadow-xs p-6">
        <span className="text-body text-ink-tertiary">暂无文档关系</span>
      </div>
    )
  }

  const getTags = (nodeId: string): string[] => {
    return edges
      .filter((e) => e.from === nodeId || e.to === nodeId)
      .flatMap((e) => {
        const otherId = e.from === nodeId ? e.to : e.from
        const other = nodes.find((n) => n.id === otherId)
        return other && other.type === "tag" ? [other.label] : []
      })
  }

  return (
    <div className="bg-surface border border-line-soft rounded-lg shadow-xs divide-y divide-line-soft">
      {docNodes.map((doc) => {
        const tags = getTags(doc.id)
        return (
          <div key={doc.id} className="flex items-center gap-3 px-5 py-3.5 hover:bg-surface-soft transition-colors">
            <FileText className="w-4 h-4 text-ink-tertiary shrink-0" strokeWidth={2} />
            <span className="text-body text-ink-primary truncate-1 flex-1">{doc.label}</span>
            <div className="flex items-center gap-1.5 shrink-0">
              {tags.map((t) => (
                <span key={t} className="text-small text-ink-tertiary">#{t}</span>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}