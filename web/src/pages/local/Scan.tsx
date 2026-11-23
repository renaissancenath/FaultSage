import { useState } from "react";
import { api } from "../../api/client";
import { Button } from "../../components/Button";
import { EmptyState, ErrorNotice } from "../../components/Common";
import { DataTable } from "../../components/DataTable";
import { StatusMarker } from "../../components/Markers";
import { PageHead } from "../../components/Shells";
import { when } from "../../lib/time";
import { useApi } from "../../lib/useApi";
import p from "../page.module.css";

interface Finding {
  severity: "error" | "warning" | "note";
  rule: string;
  file_path: string | null;
  line: number | null;
  message: string;
}
interface ScanRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  findings_count: number;
  findings: Finding[];
}

export function Scan() {
  const latest = useApi<ScanRun | null>("/api/scan/latest");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const run = latest.data;
  return (
    <div className={p.stack}>
      <PageHead title="Scan">
        <p className={p.lede}>
          A one-off check for broken imports, missing dependencies, circular imports, undefined names and
          pipeline gaps. It does not run in the background.
        </p>
      </PageHead>
      <div>
        <Button
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setErr(null);
            try {
              latest.setData(await api<ScanRun>("/api/scan", { method: "POST" }));
            } catch (e) {
              setErr(e);
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Scanning" : "Run scan"}
        </Button>
      </div>
      <ErrorNotice error={err ?? latest.error} />
      {run ? (
        <p className={p.small}>
          Scan {run.id} finished {run.finished_at ? when(run.finished_at) : "running"}: {run.findings_count}{" "}
          finding(s).
        </p>
      ) : null}
      <DataTable
        label="Scan findings"
        rows={run?.findings ?? []}
        rowKey={(r) => `${r.rule}${r.file_path}${r.line}${r.message}`}
        empty={<EmptyState>{run ? "No findings." : "No scan yet. Run one to check the project."}</EmptyState>}
        columns={[
          {
            key: "sev",
            header: "Severity",
            render: (r) => (
              <StatusMarker
                value={r.severity === "error" ? "failed" : r.severity === "warning" ? "warning" : "not_run"}
                label={r.severity}
              />
            ),
            sortValue: (r) => r.severity,
          },
          {
            key: "file",
            header: "Location",
            kind: "mono",
            render: (r) => (r.file_path ? `${r.file_path}${r.line ? `:${r.line}` : ""}` : "-"),
            sortValue: (r) => r.file_path ?? "",
          },
          { key: "rule", header: "Rule", kind: "mono", render: (r) => r.rule, sortValue: (r) => r.rule },
          { key: "msg", header: "Message", render: (r) => r.message },
        ]}
      />
    </div>
  );
}
