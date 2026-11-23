import { GithubLogo } from "@phosphor-icons/react";
import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { api } from "../../api/client";
import type { Meta } from "../../api/cloud";
import { Button } from "../../components/Button";
import b from "../../components/Button.module.css";
import { ErrorNotice, Field, Notice, inputClass } from "../../components/Common";
import { PageHead } from "../../components/Shells";
import s from "./public.module.css";

const OAUTH_ERRORS: Record<string, string> = {
  github_off: "GitHub sign in is not set up on this server.",
  github_state: "GitHub sign in expired. Try again.",
  github_denied: "GitHub did not grant access.",
  github_email: "Your GitHub account needs a verified primary email.",
  github_unreachable: "Could not reach GitHub. Try again.",
};

function useForm(onDone: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function submit(e: FormEvent, fn: () => Promise<unknown>) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await fn();
      onDone();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, submit };
}

function GitHubButton({ meta }: { meta: Meta | null }) {
  if (!meta?.github_login) return null;
  return (
    <>
      <div className={s.or}>or</div>
      <a className={b.quiet} href="/api/v1/auth/github/start">
        <GithubLogo size={20} aria-hidden="true" /> Continue with GitHub
      </a>
    </>
  );
}

function AuthPage({ title, children, foot }: { title: string; children: ReactNode; foot?: ReactNode }) {
  return (
    <div className={s.auth}>
      <PageHead title={title} />
      {children}
      {foot ? <p className={s.small}>{foot}</p> : null}
    </div>
  );
}

