import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router";
import { api } from "../../api/client";
import type { Me, Member, Meta } from "../../api/cloud";
import { Button } from "../../components/Button";
import {
  ConfirmDialog,
  ErrorNotice,
  Field,
  Notice,
  inputClass,
  kvClass,
  selectClass,
} from "../../components/Common";
import { DataTable } from "../../components/DataTable";
import { PageHead } from "../../components/Shells";
import { type Theme, setTheme, storedTheme } from "../../lib/theme";
import { when } from "../../lib/time";
import { useApi } from "../../lib/useApi";
import p from "../page.module.css";

export function AccountSettings({ me, meta, reload }: { me: Me; meta: Meta | null; reload: () => void }) {
  const nav = useNavigate();
  const members = useApi<Member[]>("/api/v1/org/members", [me.org.id]);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [name, setName] = useState(me.user.name);
  const [orgName, setOrgName] = useState(me.org.name);
  const [pw, setPw] = useState({ current: "", next: "" });
  const [invite, setInvite] = useState("");
  const [theme, setT] = useState<Theme>(storedTheme());
  const [del, setDel] = useState(false);
  const [typed, setTyped] = useState("");
  const [delPw, setDelPw] = useState("");
  const owner = me.org.role === "owner";
  const plan = me.org.plan;

  async function act(e: FormEvent | null, fn: () => Promise<unknown>, done: string) {
    e?.preventDefault();
    setErr(null);
    setMsg(null);
    try {
      const r = (await fn()) as { message?: string; checkout_url?: string | null } | undefined;
      if (r?.checkout_url) {
        window.location.assign(r.checkout_url);
        return;
      }
      setMsg(r?.message ?? done);
      reload();
      members.reload();
    } catch (x) {
      setErr(x);
    }
  }

  return (
    <div className={p.stack}>
      <PageHead title="Settings" />
      {msg ? <Notice tone="ok">{msg}</Notice> : null}
      <ErrorNotice error={err} />
      <div className={p.two}>
        <div className={p.wide}>
          <section className={p.section}>
            <h2>Plan and usage</h2>
            <dl className={kvClass}>
              <dt>Plan</dt>
              <dd>{plan.name}</dd>
              <dt>Projects</dt>
              <dd>
                {me.usage.projects} of {plan.projects}
              </dd>
              <dt>Events this month</dt>
              <dd>
                {me.usage.events.toLocaleString()} of {plan.events_per_month.toLocaleString()}
                {me.usage.dropped ? `, ${me.usage.dropped.toLocaleString()} dropped` : ""}
              </dd>
              <dt>History kept</dt>
              <dd>{plan.retention_days} days</dd>
              <dt>Seats</dt>
              <dd>
                {me.usage.members} of {plan.seats}
              </dd>
            </dl>
            {owner && plan.id === "free" ? (
              <div>
                <Button
                  onClick={() =>
                    act(
                      null,
                      () => api("/api/v1/billing/upgrade", { json: { plan: "pro" } }),
                      "Request saved.",
                    )
                  }
                >
                  {meta?.billing ? "Upgrade to Pro" : "Ask to upgrade to Pro"}
                </Button>
              </div>
            ) : null}
          </section>
          <section className={p.section}>
            <h2>Members of {me.org.name}</h2>
            <DataTable
              label="Members"
              rows={members.data ?? []}
              rowKey={(r) => r.id}
              empty="Only you."
              columns={[
                { key: "e", header: "Email", kind: "mono", render: (r) => r.email },
                { key: "n", header: "Name", render: (r) => r.name || "-" },
                {
                  key: "r",
                  header: "Role",
                  render: (r) =>
                    owner && r.role !== "owner" ? (
                      <select
                        className={selectClass}
                        aria-label={`Role of ${r.email}`}
                        value={r.role}
                        onChange={(e) =>
                          act(
                            null,
                            () =>
                              api(`/api/v1/org/members/${r.id}`, {
                                method: "PUT",
                                json: { role: e.target.value },
                              }),
                            "Role changed.",
                          )
                        }
                      >
                        <option value="viewer">viewer</option>
                        <option value="maintainer">maintainer</option>
                      </select>
                    ) : (
                      r.role
                    ),
                },
                { key: "j", header: "Joined", kind: "mono", render: (r) => when(r.created_at) },
                {
                  key: "x",
                  header: "",
                  render: (r) =>
                    owner && r.role !== "owner" ? (
                      <Button
                        kind="text"
                        danger
                        onClick={() =>
                          act(
                            null,
                            () => api(`/api/v1/org/members/${r.id}`, { method: "DELETE" }),
                            "Member removed.",
                          )
                        }
                      >
                        Remove
                      </Button>
                    ) : null,
                },
              ]}
            />
            {owner ? (
              <form
                className={p.form}
                onSubmit={(e) =>
                  act(
                    e,
                    () => api("/api/v1/org/members/invite", { json: { email: invite } }),
                    `Invited ${invite}.`,
                  )
                }
              >
                <Field label="Invite by email" hint="They join as viewer. Change the role after they join.">
                  {(id, d) => (
                    <input
                      id={id}
                      aria-describedby={d}
                      className={inputClass}
                      type="email"
                      required
                      value={invite}
                      onChange={(e) => setInvite(e.target.value)}
                    />
                  )}
                </Field>
                <div>
                  <Button kind="quiet" type="submit">
                    Send invite
                  </Button>
                </div>
              </form>
            ) : null}
          </section>
        </div>
        <div className={p.narrow}>
          <form
            className={p.form}
            onSubmit={(e) =>
              act(e, () => api("/api/v1/me", { method: "PUT", json: { name } }), "Name saved.")
            }
          >
            <h2>Your account</h2>
            <p className={p.small}>
              {me.user.email}
              {me.user.email_verified ? ", confirmed" : ", not confirmed"}
              {me.user.github_linked ? ", GitHub linked" : ""}
            </p>
            <Field label="Name">
              {(id) => (
                <input
                  id={id}
                  className={inputClass}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              )}
            </Field>
            <div>
              <Button kind="quiet" type="submit">
                Save name
              </Button>
            </div>
          </form>
          {owner ? (
            <form
              className={p.form}
              onSubmit={(e) =>
                act(
                  e,
                  () => api("/api/v1/org", { method: "PUT", json: { name: orgName } }),
                  "Workspace renamed.",
                )
              }
            >
              <Field label="Workspace name">
                {(id) => (
                  <input
                    id={id}
                    className={inputClass}
                    value={orgName}
                    onChange={(e) => setOrgName(e.target.value)}
                  />
                )}
              </Field>
              <div>
                <Button kind="quiet" type="submit">
                  Rename workspace
                </Button>
              </div>
            </form>
          ) : null}
          <form
            className={p.form}
            onSubmit={(e) =>
              act(
                e,
                () =>
                  api("/api/v1/auth/change-password", {
                    json: { current_password: pw.current, new_password: pw.next },
                  }),
                "Password changed. Other sessions were signed out.",
              )
            }
          >
            <h2>Password</h2>
            {me.user.has_password ? (
              <Field label="Current password">
                {(id) => (
                  <input
                    id={id}
                    className={inputClass}
                    type="password"
                    autoComplete="current-password"
                    value={pw.current}
                    onChange={(e) => setPw({ ...pw, current: e.target.value })}
                  />
                )}
              </Field>
            ) : (
              <p className={p.small}>You sign in with GitHub. You can add a password.</p>
            )}
            <Field label="New password" hint="At least 12 characters.">
              {(id, d) => (
                <input
                  id={id}
                  aria-describedby={d}
                  className={inputClass}
                  type="password"
                  autoComplete="new-password"
                  minLength={12}
                  value={pw.next}
                  onChange={(e) => setPw({ ...pw, next: e.target.value })}
                />
              )}
            </Field>
            <div>
              <Button kind="quiet" type="submit">
                Change password
              </Button>
            </div>
          </form>
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
          <div>
            <Button
              kind="text"
              onClick={() =>
                act(
                  null,
                  async () => {
                    await api("/api/v1/auth/logout-everywhere", { method: "POST" });
                    nav("/login");
                  },
                  "Signed out everywhere.",
                )
              }
            >
              Sign out of all devices
            </Button>
          </div>
          <section className={p.danger}>
            <h2>Delete account</h2>
            <p>
              Removes your personal data now. Workspaces where you are the only member are deleted with their
              projects.
            </p>
            <div>
              <Button kind="text" danger onClick={() => setDel(true)}>
                Delete account
              </Button>
            </div>
          </section>
        </div>
      </div>
      {del ? (
        <ConfirmDialog
          title="Delete your account"
          confirmLabel="Delete account"
          confirmDisabled={typed !== `delete ${me.user.email}`}
          onCancel={() => {
            setDel(false);
            setTyped("");
            setDelPw("");
          }}
          onConfirm={() =>
            act(
              null,
              async () => {
                await api("/api/v1/me/delete", { json: { confirm: typed, password: delPw } });
                nav("/");
              },
              "Account deleted.",
            )
          }
        >
          <p>This cannot be undone.</p>
          <Field label={`Type delete ${me.user.email} to confirm`}>
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
          {me.user.has_password ? (
            <Field label="Password">
              {(id) => (
                <input
                  id={id}
                  className={inputClass}
                  type="password"
                  value={delPw}
                  onChange={(e) => setDelPw(e.target.value)}
                />
              )}
            </Field>
          ) : null}
        </ConfirmDialog>
      ) : null}
    </div>
  );
}
