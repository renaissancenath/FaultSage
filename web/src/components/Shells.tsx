import { type ReactNode, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router";
import { api, setOrg } from "../api/client";
import type { Me } from "../api/cloud";
import { Button, LinkButton } from "./Button";
import { Logo, Notice } from "./Common";
import s from "./Shell.module.css";

function Nav({ items, label }: { items: [string, string][]; label: string }) {
  return (
    <ul className={s.navList} aria-label={label}>
      {items.map(([to, text]) => (
        <li key={to}>
          <NavLink
            to={to}
            end={to === "/" || to === "/app"}
            className={({ isActive }) => `${s.navLink} ${isActive ? s.active : ""}`}
          >
            {text}
          </NavLink>
        </li>
      ))}
    </ul>
  );
}

export function SkipLink() {
  return (
    <a className="fs-skip" href="#main">
      Skip to content
    </a>
  );
}

/* ---- local dashboard ------------------------------------------------------------------- */

export interface LocalStatus {
  state: "running" | "paused" | "stopped";
  project: string;
  since: number;
  open_incidents: number;
  signals: Record<string, boolean>;
  git: { head: string | null; branch: string | null };
  python: string;
  tests_found: number;
  root: string;
  weights: string;
  cloud: { enabled: boolean; url: string };
}

export function statusSentence(st: LocalStatus): string {
  const since = new Date(st.since * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const on = Object.entries(st.signals)
    .filter(([, v]) => v)
    .map(([k]) => k.replace("_", " "));
  const off = Object.entries(st.signals)
    .filter(([, v]) => !v)
    .map(([k]) => k.replace("_", " "));
  const open = st.open_incidents === 1 ? "1 open incident" : `${st.open_incidents} open incidents`;
  if (st.state === "paused")
    return `Paused. New signals are queued and will be processed when you resume. ${open}.`;
  if (st.state === "stopped") return "Stopped. Run faultsage watch to start again.";
  return `Watching ${st.project} since ${since}. ${open}. ${on.join(", ")} on${off.length ? `. ${off.join(", ")} off` : ""}.`;
}

export function LocalShell({
  status,
  onRefresh,
  live,
  disconnected,
}: {
  status: LocalStatus | null;
  onRefresh: () => void;
  live: string;
  disconnected: boolean;
}) {
  async function control(cmd: "pause" | "resume" | "stop") {
    await api(`/api/watch/${cmd}`, { method: "POST" });
    setTimeout(onRefresh, 400);
  }
  return (
    <div className={s.app}>
      <SkipLink />
      <nav className={s.nav} aria-label="Main">
        <Logo to="/" />
        <Nav
          label="Screens"
          items={[
            ["/", "Overview"],
            ["/incidents", "Incidents"],
            ["/pipeline", "Pipeline"],
            ["/scan", "Scan"],
            ["/evaluation", "Evaluation"],
            ["/settings", "Settings"],
          ]}
        />
        <div className={s.navFoot}>
          <span>Local dashboard. Nothing leaves this machine.</span>
        </div>
      </nav>
      <div className={s.main}>
        <div className={s.status}>
          <span>
            {disconnected
              ? "Lost connection to the FaultSage daemon. Is faultsage watch still running?"
              : status
                ? statusSentence(status)
                : "Connecting to the daemon"}
          </span>
          <span className={s.statusActions}>
            {disconnected ? (
              <Button kind="text" onClick={onRefresh}>
                Retry
              </Button>
            ) : null}
            {status?.state === "running" ? (
              <Button kind="text" onClick={() => control("pause")}>
                Pause
              </Button>
            ) : null}
            {status?.state === "paused" ? (
              <Button kind="text" onClick={() => control("resume")}>
                Resume
              </Button>
            ) : null}
            {status && status.state !== "stopped" ? (
              <Button kind="text" onClick={() => control("stop")}>
                Stop
              </Button>
            ) : null}
          </span>
        </div>
        <main id="main" className={s.content}>
          <div className="fs-visually-hidden" aria-live="polite">
            {live}
          </div>
          <Outlet />
        </main>
      </div>
    </div>
  );
}

/* ---- public site (before sign in) -------------------------------------------------------- */

export function PublicShell({ signedIn }: { signedIn: boolean }) {
  return (
    <div className={s.public}>
      <SkipLink />
      <header className={s.topbar}>
        <Logo to="/" />
        <nav className={s.topnav} aria-label="Site">
          <Link to="/how-it-works" className={undefined}>
            How it works
          </Link>
          <Link to="/pricing">Pricing</Link>
          <Link to="/docs">Docs</Link>
          {signedIn ? (
            <LinkButton to="/app">Open dashboard</LinkButton>
          ) : (
            <>
              <Link to="/login">Sign in</Link>
              <span className={s.hideSm}>
                <LinkButton to="/signup" kind="quiet">
                  Create free account
                </LinkButton>
              </span>
            </>
          )}
        </nav>
      </header>
      <main id="main" className={s.publicMain}>
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}

export function Footer() {
  return (
    <footer className={s.footer}>
      <div className={s.footerInner}>
        <span>FaultSage. Free local CLI. Hosted dashboard optional.</span>
        <span className={s.footerLinks}>
          <Link to="/docs">Docs</Link>
          <Link to="/pricing">Pricing</Link>
          <Link to="/privacy">Privacy</Link>
          <Link to="/terms">Terms</Link>
          <Link to="/refunds">Refunds</Link>
          <Link to="/security">Security</Link>
        </span>
      </div>
    </footer>
  );
}

/* ---- cloud app (after sign in) ------------------------------------------------------------ */

export function CloudShell({ me, reload }: { me: Me; reload: () => void }) {
  const nav = useNavigate();
  const [sent, setSent] = useState(false);
  async function signOut() {
    await api("/api/v1/auth/logout", { method: "POST" });
    nav("/login");
    reload();
  }
  return (
    <div className={s.app}>
      <SkipLink />
      <nav className={s.nav} aria-label="Main">
        <Logo to="/app" />
        {me.orgs.length > 1 ? (
          <label>
            <span className="fs-visually-hidden">Workspace</span>
            <select
              className={s.orgSelect}
              value={me.org.id}
              onChange={(e) => {
                setOrg(e.target.value);
                reload();
              }}
            >
              {me.orgs.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <span className={s.orgLine}>{me.org.name}</span>
        )}
        <Nav
          label="Screens"
          items={[
            ["/app", "Projects"],
            ["/app/settings", "Settings"],
            ["/docs", "Docs"],
          ]}
        />
        <div className={s.navFoot}>
          <span>{me.org.plan.name} plan</span>
          <span>{me.user.email}</span>
        </div>
      </nav>
      <div className={s.main}>
        <div className={s.status}>
          <span>
            {me.org.name}: {me.usage.projects} of {me.org.plan.projects} projects,{" "}
            {me.usage.events.toLocaleString()} of {me.org.plan.events_per_month.toLocaleString()} events this
            month.
          </span>
          <span className={s.statusActions}>
            <Button kind="text" onClick={signOut}>
              Sign out
            </Button>
          </span>
        </div>
        <main id="main" className={s.content}>
          {!me.user.email_verified ? (
            <Notice
              tone="warn"
              next={
                sent ? (
                  "Sent. Check your inbox."
                ) : (
                  <Button
                    kind="text"
                    onClick={async () => {
                      await api("/api/v1/auth/resend-verification", { method: "POST" });
                      setSent(true);
                    }}
                  >
                    Send the link again
                  </Button>
                )
              }
            >
              Confirm your email address. We sent a link to {me.user.email}.
            </Notice>
          ) : null}
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export function PageHead({ title, children }: { title: string; children?: ReactNode }) {
  useEffect(() => {
    document.title = `${title} | FaultSage`;
  }, [title]);
  return (
    <header>
      <h1>{title}</h1>
      {children}
    </header>
  );
}
