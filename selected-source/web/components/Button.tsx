import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router";
import s from "./Button.module.css";

type Kind = "primary" | "text" | "quiet";
interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  kind?: Kind;
  danger?: boolean;
  children: ReactNode;
}

/** One primary per screen. Others are text buttons or quiet buttons. Hover is an instant step. */
export function Button({ kind = "primary", danger, className, type = "button", children, ...rest }: Props) {
  return (
    <button type={type} className={`${s[kind]} ${danger ? s.danger : ""} ${className ?? ""}`} {...rest}>
      {children}
    </button>
  );
}

export function LinkButton({
  to,
  kind = "primary",
  children,
}: { to: string; kind?: Kind; children: ReactNode }) {
  if (/^https?:/.test(to)) {
    return (
      <a href={to} className={s[kind]} rel="noopener noreferrer">
        {children}
      </a>
    );
  }
  return (
    <Link to={to} className={s[kind]}>
      {children}
    </Link>
  );
}
