export function relative(iso: string, now: number = Date.now()): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 60) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h} h ago`;
  return `${Math.round(h / 24)} days ago`;
}

/** "14:02 (5 min ago)" in the user's local time (UI brief section 5). */
export function when(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const sameDay = new Date().toDateString() === d.toDateString();
  const clock = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const date = sameDay ? clock : `${d.toLocaleDateString([], { day: "numeric", month: "short" })} ${clock}`;
  return `${date} (${relative(iso)})`;
}

export function count(n: number, word: string): string {
  return `${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`;
}
