import { ArrowSquareOut } from "@phosphor-icons/react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { api } from "../../api/client";
import type { IssueDetail, Me } from "../../api/cloud";
import type { CaseFile } from "../../api/generated";
import { Button, LinkButton } from "../../components/Button";
import cs from "../../components/CaseFile.module.css";
import { CaseFileView } from "../../components/CaseFileView";
import {
  CopyButton,
  ErrorNotice,
  Field,
  Loading,
  Notice,
  kvClass,
  selectClass,
} from "../../components/Common";
import { CertaintyMarker, IncidentStatus } from "../../components/Markers";
import { PageHead } from "../../components/Shells";
import { when } from "../../lib/time";
import { useApi } from "../../lib/useApi";
import p from "../page.module.css";

export function Issue({ me }: { me: Me }) {
  const { pid, iid } = useParams();
  const issue = useApi<IssueDetail>(`/api/v1/projects/${pid}/issues/${iid}`);
  const [err, setErr] = useState<unknown>(null);
  if (issue.error) return <ErrorNotice error={issue.error} />;
  if (!issue.data) return <Loading what="issue" />;
  const d = issue.data;
  const t = d.triage;
  const exc = d.events.find((e) => e.payload.exception)?.payload.exception;
  const frames = exc?.frames ?? [];
  const canEdit = me.org.role !== "viewer";
  return (
    <div className={p.stack}>
      <p className={p.small}>
        <Link to={`/app/projects/${pid}`}>Back to production errors</Link>
      </p>
      <PageHead title={d.title} />
      <div className={cs.meta}>
        <span>FS-{d.id}</span>
        <span>{d.event_count} events</span>
        <span>first seen {when(d.first_seen_at)}</span>
        <span>last seen {when(d.last_seen_at)}</span>
        <span>{d.environment}</span>
        {d.last_release ? <span>release {d.last_release}</span> : null}
        <IncidentStatus status={d.status} />
      </div>
      <ErrorNotice error={err} />
      <div className={p.two}>
        <div className={p.wide}>
          <section className={p.section}>
            <h2>Triage</h2>
            {t ? (
              <>
                <p>
                  <CertaintyMarker value={t.certainty} /> {t.summary}
                </p>
                {t.location ? (
                  <p>
                    Likely location:{" "}
                    <code>
                      {t.location.file_path}:{t.location.line}
                    </code>
                    {t.location.function ? (
                      <>
                        {" "}
                        in <code>{t.location.function}</code>
                      </>
                    ) : null}
                    . From the captured traceback only.
                  </p>
                ) : null}
                <p className={p.small}>
                  Not available to the cloud: {t.missing.join(", ")}. For a ranked case file with code
                  evidence, reproduce it locally under faultsage watch.
                </p>
              </>
            ) : (
              <p>Not triaged yet.</p>
            )}
            {canEdit ? (
              <div className={p.row}>
                {t?.github_issue_url ? (
                  <LinkButton to={t.github_issue_url}>
                    Open GitHub issue <ArrowSquareOut size={16} aria-hidden="true" />
                  </LinkButton>
                ) : null}
                <Button
                  kind={t?.github_issue_url ? "text" : "primary"}
                  onClick={async () => {
                    try {
                      await api(`/api/v1/projects/${pid}/issues/${iid}/triage`, { method: "POST" });
                      issue.reload();
                    } catch (e) {
                      setErr(e);
                    }
                  }}
                >
                  Run triage again
                </Button>
              </div>
            ) : null}
          </section>
          {t?.draft_test ? (
            <section className={p.section}>
              <h2>Draft regression test</h2>
              <pre className={cs.diff} tabIndex={0}>
                {t.draft_test.replace(/^```python\n|```$/gm, "")}
              </pre>
            </section>
          ) : null}
          {t?.agent_prompt ? (
            <section className={p.section}>
              <h2>Fix request for your coding agent</h2>
              <p className={p.small}>
                Give this to your coding agent. It writes the failing test and the smallest fix as a pull
                request; you review it before merging.
              </p>
              <pre className={cs.diff} tabIndex={0}>
                {t.agent_prompt}
              </pre>
              <div>
                <CopyButton text={t.agent_prompt} label="Copy prompt" />
              </div>
            </section>
          ) : null}
          <section className={p.section}>
            <h2>Traceback</h2>
            <pre className={cs.diff} tabIndex={0}>
              {exc
                ? [
                    `${exc.type}: ${exc.message ?? ""}`,
                    ...frames.map(
                      (f) =>
                        `  File "${f.file_path}", line ${f.line ?? "?"}, in ${f.function}${f.is_project ? "" : "  (library)"}${f.code ? `\n    ${f.code}` : ""}`,
                    ),
                  ].join("\n")
                : (d.events[0]?.payload.message ?? "No traceback captured.")}
            </pre>
          </section>
        </div>
        <aside className={p.narrow}>
          {canEdit ? (
            <Field label="Status">
              {(id) => (
                <select
                  id={id}
                  className={selectClass}
                  value={d.status === "reopened" ? "open" : d.status}
                  onChange={async (e) => {
                    try {
                      await api(`/api/v1/projects/${pid}/issues/${iid}/status`, {
                        method: "PUT",
                        json: { status: e.target.value },
                      });
                      issue.reload();
                    } catch (x) {
                      setErr(x);
                    }
                  }}
                >
                  {["open", "triaged", "fix_in_review", "resolved", "ignored"].map((s) => (
                    <option key={s} value={s}>
                      {s.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          ) : null}
          {d.status === "reopened" ? (
            <Notice tone="warn">This was resolved, then happened again.</Notice>
          ) : null}
          <section className={p.section}>
            <h2>Where it happens</h2>
            <dl className={kvClass}>
              <dt>Releases</dt>
              <dd>
                {Object.entries(t?.releases ?? {})
                  .map(([k, v]) => `${k} (${v})`)
                  .join(", ") || "-"}
              </dd>
              <dt>Environments</dt>
              <dd>
                {Object.entries(t?.environments ?? {})
                  .map(([k, v]) => `${k} (${v})`)
                  .join(", ") || "-"}
              </dd>
            </dl>
          </section>
          <section className={p.section}>
            <h2>Recent events</h2>
            <ol className={cs.timeline}>
              {d.events.map((e) => (
                <li key={e.id}>
                  <time dateTime={e.received_at}>{when(e.received_at)}</time>
                  <span>
                    {e.payload.server_name || "unknown host"}
                    {e.payload.release ? `, ${e.payload.release}` : ""}
                  </span>
                </li>
              ))}
            </ol>
          </section>
        </aside>
      </div>
    </div>
  );
}

export function CloudCaseFile() {
  const { pid, cid } = useParams();
  const cf = useApi<{ payload: CaseFile; updated_at: string }>(`/api/v1/projects/${pid}/case-files/${cid}`);
  if (cf.error) return <ErrorNotice error={cf.error} />;
  if (!cf.data) return <Loading what="case file" />;
  return (
    <div className={p.stack}>
      <p className={p.small}>
        <Link to={`/app/projects/${pid}?tab=case-files`}>Back to case files</Link>
      </p>
      <CaseFileView
        cf={cf.data.payload}
        graph={null}
        extraHead={
          <Notice tone="info">
            Synced from the CLI {when(cf.data.updated_at)}. Apply patches and verify in your local dashboard;
            the cloud never changes your files.
          </Notice>
        }
      />
    </div>
  );
}
