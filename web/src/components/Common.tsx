import { Check, Copy } from "@phosphor-icons/react";
import { type ReactNode, useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router";
import { ApiError } from "../api/client";
import { Button } from "./Button";
import s from "./Common.module.css";

export function Logo({ to = "/" }: { to?: string }) {
  return (
    <Link to={to} className={s.logo} aria-label="FaultSage home">
      <LogoMark />
      <span>FaultSage</span>
    </Link>
  );
}

/** A square node with one line leaving it: the root cause and its first edge. */
export function LogoMark() {
  return (
    <svg className={s.mark} viewBox="0 0 32 32" aria-hidden="true">
      <rect x="3" y="3" width="13" height="13" fill="currentColor" />
      <path d="M16 9.5h7.5V29" fill="none" stroke="currentColor" strokeWidth="3" />
    </svg>
  );
}

type Tone = "error" | "warn" | "ok" | "info";
export function Notice({
  tone = "info",
  children,
  next,
}: { tone?: Tone; children: ReactNode; next?: ReactNode }) {
  const cls = { error: s.noticeError, warn: s.noticeWarn, ok: s.noticeOk, info: s.noticeInfo }[tone];
  return (
    <div className={`${s.notice} ${cls}`} role={tone === "error" ? "alert" : "status"}>
      <div>
        <p>{children}</p>
        {next ? <p className={s.next}>{next}</p> : null}
      </div>
    </div>
  );
}

export function ErrorNotice({ error }: { error: unknown }) {
  if (!error) return null;
  if (error instanceof ApiError)
    return (
      <Notice tone="error" next={error.nextStep || undefined}>
        {error.message}
      </Notice>
    );
  return <Notice tone="error">Lost connection to the server. Check that it is running, then reload.</Notice>;
}

export function EmptyState({ children, command }: { children: ReactNode; command?: string }) {
  return (
    <div className={s.empty}>
      <p>{children}</p>
      {command ? <Command text={command} /> : null}
    </div>
  );
}

export function Loading({ what }: { what: string }) {
  return <p className={s.loading}>Loading {what}</p>;
}

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <Button
      kind="text"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          setTimeout(() => setDone(false), 2000);
        } catch {
          setDone(false);
        }
      }}
    >
      {done ? <Check size={16} aria-hidden="true" /> : <Copy size={16} aria-hidden="true" />}
      {done ? "Copied" : label}
    </Button>
  );
}

export function Command({ text }: { text: string }) {
  return (
    <div className={s.cmd}>
      <code tabIndex={0}>{text}</code>
      <CopyButton text={text} />
    </div>
  );
}

interface FieldProps {
  label: string;
  hint?: string;
  error?: string;
  children: (id: string, describedBy: string | undefined) => ReactNode;
}
export function Field({ label, hint, error, children }: FieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className={s.field}>
      <label className={s.label} htmlFor={id}>
        {label}
      </label>
      {children(id, hint || error ? hintId : undefined)}
      {error ? (
        <span id={hintId} className={s.error}>
          {error}
        </span>
      ) : hint ? (
        <span id={hintId} className={s.hint}>
          {hint}
        </span>
      ) : null}
    </div>
  );
}

export const inputClass = s.input;
export const selectClass = s.select;
export const kvClass = s.kv;

/** The only modal: shows exactly what will change and needs an explicit confirm (LR-8). */
export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  onConfirm,
  onCancel,
  busy,
  confirmDisabled,
}: {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  busy?: boolean;
  confirmDisabled?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    const first = ref.current?.querySelector<HTMLElement>("button, input, textarea, select, a[href]");
    first?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onCancel();
      if (e.key === "Tab" && ref.current) {
        const f = Array.from(
          ref.current.querySelectorAll<HTMLElement>(
            "button:not(:disabled), input, textarea, select, a[href]",
          ),
        );
        if (f.length === 0) return;
        const a = f[0] as HTMLElement;
        const z = f[f.length - 1] as HTMLElement;
        if (e.shiftKey && document.activeElement === a) {
          e.preventDefault();
          z.focus();
        } else if (!e.shiftKey && document.activeElement === z) {
          e.preventDefault();
          a.focus();
        }
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      prev?.focus();
    };
  }, [onCancel]);
  return (
    <div className={s.dialogBackdrop}>
      <dialog open className={s.dialog} aria-modal="true" aria-labelledby={titleId} ref={ref}>
        <h2 id={titleId}>{title}</h2>
        {children}
        <div className={s.dialogActions}>
          <Button onClick={onConfirm} disabled={busy || confirmDisabled}>
            {busy ? "Working" : confirmLabel}
          </Button>
          <Button kind="text" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </dialog>
    </div>
  );
}
