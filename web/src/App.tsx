import { useCallback, useEffect, useRef, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { ApiError, api, detectMode, exchangeLocalToken, setMode } from "./api/client";
import type { Me, Meta } from "./api/cloud";
import { ErrorNotice, Loading, Notice } from "./components/Common";
import { CloudShell, LocalShell, type LocalStatus, PublicShell } from "./components/Shells";
import { AccountSettings } from "./pages/app/AccountSettings";
import { Home } from "./pages/app/Home";
import { CloudCaseFile, Issue } from "./pages/app/Issue";
import { Project } from "./pages/app/Project";
import { CaseFilePage } from "./pages/local/CaseFilePage";
import { Evaluation } from "./pages/local/Evaluation";
import { Incidents } from "./pages/local/Incidents";
import { Overview } from "./pages/local/Overview";
import { Pipeline } from "./pages/local/Pipeline";
import { Scan } from "./pages/local/Scan";
import { Settings } from "./pages/local/Settings";
import { Forgot, Login, Reset, Signup, Verify } from "./pages/public/Auth";
import { Docs } from "./pages/public/Docs";
import { HowItWorks } from "./pages/public/HowItWorks";
import { Landing } from "./pages/public/Landing";
import { NotFound, Privacy, Refunds, Security, Terms } from "./pages/public/Legal";
import { Pricing } from "./pages/public/Pricing";

export function App() {
  const [mode, setM] = useState<"local" | "cloud" | null>(null);
  const [meta, setMeta] = useState<Record<string, unknown> | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    detectMode()
      .then(({ mode, meta }) => {
        setMode(mode);
        setM(mode);
        setMeta(meta);
      })
      .catch(() => setFailed(true));
  }, []);
  if (failed)
    return (
      <main id="main">
        <Notice tone="error" next="Is faultsage watch (or the cloud server) running?">
          Lost connection to the FaultSage server.
        </Notice>
      </main>
    );
  if (!mode)
    return (
      <main id="main">
        <Loading what="FaultSage" />
      </main>
    );
  return (
    <BrowserRouter>
      {mode === "local" ? <LocalApp /> : <CloudApp meta={meta as unknown as Meta} />}
    </BrowserRouter>
  );
}

/* ---- local dashboard ---------------------------------------------------------------------- */

function LocalApp() {
  const [status, setStatus] = useState<LocalStatus | null>(null);
  const [authError, setAuthError] = useState<unknown>(null);
  const [disconnected, setDisconnected] = useState(false);
  const [version, setVersion] = useState(0);
  const [live, setLive] = useState("");
  const [ready, setReady] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const refresh = useCallback(async () => {
    try {
      setStatus(await api<LocalStatus>("/api/status"));
      setDisconnected(false);
      setAuthError(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setAuthError(e);
      else setDisconnected(true);
    }
  }, []);

  useEffect(() => {
    exchangeLocalToken()
      .catch((e: unknown) => setAuthError(e))
      .finally(() => {
        setReady(true);
        refresh();
      });
  }, [refresh]);

  useEffect(() => {
    if (!ready || authError) return;
    let closed = false;
    function connect() {
      const ws = new WebSocket(`ws://${window.location.host}/ws/events`);
      wsRef.current = ws;
      ws.onmessage = (m) => {
        const ev = JSON.parse(String(m.data)) as {
          type: string;
          payload: { id?: number; title?: string; status?: string };
        };
        if (ev.type === "incident.created" && ev.payload.id)
          setLive(`New incident I-${ev.payload.id}: ${ev.payload.title ?? ""}`);
        setVersion((v) => v + 1);
        refresh();
      };
      ws.onclose = () => {
        if (!closed) setTimeout(connect, 3000);
      };
    }
    connect();
    const poll = setInterval(refresh, 10000);
    return () => {
      closed = true;
      wsRef.current?.close();
      clearInterval(poll);
    };
  }, [ready, authError, refresh]);

  if (!ready) return <Loading what="dashboard" />;
  if (authError) {
    return (
      <main id="main">
        <ErrorNotice
          error={
            authError instanceof ApiError
              ? authError
              : new ApiError(
                  401,
                  "unauthorised",
                  "Not signed in to this dashboard.",
                  "Run faultsage dashboard to open a new link.",
                )
          }
        />
      </main>
    );
  }
  return (
    <Routes>
      <Route
        element={<LocalShell status={status} onRefresh={refresh} live={live} disconnected={disconnected} />}
      >
        <Route index element={<Overview status={status} version={version} />} />
        <Route path="incidents" element={<Incidents version={version} />} />
        <Route path="incidents/:id" element={<CaseFilePage version={version} />} />
        <Route path="pipeline" element={<Pipeline version={version} />} />
        <Route path="scan" element={<Scan />} />
        <Route path="evaluation" element={<Evaluation />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

/* ---- cloud: public site and signed-in app -------------------------------------------------- */

function CloudApp({ meta }: { meta: Meta }) {
  const [me, setMe] = useState<Me | null>(null);
  const [checked, setChecked] = useState(false);
  const loadMe = useCallback(async () => {
    try {
      setMe(await api<Me>("/api/v1/me"));
    } catch {
      setMe(null);
    } finally {
      setChecked(true);
    }
  }, []);
  useEffect(() => {
    loadMe();
  }, [loadMe]);
  if (!checked) return <Loading what="FaultSage" />;
  const email = meta.support_email;
  const guard = (el: JSX.Element) => (me ? el : <Navigate to="/login" replace />);
  return (
    <Routes>
      <Route element={<PublicShell signedIn={Boolean(me)} />}>
        <Route index element={<Landing signedIn={Boolean(me)} />} />
        <Route path="how-it-works" element={<HowItWorks />} />
        <Route path="pricing" element={<Pricing meta={meta} />} />
        <Route path="docs" element={<Docs />} />
        <Route path="privacy" element={<Privacy legal={meta.legal} />} />
        <Route path="terms" element={<Terms legal={meta.legal} />} />
        <Route path="refunds" element={<Refunds legal={meta.legal} />} />
        <Route path="security" element={<Security email={email} />} />
        <Route
          path="login"
          element={me ? <Navigate to="/app" replace /> : <Login meta={meta} onSignedIn={loadMe} />}
        />
        <Route
          path="signup"
          element={me ? <Navigate to="/app" replace /> : <Signup meta={meta} onSignedIn={loadMe} />}
        />
        <Route path="forgot-password" element={<Forgot />} />
        <Route path="reset-password" element={<Reset onSignedIn={loadMe} />} />
        <Route path="verify-email" element={<Verify />} />
        <Route path="*" element={<NotFound />} />
      </Route>
      <Route path="app" element={guard(<CloudShell me={me as Me} reload={loadMe} />)}>
        <Route index element={me ? <Home me={me} onChange={loadMe} /> : null} />
        <Route path="projects/:pid" element={me ? <Project me={me} /> : null} />
        <Route path="projects/:pid/issues/:iid" element={me ? <Issue me={me} /> : null} />
        <Route path="projects/:pid/case-files/:cid" element={<CloudCaseFile />} />
        <Route
          path="settings"
          element={me ? <AccountSettings me={me} meta={meta} reload={loadMe} /> : null}
        />
      </Route>
    </Routes>
  );
}
