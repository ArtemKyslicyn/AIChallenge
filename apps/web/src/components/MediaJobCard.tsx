import { useEffect, useState } from "react";

import type { MediaJobState } from "../types";

export type { MediaJobKind, MediaJobState } from "../types";

function formatElapsed(ms: number): string {
  const sec = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m > 0 ? `${m}:${String(s).padStart(2, "0")}` : `${s} с`;
}

interface Props {
  job: MediaJobState;
  compact?: boolean;
}

export function MediaJobCard({ job, compact = false }: Props) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (job.phase !== "running") return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [job.phase, job.startedAt]);

  const elapsed = formatElapsed(now - job.startedAt);
  const isVideo = job.kind === "video";
  const isComic = job.kind === "comic";
  const title =
    job.phase === "error"
      ? isVideo
        ? "Видео не удалось"
        : isComic
          ? "Комикс не удался"
          : "Картинка не удалась"
      : job.phase === "done"
        ? isVideo
          ? "Видео готово"
          : isComic
            ? "Комикс готов"
            : "Картинка готова"
        : isVideo
          ? "Генерирую видео"
          : isComic
            ? "Собираю комикс"
            : "Генерирую картинку";

  const hint =
    job.phase === "running"
      ? isVideo
        ? "Джоба Pixazo в очереди — обычно 1–3 минуты"
        : isComic
          ? "Раскадровка, потом панели Pollinations"
          : "Pollinations рисует — обычно 10–40 секунд"
      : job.phase === "error"
        ? job.error || "Ошибка генерации"
        : job.providerLabel || "Можно смотреть ниже";

  return (
    <div
      className={`media-job${compact ? " media-job--compact" : ""} media-job--${job.phase} media-job--${job.kind}`}
      role="status"
      aria-live="polite"
      aria-busy={job.phase === "running"}
    >
      <div className="media-job-visual" aria-hidden="true">
        {job.phase === "running" ? (
          <span className="media-job-spinner" />
        ) : job.phase === "error" ? (
          <span className="media-job-mark">!</span>
        ) : (
          <span className="media-job-mark">✓</span>
        )}
      </div>
      <div className="media-job-copy">
        <p className="media-job-title">{title}</p>
        <p className="media-job-hint">{hint}</p>
      </div>
      {job.phase === "running" && (
        <time className="media-job-elapsed" dateTime={`PT${Math.floor((now - job.startedAt) / 1000)}S`}>
          {elapsed}
        </time>
      )}
    </div>
  );
}
