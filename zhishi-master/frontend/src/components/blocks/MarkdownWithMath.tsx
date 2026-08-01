import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import remarkMath from "remark-math"
import rehypeKatex from "rehype-katex"
import "katex/dist/katex.min.css"
import { cn } from "@/lib/utils"

/** 默认 prose 样式，适用于助手消息 / 正文 */
export const markdownProseClass =
  "prose prose-sm max-w-none prose-headings:text-ink-primary prose-p:text-ink-primary prose-p:my-1 prose-strong:text-ink-primary prose-a:text-primary prose-code:bg-surface-soft prose-code:px-1 prose-code:rounded prose-code:text-small prose-pre:bg-surface-soft prose-pre:border prose-pre:border-line-soft prose-ul:my-1 prose-ol:my-1"

/** 用户消息（深色背景）prose 样式 */
export const markdownProseInvertClass =
  "prose prose-sm prose-invert max-w-none prose-p:my-1 prose-p:text-white prose-strong:text-white prose-a:text-white prose-code:bg-white/15 prose-code:px-1 prose-code:rounded prose-code:text-small prose-pre:bg-white/10 prose-pre:border prose-pre:border-white/20 prose-ul:my-1 prose-ol:my-1"

interface MarkdownWithMathProps {
  children: string
  className?: string
  proseClass?: string
}

/**
 * 支持 GFM + LaTeX（$...$ 行内、$$...$$ 块级）的 Markdown 渲染。
 * 行内公式示例：质能方程 $E=mc^2$
 * 块级公式示例：
 * $$
 * \int_0^1 x^2 dx = \frac{1}{3}
 * $$
 */
export function MarkdownWithMath({
  children,
  className,
  proseClass = markdownProseClass,
}: MarkdownWithMathProps) {
  if (!children) return null

  return (
    <div className={cn(proseClass, className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
        {children}
      </ReactMarkdown>
    </div>
  )
}
