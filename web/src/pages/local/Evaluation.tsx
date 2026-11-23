import { useState } from "react";
import { EmptyState, ErrorNotice, Loading } from "../../components/Common";
import { DataTable } from "../../components/DataTable";
import { PageHead } from "../../components/Shells";
import { useApi } from "../../lib/useApi";
import p from "../page.module.css";

interface RunSummary {
  run_id: string;
  dataset: string;
  dataset_version: string;
  split: string;
  cases_attempted: number;
  cases_reproduced: number;
  cases_excluded: Record<string, number>;
}
type Topk = Record<"top1" | "top3" | "top5", { mean: number; ci95: [number, number] }>;
interface Run extends RunSummary {
  metrics: { faultsage?: Topk; blast_radius?: { precision: number; recall: number } };
  baselines: Record<string, Topk>;
}

/** Only real run records from results/runs. No numbers are invented here (AGENTS.md section 8). */
export function Evaluation() {
  const runs = useApi<RunSummary[]>("/api/bench/runs");
  const [sel, setSel] = useState<string | null>(null);
  const run = useApi<Run>(sel ? `/api/bench/runs/${encodeURIComponent(sel)}` : null, [sel]);
  if (runs.error) return <ErrorNotice error={runs.error} />;
  if (!runs.data) return <Loading what="benchmark runs" />;
  const rows = run.data
    ? ([["faultsage", run.data.metrics.faultsage], ...Object.entries(run.data.baselines)] as [
        string,
        Topk | undefined,
      ][])
    : [];
  return (
    <div className={p.stack}>
      <PageHead title="Evaluation">
        <p className={p.lede}>
          Accuracy on real bugs from real projects, against simple baselines. Every number comes from a run
          record you can recompute.
        </p>
      </PageHead>
      <DataTable
        label="Benchmark runs"
        rows={runs.data}
        rowKey={(r) => r.run_id}
        onOpen={(r) => setSel(r.run_id)}
        empty={
          <EmptyState command="faultsage bench run bugsinpy --split dev">No benchmark runs yet.</EmptyState>
        }
        columns={[
          { key: "id", header: "Run", kind: "mono", render: (r) => r.run_id },
          { key: "ds", header: "Dataset", render: (r) => r.dataset },
          { key: "v", header: "Version", kind: "mono", render: (r) => r.dataset_version },
          { key: "split", header: "Split", render: (r) => r.split },
          { key: "a", header: "Attempted", kind: "num", render: (r) => r.cases_attempted },
          { key: "r", header: "Reproduced", kind: "num", render: (r) => r.cases_reproduced },
          {
            key: "x",
            header: "Excluded",
            kind: "num",
            render: (r) => Object.values(r.cases_excluded ?? {}).reduce((a, b) => a + b, 0),
          },
        ]}
      />
      {run.data ? (
        <section className={p.section}>
          <h2>{run.data.run_id}: file localisation</h2>
          <DataTable
            label="Metrics with baselines"
            rows={rows}
            rowKey={(r) => r[0]}
            empty="No metrics."
            columns={[
              { key: "m", header: "Method", kind: "mono", render: (r) => r[0] },
              ...(["top1", "top3", "top5"] as const).map((k) => ({
                key: k,
                header: k.replace("top", "Top-"),
                kind: "num" as const,
                render: (r: [string, Topk | undefined]) =>
                  r[1]?.[k]
                    ? `${r[1][k].mean.toFixed(3)} [${r[1][k].ci95[0].toFixed(2)}, ${r[1][k].ci95[1].toFixed(2)}]`
                    : "-",
              })),
            ]}
          />
          <div className={p.bars} aria-hidden="true">
            {rows.map(([m, t]) => (
              <div key={m} className={p.barRow}>
                <span>{m}</span>
                <svg
                  viewBox="0 0 100 8"
                  preserveAspectRatio="none"
                  height="8"
                  width="100%"
                  aria-hidden="true"
                >
                  <rect
                    x="0"
                    y="0"
                    width={(t?.top3.mean ?? 0) * 100}
                    height="8"
                    fill={m === "faultsage" ? "var(--fs-brand)" : "var(--fs-ink-2)"}
                  />
                </svg>
                <span>{t ? `${(t.top3.mean * 100).toFixed(1)}%` : "-"}</span>
              </div>
            ))}
          </div>
          <p className={p.small}>Bars show Top-3. Brackets are 95% bootstrap intervals.</p>
        </section>
      ) : null}
    </div>
  );
}
