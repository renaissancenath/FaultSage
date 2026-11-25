# Selected source

Real files from the private FaultSage repository, chosen to show the languages and the style of the
code without publishing the ranking engine, its trained model or the server. They are copies, not a
runnable project, and the [licence](../LICENSE) does not allow reuse.

| File | Language | What it is |
|---|---|---|
| `python/sdk.py` | Python | The SDK a customer adds to their app: captures unhandled errors, redacts them, sends them in a background thread, never blocks or crashes the app |
| `python/redact.py` | Python | Removes secrets, tokens, emails and data values before anything is stored or sent |
| `notebooks/ranker_results.ipynb` | Jupyter Notebook | The executed model-selection and held-out-results notebook (training cell removed) |
| `web/design/tokens.css` | CSS | The design system: colour, type and spacing tokens for light and dark |
| `web/components/*.tsx`, `*.module.css` | TypeScript, CSS | Two interface components: the button and the certainty label |
| `web/install.ts` | TypeScript | Builds the install command from the site's own address |
| `e2e/journey.mjs` | JavaScript | The 16-step customer journey run in a real browser on every pull request and against the live site |
| `tools/make_sample_project.sh` | Shell | Builds the sample project with a renamed column used in the end-to-end checks |
| `Dockerfile` | Dockerfile | The production image: builds the web app, the CLI installer and the server in one image |
