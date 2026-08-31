import { useLayoutEffect, useRef, useState } from "react";

interface Props {
  onSend: (text: string) => void;
  onStop: () => void;
  busy: boolean;
  maxChars: number;
  /** A suggestion to drop into the box. The counter makes picking the same
   *  suggestion twice register as a new request. */
  seed: { text: string; nonce: number } | null;
}

const MAX_HEIGHT = 200;

export function Composer({ onSend, onStop, busy, maxChars, seed }: Props) {
  const [value, setValue] = useState("");
  const box = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    if (seed) setValue(seed.text);
  }, [seed]);

  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
  }, [value]);

  const trimmed = value.trim();
  const tooLong = value.length > maxChars;
  const canSend = Boolean(trimmed) && !busy && !tooLong;

  function submit() {
    if (!canSend) return;
    onSend(trimmed);
    setValue("");
  }

  return (
    <div className="composer-wrap">
      {tooLong && (
        <p className="alert" role="alert">
          <strong>Слишком длинно.</strong> {value.length.toLocaleString()} из{" "}
          {maxChars.toLocaleString()} символов.
        </p>
      )}

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <textarea
          ref={box}
          rows={1}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            // Enter sends, Shift+Enter breaks the line. isComposing guards IME
            // input, where Enter commits a candidate rather than a message.
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="Напишите сообщение…"
          aria-label="Сообщение"
        />

        {busy ? (
          <button
            type="button"
            className="icon-button"
            data-variant="stop"
            onClick={onStop}
            aria-label="Остановить генерацию"
            title="Остановить генерацию"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
              <rect width="12" height="12" rx="2.5" fill="currentColor" />
            </svg>
          </button>
        ) : (
          <button
            type="submit"
            className="icon-button"
            disabled={!canSend}
            aria-label="Отправить сообщение"
            title="Отправить"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M12 20V5m0 0-6 6m6-6 6 6"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        )}
      </form>

      <p className="hint">
        <kbd>Enter</kbd> — отправить · <kbd>Shift</kbd>+<kbd>Enter</kbd> — новая строка
      </p>
    </div>
  );
}
