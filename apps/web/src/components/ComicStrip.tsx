import type { ComicCharacter, ComicPanelState, ComicStripState } from "../comic";

function speakerName(characters: ComicCharacter[], speaker: string | null | undefined): string {
  if (!speaker) return "";
  const hit = characters.find((c) => c.id === speaker || c.name === speaker);
  return hit?.name || speaker;
}

function PanelCard({
  panel,
  characters,
}: {
  panel: ComicPanelState;
  characters: ComicCharacter[];
}) {
  const who = speakerName(characters, panel.speaker);
  const showBubble =
    (panel.text_mode === "bubble" || panel.text_mode === "both") && Boolean(panel.dialogue);
  const showCaption =
    (panel.text_mode === "caption" || panel.text_mode === "both" || !showBubble) &&
    Boolean(panel.caption || (!showBubble && panel.dialogue));
  const captionText = panel.caption || (!showBubble ? panel.dialogue : null);

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
        {showBubble && panel.dialogue ? (
          <div className="comic-bubble">
            {who ? <span className="comic-bubble-who">{who}</span> : null}
            <p>{panel.dialogue}</p>
          </div>
        ) : null}
      </div>
      {showCaption && captionText ? (
        <figcaption className="comic-caption">
          {who && !showBubble ? <strong>{who}: </strong> : null}
          {captionText}
        </figcaption>
      ) : null}
      {panel.status === "error" && panel.error ? (
        <p className="comic-panel-error">{panel.error}</p>
      ) : null}
    </figure>
  );
}

export function ComicStrip({ comic }: { comic: ComicStripState }) {
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
