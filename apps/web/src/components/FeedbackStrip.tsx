import { useCallback, useEffect, useRef, useState } from "react";

import {
  deleteMessageFeedback,
  postMessageFeedback,
  type FeedbackValue,
  type SessionCredentials,
} from "../api/client";

/**
 * «Полезно» / «Не полезно» under a finished assistant turn.
 *
 * Mounted by `Turn.tsx` only for an assistant turn that already has a server
 * `messageId` and is not streaming (prep D10) — that absence is the checklist's
 * H5 «no feedback mid-stream», so no disabled placeholder is rendered either.
 *
 * Clicking the pressed thumb takes the vote back (design spec §3 «повторный
 * клик переключает», resolved as retract) — that is what `aria-pressed`
 * already tells assistive technology, so the behaviour matches the promise
 * rather than the promise being weakened.
 *
 * All copy comes verbatim from
 * `docs/superpowers/specs/2026-09-03-lab-observability-ux-checklist.md`.
 */
const COPY = {
  group: "Оценка ответа",
  up: "Полезно",
  down: "Не полезно",
  thanks: "Спасибо",
  error: "Не удалось сохранить оценку",
} as const;

/** Design spec §3: «Спасибо» is a 1.2s inline confirmation, not a toast. */
const THANKS_MS = 1200;

const VALUES: { value: FeedbackValue; icon: string; label: string }[] = [
  { value: "up", icon: "👍", label: COPY.up },
  { value: "down", icon: "👎", label: COPY.down },
];

export interface FeedbackStripProps {
  /** Session that owns the message — its token authorises the vote (prep D6). */
  session: SessionCredentials;
  /** Real server message id; the strip is never rendered without one. */
  messageId: string;
  /** Vote already stored on the server, so a reload shows what was cast. */
  initialValue?: FeedbackValue | null;
}

export function FeedbackStrip({ session, messageId, initialValue = null }: FeedbackStripProps) {
  const [value, setValue] = useState<FeedbackValue | null>(initialValue);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);
  const [thanks, setThanks] = useState(false);

  /** Only the newest click may settle — a fast re-vote must not be overwritten. */
  const ticket = useRef(0);
  const thanksTimer = useRef<number | null>(null);
  const live = useRef(true);

  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
      if (thanksTimer.current !== null) window.clearTimeout(thanksTimer.current);
      thanksTimer.current = null;
    };
  }, []);

  const vote = useCallback(
    (clicked: FeedbackValue) => {
      // Gate here rather than with `disabled`: disabling the button the user
      // just pressed blurs it, and the browser hands focus to <body>.
      if (pending) return;
      const previous = value;
      // Pressing the pressed thumb retracts; the other one still switches.
      // `aria-pressed` says these buttons can be un-pressed, so they must be —
      // otherwise a mis-click is permanent and the promise is a lie.
      const next = previous === clicked ? null : clicked;
      const mine = ++ticket.current;

      // Optimistic: `aria-pressed` moves before the request, and rolls back below.
      setValue(next);
      setPending(true);
      setFailed(false);
      setThanks(false);
      if (thanksTimer.current !== null) {
        window.clearTimeout(thanksTimer.current);
        thanksTimer.current = null;
      }

      const sent =
        next === null
          ? deleteMessageFeedback(session, messageId)
          : postMessageFeedback(session, messageId, next);

      sent
        .then(() => {
          if (!live.current || mine !== ticket.current) return;
          setPending(false);
          // No «Спасибо» for a retraction — thanking someone for withdrawing
          // their opinion reads as a shrug, and the empty thumbs are already
          // the confirmation. The live region just goes quiet.
          if (next === null) return;
          setThanks(true);
          thanksTimer.current = window.setTimeout(() => {
            thanksTimer.current = null;
            if (live.current) setThanks(false);
          }, THANKS_MS);
        })
        .catch(() => {
          if (!live.current || mine !== ticket.current) return;
          // Feedback lives entirely inside this strip: a failing API rolls the
          // toggle back and states it here, never touching the chat thread.
          setPending(false);
          setValue(previous);
          setFailed(true);
        });
    },
    [session, messageId, value, pending],
  );

  return (
    // Named group: tabbing a long thread otherwise reads as an undifferentiated
    // stream of «Полезно / Не полезно» with nothing to tie a pair to its answer.
    <div className="feedback-strip" role="group" aria-label={COPY.group}>
      {VALUES.map((item) => (
        <button
          key={item.value}
          type="button"
          className="feedback-strip-button"
          data-value={item.value}
          aria-pressed={value === item.value}
          /* `aria-disabled`, never `disabled` — it announces the in-flight
             state without taking focus off the button that is in flight. */
          aria-disabled={pending || undefined}
          onClick={() => vote(item.value)}
        >
          <span aria-hidden="true">{item.icon}</span>
          <span className="sr-only">{item.label}</span>
        </button>
      ))}

      {/* One polite region: «Спасибо» on success, the error text on failure. */}
      <span className="feedback-strip-note" role="status" aria-live="polite">
        {thanks ? COPY.thanks : ""}
      </span>
      {failed && (
        <span className="feedback-strip-error" role="alert">
          {COPY.error}
        </span>
      )}
    </div>
  );
}
