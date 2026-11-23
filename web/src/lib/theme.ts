export type Theme = "light" | "dark" | "system";
const KEY = "faultsage-theme";

export function storedTheme(): Theme {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

export function applyTheme(t: Theme = storedTheme()): void {
  const dark =
    t === "dark" || (t === "system" && window.matchMedia?.("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

export function setTheme(t: Theme): void {
  try {
    if (t === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, t);
  } catch {
    /* private mode: theme still applies for this page */
  }
  applyTheme(t);
}
