"use client";

import * as React from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/shared/lib/utils";

const COMPONENTS: Components = {
  p: ({ children, ...rest }) => (
    <p dir="auto" className="whitespace-pre-wrap [&:not(:first-child)]:mt-2" {...rest}>
      {children}
    </p>
  ),
  strong: ({ children, ...rest }) => (
    <strong className="font-semibold" {...rest}>
      {children}
    </strong>
  ),
  em: ({ children, ...rest }) => (
    <em className="italic" {...rest}>
      {children}
    </em>
  ),
  del: ({ children, ...rest }) => (
    <del className="line-through opacity-70" {...rest}>
      {children}
    </del>
  ),
  a: ({ children, href, ...rest }) => (
    <a
      {...rest}
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="underline underline-offset-2 hover:opacity-80 transition-opacity"
    >
      {children}
    </a>
  ),
  ul: ({ children, ...rest }) => (
    <ul dir="auto" className="my-2 list-disc ps-5 space-y-1 marker:text-current/60" {...rest}>
      {children}
    </ul>
  ),
  ol: ({ children, ...rest }) => (
    <ol dir="auto" className="my-2 list-decimal ps-5 space-y-1 marker:text-current/60" {...rest}>
      {children}
    </ol>
  ),
  li: ({ children, ...rest }) => (
    <li className="leading-relaxed" {...rest}>
      {children}
    </li>
  ),
  blockquote: ({ children, ...rest }) => (
    <blockquote
      dir="auto"
      className="my-2 ps-3 border-s-2 border-current/20 opacity-90 italic"
      {...rest}
    >
      {children}
    </blockquote>
  ),
  h1: ({ children, ...rest }) => (
    <h3 dir="auto" className="text-base font-semibold [&:not(:first-child)]:mt-3 mb-1" {...rest}>
      {children}
    </h3>
  ),
  h2: ({ children, ...rest }) => (
    <h4 dir="auto" className="text-sm font-semibold [&:not(:first-child)]:mt-3 mb-1" {...rest}>
      {children}
    </h4>
  ),
  h3: ({ children, ...rest }) => (
    <h5 dir="auto" className="text-sm font-semibold [&:not(:first-child)]:mt-2 mb-0.5" {...rest}>
      {children}
    </h5>
  ),
  h4: ({ children, ...rest }) => (
    <h6 dir="auto" className="text-sm font-medium [&:not(:first-child)]:mt-2 mb-0.5" {...rest}>
      {children}
    </h6>
  ),
  code: ({ className, children, ...rest }) => {
    const isBlock = /language-/.test(className ?? "");
    if (isBlock) {
      return (
        <code className={cn("font-mono text-[0.8125rem] leading-relaxed", className)} {...rest}>
          {children}
        </code>
      );
    }
    return (
      <code
        dir="ltr"
        className="inline-block rounded-md bg-black/[0.06] px-1.5 py-px font-mono text-[0.8125em] align-baseline"
        {...rest}
      >
        {children}
      </code>
    );
  },
  pre: ({ children, ...rest }) => (
    <pre
      dir="ltr"
      className="my-2 overflow-x-auto rounded-xl bg-black/[0.06] p-3 text-left"
      {...rest}
    >
      {children}
    </pre>
  ),
  hr: ({ ...rest }) => <hr className="my-3 border-current/15" {...rest} />,
  table: ({ children, ...rest }) => (
    <div className="my-2 overflow-x-auto">
      <table dir="auto" className="w-full border-collapse text-[0.8125rem]" {...rest}>
        {children}
      </table>
    </div>
  ),
  thead: ({ children, ...rest }) => (
    <thead className="border-b border-current/15" {...rest}>
      {children}
    </thead>
  ),
  th: ({ children, ...rest }) => (
    <th className="px-2 py-1 text-start font-semibold" {...rest}>
      {children}
    </th>
  ),
  td: ({ children, ...rest }) => (
    <td className="px-2 py-1 border-t border-current/10" {...rest}>
      {children}
    </td>
  ),
};

export function MessageMarkdown({ content, className }: { content: string; className?: string }) {
  return (
    <div className={cn("break-words", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
