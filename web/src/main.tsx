import "@xyflow/react/dist/base.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { applyTheme } from "./lib/theme";
import "./styles/global.css";

applyTheme();
window.matchMedia?.("(prefers-color-scheme: dark)").addEventListener?.("change", () => applyTheme());
const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
