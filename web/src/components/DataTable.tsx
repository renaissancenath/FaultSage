import { type KeyboardEvent, type ReactNode, useMemo, useRef, useState } from "react";
import s from "./DataTable.module.css";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  sortValue?: (row: T) => string | number;
  kind?: "text" | "mono" | "num";
}

interface Props<T> {
  label: string;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  onOpen?: (row: T) => void;
  empty: ReactNode;
}

/** Rules not cards. Arrow keys move row focus, Enter opens (UI brief 4.2). */
export function DataTable<T>({ label, columns, rows, rowKey, onOpen, empty }: Props<T>) {
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);
  const body = useRef<HTMLTableSectionElement>(null);
  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sortValue) return rows;
    const get = col.sortValue;
    return [...rows].sort((a, b) => (get(a) > get(b) ? 1 : get(a) < get(b) ? -1 : 0) * sort.dir);
  }, [rows, sort, columns]);

  function onKey(e: KeyboardEvent<HTMLTableRowElement>, row: T) {
    const rowsEls = Array.from(body.current?.querySelectorAll<HTMLTableRowElement>("tr[tabindex]") ?? []);
    const i = rowsEls.indexOf(e.currentTarget);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      rowsEls[Math.min(i + 1, rowsEls.length - 1)]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      rowsEls[Math.max(i - 1, 0)]?.focus();
    } else if (e.key === "Enter" && onOpen) {
      onOpen(row);
    }
  }

  return (
    <div className={s.root}>
      <p className={s.hint}>Scroll sideways for more columns.</p>
      <section className={s.wrap} aria-label={`${label} table`} tabIndex={0}>
        <table className={s.table} aria-label={label}>
          <thead>
            <tr>
              {columns.map((c) => (
                <th
                  key={c.key}
                  scope="col"
                  className={c.kind === "num" ? s.num : undefined}
                  aria-sort={sort?.key === c.key ? (sort.dir === 1 ? "ascending" : "descending") : undefined}
                >
                  {c.sortValue ? (
                    <button
                      type="button"
                      className={s.sort}
                      onClick={() =>
                        setSort((p) => ({ key: c.key, dir: p?.key === c.key && p.dir === 1 ? -1 : 1 }))
                      }
                    >
                      {c.header}
                      <span aria-hidden="true">
                        {sort?.key === c.key ? (sort.dir === 1 ? "↑" : "↓") : ""}
                      </span>
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody ref={body}>
            {sorted.length === 0 ? (
              <tr className={s.emptyRow}>
                <td colSpan={columns.length}>{empty}</td>
              </tr>
            ) : (
              sorted.map((row) => (
                <tr
                  key={rowKey(row)}
                  className={onOpen ? s.row : undefined}
                  tabIndex={onOpen ? 0 : undefined}
                  onClick={onOpen ? () => onOpen(row) : undefined}
                  onKeyDown={onOpen ? (e) => onKey(e, row) : undefined}
                >
                  {columns.map((c) => (
                    <td
                      key={c.key}
                      className={c.kind === "mono" ? s.mono : c.kind === "num" ? s.num : undefined}
                    >
                      {c.render(row)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
