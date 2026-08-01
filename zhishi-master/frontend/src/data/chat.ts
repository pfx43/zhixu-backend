import type { ChatMessage } from "@/types"

export const welcomeMessage: ChatMessage = {
  id: "welcome",
  role: "assistant",
  content: "你好，啊噗！我是 Tina，你的知识管理助手。\n你可以问我课程知识、上传文档、整理笔记，或者让我帮你生成学习路径。",
  time: "刚刚",
}

export const sampleMessages: ChatMessage[] = [
  {
    id: "m1",
    role: "user",
    content: "帮我整理一下 Flutter State 管理的核心知识点。",
    time: "14:02",
  },
  {
    id: "m2",
    role: "assistant",
    content:
      "好的，以下是 Flutter State 管理的核心知识点整理：\n\n1. setState：最基础的方式，适用于局部、简单的状态。当状态变化范围超出单个 widget 时，会导致大量重建，性能不佳。\n\n2. InheritedWidget：在 widget 树中向下传递数据，Provider 就是基于它实现的。适合共享只读或少变的状态。\n\n3. Provider：官方推荐的基础方案，结合 ChangeNotifier 可以实现响应式更新。写法清晰，但需要手动管理 dispose。\n\n4. Riverpod：Provider 的改进版，解决了 Provider 的部分痛点（如上下文依赖、不可测试）。推荐在新项目使用。\n\n5. Bloc / Cubit：基于事件驱动的方案，适合复杂业务逻辑。学习曲线较陡，但可维护性强。\n\n建议你按 setState → Provider → Riverpod 的顺序学习，先把基础打牢再上复杂方案。",
    time: "14:02",
    refs: ["Flutter State 管理笔记", "Provider 与 Riverpod 对比"],
  },
  {
    id: "m3",
    role: "user",
    content: "Provider 和 Riverpod 具体有什么区别？为什么推荐 Riverpod？",
    time: "14:05",
  },
  {
    id: "m4",
    role: "assistant",
    content:
      "Provider 和 Riverpod 的核心区别：\n\n• 依赖上下文：Provider 依赖 BuildContext，跨树访问麻烦；Riverpod 不依赖 context，可以在任何地方读取状态。\n\n• 类型安全：Riverpod 是编译时类型安全的，Provider 在运行时才能发现错误。\n\n• 可测试性：Riverpod 的 Provider 可以直接 override，单元测试更简单。\n\n• dispose 管理：Riverpod 自动管理生命周期，Provider 需要手动处理。\n\n推荐 Riverpod 主要因为它的可维护性和可测试性更强，特别适合中大型项目。但如果是简单应用，Provider 已经够用。",
    time: "14:06",
    refs: ["Provider 与 Riverpod 对比"],
  },
]

export const contextPanel = {
  kb: "默认知识库",
  refs: 2,
  mode: "高效笔记",
  output: "回答 + 可生成笔记",
}

export const recentRefs = ["Flutter State 管理笔记", "Provider 与 Riverpod 对比", "Dart 异步编程"]

export const suggestedQuestions = [
  "State 管理的最佳实践是什么？",
  "如何选择 Provider 和 Riverpod？",
  "帮我生成 State 管理学习路径",
]
