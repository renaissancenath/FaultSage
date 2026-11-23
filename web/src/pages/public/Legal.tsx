import type { ReactNode } from "react";
import { Link } from "react-router";
import type { Legal as LegalInfo } from "../../api/cloud";
import { Notice } from "../../components/Common";
import { PageHead } from "../../components/Shells";
import s from "./public.module.css";

const UPDATED = "23 November 2026";

function v(value: string, label: string): ReactNode {
  return value ? value : <em>{label} (not set yet)</em>;
}

/** Drafts written for an Indian sole seller of a developer tool. A lawyer must review them. */
function Draft() {
  return (
    <Notice tone="warn">
      Draft written for this project, not legal advice. Have a lawyer review it for your situation before you
      take payments.
    </Notice>
  );
}

function Operator({ legal }: { legal: LegalInfo }) {
  return (
    <table className={s.ledger}>
      <tbody>
        <tr>
          <th scope="row">Service</th>
          <td>FaultSage Cloud (the hosted dashboard)</td>
        </tr>
        <tr>
          <th scope="row">Operated by</th>
          <td>{v(legal.operator_name, "Legal name")}</td>
        </tr>
        <tr>
          <th scope="row">Address</th>
          <td>{v(legal.operator_address, "Postal address")}</td>
        </tr>
        <tr>
          <th scope="row">Grievance Officer</th>
          <td>{v(legal.grievance_officer, "Name")}</td>
        </tr>
        <tr>
          <th scope="row">Grievance email</th>
          <td>{v(legal.grievance_email, "Email")}</td>
        </tr>
      </tbody>
    </table>
  );
}

export function Privacy({ legal }: { legal: LegalInfo }) {
  return (
    <div className={s.prose}>
      <PageHead title="Privacy notice" />
      <p className={s.small}>Last updated {UPDATED}.</p>
      <Draft />
      <h2>Who is responsible</h2>
      <p>
        The operator below is the Data Fiduciary for FaultSage Cloud under India's Digital Personal Data
        Protection Act, 2023, and the controller for users in the EU and UK.
      </p>
      <Operator legal={legal} />
      <h2>What we collect and why</h2>
      <table className={s.ledger}>
        <thead>
          <tr>
            <th scope="col">Data</th>
            <th scope="col">Purpose</th>
            <th scope="col">Basis</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">Email, name, password hash (Argon2id) or GitHub id</th>
            <td>Your account and sign-in</td>
            <td>Your consent and the contract</td>
          </tr>
          <tr>
            <th scope="row">Sign-in sessions, user agent, IP for rate limiting</th>
            <td>Security, stopping abuse</td>
            <td>Legitimate use for security</td>
          </tr>
          <tr>
            <th scope="row">Projects, API key hashes, member roles, audit log</th>
            <td>Running your workspace</td>
            <td>The contract</td>
          </tr>
          <tr>
            <th scope="row">Error events from your app and case files from the CLI</th>
            <td>Showing and triaging failures</td>
            <td>The contract; you choose what to send</td>
          </tr>
          <tr>
            <th scope="row">Plan and usage counts; plan upgrade requests</th>
            <td>Plan limits and billing</td>
            <td>The contract</td>
          </tr>
        </tbody>
      </table>
      <p>
        We do not collect your source files. Error events contain the traceback your app reports, which, as in
        any error monitor, includes the one line of code shown for each frame. Case files synced from the CLI
        contain locations and evidence but no code excerpts or patches; those stay on your machine. The CLI
        and SDK remove secrets, environment values and data values before anything is sent, and the server
        removes them again. We do not sell personal data, show ads, or use analytics or tracking cookies.
      </p>
      <h2>Cookies</h2>
      <p>
        Only essential cookies: a session cookie that keeps you signed in, and a security token that blocks
        cross-site requests. No consent banner is needed for these; there are no others.
      </p>
      <h2>How long we keep it</h2>
      <p>
        Error events: your plan's history period (14 days on Free, 90 on Pro). Account and workspace data:
        until you delete them. Audit records of security events: up to 1 year. Backups roll over within 30
        days.
      </p>
      <h2>Where it is stored</h2>
      <p>
        On our hosting and database providers in {v(legal.hosting_region, "Hosting region")}. If that is
        outside India, data is transferred there only as the law allows.
      </p>
      <h2>Who else processes it</h2>
      <p>
        Our hosting provider, database provider and email provider, only to run the service. If paid plans are
        enabled, the payment provider processes payment details; we never see card numbers.
      </p>
      <h2>Your rights</h2>
      <ul className={s.list}>
        <li>Access a summary of your data and who processed it.</li>
        <li>Correct or update it (most of it in Settings).</li>
        <li>Erase it: Settings, Delete account removes your personal data at once.</li>
        <li>
          Withdraw consent at any time by deleting your account; this does not undo earlier lawful processing.
        </li>
        <li>Nominate someone to exercise your rights if you die or cannot act.</li>
        <li>
          Raise a grievance with the Grievance Officer, and if unresolved, with the Data Protection Board of
          India. EU and UK users may contact their data protection authority.
        </li>
      </ul>
      <p>
        Write to {v(legal.grievance_email, "Grievance email")}. We acknowledge within 24 hours and resolve
        within 15 days.
      </p>
      <h2>Children</h2>
      <p>
        FaultSage Cloud is for people aged 18 or older. We do not knowingly process data of children; if you
        believe a child has an account, contact us and we will delete it.
      </p>
      <h2>Security and breaches</h2>
      <p>
        See the <Link to="/security">security page</Link>. If a personal data breach happens, we will inform
        affected users and the Data Protection Board of India as the law requires.
      </p>
      <h2>Changes</h2>
      <p>
        We will post changes here with a new date, and email account holders about material changes before
        they apply.
      </p>
    </div>
  );
}

