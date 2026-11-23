import { Link } from "react-router";
import { LinkButton } from "../../components/Button";
import { Command } from "../../components/Common";
import { PageHead } from "../../components/Shells";
import s from "./public.module.css";

export function Landing({ signedIn }: { signedIn: boolean }) {
  return (
    <>
      <div className="fs-visually-hidden">
        <PageHead title="Find the line that broke your Python project" />
      </div>
      <section className={s.hero} aria-labelledby="hero">
        <div className={s.heroText}>
          <h2 id="hero" className={s.headline}>
            Find the line that broke your Python project, and what else it broke.
          </h2>
          <p className={s.sub}>
            FaultSage is a free, local CLI and dashboard. It ranks likely causes with evidence, maps the blast
            radius and checks your fix. The hosted dashboard adds team history and catches errors from your
            deployed app.
          </p>
          <div className={s.cta}>
            {signedIn ? (
              <LinkButton to="/app">Open dashboard</LinkButton>
            ) : (
              <LinkButton to="/signup">Create free account</LinkButton>
            )}
            <Link to="/how-it-works">Read how it works</Link>
          </div>
        </div>
        <figure className={s.heroShot}>
          <img
            src="/screens/case-file.png"
            width="1440"
            height="900"
            alt="FaultSage case file: test_fit failed with KeyError transaction_amount. Top cause, rated Possible: clean.py line 4 renamed the column to amount."
          />
          <figcaption>
            The case file for a renamed column, from a sample project. Screenshot of the real dashboard.
          </figcaption>
        </figure>
      </section>

      <section className={s.section} aria-labelledby="how">
        <h2 id="how">How it works</h2>
        <ol className={s.steps}>
          <li>
            <span>Install it in your project's virtual environment and connect the project.</span>
            <Command
              text={
                "pip install https://github.com/renaissancenath/FaultSage/releases/download/v0.1.0/faultsage-0.1.0-py3-none-any.whl && faultsage init"
              }
            />
          </li>
          <li>
            <span>Keep it watching while you work. Failing tests and scripts become case files.</span>
            <Command text="faultsage watch" />
          </li>
          <li>
            <span>
              Read the ranked causes, apply the suggested patch after you approve it, and check the fix.
            </span>
            <Command text="faultsage verify I-1" />
          </li>
        </ol>
      </section>

      <section className={s.section} aria-labelledby="where">
        <h2 id="where">What runs where</h2>
        <table className={s.ledger}>
          <thead>
            <tr>
              <th scope="col">Part</th>
              <th scope="col">Runs on</th>
              <th scope="col">What it sees</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">CLI, analysis, patch apply, verification</th>
              <td>Your machine</td>
              <td>Your code. It never leaves the machine.</td>
            </tr>
            <tr>
              <th scope="row">Local dashboard</th>
              <td>127.0.0.1 on your machine</td>
              <td>Your incidents, only in your browser.</td>
            </tr>
            <tr>
              <th scope="row">Hosted dashboard (optional)</th>
              <td>FaultSage Cloud</td>
              <td>Redacted case files you push, and errors your deployed app sends.</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section className={s.section} aria-labelledby="results">
        <h2 id="results">How accurate is it</h2>
        <p>
          Measured on real bugs from open-source projects (BugsInPy) that the ranker never saw while it was
          tuned. In the first test run (19 reproduced bugs, run 2026-11-23_bugsinpy_test_090824) the true file
          was in FaultSage's top 5 for 58% of bugs, the same as the top stack frame, but its first guess was
          right only 11% of the time against 53% for the top stack frame. Ranking is being improved; every
          number comes from a run record you can rerun.
        </p>
        <Link to="/docs#evaluation">Read the evaluation method</Link>
      </section>
    </>
  );
}
