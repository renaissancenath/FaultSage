import { useNavigate } from "react-router";
import type { IncidentSummary } from "../../api/generated";
import { LinkButton } from "../../components/Button";
import { EmptyState, ErrorNotice, Loading, kvClass } from "../../components/Common";
import { DataTable } from "../../components/DataTable";
import { CertaintyMarker, IncidentStatus, StatusMarker } from "../../components/Markers";
import { type LocalStatus, PageHead, statusSentence } from "../../components/Shells";
import { when } from "../../lib/time";
import { useApi } from "../../lib/useApi";
import p from "../page.module.css";

export function Overview({ status, version }: { status: LocalStatus | null; version: number }) {
  const nav = useNavigate();
  const inc = useApi<{ items: IncidentSummary[] }>("/api/incidents?status=open_any&limit=10", [version]);
  const runs = useApi<{ at: string; command: string; exit_code: number }[]>("/api/runs", [version]);
  const first = inc.data?.items[0];
  return (
    <div className={p.stack}>
      <PageHead title={status ? (statusSentence(status).split(".")[0] ?? "Overview") : "Overview"}>
        {status ? <p className={p.lede}>{statusSentence(status).split(". ").slice(1).join(". ")}</p> : null}
      </PageHead>
      {first ? (
        <div>
          <LinkButton to={`/incidents/${first.id}`}>Open case file</LinkButton>
        </div>
      ) : null}
      <div className={p.two}>
        <section className={`${p.wide} ${p.section}`} aria-labelledby="open">
          <h2 id="open">Open incidents</h2>
          <ErrorNotice error={inc.error} />
          {inc.loading && !inc.data ? (
            <Loading what="incidents" />
          ) : (
            <DataTable
              label="Open incidents"
              rows={inc.data?.items ?? []}
              rowKey={(r) => r.id}
              onOpen={(r) => nav(`/incidents/${r.id}`)}
              empty={
                <EmptyState command="pytest">
                  No open incidents. Run pytest while faultsage watch is running.
                </EmptyState>
              }
              columns={[
                { key: "id", header: "ID", kind: "mono", render: (r) => `I-${r.id}` },
                { key: "title", header: "What failed", render: (r) => r.title },
                { key: "status", header: "Status", render: (r) => <IncidentStatus status={r.status} /> },
                {
                  key: "cert",
                  header: "Top cause",
                  render: (r) => <CertaintyMarker value={r.top_certainty} />,
                },
                { key: "last", header: "Last seen", kind: "mono", render: (r) => when(r.last_seen_at) },
              ]}
            />
          )}
          {(inc.data?.items.length ?? 0) >= 10 ? (
            <LinkButton kind="text" to="/incidents">
              All incidents
            </LinkButton>
          ) : null}
        </section>
        <section className={`${p.narrow} ${p.section}`} aria-labelledby="facts">
          <h2 id="facts">Project</h2>
          {status ? (
            <dl className={kvClass}>
              <dt>Root</dt>
              <dd>{status.root}</dd>
              <dt>Python</dt>
              <dd>{status.python}</dd>
              <dt>Test files</dt>
              <dd>{status.tests_found}</dd>
              <dt>Git</dt>
              <dd>
                {status.git.head ? `${status.git.branch} @ ${status.git.head}` : "not a git repository"}
              </dd>
              <dt>Ranking weights</dt>
              <dd>{status.weights}</dd>
              <dt>Cloud sync</dt>
              <dd>{status.cloud.enabled ? "on" : "off"}</dd>
            </dl>
          ) : (
            <Loading what="project facts" />
          )}
          <h2>Last runs</h2>
          <DataTable
            label="Last runs"
            rows={runs.data ?? []}
            rowKey={(r) => r.at + r.command}
            empty="No failed faultsage run commands yet."
            columns={[
              { key: "cmd", header: "Command", kind: "mono", render: (r) => r.command },
              {
                key: "res",
                header: "Result",
                render: (r) => (
                  <StatusMarker
                    value={r.exit_code === 0 ? "passed" : "failed"}
                    label={r.exit_code === 0 ? "passed" : `exit ${r.exit_code}`}
                  />
                ),
              },
              { key: "at", header: "When", kind: "mono", render: (r) => when(r.at) },
            ]}
          />
        </section>
      </div>
    </div>
  );
}
