import type { RagDocumentDto, RagToolTurn } from "../types";

interface Props {
  turn: RagToolTurn;
}

function DocRow({ doc }: { doc: RagDocumentDto }) {
  return (
    <li>
      <strong>{doc.title || doc.source}</strong>
      <span className="rag-sources-meta">
        {" "}
        · {doc.chunk_count} чанк.
        {doc.scope ? ` · ${doc.scope}` : ""}
        {doc.strategy ? ` · ${doc.strategy}` : ""}
      </span>
      {doc.preview ? <pre>{doc.preview}</pre> : null}
    </li>
  );
}

/** Expandable tool card in the chat thread (ingest / list documents). */
export function RagToolCard({ turn }: Props) {
  return (
    <details
      className="rag-tool-call"
      data-tool={turn.tool}
      open={turn.open ?? true}
    >
      <summary>
        <code>{turn.tool}</code> · {turn.title}
      </summary>
      <p className="rag-tool-call-summary">{turn.summary}</p>
      {turn.preview ? <pre className="rag-tool-call-preview">{turn.preview}</pre> : null}
      {turn.documents && turn.documents.length > 0 ? (
        <ul className="rag-tool-call-docs">
          {turn.documents.map((doc) => (
            <DocRow key={`${doc.scope}:${doc.owner_id}:${doc.source}`} doc={doc} />
          ))}
        </ul>
      ) : null}
    </details>
  );
}
