import { CertaintyMarker } from "../../components/Markers";
import { PageHead } from "../../components/Shells";
import s from "./public.module.css";

export function HowItWorks() {
  return (
    <div className={s.prose}>
      <PageHead title="How FaultSage finds the cause" />
      <p>
        A traceback tells you where the program stopped. FaultSage collects the other evidence a developer
        would check by hand, and ranks the places that could have caused the failure.
      </p>
      <h2>Evidence it uses</h2>
      <table className={s.ledger}>
        <tbody>
          <tr>
            <th scope="row">Traceback</th>
            <td>Project frames only, innermost first. Library frames are context, not causes.</td>
          </tr>
          <tr>
            <th scope="row">Git</th>
            <td>Lines changed since the last passing run, and how long ago.</td>
          </tr>
          <tr>
            <th scope="row">Pipeline checkpoints</th>
            <td>Column names and types at each step, never values. Shows where a column disappeared.</td>
          </tr>
          <tr>
            <th scope="row">Coverage</th>
            <td>
              Lines run mostly by failing tests (Ochiai score), when you run pytest with coverage contexts.
            </td>
          </tr>
          <tr>
            <th scope="row">Import graph</th>
            <td>How far a candidate is from the failing test, and what depends on it.</td>
          </tr>
          <tr>
            <th scope="row">History</th>
            <td>Earlier incidents at the same place.</td>
          </tr>
        </tbody>
      </table>
      <h2>How sure it is</h2>
      <p>Every claim carries one of four labels, so you know how much to trust it.</p>
      <table className={s.ledger}>
        <tbody>
          <tr>
            <th scope="row">
              <CertaintyMarker value="confirmed" />
            </th>
            <td>
              Observed directly: the exception, the line that raised it, a column missing in a checkpoint.
            </td>
          </tr>
          <tr>
            <th scope="row">
              <CertaintyMarker value="strong" />
            </th>
            <td>
              Top candidate, clearly ahead of the next, with two or more independent kinds of evidence and
              nothing against it. Not shown at the moment: on projects it had never seen, this label was right
              too rarely, so the top cause is labelled Possible until a new benchmark run earns it back.
            </td>
          </tr>
          <tr>
            <th scope="row">
              <CertaintyMarker value="possible" />
            </th>
            <td>Some evidence points here.</td>
          </tr>
          <tr>
            <th scope="row">
              <CertaintyMarker value="unknown" />
            </th>
            <td>Not enough evidence. FaultSage says what is missing instead of guessing.</td>
          </tr>
        </tbody>
      </table>
      <h2>Changes need your approval</h2>
      <p>
        FaultSage never edits your files by itself. A patch is applied only after you confirm it in the
        dashboard or type the confirmation in the terminal, only if the file has not changed and your git tree
        is clean, and only after a backup is written.
      </p>
      <h2>Errors from your deployed app</h2>
      <p>
        Add the FaultSage SDK to your app. Unhandled errors are redacted on your server, sent to your hosted
        dashboard, grouped, and given a triage note with a draft regression test and a prompt for your coding
        agent. You review the fix; nothing is merged for you.
      </p>
    </div>
  );
}
