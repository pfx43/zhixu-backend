import { useCallback, useEffect, useState } from "react"
import { kbApi } from "@/lib/api"
import { mapKbDocument } from "@/lib/mapKbDocument"
import type { KbCollection, KnowledgeDoc } from "@/types"

interface UseKbDocumentsOptions {
  /** 仅保留学习区或生活区 */
  zoneFilter?: "study" | "life"
  /** 默认选中分区：优先 is_default，否则第一个 */
  preferDefault?: boolean
  /** 默认分区 zone 偏好 */
  preferZone?: "study" | "life"
}

export function useKbDocuments(options: UseKbDocumentsOptions = {}) {
  const { zoneFilter, preferDefault = true, preferZone } = options

  const [collections, setCollections] = useState<KbCollection[]>([])
  const [selectedCollectionId, setSelectedCollectionId] = useState("")
  const [documents, setDocuments] = useState<KnowledgeDoc[]>([])
  const [loadingCollections, setLoadingCollections] = useState(true)
  const [loadingDocuments, setLoadingDocuments] = useState(false)

  const selectedCollection = collections.find((c) => c.id === selectedCollectionId)

  const loadDocuments = useCallback(
    async (collectionId: string, zone?: string, silent = false) => {
      if (!collectionId) {
        setDocuments([])
        return []
      }
      if (!silent) setLoadingDocuments(true)
      try {
        const res = await kbApi.listDocuments(1, 50, collectionId)
        const items = (res.documents || []) as Record<string, unknown>[]
        const docs = items.map((d) => mapKbDocument(d, zone))
        setDocuments(docs)
        return docs
      } catch {
        if (!silent) setDocuments([])
        return []
      } finally {
        if (!silent) setLoadingDocuments(false)
      }
    },
    []
  )

  const refreshDocuments = useCallback(
    async (silent = false) => {
      if (!selectedCollectionId) return []
      return loadDocuments(selectedCollectionId, selectedCollection?.zone, silent)
    },
    [selectedCollectionId, selectedCollection?.zone, loadDocuments]
  )

  const updateDocument = useCallback((docId: string, patch: Partial<KnowledgeDoc>) => {
    setDocuments((prev) => prev.map((d) => (d.id === docId ? { ...d, ...patch } : d)))
  }, [])

  useEffect(() => {
    setLoadingCollections(true)
    kbApi
      .listCollections()
      .then((res) => {
        let cols = (res.collections || []) as KbCollection[]
        if (zoneFilter) cols = cols.filter((c) => c.zone === zoneFilter)
        setCollections(cols)
        if (cols.length === 0) return
        const defaultCol =
          (preferZone
            ? cols.find((c) => c.is_default && c.zone === preferZone) ||
              cols.find((c) => c.zone === preferZone)
            : undefined) ||
          (preferDefault ? cols.find((c) => c.is_default) : undefined) ||
          cols[0]
        if (defaultCol) setSelectedCollectionId(defaultCol.id)
      })
      .catch(() => setCollections([]))
      .finally(() => setLoadingCollections(false))
  }, [zoneFilter, preferDefault, preferZone])

  useEffect(() => {
    if (selectedCollectionId) {
      void loadDocuments(selectedCollectionId, selectedCollection?.zone)
    } else {
      setDocuments([])
    }
  }, [selectedCollectionId, selectedCollection?.zone, loadDocuments])

  const hasOcrInProgress = documents.some((d) => d.ocr_status === "processing")

  useEffect(() => {
    if (!selectedCollectionId || !hasOcrInProgress) return
    const timer = window.setInterval(() => {
      void loadDocuments(selectedCollectionId, selectedCollection?.zone, true)
    }, 2500)
    return () => window.clearInterval(timer)
  }, [selectedCollectionId, selectedCollection?.zone, hasOcrInProgress, loadDocuments])

  return {
    collections,
    selectedCollectionId,
    setSelectedCollectionId,
    selectedCollection,
    documents,
    setDocuments,
    loadingCollections,
    loadingDocuments,
    loadDocuments,
    refreshDocuments,
    updateDocument,
  }
}
