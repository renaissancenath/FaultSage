import { useState } from "react";
import type { EvidenceItem, Hypothesis, Location, TimelineEntry } from "../api/generated";
import { when } from "../lib/time";
import { Button } from "./Button";
import s from "./CaseFile.module.css";
import { CertaintyMarker } from "./Markers";

export function ClaimRow({ h }: { h: Hypothesis }) {
  const [open, setOpen] = useState(h.rank === 1);
  const ev = h.evidence ?? [];
  return (
    <li className={s.claim}>
      <div className={s.claimHead}>
        <span className={s.rank}>{h.rank}.</span>
        <CertaintyMarker value={h.certainty} />
        <span className={s.claimText}>{h.claim}</span>
        {ev.length > 0 ? (
          <Button
            kind="text"
            className={s.evidenceToggle}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            {open ? "Hide" : "Show"} {ev.length} piece{ev.length === 1 ? "" : "s"} of evidence
          </Button>
        ) : null}
      </div>
      {open && ev.length > 0 ? (
        <ul className={s.evidence}>
          {ev.map((e, i) => (
            <Evidence key={`${e.source}-${i}`} e={e} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

const SOURCE: Record<string, string> = {
  traceback: "traceback",
  git: "git",
  checkpoint: "checkpoint",
  coverage: "coverage",
  log: "log",
  import_graph: "import graph",
  history: "history",
  scan: "code search",
};

export function Evidence({ e }: { e: EvidenceItem }) {
  return (
    <li className={s.evItem}>
      <span className={s.evSource}>{SOURCE[e.source] ?? e.source}</span>
      <span className={e.stance === "contradicts" ? s.evContra : undefined}>{e.stance}</span>
      <span className={s.evText}>{e.summary}</span>
    </li>
  );
}

/** Text only, never HTML. The root-cause line gets the wash and the 3 px signal bar. */
export function CodeExcerpt({ loc, title }: { loc: Location; title?: string }) {
  if (!loc.available || !loc.excerpt?.length) {
    return (
      <div className={s.code}>
        <div className={s.codeHead}>
          {loc.file_path}: line not available. The source is missing or changed since the failure.
        </div>
      </div>
    );
  }
  return (
    <figure className={s.code} tabIndex={0}>
      <figcaption className={s.codeHead}>
        {title ?? `${loc.file_path}:${loc.line}`}
        {loc.function ? ` in ${loc.function}` : ""}
      </figcaption>
      <table className={s.codeTable}>
        <tbody>
          {loc.excerpt.map(([n, text]) => (
            <tr
              key={n}
              className={n === loc.line ? s.hot : undefined}
              aria-current={n === loc.line ? "true" : undefined}
            >
              <td className={s.ln} aria-hidden="true">
                {n}
              </td>
              <td>{text || " "}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

export function PatchDiff({ diff }: { diff: string }) {
  return (
    <section className={s.diff} aria-label="Patch preview" tabIndex={0}>
      {diff
        .split("\n")
        .filter((l, i, a) => l || i < a.length - 1)
        .map((line, i) => {
          const cls = line.startsWith("@@")
            ? s.hunk
            : line.startsWith("+") && !line.startsWith("+++")
              ? s.add
              : line.startsWith("-") && !line.startsWith("---")
                ? s.del
                : undefined;
          return (
            // biome-ignore lint/suspicious/noArrayIndexKey: diff lines are static and ordered
            <div key={i} className={cls}>
              {line || " "}
            </div>
          );
        })}
    </section>
  );
}

export function Timeline({ entries }: { entries: TimelineEntry[] }) {
  if (!entries.length) return <p>No activity yet.</p>;
  return (
    <ol className={s.timeline}>
      {entries.map((t, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: timeline is append-only
        <li key={i}>
          <time dateTime={t.at}>{when(t.at)}</time>
          <span>{t.text}</span>
        </li>
      ))}
    </ol>
  );
}
