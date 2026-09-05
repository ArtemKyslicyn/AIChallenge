import type { ComicCharacter, ComicPanelState, ComicStripState } from "../comic";

function speakerName(characters: ComicCharacter[], speaker: string | null | undefined): string {
  if (!speaker) return "";
  const hit = characters.find((c) => c.id === speaker || c.name === speaker);
  return hit?.name || speaker;
}

function OverlayCopy({
  panel,
  characters,
}: {
  panel: ComicPanelState;
  characters: ComicCharacter[];
}) {
  const who = speakerName(characters, panel.speaker);
  const showBubble =
    Boolean(panel.dialogue) &&
    (panel.text_mode === "bubble" ||
      panel.text_mode === "both" ||
      (!panel.caption && panel.text_mode !== "caption"));
  const showCaption =
    Boolean(panel.caption) &&
    (panel.text_mode === "caption" || panel.text_mode === "both" || !showBubble);
  const captionText = panel.caption || (!showBubble ? panel.dialogue : null);

  return (
    <>
      {showBubble && panel.dialogue ? (
        <div className="comic-bubble">
          {who ? <span className="comic-bubble-who">{who}</span> : null}
          <p>{panel.dialogue}</p>
        </div>
      ) : null}
      {showCaption && captionText ? (
        <div className="comic-caption comic-caption--overlay">
          {who && !showBubble ? <strong>{who}: </strong> : null}
          {captionText}
        </div>
      ) : null}
    </>
  );
}

function PanelCard({
  panel,
  characters,
}: {
  panel: ComicPanelState;
  characters: ComicCharacter[];
}) {
  return (
    <figure className={`comic-panel comic-panel--${panel.status}`}>
      <div className="comic-panel-art">
        {panel.status === "ok" && panel.image_url ? (
          <img src={panel.image_url} alt={`Панель ${panel.index}`} loading="lazy" />
        ) : panel.status === "error" ? (
          <div className="comic-panel-fallback">панель не сгенерировалась</div>
        ) : (
          <div className="comic-panel-skeleton" aria-hidden="true" />
        )}
        <OverlayCopy panel={panel} characters={characters} />
      </div>
      {panel.status === "error" && panel.error ? (
        <p className="comic-panel-error">{panel.error}</p>
      ) : null}
    </figure>
  );
}

function SinglePageStrip({ comic }: { comic: ComicStripState }) {
  const count = comic.panels.length || comic.panel_count;
  const n = Math.min(Math.max(count, 3), 6);
  const pageUrl =
    comic.page_image_url || comic.panels.find((p) => p.image_url)?.image_url || null;
  const pending = !pageUrl && comic.panels.some((p) => p.status === "pending");
  const failed = !pageUrl && comic.panels.every((p) => p.status === "error");

  return (
    <section
      className={`comic-strip comic-strip--page comic-strip--n${n}`}
      aria-label={comic.title || "Комикс"}
    >
      {comic.title ? <header className="comic-strip-title">{comic.title}</header> : null}
      <div className="comic-page">
        {pageUrl ? (
          <img className="comic-page-art" src={pageUrl} alt={comic.title || "Комикс"} />
        ) : failed ? (
          <div className="comic-panel-fallback">страница комикса не сгенерировалась</div>
        ) : (
          <div className={`comic-panel-skeleton${pending ? "" : ""}`} aria-hidden="true" />
        )}
        <div className="comic-page-overlays" aria-hidden={!pageUrl}>
          {comic.panels.map((panel) => (
            <div key={panel.index} className="comic-page-cell">
              <OverlayCopy panel={panel} characters={comic.characters} />
            </div>
          ))}
        </div>
      </div>
      {failed && comic.panels[0]?.error ? (
        <p className="comic-panel-error">{comic.panels[0].error}</p>
      ) : null}
    </section>
  );
}

export function ComicStrip({ comic }: { comic: ComicStripState }) {
    const layout = comic.layout || "per_panel";
  if (layout === "single_page") {
    return <SinglePageStrip comic={comic} />;
  }

  const count = comic.panels.length || comic.panel_count;
  return (
    <section
      className={`comic-strip comic-strip--n${Math.min(Math.max(count, 3), 6)}`}
      aria-label={comic.title || "Комикс"}
    >
      {comic.title ? <header className="comic-strip-title">{comic.title}</header> : null}
      <div className="comic-strip-grid">
        {comic.panels.map((panel) => (
          <PanelCard key={panel.index} panel={panel} characters={comic.characters} />
        ))}
      </div>
    </section>
  );
}
