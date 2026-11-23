# Evaluation

Every number below is copied from a run record. File-level localisation on BugsInPy: a case counts as a hit when a file the developer's fix changed is in the top k. Test files are excluded from every ranking.

**Test split, run `2026-11-23_bugsinpy_test_090824`** (`results/runs/2026-11-23_bugsinpy_test_090824/run.json`): projects PySnooper, cookiecutter, thefuck, fastapi, tornado. Attempted 71, **reproduced 19** (16 of them from tornado), excluded 52 (fixed version still fails 6, dependency install failed 46). Brackets are 95% bootstrap intervals; with 19 cases they are wide.

| Method | Top-1 | Top-3 | Top-5 |
|---|---|---|---|
| FaultSage (weights trained on dev) | 0.11 [0.00, 0.26] | 0.37 [0.16, 0.58] | 0.58 [0.37, 0.79] |
| Top stack frame | 0.53 [0.32, 0.79] | 0.58 [0.37, 0.79] | 0.58 [0.37, 0.79] |
| Recently changed | 0.11 [0.00, 0.26] | 0.16 [0.00, 0.32] | 0.16 [0.00, 0.32] |
| Random (mean of 20 seeds) | 0.07 [0.05, 0.09] | 0.21 [0.15, 0.26] | 0.33 [0.25, 0.41] |

What this says, plainly:

- On projects it never saw, FaultSage's Top-1 (0.11) is far below the top stack frame (0.53). It only matches that baseline at Top-5. The recency weight learned on the dev projects did not carry over to tornado.
- The "Strong" label was right on 1 of 8 test cases (12.5%), against 76% on dev. It is therefore switched off: the top cause is shown as Possible until a new held-out run shows Strong is right at least 75% of the time (D-024).
- Verification was correct on all 19 reproduced cases (buggy fails, fixed passes).
- Blast radius: test precision 0.01, recall 0.32. Precision is poor.

Dev split (used for tuning, so optimistic): run `2026-11-23_bugsinpy_dev_090659_reanalysed` on 36 reproduced cases from black, tqdm, httpie and sanic: FaultSage Top-1 0.72, top stack frame 0.17, recently changed 0.64.

Not run: pandas, keras, matplotlib, spacy (long native builds), ansible (size), youtube-dl (tests need network); luigi, thefuck and most fastapi cases did not install because pinned packages are gone from PyPI or old pip crashes. Reproduce with `faultsage bench run bugsinpy --split test --projects ...`; the protocol is in `docs/TESTING.md`.

## Later experiment (not a new result)

A `top_frame` feature (the innermost frame outside test code) was added and the ranker retrained on the dev split only. Dev Top-1 stayed at 0.72, because on the dev projects the top frame is right in only 17% of cases, so training kept favouring recency. The change was reverted and the test split was not used again. The next step is more varied dev projects, not more training on the same four.

## Would a bigger model help? (dev only)

Leave-one-project-out on the dev run `2026-11-23_bugsinpy_dev_090659_reanalysed` (34 cases with candidates from black, httpie and tqdm): train on two projects, score Top-1 on the third, repeat. This estimates accuracy on unseen projects without touching the test split.

| Model (scikit-learn 1.5.2) | Top-1 on the held-out dev project |
|---|---|
| Logistic regression (current) | **0.76** |
| Gradient boosting, 200 trees | 0.68 |
| Histogram gradient boosting | 0.62 |
| Random forest, 500 trees | 0.62 |
| Recently changed (baseline) | 0.68 |
| Top stack frame (baseline) | 0.18 |

Larger models do worse on projects they did not train on: with 34 cases, 22 of them from one project, they learn that project's habits. The ranker stays logistic regression. Accuracy will come from more and more varied training projects, not from a larger model.
