# Backend API Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a dedicated backend integration branch that adds a real login page and connects the Zhishi Web app to every public backend capability exposed by `https://zhishi-backend.ximocy.com/openapi.json`.

**Architecture:** Add a small typed API boundary under `src/lib/api/`, an auth provider that owns token persistence and current-user loading, protected routes around the existing app shell, and feature hooks/components that replace `src/data/*` mock reads with backend-backed state. Keep the current design system and page layout, but make each page resilient to loading, empty, and backend error states.

**Tech Stack:** React 19, Vite 7, TypeScript strict mode, React Router, Tailwind CSS, existing shadcn/Radix UI primitives, browser `fetch`, `FormData`, and streaming `ReadableStream`.

---

## Verified Backend Surface

Source checked on 2026-06-25:

- Swagger UI: `https://zhishi-backend.ximocy.com/docs`
- OpenAPI JSON: `https://zhishi-backend.ximocy.com/openapi.json`
- Health: `https://zhishi-backend.ximocy.com/health`

Current health response:

```json
{"status":"degraded","skills_count":9,"model_loaded":false}
```

Important drift from `docs/API.md`:

- `POST /api/v1/auth/token` returns `access_token`, `token_type`, and `expires_in`.
- `POST /api/v1/chat` has `stream` default `false` in OpenAPI, while `docs/API.md` describes SSE streaming as the main mode. The client should support both and use streaming only where the browser response is actually `text/event-stream`.
- KT `states` are object maps (`Record<string, number>`) in OpenAPI, not arrays.
- `GET /api/v1/kt/skill-graph` returns `skills`, `edges`, `total_skills`, and `total_edges`, not `nodes`.
- `POST /api/v1/kt/prerequisites` uses `skill_id: string` and returns `dependents`, not `successors`.
- `GET /api/v1/plan/` is not protected in OpenAPI, while `docs/API.md` says it requires auth.
- `PlanTier` uses `price_monthly` and `knowledge_base_limit`; `docs/API.md` examples use `price` and `kb_limit`.

## File Structure

- Create `src/lib/api/config.ts`: backend base URL and storage key constants.
- Create `src/lib/api/errors.ts`: `ApiError`, error parsing, and HTTP status helpers.
- Create `src/lib/api/types.ts`: OpenAPI-aligned TypeScript types.
- Create `src/lib/api/client.ts`: JSON, form, multipart, and auth-aware request helpers.
- Create `src/lib/api/auth.ts`: auth endpoints.
- Create `src/lib/api/chat.ts`: chat sessions, history, delete, non-streaming send, and SSE streaming helper.
- Create `src/lib/api/kb.ts`: upload, list, status, delete, preview, config.
- Create `src/lib/api/dashboard.ts`: suggestions.
- Create `src/lib/api/kt.ts`: correct, evaluate, learning path, prerequisites, skill graph.
- Create `src/lib/api/plan.ts`: all plans and my plan.
- Create `src/lib/api/health.ts`: health check.
- Create `src/lib/auth/AuthContext.tsx`: token persistence, login, register, logout, profile refresh, route guard helpers.
- Create `src/features/auth/LoginPage.tsx`: login/register/forgot/reset/email verification entry using existing design tokens.
- Create `src/components/auth/ProtectedRoute.tsx`: redirect unauthenticated users to `/login`.
- Create `src/components/auth/AuthGate.tsx`: app bootstrap loading state.
- Modify `src/App.tsx`: wrap with `AuthProvider`.
- Modify `src/routes/index.tsx`: add `/login`, `/forgot-password`, `/reset-password`, and route protection for the app.
- Modify `src/components/layout/Sidebar.tsx`: show authenticated user name/avatar and logout affordance.
- Modify `src/components/layout/Topbar.tsx`: show backend health/session state and navigate top search to chat.
- Modify `src/features/dashboard/DashboardPage.tsx`: fetch current user, dashboard suggestions, KB documents, quota/plan summary.
- Modify `src/features/chat/ChatPage.tsx`: replace simulated replies with chat sessions, history, streaming send, delete session.
- Modify `src/features/knowledge-base/KnowledgeBasePage.tsx`: list/delete/preview documents and display real indexing status.
- Modify `src/features/knowledge-base/UploadPage.tsx`: real file picker, drag-drop upload, progress polling by `batch_id`, KB config.
- Modify `src/features/knowledge-graph/KnowledgeGraphPage.tsx`: transform KT `skills`/`edges` into graph nodes.
- Modify `src/features/learning/LearningAnalyticsPage.tsx`: call KT evaluate/correct on a local editable state map and render returned consistency metrics.
- Modify `src/features/learning/LearningPathPage.tsx`: call KT learning path and prerequisites with the same state map.
- Modify `src/features/profile/ProfilePage.tsx`: load/update current profile and tags.
- Modify `src/features/settings/SettingsPage.tsx`: show health, plan, quota, KB config, token test, logout/change-password/delete-account entry points.
- Modify `src/features/settings/DiagnosticsPage.tsx`: replace mobile permission mock with backend diagnostics.
- Create tests under `src/lib/api/*.test.ts` or a lightweight local test harness if the repo does not yet include a test runner.

