import { Link } from "react-router";
import { Command } from "../../components/Common";
import { PageHead } from "../../components/Shells";
import s from "./public.module.css";

const SDK = `# pip install https://github.com/renaissancenath/FaultSage/releases/download/v0.1.0/faultsage-0.1.0-py3-none-any.whl
import os
import faultsage.sdk as fs

fs.init(
    api_key=os.environ["FAULTSAGE_API_KEY"],   # Project settings > API keys
    url=os.environ["FAULTSAGE_URL"],           # your FaultSage Cloud address
    environment="production",
    release=os.environ.get("APP_VERSION", ""),
)

# FastAPI or any ASGI app
from fastapi import FastAPI
app = FastAPI()
app.add_middleware(fs.ASGIMiddleware)          # or: app = fs.ASGIMiddleware(app)

# Anywhere else
try:
    risky()
except Exception as exc:
    fs.capture_exception(exc, job="nightly-import")
    raise`;

const PIPE = `[[step]]
name = "clean"
command = ["python", "-m", "pipeline.clean"]
inputs = ["raw_transactions"]
outputs = ["clean_transactions"]`;

export function Docs() {
  return (
    <div className={s.prose}>
      <PageHead title="Docs" />
      <nav className={s.toc} aria-label="On this page">
        <a href="#install">Install</a>
        <a href="#watch">Watch a project</a>
        <a href="#fix">Apply and verify</a>
        <a href="#pipeline">Pipelines</a>
        <a href="#cloud">Hosted dashboard</a>
        <a href="#sdk">Production errors</a>
        <a href="#evaluation">Evaluation</a>
        <a href="#data">Your data</a>
      </nav>
      <h2 id="install">Install</h2>
      <p>
        Inside your project's virtual environment (Windows PowerShell shown; bash is the same without the
        Activate line):
      </p>
      <Command text=".\.venv\Scripts\Activate.ps1" />
      <Command
        text={
          "python -m pip install https://github.com/renaissancenath/FaultSage/releases/download/v0.1.0/faultsage-0.1.0-py3-none-any.whl"
        }
      />
      <Command text="faultsage init" />
      <p>
        Init detects sources, tests, dependency files and git, and writes .faultsage/config.toml. Edit that
        file to turn signals on or off.
      </p>
      <h2 id="watch">Watch a project</h2>
      <Command text="faultsage watch" />
      <p>
        This starts the local dashboard at http://127.0.0.1:8765 and opens it. Then work as usual: run pytest,
        or wrap scripts with faultsage run.
      </p>
      <Command text="faultsage run -- python -m mypipeline" />
      <h2 id="fix">Apply and verify</h2>
      <p>
        Open the case file, read the causes, and click Apply patch. The dialog shows the full diff. FaultSage
        checks the file has not changed, that git is clean, writes a backup, then applies. In the terminal:
      </p>
      <Command text="faultsage apply S-1" />
      <Command text="faultsage verify I-1" />
      <h2 id="pipeline">Pipelines</h2>
      <p>
        Declare steps in .faultsage/pipeline.toml, and record schemas at step boundaries with
        faultsage.checkpoint(df, step="clean"). Only column names, types and shapes are stored.
      </p>
      <pre tabIndex={0}>{PIPE}</pre>
      <h2 id="cloud">Hosted dashboard</h2>
      <p>
        Create a project in the hosted dashboard, create an API key in its settings, then connect the CLI.
        Case files are redacted before they leave your machine; source files never do.
      </p>
      <Command text="faultsage cloud login --url https://your-faultsage.example.com" />
      <Command text="faultsage cloud push all" />
      <h2 id="sdk">Production errors</h2>
      <p>
        Errors that only happen in your deployed app are captured by the SDK, grouped into issues, and
        triaged. Each issue gets a likely location, a draft regression test and a prompt you can give your
        coding agent to open a fix pull request for you to review.
      </p>
      <pre tabIndex={0}>{SDK}</pre>
      <h2 id="evaluation">Evaluation</h2>
      <p>
        FaultSage is measured on BugsInPy, real bugs with the developer's fix and failing tests, split by
        project so tuning never sees the test projects. Every run records attempted, reproduced and excluded
        cases and compares against random, top stack frame, Ochiai and recently changed baselines. Numbers are
        only published from a test-split run record.
      </p>
      <Command text="faultsage bench run bugsinpy --split dev" />
      <h2 id="data">Your data</h2>
      <p>
        Secrets, environment values and data values are never stored. Text is redacted before storage, display
        or export. Read the <Link to="/privacy">privacy notice</Link> and the{" "}
        <Link to="/security">security page</Link>.
      </p>
    </div>
  );
}
