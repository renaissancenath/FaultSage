import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router";
import { api } from "../../api/client";
import type { Me, Project } from "../../api/cloud";
import { Button } from "../../components/Button";
import { EmptyState, ErrorNotice, Field, Loading, Notice, inputClass } from "../../components/Common";
import { DataTable } from "../../components/DataTable";
import { PageHead } from "../../components/Shells";
import { when } from "../../lib/time";
import { useApi } from "../../lib/useApi";
import p from "../page.module.css";

export function Home({ me, onChange }: { me: Me; onChange: () => void }) {
  const nav = useNavigate();
  const projects = useApi<Project[]>("/api/v1/projects", [me.org.id]);
  const [name, setName] = useState("");
  const [repo, setRepo] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const canCreate = me.org.role !== "viewer";
  const atLimit = me.usage.projects >= me.org.plan.projects;
  async function create(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const r = await api<{ id: number }>("/api/v1/projects", { json: { name, repo_url: repo } });
      onChange();
      nav(`/app/projects/${r.id}?tab=setup`);
    } catch (x) {
      setErr(x);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className={p.stack}>
      <PageHead title={me.user.name ? `Projects, ${me.user.name}` : "Projects"}>
        <p className={p.lede}>
          Each project gets an API key for the CLI and the SDK. Open issues are production errors not yet
          resolved.
        </p>
      </PageHead>
      <ErrorNotice error={projects.error} />
      {projects.loading && !projects.data ? (
        <Loading what="projects" />
      ) : (
        <DataTable
          label="Projects"
          rows={projects.data ?? []}
          rowKey={(r) => r.id}
          onOpen={(r) => nav(`/app/projects/${r.id}`)}
          empty={<EmptyState>No projects yet. Create one below to get an API key.</EmptyState>}
          columns={[
            { key: "name", header: "Project", render: (r) => r.name, sortValue: (r) => r.name },
            {
              key: "open",
              header: "Open issues",
              kind: "num",
              render: (r) => r.open_issues,
              sortValue: (r) => r.open_issues,
            },
            {
              key: "cf",
              header: "Case files",
              kind: "num",
              render: (r) => r.case_files,
              sortValue: (r) => r.case_files,
            },
            {
              key: "repo",
              header: "Repository",
              kind: "mono",
              render: (r) => r.repo_url.replace("https://github.com/", "") || "-",
            },
            {
              key: "created",
              header: "Created",
              kind: "mono",
              render: (r) => when(r.created_at),
              sortValue: (r) => r.created_at,
            },
          ]}
        />
      )}
      {canCreate ? (
        <section className={p.section} aria-labelledby="new">
          <h2 id="new">New project</h2>
          {atLimit ? (
            <Notice tone="warn" next="Delete a project, or ask to upgrade in Settings.">
              The {me.org.plan.name} plan allows {me.org.plan.projects} projects. You have {me.usage.projects}
              .
            </Notice>
          ) : (
            <form className={p.form} onSubmit={create}>
              <ErrorNotice error={err} />
              <Field label="Project name">
                {(id) => (
                  <input
                    id={id}
                    className={inputClass}
                    required
                    maxLength={120}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="checkout-api"
                  />
                )}
              </Field>
              <Field label="GitHub repository" hint="Optional. Used to open issues for production errors.">
                {(id, d) => (
                  <input
                    id={id}
                    aria-describedby={d}
                    className={inputClass}
                    type="url"
                    value={repo}
                    onChange={(e) => setRepo(e.target.value)}
                    placeholder="https://github.com/you/checkout-api"
                  />
                )}
              </Field>
              <div>
                <Button type="submit" disabled={busy}>
                  {busy ? "Creating" : "Create project"}
                </Button>
              </div>
            </form>
          )}
        </section>
      ) : null}
    </div>
  );
}
