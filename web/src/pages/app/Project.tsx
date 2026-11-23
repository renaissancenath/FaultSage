import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { api } from "../../api/client";
import type { ApiKey, CaseFileRow, IssueRow, Me, Project as P } from "../../api/cloud";
import { Button } from "../../components/Button";
import {
  Command,
  ConfirmDialog,
  CopyButton,
  EmptyState,
  ErrorNotice,
  Field,
  Loading,
  Notice,
  inputClass,
} from "../../components/Common";
import { DataTable } from "../../components/DataTable";
import { CertaintyMarker, IncidentStatus } from "../../components/Markers";
import { PageHead } from "../../components/Shells";
import { when } from "../../lib/time";
import { useApi } from "../../lib/useApi";
import p from "../page.module.css";

type Tab = "issues" | "case-files" | "setup" | "settings";

export function Project({ me }: { me: Me }) {
  const pid = Number(useParams().pid);
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) ?? "issues";
  const project = useApi<P>(`/api/v1/projects/${pid}`);
  if (project.error) return <ErrorNotice error={project.error} />;
  if (!project.data) return <Loading what="project" />;
  const tabs: [Tab, string][] = [
    ["issues", "Production errors"],
    ["case-files", "Case files"],
    ["setup", "Setup"],
  ];
  if (me.org.role !== "viewer") tabs.push(["settings", "Settings"]);
  return (
    <div className={p.stack}>
      <PageHead title={project.data.name} />
      <div className={p.tabs} role="tablist">
        {tabs.map(([t, label]) => (
          <button
            key={t}
            type="button"
            role="tab"
            className={p.tab}
            aria-selected={tab === t}
            onClick={() => setParams({ tab: t })}
          >
            {label}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        {tab === "issues" ? <Issues pid={pid} /> : null}
        {tab === "case-files" ? <CaseFiles pid={pid} /> : null}
        {tab === "setup" ? <Setup project={project.data} canKeys={me.org.role !== "viewer"} /> : null}
        {tab === "settings" ? (
          <ProjectSettings project={project.data} me={me} reload={project.reload} />
        ) : null}
      </div>
    </div>
  );
}

function Issues({ pid }: { pid: number }) {
  const nav = useNavigate();
  const [status, setStatus] = useState("");
  const issues = useApi<IssueRow[]>(`/api/v1/projects/${pid}/issues${status ? `?status=${status}` : ""}`, [
    status,
  ]);
  return (
    <div className={p.stack}>
      <div className={p.filters}>
        <Field label="Status">
          {(id) => (
            <select id={id} className={inputClass} value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Any</option>
              {["open", "triaged", "fix_in_review", "reopened", "resolved", "ignored"].map((s) => (
                <option key={s} value={s}>
                  {s.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          )}
        </Field>
      </div>
      <ErrorNotice error={issues.error} />
      <DataTable
        label="Production errors"
        rows={issues.data ?? []}
        rowKey={(r) => r.id}
        onOpen={(r) => nav(`/app/projects/${pid}/issues/${r.id}`)}
        empty={
          <EmptyState>No production errors captured. Add the SDK to your app: see the Setup tab.</EmptyState>
        }
        columns={[
          { key: "id", header: "ID", kind: "mono", render: (r) => `FS-${r.id}`, sortValue: (r) => r.id },
          { key: "title", header: "Error", render: (r) => r.title, sortValue: (r) => r.title },
          {
            key: "status",
            header: "Status",
            render: (r) => <IncidentStatus status={r.status} />,
            sortValue: (r) => r.status,
          },
          { key: "env", header: "Environment", render: (r) => r.environment || "-" },
          { key: "rel", header: "Release", kind: "mono", render: (r) => r.last_release || "-" },
          {
            key: "n",
            header: "Events",
            kind: "num",
            render: (r) => r.event_count,
            sortValue: (r) => r.event_count,
          },
          {
            key: "last",
            header: "Last seen",
            kind: "mono",
            render: (r) => when(r.last_seen_at),
            sortValue: (r) => r.last_seen_at,
          },
        ]}
      />
    </div>
  );
}

function CaseFiles({ pid }: { pid: number }) {
  const nav = useNavigate();
  const rows = useApi<CaseFileRow[]>(`/api/v1/projects/${pid}/case-files`);
  return (
    <>
      <ErrorNotice error={rows.error} />
      <DataTable
        label="Case files"
        rows={rows.data ?? []}
        rowKey={(r) => r.id}
        onOpen={(r) => nav(`/app/projects/${pid}/case-files/${r.id}`)}
        empty={
          <EmptyState command="faultsage cloud push all">
            No case files synced. Push them from the CLI.
          </EmptyState>
        }
        columns={[
          { key: "id", header: "Local ID", kind: "mono", render: (r) => `I-${r.local_incident_id}` },
          { key: "t", header: "What failed", render: (r) => r.title },
          { key: "s", header: "Status", render: (r) => <IncidentStatus status={r.status} /> },
          { key: "c", header: "Top cause", render: (r) => <CertaintyMarker value={r.top_certainty} /> },
          {
            key: "u",
            header: "Updated",
            kind: "mono",
            render: (r) => when(r.updated_at),
            sortValue: (r) => r.updated_at,
          },
        ]}
      />
    </>
  );
}

function Setup({ project, canKeys }: { project: P; canKeys: boolean }) {
  const [key, setKey] = useState<string | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const base = window.location.origin;
  const k = key ?? "fsk_...";
  return (
    <div className={p.stack}>
      {canKeys ? (
        <section className={p.section}>
          <h2>1. Create an API key</h2>
          <ErrorNotice error={err} />
          {key ? (
            <div className={p.statement}>
              <strong>Copy this key now. It is shown only once.</strong>
              <code className={p.mono}>{key}</code>
              <div>
                <CopyButton text={key} label="Copy key" />
              </div>
            </div>
          ) : (
            <div>
              <Button
                onClick={async () => {
                  try {
                    setKey(
                      (
                        await api<{ key: string }>(`/api/v1/projects/${project.id}/keys`, {
                          json: { name: "default" },
                        })
                      ).key,
                    );
                  } catch (e) {
                    setErr(e);
                  }
                }}
              >
                Create API key
              </Button>
            </div>
          )}
        </section>
      ) : (
        <Notice tone="info">Ask a maintainer for an API key.</Notice>
      )}
      <section className={p.section}>
        <h2>2. Connect the CLI on your machine</h2>
        <Command text={`faultsage cloud login --url ${base} --api-key ${k}`} />
        <Command text="faultsage cloud push all" />
        <p className={p.small}>
          Or set [cloud] enabled = true in .faultsage/config.toml to sync new case files automatically.
        </p>
      </section>
      <section className={p.section}>
        <h2>3. Capture errors from your deployed app</h2>
        <Command text={`FAULTSAGE_URL=${base} FAULTSAGE_API_KEY=${k}`} />
        <pre className={p.mono} tabIndex={0}>
          {
            'import faultsage.sdk as fs\nfs.init(environment="production", release="1.0.0")  # reads FAULTSAGE_URL and FAULTSAGE_API_KEY\napp.add_middleware(fs.ASGIMiddleware)               # FastAPI / Starlette'
          }
        </pre>
      </section>
    </div>
  );
}

function ProjectSettings({ project, me, reload }: { project: P; me: Me; reload: () => void }) {
  const nav = useNavigate();
  const keys = useApi<ApiKey[]>(`/api/v1/projects/${project.id}/keys`);
  const [name, setName] = useState(project.name);
  const [repo, setRepo] = useState(project.repo_url);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [del, setDel] = useState(false);
  const [typed, setTyped] = useState("");
  async function act(fn: () => Promise<unknown>, done: string) {
    setErr(null);
    try {
      await fn();
      setMsg(done);
    } catch (e) {
      setErr(e);
    }
  }
  return (
    <div className={p.stack}>
      {msg ? <Notice tone="ok">{msg}</Notice> : null}
      <ErrorNotice error={err} />
      <form
        className={p.form}
        onSubmit={(e) => {
          e.preventDefault();
          act(
            () => api(`/api/v1/projects/${project.id}`, { method: "PUT", json: { name, repo_url: repo } }),
            "Saved.",
          ).then(reload);
        }}
      >
        <Field label="Project name">
          {(id) => (
            <input id={id} className={inputClass} value={name} onChange={(e) => setName(e.target.value)} />
          )}
        </Field>
        <Field label="GitHub repository">
          {(id) => (
            <input
              id={id}
              className={inputClass}
              type="url"
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
            />
          )}
        </Field>
        <div>
          <Button type="submit">Save</Button>
        </div>
      </form>
      <section className={p.section}>
        <h2>API keys</h2>
        <DataTable
          label="API keys"
          rows={keys.data ?? []}
          rowKey={(r) => r.id}
          empty="No keys yet. Create one in Setup."
          columns={[
            { key: "n", header: "Name", render: (r) => r.name },
            { key: "p", header: "Starts with", kind: "mono", render: (r) => r.prefix },
            {
              key: "u",
              header: "Last used",
              kind: "mono",
              render: (r) => (r.last_used_at ? when(r.last_used_at) : "never"),
            },
            { key: "s", header: "State", render: (r) => (r.revoked_at ? "revoked" : "active") },
            {
              key: "a",
              header: "",
              render: (r) =>
                r.revoked_at ? null : (
                  <Button
                    kind="text"
                    danger
                    onClick={() =>
                      act(
                        () => api(`/api/v1/projects/${project.id}/keys/${r.id}`, { method: "DELETE" }),
                        "Key revoked.",
                      ).then(keys.reload)
                    }
                  >
                    Revoke
                  </Button>
                ),
            },
          ]}
        />
      </section>
      {me.org.role === "owner" ? (
        <section className={p.danger}>
          <h2>Delete project</h2>
          <p>Deletes its production errors, case files and API keys. It cannot be undone.</p>
          <div>
            <Button kind="text" danger onClick={() => setDel(true)}>
              Delete project
            </Button>
          </div>
        </section>
      ) : null}
      {del ? (
        <ConfirmDialog
          title={`Delete ${project.name}`}
          confirmLabel="Delete project"
          confirmDisabled={typed !== `delete ${project.slug}`}
          onCancel={() => {
            setDel(false);
            setTyped("");
          }}
          onConfirm={() =>
            act(
              () => api(`/api/v1/projects/${project.id}/delete`, { json: { confirm: typed } }),
              "Deleted.",
            ).then(() => nav("/app"))
          }
        >
          <p>All issues, events, case files and keys of this project are deleted.</p>
          <Field label={`Type delete ${project.slug} to confirm`}>
            {(id) => (
              <input
                id={id}
                className={inputClass}
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                autoComplete="off"
              />
            )}
          </Field>
        </ConfirmDialog>
      ) : null}
    </div>
  );
}
