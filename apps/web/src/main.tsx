import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App.tsx";
import "./index.css";

const apiBase = import.meta.env.VITE_API_URL || "/api/v1";
void fetch(`${apiBase}/health`)
  .then((r) => (r.ok ? r.json() : null))
  .then((h: { build?: string; source?: string } | null) => {
    const build = h?.build || import.meta.env.VITE_BUILD_ID || "dev";
    const source = h?.source || "local-mac";
    console.info(`[AIChallenge] build ${build} · ${source}`);
  })
  .catch(() => {
    console.info(`[AIChallenge] build ${import.meta.env.VITE_BUILD_ID || "dev"} · local-mac`);
  });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
