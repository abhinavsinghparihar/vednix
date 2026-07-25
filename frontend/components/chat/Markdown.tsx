/**
 * Markdown renderer: GFM tables/strikethrough/task-lists, syntax-highlighted
 * code with copy button + language badge, lazy-loaded Mermaid diagrams.
 */

"use client";

import { memo, useEffect, useRef, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import rehypeHighlight from "rehype-highlight";
import { Check, Copy, GitBranch } from "lucide-react";
import { cn } from "@/lib/utils";

let mermaidSeq = 0;

function MermaidBlock({ code }: { code: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const idRef = useRef(`mmd-${++mermaidSeq}`);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        // ~500KB diagram engine loads ONLY when a mermaid block exists
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: "dark",
          securityLevel: "strict",
          themeVariables: {
            primaryColor: "#2a2318",
            primaryBorderColor: "#e3b857",
            primaryTextColor: "#f5f0e6",
            lineColor: "#b08d3e",
            secondaryColor: "#1b1815",
            tertiaryColor: "#14120f",
            fontFamily: "inherit",
          },
        });
        const { svg } = await mermaid.render(idRef.current, code);
        if (alive) setSvg(svg);
      } catch {
        if (alive) setFailed(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, [code]);

  if (failed) {
    return (
      <pre className="overflow-x-auto rounded-xl border border-edge bg-black/50 p-4 text-xs text-muted">
        <code>{code}</code>
      </pre>
    );
  }
  if (!svg) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-edge bg-black/30 p-6 text-xs text-muted">
        <GitBranch className="h-4 w-4 animate-pulse-soft text-gold" /> Rendering diagram…
      </div>
    );
  }
  return <div className="mermaid-render overflow-x-auto rounded-xl border border-edge bg-black/30 p-3 [&>svg]:mx-auto" dangerouslySetInnerHTML={{ __html: svg }} />;
}

function Pre({ children }: { children?: ReactNode }) {
  const ref = useRef<HTMLPreElement>(null);
  const [copied, setCopied] = useState(false);

  // language-xxx comes from the child <code> after rehype-highlight
  const childProps = (children as { props?: { className?: string; children?: ReactNode } })?.props;
  const lang = /language-([\w-]+)/.exec(childProps?.className ?? "")?.[1];

  const copy = async () => {
    const text = ref.current?.innerText ?? "";
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch { /* clipboard unavailable (non-secure context) */ }
  };

  if (lang === "mermaid" && typeof childProps?.children === "string") {
    return <MermaidBlock code={childProps.children} />;
  }

  return (
    <div className="group/code relative my-3">
      <div className="flex items-center justify-between rounded-t-xl border border-b-0 border-edge bg-[#171410] px-3.5 py-1.5">
        <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-gold/70">{lang ?? "code"}</span>
        <button
          onClick={copy}
          aria-label="Copy code"
          className="flex items-center gap-1 text-[11px] text-muted transition-colors hover:text-gold-bright"
        >
          {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre
        ref={ref}
        className="overflow-x-auto rounded-b-xl border border-edge bg-[#0b0a08] p-4 font-mono text-[13px] leading-relaxed"
      >
        {children}
      </pre>
    </div>
  );
}

export const Markdown = memo(function Markdown({ content }: { content: string }) {
  return (
    <div className={cn("md-body")}>
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]} rehypePlugins={[rehypeHighlight]} components={{ pre: Pre }}>
        {content}
      </ReactMarkdown>
    </div>
  );
});
