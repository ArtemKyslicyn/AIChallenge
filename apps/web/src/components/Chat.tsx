import { useEffect, useRef, useState } from "react";

import {
  listMessages,
  sendMessageSSE,
  type ChatEvent,
  type MessageDto,
  type SessionCredentials,
} from "../api/client";

interface Bubble {
  id: string;
  role: "user" | "assistant";
  content: string;
  modelId: string | null;
  failed?: boolean;
}

function toBubble(message: MessageDto): Bubble {
  return {
    id: message.id,
    role: message.role === "assistant" ? "assistant" : "user",
    content: message.content,
    modelId: message.model_id,
  };
}

export function Chat({ session }: { session: SessionCredentials }) {
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listMessages(session)
      .then((history) => setBubbles(history.filter((m) => m.role !== "system").map(toBubble)))
      .catch((e: Error) => setError(e.message));
  }, [session]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [bubbles]);

  async function send() {
    const content = draft.trim();
    if (!content || busy) return;

    const replyId = `pending-${Date.now()}`;
    setDraft("");
    setError(null);
    setBusy(true);
    setBubbles((prev) => [
      ...prev,
      { id: `local-${Date.now()}`, role: "user", content, modelId: null },
      { id: replyId, role: "assistant", content: "", modelId: null },
    ]);

    const patch = (change: Partial<Bubble>) =>
      setBubbles((prev) => prev.map((b) => (b.id === replyId ? { ...b, ...change } : b)));

    try {
      await sendMessageSSE(session, content, (event: ChatEvent) => {
        switch (event.type) {
          case "model":
            // Shown before the first token, so the label never lags the answer.
            patch({ modelId: event.model_id });
            break;
          case "token":
            setBubbles((prev) =>
              prev.map((b) => (b.id === replyId ? { ...b, content: b.content + event.text } : b)),
            );
            break;
          case "message_end":
            patch({ content: event.content, modelId: event.model_id });
            break;
          case "error":
            patch({ failed: true });
            setError(event.message);
            break;
        }
      });
    } catch (e) {
      patch({ failed: true });
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="chat">
      <ol className="messages">
        {bubbles.map((bubble) => (
          <li key={bubble.id} className={`bubble ${bubble.role}`}>
            <p className="content">
              {bubble.content || (bubble.role === "assistant" && busy ? "…" : "")}
            </p>
            {bubble.role === "assistant" && (
              <p className="meta">
                {bubble.modelId ? `model: ${bubble.modelId}` : "model: resolving…"}
                {bubble.failed && " · interrupted"}
              </p>
            )}
          </li>
        ))}
        <div ref={bottom} />
      </ol>

      {error && <p className="error">{error}</p>}

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Type a message…"
          aria-label="Message"
          disabled={busy}
        />
        <button type="submit" disabled={busy || !draft.trim()}>
          {busy ? "Streaming…" : "Send"}
        </button>
      </form>
    </section>
  );
}
