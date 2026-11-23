import { Play } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { api } from "../../api/client";
import type { Approval, CaseFile, Graph, Verification } from "../../api/generated";
import { Button } from "../../components/Button";
import cs from "../../components/CaseFile.module.css";
import { CaseFileView } from "../../components/CaseFileView";
import { PatchDiff } from "../../components/CaseParts";
import { ConfirmDialog, CopyButton, ErrorNotice, Loading, Notice } from "../../components/Common";
import { useApi } from "../../lib/useApi";

const RESULT: Record<string, string> = {
  resolved: "Fixed",
  still_failing: "Still failing",
  new_failures: "Fixed, but new failures appeared",
  timeout: "Verification timed out",
  error: "Verification could not run",
};

function VerifyResult({ v }: { v: Verification }) {
  if (!v.result)
    return (
      <Notice tone="info">Running verification V-{v.id}. Results appear here when pytest finishes.</Notice>
    );
  const tests = v.tests ?? [];
  const passed = tests.filter((t) => t.outcome === "passed").length;
  return (
    <output className={cs.result}>
      <strong>
        {RESULT[v.result] ?? v.result}: {passed} of {tests.length} tests pass.
      </strong>
      <ul className={cs.tests}>
        {tests.map((t) => (
          <li key={t.node_id}>
            <code>
              {t.outcome.padEnd(7, " ")} {t.node_id}
            </code>
          </li>
        ))}
      </ul>
    </output>
  );
}

export function CaseFilePage({ version }: { version: number }) {
  const id = Number(useParams().id);
  const cf = useApi<CaseFile>(`/api/incidents/${id}`, [version]);
  const graph = useApi<Graph>(`/api/graph?kind=imports&focus=${id}`, [version]);
  const [confirm, setConfirm] = useState<null | "apply" | "dismiss">(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [result, setResult] = useState<Approval | null>(null);
  const [verif, setVerif] = useState<Verification | null>(null);

  const last = cf.data?.verifications?.at(-1);
  useEffect(() => {
    if (last) setVerif(last);
  }, [last]);
  useEffect(() => {
    if (!verif || verif.result) return;
    const t = setInterval(async () => {
      const v = await api<Verification>(`/api/verifications/${verif.id}`);
      setVerif(v);
      if (v.result) cf.reload();
    }, 1000);
    return () => clearInterval(t);
  }, [verif, cf.reload]);

  if (cf.error) return <ErrorNotice error={cf.error} />;
  if (!cf.data) return <Loading what="case file" />;
  const data = cf.data;
  const sug = (data.suggestions ?? []).find((x) => x.state === "proposed");

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setErr(null);
    try {
      await fn();
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
      setConfirm(null);
    }
  }

  return (
    <>
      <CaseFileView
        cf={data}
        graph={graph.data ?? null}
        actions={(s) => (
          <>
            {!sug?.patch_diff ? (
              <Button
                onClick={() =>
                  run(async () =>
                    setVerif(await api<Verification>(`/api/incidents/${id}/verify`, { method: "POST" })),
                  )
                }
                disabled={busy || Boolean(verif && !verif.result)}
              >
                <Play size={16} aria-hidden="true" /> Run verification
              </Button>
            ) : (
              <Button onClick={() => setConfirm("apply")}>Apply patch</Button>
            )}
            {s?.patch_diff ? <CopyButton text={s.patch_diff} label="Copy patch" /> : null}
            <a href={`/api/incidents/${id}/export?format=md`} download>
              Export
            </a>
            {data.status === "verified" ? (
              <Button
                kind="text"
                onClick={() =>
                  run(async () => {
                    await api(`/api/incidents/${id}/resolve`, { method: "POST" });
                    cf.reload();
                  })
                }
              >
                Mark resolved
              </Button>
            ) : null}
            {data.status !== "dismissed" ? (
              <Button kind="text" onClick={() => setConfirm("dismiss")}>
                Dismiss incident
              </Button>
            ) : null}
          </>
        )}
        verifyPanel={
          <>
            <ErrorNotice error={err} />
            {result ? (
              <Notice
                tone={result.outcome === "applied" ? "ok" : "warn"}
                next={result.backup_path ? `Backup: ${result.backup_path}` : undefined}
              >
                A-{result.id}: {result.outcome === "applied" ? "Patch applied." : result.outcome_detail}
                {result.outcome === "applied" ? " Next: run verification." : ""}
              </Notice>
            ) : null}
            {verif ? <VerifyResult v={verif} /> : null}
          </>
        }
      />
      {confirm === "apply" && sug?.patch_diff ? (
        <ConfirmDialog
          title={`Apply patch S-${sug.id}`}
          confirmLabel={`Apply patch to ${sug.files?.length ?? 1} file${(sug.files?.length ?? 1) === 1 ? "" : "s"}`}
          busy={busy}
          onCancel={() => setConfirm(null)}
          onConfirm={() =>
            run(async () => {
              setResult(
                await api<Approval>(`/api/suggestions/${sug.id}/approve`, { json: { confirm: true } }),
              );
              cf.reload();
            })
          }
        >
          <p>
            FaultSage writes only these files, after checking they have not changed and your git tree is
            clean. A backup is kept in .faultsage/backups.
          </p>
          <ul>
            {(sug.files ?? []).map((f) => (
              <li key={f}>
                <code>{f}</code>
              </li>
            ))}
          </ul>
          <PatchDiff diff={sug.patch_diff} />
        </ConfirmDialog>
      ) : null}
      {confirm === "dismiss" ? (
        <ConfirmDialog
          title={`Dismiss I-${id}`}
          confirmLabel="Dismiss incident"
          busy={busy}
          onCancel={() => setConfirm(null)}
          onConfirm={() =>
            run(async () => {
              await api(`/api/incidents/${id}/dismiss`, { method: "POST" });
              cf.reload();
            })
          }
        >
          <p>
            The incident is hidden from open lists. Its evidence is kept. If the same failure happens again,
            it opens a new incident.
          </p>
        </ConfirmDialog>
      ) : null}
    </>
  );
}
