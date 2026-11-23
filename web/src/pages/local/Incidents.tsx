import { useState } from "react";
import { useNavigate } from "react-router";
import type { IncidentSummary } from "../../api/generated";
import { EmptyState, ErrorNotice, Field, Loading, inputClass, selectClass } from "../../components/Common";
import { DataTable } from "../../components/DataTable";
import { CertaintyMarker, IncidentStatus } from "../../components/Markers";
import { PageHead } from "../../components/Shells";
import { when } from "../../lib/time";
import { useApi } from "../../lib/useApi";
import p from "../page.module.css";

const STATUSES = [
  "",
  "open_any",
  "open",
  "fix_proposed",
  "fix_applied",
  "verified",
  "resolved",
  "reopened",
  "dismissed",
];

export function Incidents({ version }: { version: number }) {
  const nav = useNavigate();
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const qs = new URLSearchParams({ limit: "200", ...(status ? { status } : {}), ...(q ? { q } : {}) });
  const { data, error, loading } = useApi<{ items: IncidentSummary[] }>(`/api/incidents?${qs}`, [version]);
  return (
    <div className={p.stack}>
      <PageHead title="Incidents" />
      <div className={p.filters}>
        <Field label="Status">
          {(id) => (
            <select
              id={id}
              className={selectClass}
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s === "" ? "Any" : s === "open_any" ? "Any open" : s.replace("_", " ")}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="File or test">
          {(id) => (
            <input
              id={id}
              className={inputClass}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="train.py"
            />
          )}
        </Field>
      </div>
      <ErrorNotice error={error} />
      {loading && !data ? (
        <Loading what="incidents" />
      ) : (
        <DataTable
          label="Incidents"
          rows={data?.items ?? []}
          rowKey={(r) => r.id}
          onOpen={(r) => nav(`/incidents/${r.id}`)}
          empty={
            <EmptyState command="faultsage watch">
              No incidents yet. Run pytest while faultsage watch is running.
            </EmptyState>
          }
          columns={[
            { key: "id", header: "ID", kind: "mono", render: (r) => `I-${r.id}`, sortValue: (r) => r.id },
            { key: "title", header: "What failed", render: (r) => r.title, sortValue: (r) => r.title },
            {
              key: "status",
              header: "Status",
              render: (r) => <IncidentStatus status={r.status} />,
              sortValue: (r) => r.status,
            },
            {
              key: "cert",
              header: "Top cause",
              render: (r) => <CertaintyMarker value={r.top_certainty} />,
              sortValue: (r) => r.top_certainty ?? "",
            },
            {
              key: "first",
              header: "First seen",
              kind: "mono",
              render: (r) => when(r.first_seen_at),
              sortValue: (r) => r.first_seen_at,
            },
            {
              key: "last",
              header: "Last seen",
              kind: "mono",
              render: (r) => when(r.last_seen_at),
              sortValue: (r) => r.last_seen_at,
            },
            {
              key: "n",
              header: "Occurrences",
              kind: "num",
              render: (r) => r.occurrence_count,
              sortValue: (r) => r.occurrence_count,
            },
          ]}
        />
      )}
    </div>
  );
}
