import type { Meta } from "../../api/cloud";
import { LinkButton } from "../../components/Button";
import { PageHead } from "../../components/Shells";
import s from "./public.module.css";

export function Pricing({ meta }: { meta: Meta | null }) {
  const plans = meta?.plans ?? [];
  return (
    <>
      <PageHead title="Pricing">
        <p className={s.sub}>
          The local CLI and dashboard are free. Plans apply only to the hosted dashboard.
        </p>
      </PageHead>
      <div className={s.plans}>
        {plans.map((p) => (
          <section key={p.id} className={s.plan} aria-labelledby={`plan-${p.id}`}>
            <h2 id={`plan-${p.id}`}>{p.name}</h2>
            <p className={s.price}>{p.price_usd_month === 0 ? "$0" : `$${p.price_usd_month} per month`}</p>
            <table className={s.ledger}>
              <tbody>
                <tr>
                  <th scope="row">Projects</th>
                  <td>{p.projects}</td>
                </tr>
                <tr>
                  <th scope="row">Events per month</th>
                  <td>{p.events_per_month.toLocaleString()}</td>
                </tr>
                <tr>
                  <th scope="row">History kept</th>
                  <td>{p.retention_days} days</td>
                </tr>
                <tr>
                  <th scope="row">Team seats</th>
                  <td>{p.seats}</td>
                </tr>
              </tbody>
            </table>
            <ul className={s.list}>
              {p.features.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
            {p.id === "free" ? (
              <LinkButton to="/signup">Create free account</LinkButton>
            ) : (
              <p className={s.small}>
                {meta?.billing
                  ? "Upgrade from Settings after you sign up."
                  : "Not open yet. Sign up for Free and ask to upgrade from Settings; we will email you when Pro opens."}
              </p>
            )}
          </section>
        ))}
      </div>
      <p className={s.small}>
        Events are production errors and case files received. When a month's limit is reached, new events are
        dropped and counted; your local FaultSage keeps working.
      </p>
    </>
  );
}
