import { isValidElement, useMemo, useState, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { Mermaid } from "./Mermaid";

/** Collect the plain text of a rendered subtree — used to copy a code block. */
function nodeText(node: ReactNode): string {
  if (typeof node === "string") return node;
  if (typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(nodeText).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) return nodeText(node.props.children);
  return "";
}

function nodeLanguage(node: ReactNode): string {
  if (isValidElement<{ className?: string }>(node)) {
    const match = /language-([\w+#-]+)/.exec(node.props.className ?? "");
    if (match) return match[1];
  }
  if (Array.isArray(node)) {
    for (const child of node) {
      const found = nodeLanguage(child);
      if (found) return found;
    }
  }
  return "";
}

function CodeBlock({ children }: { children?: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const code = nodeText(children);
  const language = nodeLanguage(children);

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard is unavailable outside a secure context; selecting still works.
    }
  }

  return (
    <div className="md-code">
      <div className="md-code-bar">
        <span className="md-code-lang">{language || "код"}</span>
        <button type="button" className="md-copy" onClick={() => void copy()}>
          {copied ? "Скопировано" : "Копировать"}
        </button>
      </div>
      <pre>{children}</pre>
    </div>
  );
}

function buildComponents(streaming: boolean): Components {
  return {
    pre: ({ children }) => {
      // A diagram is only drawn once the block is complete: mermaid cannot
      // parse half a graph, and retrying on every token would just flicker.
      if (!streaming && nodeLanguage(children) === "mermaid") {
        return <Mermaid code={nodeText(children).replace(/\n$/, "")} />;
      }
      return <CodeBlock>{children}</CodeBlock>;
    },
    img: ({ src, alt }) => (
      // Model output is untrusted: no referrer, lazy, and never wider than the
      // message. react-markdown already strips dangerous URL schemes.
      <img className="md-image" src={typeof src === "string" ? src : undefined} alt={alt ?? ""} loading="lazy" referrerPolicy="no-referrer" />
    ),
    a: ({ href, children }) => {
      const url = typeof href === "string" ? href : undefined;
      if (url && isMediaVideoUrl(url)) {
        return (
          <video className="md-video" controls playsInline preload="metadata" src={url}>
            <a href={url} target="_blank" rel="noopener noreferrer nofollow">
              {children}
            </a>
          </video>
        );
      }
      // Model output is untrusted: never open a link with the opener intact.
      return (
        <a href={href} target="_blank" rel="noopener noreferrer nofollow">
          {children}
        </a>
      );
    },
    table: ({ children }) => (
      <div className="md-table">
        <table>{children}</table>
      </div>
    ),
  };
}

function isMediaVideoUrl(href: string): boolean {
  const path = href.split("?")[0]?.toLowerCase() ?? "";
  return path.endsWith(".mp4") || path.endsWith(".webm") || path.endsWith(".mov");
}

/**
 * Renders model output as Markdown.
 *
 * Raw HTML is deliberately not enabled (no rehype-raw): the content comes from
 * a model and must not be able to inject markup. react-markdown also strips
 * dangerous URL schemes from links by default.
 */
export function Markdown({ children, streaming = false }: { children: string; streaming?: boolean }) {
  const components = useMemo(() => buildComponents(streaming), [streaming]);
  return (
    <div className="md">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
