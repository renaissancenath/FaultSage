import s from "./Markers.module.css";

export type Certainty = "confirmed" | "strong" | "possible" | "unknown";
const LABEL: Record<Certainty, string> = {
  confirmed: "Confirmed",
  strong: "Strong",
  possible: "Possible",
  unknown: "Unknown",
};

/** Confirmed: filled square. Strong: half fill. Possible: outline. Unknown: dashed outline. Always with the word. */
export function CertaintyMarker({ value }: { value: Certainty | string | null | undefined }) {
  const v = (value ?? "unknown") as Certainty;
  const cls = v === "strong" ? s.strongHalf : s[v];
  return (
    <span className={s.marker}>
      <span className={`${s.shape} ${cls}`} aria-hidden="true" />
      <span className={s.word}>{LABEL[v] ?? "Unknown"}</span>
    </span>
  );
}

export type Status = "passed" | "failed" | "warning" | "not_run";

/** Passed: filled circle. Failed: filled square in signal. Warning: triangle. Not run: outline circle. */
export function StatusMarker({ value, label }: { value: Status; label?: string }) {
  const word = label ?? { passed: "passed", failed: "failed", warning: "warning", not_run: "not run" }[value];
  if (value === "warning") {
    return (
      <span className={s.marker}>
        <span className={s.warnShape} aria-hidden="true" />
        <span className={`${s.word} ${s.warnWord}`}>{word}</span>
      </span>
    );
  }
  const shape =
    value === "passed"
      ? `${s.circle} ${s.passed}`
      : value === "failed"
        ? s.failed
        : `${s.circle} ${s.notRun}`;
  const wordCls = value === "passed" ? s.okWord : value === "failed" ? s.failWord : "";
  return (
    <span className={s.marker}>
      <span className={`${s.shape} ${shape}`} aria-hidden="true" />
      <span className={`${s.word} ${wordCls}`}>{word}</span>
    </span>
  );
}

const INCIDENT_STATUS: Record<string, Status> = {
  open: "failed",
  investigating: "failed",
  reopened: "failed",
  fix_proposed: "warning",
  fix_applied: "warning",
  triaged: "warning",
  fix_in_review: "warning",
  verified: "passed",
  resolved: "passed",
  dismissed: "not_run",
  ignored: "not_run",
};

export function IncidentStatus({ status }: { status: string }) {
  return <StatusMarker value={INCIDENT_STATUS[status] ?? "not_run"} label={status.replaceAll("_", " ")} />;
}