## Phase 0: Branch And Scope Safety

- [x] **Step 1: Check initial branch and dirty scope**

Run:

```powershell
git status --short --branch
```

Observed:

```text
## main...origin/main
A  docs/API.md
```

- [x] **Step 2: Create dedicated backend integration branch**

Run:

```powershell
git switch -c codex/backend-api-integration
```

Expected:

```text
Switched to a new branch 'codex/backend-api-integration'
```

- [ ] **Step 3: Preserve user-supplied staged doc**

Before any commit, use whitelist staging only. Do not unstage, rewrite, or bundle `docs/API.md` unless the user explicitly asks to include it.

## Phase 1: Typed API Boundary

### Task 1: Add API Type And Error Tests

**Files:**

- Create: `src/lib/api/errors.ts`
- Create: `src/lib/api/types.ts`
- Create: `src/lib/api/__tests__/errors.test.ts` or `src/lib/api/errors.test.ts`
- Modify: `package.json` only if a test runner is missing and a minimal runner is selected.

- [ ] **Step 1: Write failing error parsing tests**

Test cases:

```ts
import { describe, expect, it } from "vitest"
import { ApiError, getErrorMessage } from "../errors"

describe("ApiError", () => {
  it("uses FastAPI detail string as the display message", () => {
    const error = new ApiError(401, "Unauthorized", { detail: "未登录或 Token 过期" })
    expect(error.message).toBe("未登录或 Token 过期")
  })

  it("summarizes FastAPI validation detail arrays", () => {
    const error = new ApiError(422, "Validation Error", {
      detail: [{ loc: ["body", "email"], msg: "field required", type: "missing" }],
    })
    expect(error.message).toBe("email: field required")
  })

  it("normalizes unknown thrown values", () => {
    expect(getErrorMessage("boom")).toBe("boom")
    expect(getErrorMessage({ detail: "请求失败" })).toBe("请求失败")
  })
})
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
npm run test -- src/lib/api/errors.test.ts
```

Expected: fail because no test runner or no `errors.ts` exists yet.

- [ ] **Step 3: Implement `ApiError` and `getErrorMessage`**

Implementation requirements:

- Preserve HTTP `status`, `statusText`, and raw response payload.
- Prefer `detail` string.
- For `detail` arrays, use the last non-generic `loc` segment plus `msg`.
- Fall back to `message`, `statusText`, then `请求失败`.

- [ ] **Step 4: Run test and verify GREEN**

Run:

```powershell
npm run test -- src/lib/api/errors.test.ts
```

Expected: pass.

### Task 2: Add Fetch Client Tests And Implementation

**Files:**

- Create: `src/lib/api/config.ts`
- Create: `src/lib/api/client.ts`
- Create: `src/lib/api/client.test.ts`

- [ ] **Step 1: Write failing client tests**

Test cases:

