import type { ReactNode } from "react";
import type { CaseFile, Graph, Suggestion } from "../api/generated";
import { when } from "../lib/time";
import s from "./CaseFile.module.css";
import { ClaimRow, CodeExcerpt, PatchDiff, Timeline } from "./CaseParts";
import { Command, Notice } from "./Common";
import { DataTable } from "./DataTable";
import { IncidentStatus } from "./Markers";
import { PropagationGraph } from "./PropagationGraph";

interface Props {
  cf: CaseFile;
  graph?: Graph | null;
  actions?: (s: Suggestion | undefined) => ReactNode;
  verifyPanel?: ReactNode;
  extraHead?: ReactNode;
}

/** UI brief 4.3. Left 7 columns: what failed, causes, code, fix. Right 5: graph, affected, timeline. */
export function CaseFileView({ cf, graph, actions, verifyPanel, extraHead }: Props) {
  // graph === null marks a case file synced to the cloud: code and patches stayed on the machine.
  const synced = graph === null;
  const hyps = cf.hypotheses ?? [];
  const top = hyps[0];
  const unknown = !top || top.certainty === "unknown";
  const sug =
    (cf.suggestions ?? []).find((x) => x.state === "proposed" || x.state === "applied") ??
    cf.suggestions?.[0];
  const rs = cf.raise_site;
  const exc = cf.exception;
  const untrained = top?.weights_version === "untrained";
  return (
    <article className={s.grid}>
      <header className={s.head}>
        <h1 className={s.headline}>{cf.title}</h1>
        <div className={s.meta}>
          <span>I-{cf.incident_id}</span>
          {cf.failing_tests?.[0] ? <span>{cf.failing_tests[0]}</span> : null}
          {rs ? (
            <span>
              {rs.available ? `${rs.file_path}:${rs.line}` : `${rs.file_path} (line not available)`}
            </span>
          ) : null}
          <span>first seen {when(cf.first_seen_at)}</span>
          <span>
            {cf.occurrence_count} occurrence{cf.occurrence_count === 1 ? "" : "s"}
          </span>
          <IncidentStatus status={cf.status} />
        </div>
        {extraHead}
        {cf.analysis_error ? <Notice tone="warn">{cf.analysis_error}</Notice> : null}
      </header>

      <div className={s.left}>
        <section className={s.section} aria-labelledby="what-failed">
          <h2 id="what-failed">What failed</h2>
          {exc ? (
            <p>
              <code>
                {exc.type}
                {exc.message ? `: ${exc.message.split("\n")[0]}` : ""}
              </code>
              {rs?.available ? (
                <>
                  {" "}
                  raised at{" "}
                  <code>
                    {rs.file_path}:{rs.line}
                  </code>
                  {rs.function ? (
                    <>
                      {" "}
                      in <code>{rs.function}</code>
                    </>
                  ) : null}
                  .
                </>
              ) : null}{" "}
              Confirmed: this is what the run reported.
            </p>
          ) : (
            <p>The run failed without a Python traceback. See the timeline for the command and exit code.</p>
          )}
        </section>

        <section className={s.section} aria-labelledby="causes">
          <h2 id="causes">Likely causes</h2>
          {unknown ? (
            <Notice
              tone="warn"
              next={
                cf.missing_evidence?.includes("coverage data")
                  ? "Run pytest --cov=. --cov-context=test and set coverage_contexts = true to add coverage evidence."
                  : undefined
              }
            >
              We do not have enough evidence to rank causes. Missing:{" "}
              {(cf.missing_evidence ?? []).join(", ") || "evidence"}.
            </Notice>
          ) : null}
          {hyps.length > 0 && !(unknown && hyps.length === 1) ? (
            <ol className={s.claims}>
              {hyps.slice(0, 5).map((h) => (
                <ClaimRow key={h.rank} h={h} />
              ))}
            </ol>
          ) : null}
          {untrained ? (
            <p className={s.meta}>
              Ranking weights are untrained: hand-set until the first benchmark training run.
            </p>
          ) : null}
        </section>

        {top?.location && !synced ? (
          <section className={s.section} aria-labelledby="code">
            <h2 id="code">Code at the top cause</h2>
            <CodeExcerpt loc={top.location} />
          </section>
        ) : null}

        <section className={s.section} aria-labelledby="fix">
          <h2 id="fix">Suggested fix</h2>
          {sug ? (
            <>
              <p className={s.explain}>{sug.explanation}</p>
              {sug.state === "stale" ? (
                <Notice tone="warn">
                  File changed since this suggestion was made. Regenerate suggestion.
                </Notice>
              ) : null}
              {sug.patch_diff ? (
                <PatchDiff diff={sug.patch_diff} />
              ) : synced ? (
                <p>
                  The patch and the code it changes stay on your machine. Open this case file in your local
                  dashboard to review and apply it.
                </p>
              ) : (
                <p>No safe patch for this failure. Follow the explanation above.</p>
              )}
              {sug.verify_command ? <Command text={sug.verify_command} /> : null}
            </>
          ) : (
            <p>No rule matched this failure. Read the causes above; FaultSage does not guess a fix.</p>
          )}
          {actions ? <div className={s.actions}>{actions(sug)}</div> : null}
          {verifyPanel}
        </section>
      </div>

      <aside className={s.right} aria-label="Impact">
        {graph !== undefined ? (
          <section className={s.section} aria-labelledby="graph">
            <h2 id="graph">Propagation</h2>
            {graph ? (
              <PropagationGraph graph={graph} />
            ) : (
              <p>Graph not available for synced case files. Open it in your local dashboard.</p>
            )}
          </section>
        ) : null}
        <section className={s.section} aria-labelledby="affected">
          <h2 id="affected">Affected</h2>
          <DataTable
            label="Affected components"
            columns={[
              { key: "name", header: "Name", kind: "mono", render: (r) => r.name, sortValue: (r) => r.name },
              { key: "kind", header: "Kind", render: (r) => r.kind },
              { key: "relation", header: "Relation", render: (r) => r.relation, sortValue: (r) => r.depth },
              { key: "basis", header: "Basis", render: (r) => r.basis },
            ]}
            rows={cf.impacts ?? []}
            rowKey={(r) => `${r.kind}:${r.name}`}
            empty="Nothing downstream depends on the suspected location."
          />
        </section>
        <section className={s.section} aria-labelledby="timeline">
          <h2 id="timeline">Timeline</h2>
          <Timeline entries={cf.timeline ?? []} />
        </section>
      </aside>
    </article>
  );
}
