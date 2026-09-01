import { useEffect, useId, useState } from "react";

/**
 * Renders a mermaid diagram from its source.
 *
 * The library is imported dynamically: it is by far the heaviest dependency
 * here, and most conversations never contain a diagram. Vite splits it into its
 * own chunk that is fetched the first time one appears.
 */
export function Mermaid({ code }: { code: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const id = useId().replace(/[^a-zA-Z0-9]/g, "");

  useEffect(() => {
    let cancelled = false;

    async function draw() {
      try {
        const mermaid = (await import("mermaid")).default;
        const dark = window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
        mermaid.initialize({
          startOnLoad: false,
          // The source comes from a model, so let mermaid sanitise its output.
          securityLevel: "strict",
          theme: dark ? "dark" : "default",
          fontFamily: "inherit",
        });
        const { svg: rendered } = await mermaid.render(`d${id}`, code);
        if (!cancelled) {
          setSvg(rendered);
          setFailed(false);
        }
      } catch {
        // A model can emit invalid mermaid. That is not a page error — fall
        // back to showing the source, which is still useful to the reader.
        if (!cancelled) setFailed(true);
      }
    }

    void draw();
    return () => {
      cancelled = true;
    };
  }, [code, id]);

  if (failed) {
    return (
      <div className="md-code" data-kind="mermaid-source">
        <div className="md-code-bar">
          <span className="md-code-lang">mermaid</span>
          <span className="md-code-lang">диаграмму не удалось построить</span>
        </div>
        <pre>
          <code>{code}</code>
        </pre>
      </div>
    );
  }

  if (svg === null) {
    return <p className="md-mermaid-pending">Строим диаграмму…</p>;
  }

  // Mermaid returns SVG markup; it is sanitised by securityLevel: "strict".
  return <div className="md-mermaid" dangerouslySetInnerHTML={{ __html: svg }} />;
}