export function Login({ meta, onSignedIn }: { meta: Meta | null; onSignedIn: () => void }) {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const f = useForm(() => {
    onSignedIn();
    nav("/app");
  });
  const oauthErr = params.get("error");
  return (
    <AuthPage
      title="Sign in"
      foot={
        <>
          No account? <Link to="/signup">Create a free account</Link>.
        </>
      }
    >
      {oauthErr ? <Notice tone="error">{OAUTH_ERRORS[oauthErr] ?? "Sign in failed."}</Notice> : null}
      <ErrorNotice error={f.error} />
      <form
        className={s.authForm}
        onSubmit={(e) => f.submit(e, () => api("/api/v1/auth/login", { json: { email, password } }))}
      >
        <Field label="Email">
          {(id) => (
            <input
              id={id}
              className={inputClass}
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          )}
        </Field>
        <Field label="Password">
          {(id) => (
            <input
              id={id}
              className={inputClass}
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
        </Field>
        <div>
          <Button type="submit" disabled={f.busy}>
            {f.busy ? "Signing in" : "Sign in"}
          </Button>
        </div>
        <Link to="/forgot-password">Forgot your password?</Link>
      </form>
      <GitHubButton meta={meta} />
    </AuthPage>
  );
}

export function Signup({ meta, onSignedIn }: { meta: Meta | null; onSignedIn: () => void }) {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [email, setEmail] = useState(params.get("email") ?? "");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [workspace, setWorkspace] = useState("");
  const f = useForm(() => {
    onSignedIn();
    nav("/app");
  });
  if (meta && !meta.signup_open) {
    return (
      <AuthPage title="Create account">
        <Notice tone="info">Sign up is closed on this server. Ask its operator for an invite.</Notice>
      </AuthPage>
    );
  }
  return (
    <AuthPage
      title="Create your free account"
      foot={
        <>
          Already have an account? <Link to="/login">Sign in</Link>. By creating an account you accept the{" "}
          <Link to="/terms">terms</Link> and <Link to="/privacy">privacy notice</Link>.
        </>
      }
    >
      <ErrorNotice error={f.error} />
      <form
        className={s.authForm}
        onSubmit={(e) =>
          f.submit(e, () => api("/api/v1/auth/signup", { json: { email, password, name, workspace } }))
        }
      >
        <Field label="Email">
          {(id) => (
            <input
              id={id}
              className={inputClass}
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          )}
        </Field>
        <Field label="Your name">
          {(id) => (
            <input
              id={id}
              className={inputClass}
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          )}
        </Field>
        <Field label="Password" hint="At least 12 characters. A short sentence works well.">
          {(id, d) => (
            <input
              id={id}
              aria-describedby={d}
              className={inputClass}
              type="password"
              autoComplete="new-password"
              minLength={12}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
        </Field>
        <Field label="Workspace name" hint="Optional. Usually your team or company.">
          {(id, d) => (
            <input
              id={id}
              aria-describedby={d}
              className={inputClass}
              value={workspace}
              onChange={(e) => setWorkspace(e.target.value)}
            />
          )}
        </Field>
        <div>
          <Button type="submit" disabled={f.busy}>
            {f.busy ? "Creating account" : "Create free account"}
          </Button>
        </div>
      </form>
      <GitHubButton meta={meta} />
    </AuthPage>
  );
}

export function Forgot() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const f = useForm(() => setSent(true));
  return (
    <AuthPage title="Reset your password" foot={<Link to="/login">Back to sign in</Link>}>
      {sent ? (
        <Notice tone="ok">
          If an account uses {email}, a reset link is on its way. It works once and expires in 1 hour.
        </Notice>
      ) : (
        <>
          <ErrorNotice error={f.error} />
          <form
            className={s.authForm}
            onSubmit={(e) => f.submit(e, () => api("/api/v1/auth/forgot-password", { json: { email } }))}
          >
            <Field label="Email">
              {(id) => (
                <input
                  id={id}
                  className={inputClass}
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              )}
            </Field>
            <div>
              <Button type="submit" disabled={f.busy}>
                Send reset link
              </Button>
            </div>
          </form>
        </>
      )}
    </AuthPage>
  );
}

function fragmentToken(): string {
  const m = window.location.hash.match(/token=([\w-]+)/);
  return m?.[1] ?? "";
}

export function Reset({ onSignedIn }: { onSignedIn: () => void }) {
  const nav = useNavigate();
  const [token] = useState(fragmentToken);
  const [password, setPassword] = useState("");
  const f = useForm(() => {
    onSignedIn();
    nav("/app");
  });
  useEffect(() => {
    if (window.location.hash) history.replaceState(null, "", window.location.pathname);
  }, []);
  if (!token)
    return (
      <AuthPage title="Choose a new password">
        <Notice tone="error" next={<Link to="/forgot-password">Ask for a new link</Link>}>
          This link is incomplete.
        </Notice>
      </AuthPage>
    );
  return (
    <AuthPage title="Choose a new password">
      <ErrorNotice error={f.error} />
      <form
        className={s.authForm}
        onSubmit={(e) => f.submit(e, () => api("/api/v1/auth/reset-password", { json: { token, password } }))}
      >
        <Field label="New password" hint="At least 12 characters.">
          {(id, d) => (
            <input
              id={id}
              aria-describedby={d}
              className={inputClass}
              type="password"
              autoComplete="new-password"
              minLength={12}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
        </Field>
        <div>
          <Button type="submit" disabled={f.busy}>
            Save password and sign in
          </Button>
        </div>
      </form>
    </AuthPage>
  );
}

export function Verify() {
  const [state, setState] = useState<"working" | "ok" | "failed">("working");
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    const token = fragmentToken();
    history.replaceState(null, "", window.location.pathname);
    if (!token) {
      setState("failed");
      return;
    }
    api("/api/v1/auth/verify-email", { json: { token } })
      .then(() => setState("ok"))
      .catch((e: unknown) => {
        setError(e);
        setState("failed");
      });
  }, []);
  return (
    <AuthPage title="Confirm your email">
      {state === "working" ? (
        <p>Confirming</p>
      ) : state === "ok" ? (
        <Notice tone="ok" next={<Link to="/app">Open dashboard</Link>}>
          Your email address is confirmed.
        </Notice>
      ) : error ? (
        <ErrorNotice error={error} />
      ) : (
        <Notice tone="error">This link is incomplete. Sign in and ask for a new one.</Notice>
      )}
    </AuthPage>
  );
}
