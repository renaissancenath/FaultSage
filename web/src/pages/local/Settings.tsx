import { useState } from "react";
import { api } from "../../api/client";
import { Button } from "../../components/Button";
import {
  ConfirmDialog,
  ErrorNotice,
  Field,
  Loading,
  Notice,
  inputClass,
  selectClass,
} from "../../components/Common";
import { PageHead } from "../../components/Shells";
import { type Theme, setTheme, storedTheme } from "../../lib/theme";
import { useApi } from "../../lib/useApi";
import p from "../page.module.css";

interface Cfg {
  project: { name: string };
  signals: Record<string, boolean | string[]>;
  analysis: { coverage_contexts: boolean; blast_radius_depth: number };
  retention: { event_days: number };
  dashboard: { port: number };
  model: { enabled: boolean };
  cloud: { enabled: boolean; url: string };
  verify: { extra_commands: string[][] };
  restart_required?: boolean;
}

export function Switch({
  on,
  onChange,
  label,
}: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      className={p.switch}
      onClick={() => onChange(!on)}
    >
      {on ? "on" : "off"}
    </button>
  );
}

export function Settings() {
  const cfg = useApi<Cfg>("/api/settings");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [purge, setPurge] = useState(false);
  const [typed, setTyped] = useState("");
  const [theme, setT] = useState<Theme>(storedTheme());
  if (cfg.error) return <ErrorNotice error={cfg.error} />;
  if (!cfg.data) return <Loading what="settings" />;
  const c = cfg.data;
  async function save(body: Record<string, unknown>) {
    setErr(null);
    try {
      const r = await api<Cfg>("/api/settings", { method: "PUT", json: body });
      cfg.setData(r);
      setMsg(r.restart_required ? "Saved. Restart faultsage watch to use the new port." : "Saved.");
    } catch (e) {
      setErr(e);
    }
  }
  const signals: [string, string][] = [
    ["pytest", "Pytest results"],
    ["run_wrapper", "faultsage run commands"],
    ["git", "Git changes"],
    ["file_watch", "File saves"],
  ];
  return (
    <div className={p.stack}>
      <PageHead title="Settings">
        <p className={p.lede}>
          Stored in .faultsage/config.toml. FaultSage reads only the signals that are on.
        </p>
      </PageHead>
      {msg ? <Notice tone="ok">{msg}</Notice> : null}
      <ErrorNotice error={err} />
      <section className={p.section}>
        <h2>Signals</h2>
        {signals.map(([k, label]) => (
          <div key={k} className={p.switchRow}>
            <span>{label}</span>
            <Switch
              label={label}
              on={Boolean(c.signals[k])}
              onChange={(v) => save({ signals: { [k]: v } })}
            />
          </div>
        ))}
        <div className={p.switchRow}>
          <span>Log files</span>
          <span className={p.mono}>
            {(c.signals.logs as string[]).join(", ") || "none (edit config.toml)"}
          </span>
        </div>
        <div className={p.switchRow}>
          <span>Coverage evidence (needs pytest --cov-context=test)</span>
          <Switch
            label="Coverage evidence"
            on={c.analysis.coverage_contexts}
            onChange={(v) => save({ coverage_contexts: v })}
          />
        </div>
        <div className={p.switchRow}>
          <span>Sync case files to FaultSage Cloud</span>
          <Switch label="Cloud sync" on={c.cloud.enabled} onChange={(v) => save({ cloud_enabled: v })} />
        </div>
      </section>
      <section className={p.form}>
        <h2>Limits</h2>
        <Field label="Keep events for (days)">
          {(id) => (
            <input
              id={id}
              type="number"
              min={1}
              className={inputClass}
              defaultValue={c.retention.event_days}
              onBlur={(e) => save({ retention_days: Number(e.target.value) })}
            />
          )}
        </Field>
        <Field label="Blast radius depth">
          {(id) => (
            <input
              id={id}
              type="number"
              min={1}
              max={12}
              className={inputClass}
              defaultValue={c.analysis.blast_radius_depth}
              onBlur={(e) => save({ blast_radius_depth: Number(e.target.value) })}
            />
          )}
        </Field>
        <Field label="Dashboard port" hint="Bound to 127.0.0.1 only.">
          {(id, d) => (
            <input
              id={id}
              aria-describedby={d}
              type="number"
              className={inputClass}
              defaultValue={c.dashboard.port}
              onBlur={(e) => save({ port: Number(e.target.value) })}
            />
          )}
        </Field>
        <Field label="Theme">
          {(id) => (
            <select
              id={id}
              className={selectClass}
              value={theme}
              onChange={(e) => {
                const t = e.target.value as Theme;
                setT(t);
                setTheme(t);
              }}
            >
              <option value="system">Follow system</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
          )}
        </Field>
        <p className={p.small}>
          Verify commands you allowed: {c.verify.extra_commands.map((x) => x.join(" ")).join("; ") || "none"}.
          Only commands written in config.toml can ever run.
        </p>
      </section>
      <section className={p.danger}>
        <h2>Purge local data</h2>
        <p>
          Deletes events, incidents, backups and the spool for {c.project.name}. The config and the approvals
          audit are kept.
        </p>
        <div>
          <Button kind="text" danger onClick={() => setPurge(true)}>
            Purge local data
          </Button>
        </div>
      </section>
      {purge ? (
        <ConfirmDialog
          title="Purge local data"
          confirmLabel="Purge local data"
          confirmDisabled={typed !== `purge ${c.project.name}`}
          onCancel={() => {
            setPurge(false);
            setTyped("");
          }}
          onConfirm={async () => {
            try {
              await api("/api/purge", { json: { confirm: typed } });
              setMsg("Purged.");
            } catch (e) {
              setErr(e);
            }
            setPurge(false);
            setTyped("");
          }}
        >
          <p>
            This deletes: events, incidents with their evidence, patch backups, spool files. It cannot be
            undone.
          </p>
          <Field label={`Type purge ${c.project.name} to confirm`}>
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
