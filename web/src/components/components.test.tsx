import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CodeExcerpt, PatchDiff } from "./CaseParts";
import { DataTable } from "./DataTable";
import { CertaintyMarker, StatusMarker } from "./Markers";

afterEach(cleanup);

describe("markers", () => {
  it("always show the certainty word, never colour alone", () => {
    const cases: [string, string][] = [
      ["confirmed", "Confirmed"],
      ["strong", "Strong"],
      ["possible", "Possible"],
      ["unknown", "Unknown"],
    ];
    for (const [v, word] of cases) {
      render(<CertaintyMarker value={v} />);
      expect(screen.getByText(word)).toBeTruthy();
    }
  });
  it("status marker has a word", () => {
    render(<StatusMarker value="not_run" />);
    expect(screen.getByText("not run")).toBeTruthy();
  });
});

describe("untrusted text renders as text (SR-17)", () => {
  const xss = '<img src=x onerror="alert(1)"><script>alert(2)</script>';
  it("code excerpt", () => {
    const { container } = render(
      <CodeExcerpt
        loc={{
          file_path: "a.py",
          line: 2,
          available: true,
          excerpt: [
            [1, "ok"],
            [2, xss],
          ],
        }}
      />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByText(xss)).toBeTruthy();
    expect(container.querySelector('[aria-current="true"]')?.textContent).toContain(xss);
  });
  it("patch diff", () => {
    const { container } = render(<PatchDiff diff={`+${xss}\n`} />);
    expect(container.querySelector("img")).toBeNull();
  });
  it("missing line says so instead of guessing", () => {
    render(<CodeExcerpt loc={{ file_path: "gone.py", line: null, available: false }} />);
    expect(screen.getByText(/line not available/)).toBeTruthy();
  });
});

describe("data table", () => {
  type Row = { id: number; n: string };
  const rows: Row[] = [
    { id: 2, n: "b" },
    { id: 1, n: "a" },
  ];
  const cols = [{ key: "n", header: "Name", render: (r: Row) => r.n, sortValue: (r: Row) => r.n }];
  it("sorts by a column and shows the empty state", () => {
    const { container } = render(
      <DataTable label="t" columns={cols} rows={rows} rowKey={(r) => r.id} empty="Nothing" />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Name/ }));
    expect([...container.querySelectorAll("tbody td")].map((td) => td.textContent)).toEqual(["a", "b"]);
    cleanup();
    render(<DataTable label="t" columns={cols} rows={[]} rowKey={(r) => r.id} empty="Nothing here" />);
    expect(screen.getByText("Nothing here")).toBeTruthy();
  });
  it("Enter opens the focused row", () => {
    let opened = 0;
    const { container } = render(
      <DataTable
        label="t"
        columns={cols}
        rows={rows}
        rowKey={(r) => r.id}
        onOpen={(r) => {
          opened = r.id;
        }}
        empty=""
      />,
    );
    const first = container.querySelector("tbody tr") as HTMLElement;
    fireEvent.keyDown(first, { key: "Enter" });
    expect(opened).toBe(2);
  });
});