```ts
import { describe, expect, it, vi } from "vitest"
import { apiRequest, setAccessTokenForApi } from "./client"

describe("apiRequest", () => {
  it("joins the production backend base URL and sends bearer auth", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ ok: true }),
    })
    vi.stubGlobal("fetch", fetchMock)
    setAccessTokenForApi("token-123")

    const result = await apiRequest<{ ok: boolean }>("/api/v1/auth/users/me")

    expect(result).toEqual({ ok: true })
    expect(fetchMock).toHaveBeenCalledWith(
      "https://zhishi-backend.ximocy.com/api/v1/auth/users/me",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer token-123" }),
      }),
    )
  })

  it("does not force JSON content type for FormData", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ uploaded: true }),
    })
    vi.stubGlobal("fetch", fetchMock)

    const form = new FormData()
    form.append("file", new Blob(["hello"]), "hello.txt")
    await apiRequest("/api/v1/kb/upload", { method: "POST", body: form })

    const headers = fetchMock.mock.calls[0][1].headers
    expect(headers["Content-Type"]).toBeUndefined()
  })
})
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
npm run test -- src/lib/api/client.test.ts
```

Expected: fail because `client.ts` does not exist.

- [ ] **Step 3: Implement request helpers**

Implementation requirements:

- Default base URL: `https://zhishi-backend.ximocy.com`.
- Allow override via `import.meta.env.VITE_ZHISHI_API_BASE_URL`.
- Store token in memory for requests; AuthContext owns localStorage persistence.
- For JSON bodies, set `Content-Type: application/json`.
- For `FormData`, do not set `Content-Type`.
- Throw `ApiError` for non-2xx responses.
- Return `undefined` for 204/no body; otherwise parse JSON when content type is JSON, text otherwise.

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
npm run test -- src/lib/api/client.test.ts
```

Expected: pass.

### Task 3: Add Endpoint Modules

**Files:**

- Create: `src/lib/api/auth.ts`
- Create: `src/lib/api/chat.ts`
- Create: `src/lib/api/kb.ts`
- Create: `src/lib/api/dashboard.ts`
- Create: `src/lib/api/kt.ts`
- Create: `src/lib/api/plan.ts`
- Create: `src/lib/api/health.ts`

- [ ] **Step 1: Write endpoint wrapper tests**

Minimum tests:

- `login()` sends `application/x-www-form-urlencoded` with `username` and `password`.
- `register()` sends JSON body.
- `uploadDocument()` sends `FormData` with `file`.
- `getSkillGraph()` calls `/api/v1/kt/skill-graph`.
- `getPlans()` calls `/api/v1/plan/`.

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
npm run test -- src/lib/api
```

Expected: endpoint imports fail.

- [ ] **Step 3: Implement endpoint wrappers**

Required endpoint coverage:

- Auth: register, login, refresh token, me, me plan, quota, upgrade plan, send verification, verify email, forgot password, reset password, logout, check email verification, change password, delete account, update profile, token test.
- Chat: send non-streaming, send streaming, history, sessions, delete session.
- KB: upload, documents, status, delete, content, config.
- Dashboard: suggestions.
- KT: correct, evaluate, learning path, prerequisites, skill graph.
- Plan: all plans, my plan.
- Health: health.

- [ ] **Step 4: Run endpoint tests and TypeScript**

Run:

```powershell
npm run test -- src/lib/api
npm run build
```

Expected: tests pass; build passes.

## Phase 2: Auth Shell And Login Page

### Task 4: Auth Provider And Route Guard

**Files:**

- Create: `src/lib/auth/AuthContext.tsx`
- Create: `src/components/auth/ProtectedRoute.tsx`
- Create: `src/components/auth/AuthGate.tsx`
- Modify: `src/App.tsx`
- Modify: `src/routes/index.tsx`

- [ ] **Step 1: Write auth behavior tests**

Test behaviors:

