import { createContext, useContext, useState, type ReactNode } from "react"

interface UIState {
  sidebarCollapsed: boolean
  rightPanelOpen: boolean
  toggleSidebar: () => void
  setSidebarCollapsed: (v: boolean) => void
  toggleRightPanel: () => void
  setRightPanelOpen: (v: boolean) => void
}

const UIContext = createContext<UIState | null>(null)

export function UIProvider({ children }: { children: ReactNode }) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [rightPanelOpen, setRightPanelOpen] = useState(true)

  return (
    <UIContext.Provider
      value={{
        sidebarCollapsed,
        rightPanelOpen,
        toggleSidebar: () => setSidebarCollapsed((v) => !v),
        setSidebarCollapsed,
        toggleRightPanel: () => setRightPanelOpen((v) => !v),
        setRightPanelOpen,
      }}
    >
      {children}
    </UIContext.Provider>
  )
}

export function useUI() {
  const ctx = useContext(UIContext)
  if (!ctx) throw new Error("useUI must be used within UIProvider")
  return ctx
}
