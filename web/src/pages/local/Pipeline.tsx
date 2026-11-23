import { useState } from "react";
import type { Graph } from "../../api/generated";
import { EmptyState, ErrorNotice, Loading, kvClass } from "../../components/Common";
import { DataTable } from "../../components/DataTable";
import { PropagationGraph } from "../../components/PropagationGraph";
import { PageHead } from "../../components/Shells";
import { useApi } from "../../lib/useApi";
import p from "../page.module.css";

interface Step {
  name: string;
  inputs: string[];
  outputs: string[];
  checkpoint: {
    recorded_at: string;
    object_type: string;
    shape: number[] | null;
    columns: { name: string; dtype: string }[];
  } | null;
}

const EXAMPLE = `[[step]]
name = "load"
command = ["python", "-m", "pipeline.load"]
outputs = ["raw_transactions"]

[[step]]
name = "clean"
command = ["python", "-m", "pipeline.clean"]
inputs = ["raw_transactions"]
outputs = ["clean_transactions"]`;

export function Pipeline({ version }: { version: number }) {
  const pipe = useApi<{ declared: boolean; steps: Step[] }>("/api/pipeline", [version]);
  const graph = useApi<Graph>("/api/graph?kind=pipeline", [version]);
  const [sel, setSel] = useState<Step | null>(null);
  if (pipe.error) return <ErrorNotice error={pipe.error} />;
  if (!pipe.data) return <Loading what="pipeline" />;
  if (!pipe.data.declared) {
    return (
      <div className={p.stack}>
        <PageHead title="Pipeline" />
        <EmptyState>
          No pipeline is declared. Add .faultsage/pipeline.toml like this, then call faultsage.checkpoint(df,
          step="clean") at step boundaries.
        </EmptyState>
        <pre className={p.mono} tabIndex={0}>
          {EXAMPLE}
        </pre>
      </div>
    );
  }
  return (
    <div className={p.stack}>
      <PageHead title="Pipeline" />
      {graph.data ? <PropagationGraph graph={graph.data} /> : null}
      <div className={p.two}>
        <div className={p.wide}>
          <DataTable
            label="Pipeline steps"
            rows={pipe.data.steps}
            rowKey={(r) => r.name}
            onOpen={setSel}
            empty="No steps."
            columns={[
              { key: "name", header: "Step", kind: "mono", render: (r) => r.name },
              { key: "in", header: "Reads", kind: "mono", render: (r) => r.inputs.join(", ") || "-" },
              { key: "out", header: "Writes", kind: "mono", render: (r) => r.outputs.join(", ") || "-" },
              {
                key: "cp",
                header: "Last checkpoint",
                render: (r) => (r.checkpoint ? `${r.checkpoint.columns.length} columns` : "none"),
              },
            ]}
          />
        </div>
        <section className={p.narrow} aria-live="polite">
          <h2>{sel ? `Checkpoint: ${sel.name}` : "Select a step"}</h2>
          {sel?.checkpoint ? (
            <>
              <dl className={kvClass}>
                <dt>Type</dt>
                <dd>{sel.checkpoint.object_type}</dd>
                <dt>Shape</dt>
                <dd>{sel.checkpoint.shape?.join(" x ") ?? "unknown"}</dd>
              </dl>
              <DataTable
                label="Columns"
                rows={sel.checkpoint.columns}
                rowKey={(r) => r.name}
                empty="No columns"
                columns={[
                  { key: "n", header: "Column", kind: "mono", render: (r) => r.name },
                  { key: "t", header: "Type", kind: "mono", render: (r) => r.dtype },
                ]}
              />
            </>
          ) : sel ? (
            <p>No checkpoint recorded for this step yet. Values are never stored, only names and types.</p>
          ) : null}
        </section>
      </div>
    </div>
  );
}