- Existing token in localStorage is loaded into API client.
- `login()` stores token and loads `/users/me`.
- `logout()` calls backend logout when possible, clears token even if backend rejects, and navigates to `/login`.
- Protected routes redirect to `/login` when unauthenticated.

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
npm run test -- src/lib/auth
```

Expected: fail because AuthContext does not exist.

- [ ] **Step 3: Implement provider**

State shape:

```ts
type AuthState = {
  token: string | null
  user: UserResponse | null
  status: "booting" | "authenticated" | "anonymous"
  error: string | null
}
```

Provider actions:

- `login(username, password)`
- `register(payload)`
- `logout()`
- `refreshUser()`
- `updateProfile(payload)`
- `changePassword(payload)`
- `deleteAccount()`

- [ ] **Step 4: Wrap routing**

Routes:

- Public: `/login`, `/forgot-password`, `/reset-password`
- Protected: all existing app routes.
- Unknown protected path falls back to dashboard after auth.

- [ ] **Step 5: Run tests and build**

Run:

```powershell
npm run test -- src/lib/auth
npm run build
```

Expected: pass.

### Task 5: Login/Register/Forgot UI

**Files:**

- Create: `src/features/auth/LoginPage.tsx`
- Modify: `src/routes/index.tsx`

- [ ] **Step 1: Implement login page using current design system**

Required UI states:

- Login form: email/phone, password, submit.
- Register form: email, nickname, password, optional verification code.
- Verification tools: send verification code and check verification status.
- Forgot password form: email.
- Reset password form: reset token and new password.
- Error banner, loading spinner, success message.

- [ ] **Step 2: Wire auth actions**

Behavior:

- Successful login navigates to `/`.
- Registration stores token if backend returns `access_token`; otherwise switch to login with success copy.
- Forgot/reset flows display backend message.
- Do not expose raw token in UI.

- [ ] **Step 3: Build and inspect mobile/desktop**

Run:

```powershell
npm run build
```

Expected: pass with no TypeScript errors.

## Phase 3: Page Integrations

### Task 6: Dashboard And Layout User State

**Files:**

- Modify: `src/components/layout/Sidebar.tsx`
- Modify: `src/components/layout/Topbar.tsx`
- Modify: `src/features/dashboard/DashboardPage.tsx`

- [ ] **Step 1: Replace static user data**

Use `useAuth()` user fields:

- Sidebar user name: `nickname || username || email`.
- Avatar: first visible character from nickname/email.
- Plan label: `user.plan_info.name`.
- Logout action in user area.

- [ ] **Step 2: Dashboard data**

Fetch:

- `getDashboardSuggestions()`
- `listDocuments({ page: 1, limit: 5 })`
- `getQuota()`
- `getHealth()`

Render:

- Suggestions in Tina panel.
- Recent documents from KB list.
- Health badge when degraded/unhealthy.
- Empty and error states.

### Task 7: Chat

**Files:**

- Modify: `src/features/chat/ChatPage.tsx`
- Modify: `src/components/blocks/ChatMessage.tsx` if reasoning/tool display is needed.

- [ ] **Step 1: Load sessions and selected history**

On page load:

- Fetch `listChatSessions()`.
- Select latest session if any.
- Fetch `getChatHistory(sessionId)`.
- Show welcome message only when no session is selected.

- [ ] **Step 2: Send messages**

Behavior:

- Append user message optimistically.
- Call streaming helper with `stream: true`.
- If response content type is SSE, append chunks to the active assistant message.
- If backend returns JSON, append returned content.
- Capture first returned `session_id` for new sessions and refresh sessions list.
- Show `tool_name` and `reasoning_content` only as compact metadata, not as raw JSON.

- [ ] **Step 3: Session controls**

Add:

- New chat button.
- Session list in right panel.
- Delete session action.
- Error retry.

### Task 8: Knowledge Base And Upload

**Files:**

- Modify: `src/features/knowledge-base/KnowledgeBasePage.tsx`
- Modify: `src/features/knowledge-base/UploadPage.tsx`
- Modify: `src/components/blocks/DocRow.tsx`

- [ ] **Step 1: KB list**

Fetch:

- `getKbConfig()`
- `listDocuments(page, limit)`

Render:

- Document name, file type, size, status, created/updated time.
- Stats from returned total and status counts.
- Search filters client-side over current page.
- Empty state when no docs.

- [ ] **Step 2: Document actions**

Add:

- Preview content drawer/dialog using `getDocumentContent(docId)`.
- Delete document confirmation using `deleteDocument(docId)`.
- Refresh list after delete.

- [ ] **Step 3: Upload**

Behavior:

- Real hidden file input and drag/drop.
- Validate extension and size using `getKbConfig()`.
- Call `uploadDocument(file)`.
- Show duplicate/indexing/completed/error statuses.
- Poll `getDocumentStatus(batchId)` every 2 seconds until completed/error or timeout.
- Link back to `/knowledge`.

### Task 9: KT Graph, Analytics, And Path

**Files:**

- Modify: `src/features/knowledge-graph/KnowledgeGraphPage.tsx`
- Modify: `src/features/learning/LearningAnalyticsPage.tsx`
- Modify: `src/features/learning/LearningPathPage.tsx`

- [ ] **Step 1: Skill graph transform**

Transform:

```ts
SkillGraphResponse.skills -> GraphNode[]
SkillGraphResponse.edges -> GraphEdge[]
```

Use deterministic radial layout:

- Center at `380,240`.
- Radius between `120` and `210`.
- Node size based on edge count.

- [ ] **Step 2: Shared state map**

Create local state map from graph skills:

```ts
Record<string, number>
```

Default each skill to `0.5` when no persisted mastery exists.

- [ ] **Step 3: Analytics**

Call:

- `evaluate({ states })`
- `correct({ states })`

Render:

- `lvr`
- `vs`
- `is_consistent`
- `violation_count`
- Top changed skills from `changes`.

- [ ] **Step 4: Learning path**

Call:

- `getLearningPath({ states, top_k: 5 })`
- `getPrerequisites({ skill_id })` for selected skill.

Render returned recommendations without assuming local sample fields such as `estimatedMinutes`.

### Task 10: Profile, Plan, Settings, Diagnostics

**Files:**

- Modify: `src/features/profile/ProfilePage.tsx`
- Modify: `src/features/settings/SettingsPage.tsx`
- Modify: `src/features/settings/DiagnosticsPage.tsx`

- [ ] **Step 1: Profile**

Load current user and update:

- `nickname`
- `phone`
- `gender`
- `signature`
- `tags`

After save, call `refreshUser()`.

- [ ] **Step 2: Plans and quota**

Fetch:

- `getPlans()`
- `getMyPlan()`
- `getQuota()`

Render current plan and available upgrades. Provide upgrade action via `upgradePlan({ plan_level, months: 1 })` with confirmation.

- [ ] **Step 3: Account/security**

Add:

- Change password form.
- Token test action.
- Logout action.
- Delete account confirmation requiring typed email.

- [ ] **Step 4: Diagnostics**

Replace mobile permission mock with:

- Health check.
- Token test.
- KB config.
- Quota.
- Plan.
- Current user.

Each diagnostic row should show success/warning/error with the actual backend message.

## Phase 4: Verification And Handoff

- [ ] **Step 1: Static checks**

Run:

```powershell
npm run lint
npm run build
```

Expected:

- No TypeScript errors.
- No lint errors introduced by the integration branch.

- [ ] **Step 2: Backend smoke checks**

Run:

```powershell
curl.exe -L -s https://zhishi-backend.ximocy.com/health
curl.exe -L -s https://zhishi-backend.ximocy.com/openapi.json
```

Expected:

- `/health` returns JSON.
- `/openapi.json` returns OpenAPI JSON.

- [ ] **Step 3: Browser verification**

Run:

```powershell
npm run dev -- --host 127.0.0.1
```

Verify:

- `/login` renders on desktop and mobile width.
- Bad credentials show backend error.
- Successful login enters dashboard if a valid account is available.
- Dashboard loads suggestions/docs or shows understandable empty/error state.
- Chat can send a message and render returned content or backend error.
- KB upload opens file picker and validates config.
- Settings diagnostics show health as `degraded` for the current backend state.

- [ ] **Step 4: Git scope check**

Run:

```powershell
git status --short
git diff --stat
```

Expected:

- Only planned files are modified.
- Existing user file `docs/API.md` remains preserved.

## Implementation Notes

- Do not use ad-hoc string parsing for OpenAPI data in production code; hard-code typed wrappers from the verified schema.
- Prefer small hooks/helpers over pushing all async logic into page bodies when repeated loading/error behavior appears more than twice.
- Keep all visible UI copy in Chinese.
- Do not store passwords or refresh payloads in localStorage.
- Treat `access_token` as the only persisted secret and clear it on `401`.
- The backend is currently `degraded` because the model is not loaded; the frontend should not treat this as total failure.
- If no test runner exists, add Vitest in the smallest possible way and keep tests focused on API/auth behavior.
- Because the repo already has `docs/API.md` staged before this work, all final staging/commit actions must be whitelisted.

