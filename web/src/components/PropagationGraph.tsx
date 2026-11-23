import { Controls, type Edge, MarkerType, type Node, Position, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/base.css";
import { useMemo, useState } from "react";
import type { Graph } from "../api/generated";
import { Button } from "./Button";
import s from "./Graph.module.css";
import { StatusMarker } from "./Markers";

/** Layered layout by longest path from sources: no layout library needed for small subgraphs. */
function layout(g: Graph): Record<string, { x: number; y: number }> {
  const nodes = g.nodes ?? [];
  const edges = g.edges ?? [];
  const depth: Record<string, number> = Object.fromEntries(nodes.map((n) => [n.id, 0]));
  for (let i = 0; i < nodes.length; i++) {
    let changed = false;
    for (const e of edges) {
      const d = (depth[e.source] ?? 0) + 1;
      if (e.target in depth && d > (depth[e.target] ?? 0) && d < nodes.length) {
        depth[e.target] = d;
        changed = true;
      }
    }
    if (!changed) break;
  }
  const rows: Record<number, number> = {};
  const pos: Record<string, { x: number; y: number }> = {};
  for (const n of nodes) {
    const d = depth[n.id] ?? 0;
    const r = rows[d] ?? 0;
    rows[d] = r + 1;
    pos[n.id] = { x: d * 200, y: r * 64 };
  }
  return pos;
}

export function PropagationGraph({ graph, defaultList = false }: { graph: Graph; defaultList?: boolean }) {
  const small = typeof window !== "undefined" && window.matchMedia?.("(max-width: 767px)").matches;
  const [asList, setAsList] = useState(defaultList || Boolean(small));
  const { nodes, edges } = useMemo(() => {
    const pos = layout(graph);
    const nodes: Node[] = (graph.nodes ?? []).map((n) => ({
      id: n.id,
      position: pos[n.id] ?? { x: 0, y: 0 },
      data: { label: `${n.label}${n.state === "failed" ? " (failed)" : ""}` },
      className: `${n.on_failure_path ? "fs-on-path" : ""} ${n.state === "failed" ? "fs-failed" : ""}`,
      ariaLabel: `${n.kind} ${n.label}, ${n.state?.replace("_", " ") ?? "not run"}`,
      draggable: false,
      connectable: false,
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    }));
    const edges: Edge[] = (graph.edges ?? []).map((e, i) => ({
      id: `${e.source}->${e.target}-${i}`,
      source: e.source,
      target: e.target,
      label: e.basis === "inferred" ? "inferred" : undefined,
      className: `${e.basis === "inferred" ? "fs-edge-inferred" : ""} ${e.on_failure_path ? "fs-edge-path" : ""}`,
      markerEnd: { type: MarkerType.Arrow, width: 14, height: 14 },
    }));
    return { nodes, edges };
  }, [graph]);

  const count = graph.nodes?.length ?? 0;
  if (count === 0) return <p>No dependency graph yet. It is built from your imports on the first failure.</p>;
  return (
    <div className={s.wrap}>
      <div className={s.bar}>
        <p className={s.legend}>
          <span>Solid: known edge</span>
          <span>Dashed: inferred</span>
          <span>Bold: root to failure path</span>
        </p>
        <Button kind="text" onClick={() => setAsList(!asList)}>
          {asList ? "Show as graph" : "Show as list"}
        </Button>
      </div>
      {asList ? (
        <ul className={s.list} aria-label="Dependency list">
          {(graph.nodes ?? []).map((n) => (
            <li key={n.id} className={n.on_failure_path ? s.onPath : undefined}>
              <StatusMarker value={n.state ?? "not_run"} /> {n.label}
              {n.on_failure_path ? " (on failure path)" : ""}
              {(graph.edges ?? [])
                .filter((e) => e.source === n.id)
                .map((e) => (
                  <div
                    key={`${e.source}-${e.target}`}
                  >{`  -> ${e.target}${e.basis === "inferred" ? " (inferred)" : ""}`}</div>
                ))}
            </li>
          ))}
        </ul>
      ) : (
        <div className={s.canvas}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            fitView
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable
            proOptions={{ hideAttribution: true }}
            minZoom={0.3}
            aria-label="Propagation graph"
          >
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
      )}
    </div>
  );
}
