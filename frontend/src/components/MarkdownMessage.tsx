"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

/** Renders an agent reply as Markdown */
export function MarkdownMessage({
  children,
  className,
}: {
  children: string;
  className?: string;
}) {
  return (
    <div className={cn("space-y-2 text-sm leading-relaxed", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="[&:not(:first-child)]:mt-2">{children}</p>,
          ul: ({ children }) => (
            <ul className="mt-2 space-y-1.5 [&>li]:relative [&>li]:pl-4">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="mt-2 list-decimal space-y-1.5 pl-5 marker:font-bold marker:text-primary">
              {children}
            </ol>
          ),
          li: ({ children }) => <li className="leading-snug">{children}</li>,
          strong: ({ children }) => (
            <strong className="font-bold text-foreground">{children}</strong>
          ),
          em: ({ children }) => <em className="italic">{children}</em>,
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="font-semibold text-primary underline underline-offset-2"
            >
              {children}
            </a>
          ),
          code: ({ children }) => (
            <code className="rounded bg-secondary px-1 py-0.5 font-mono text-[0.85em]">
              {children}
            </code>
          ),
          // Agents are told not to emit these; render them safely if they do.
          h1: ({ children }) => <p className="mt-2 font-extrabold">{children}</p>,
          h2: ({ children }) => <p className="mt-2 font-extrabold">{children}</p>,
          h3: ({ children }) => <p className="mt-2 font-bold">{children}</p>,
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-border pl-3 text-muted-foreground">
              {children}
            </blockquote>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto">
              <table className="mt-2 w-full text-xs">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border-b border-border px-2 py-1 text-left font-bold">
              {children}
            </th>
          ),
          td: ({ children }) => <td className="px-2 py-1 align-top">{children}</td>,
          hr: () => <hr className="my-3 border-border" />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