export function Terms({ legal }: { legal: LegalInfo }) {
  return (
    <div className={s.prose}>
      <PageHead title="Terms of service" />
      <p className={s.small}>Last updated {UPDATED}.</p>
      <Draft />
      <Operator legal={legal} />
      <h2>1. What these terms cover</h2>
      <p>
        These terms cover FaultSage Cloud and the FaultSage CLI and local dashboard. The CLI and local
        dashboard are free to use on your own projects; the source code is not licensed for copying or reuse.
      </p>
      <h2>2. Your account</h2>
      <p>
        You must be 18 or older and give a valid email address. Keep your password and API keys secret; you
        are responsible for activity under your account. Tell us at once if you suspect misuse.
      </p>
      <h2>3. Acceptable use</h2>
      <p>
        Do not use the service to break the law, to send data you have no right to send, to send secrets or
        sensitive personal data on purpose, to probe or overload it, or to resell it without permission. We
        may suspend accounts that do, after notice where possible.
      </p>
      <h2>4. Your data</h2>
      <p>
        You own what you send. You give us permission to store and process it only to provide the service. Our{" "}
        <Link to="/privacy">privacy notice</Link> explains the details.
      </p>
      <h2>5. Suggestions are suggestions</h2>
      <p>
        Rankings, triage notes, draft tests and patches are evidence-based estimates with a stated certainty.
        They can be wrong. Review every change before you apply or merge it.
      </p>
      <h2>6. Plans, prices and taxes</h2>
      <p>
        The Free plan costs nothing and has the limits shown on the <Link to="/pricing">pricing page</Link>.
        Paid plans, when offered, are billed monthly in advance through our payment provider. Prices include
        or add taxes as shown at checkout. We will give at least 30 days' notice of a price change.
      </p>
      <h2>7. Cancellation and refunds</h2>
      <p>
        See the <Link to="/refunds">refund policy</Link>.
      </p>
      <h2>8. Availability</h2>
      <p>
        We aim to keep the service available but do not promise uninterrupted service, especially on the Free
        plan. Your local FaultSage keeps working if the cloud is down.
      </p>
      <h2>9. Warranty and liability</h2>
      <p>
        To the extent the law allows, the service is provided as is, without warranties of any kind. Our total
        liability for any claim is limited to the amount you paid us in the 12 months before the claim.
        Nothing in these terms limits liability that cannot be limited by law, or your rights under the
        Consumer Protection Act, 2019.
      </p>
      <h2>10. Ending the agreement</h2>
      <p>
        You can delete your account at any time in Settings. We may end or suspend accounts for a serious
        breach of these terms. On closure we delete your data as described in the privacy notice.
      </p>
      <h2>11. Law and disputes</h2>
      <p>
        Indian law applies. Please contact the Grievance Officer first; we acknowledge within 48 hours and aim
        to resolve within 30 days. Courts at {v(legal.jurisdiction_city, "City")}, India, have jurisdiction,
        without taking away rights you have as a consumer where you live.
      </p>
      <h2>12. Changes</h2>
      <p>
        We will post changes here and email account holders about material changes at least 15 days before
        they apply.
      </p>
    </div>
  );
}

export function Refunds({ legal }: { legal: LegalInfo }) {
  return (
    <div className={s.prose}>
      <PageHead title="Cancellation and refunds" />
      <p className={s.small}>Last updated {UPDATED}.</p>
      <Draft />
      <ul className={s.list}>
        <li>The Free plan has no charges.</li>
        <li>
          Cancel a paid plan any time in Settings. It stays active until the end of the period you paid for,
          then returns to Free. No further charges are made.
        </li>
        <li>
          If you are charged by mistake, charged twice, or the paid features did not work for a reason on our
          side, write within 30 days of the charge and we refund it in full.
        </li>
        <li>
          New subscribers can ask for a full refund within 7 days of the first payment, no reason needed.
        </li>
        <li>
          Refunds go back to the original payment method within 7 working days of approval; your bank may take
          longer to show it.
        </li>
      </ul>
      <p>
        Write to {v(legal.grievance_email, "Grievance email")} with your account email and the payment date.
      </p>
      <Operator legal={legal} />
    </div>
  );
}

export function Security({ email }: { email: string }) {
  return (
    <div className={s.prose}>
      <PageHead title="Security" />
      <p>
        Report a vulnerability privately{email ? ` to ${email}` : ""}, or through GitHub private vulnerability
        reporting on the repository. Please include steps to reproduce, the affected version and the impact.
        We acknowledge reports within 7 days.
      </p>
      <h2>How the service protects you</h2>
      <ul className={s.list}>
        <li>
          HTTPS only, Secure and HttpOnly session cookies, CSRF tokens on every change, sessions rotated on
          sign in.
        </li>
        <li>
          Passwords hashed with Argon2id, checked against known breached passwords, with lockout after
          repeated failures.
        </li>
        <li>API keys shown once and stored only as hashes. Revoke them at any time.</li>
        <li>Text from your app is redacted before storage and shown as text, never as HTML.</li>
        <li>Destructive database changes need a named human approval and a backup, every time.</li>
      </ul>
    </div>
  );
}

export function NotFound() {
  return (
    <div className={s.prose}>
      <PageHead title="Page not found" />
      <p>This address does not exist. Check the link, or go back to the start page.</p>
      <p>
        <a href="/">Go to the start page</a>
      </p>
    </div>
  );
}
