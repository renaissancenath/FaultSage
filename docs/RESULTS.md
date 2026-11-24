# Results: FaultSage

How well FaultSage finds the file that caused a failure, measured on real bugs. Every number here is copied from a run record; brackets are 95% bootstrap intervals.

## Method

- **Data**: [BugsInPy](https://github.com/soarsmu/BugsInPy), real bugs from open-source Python projects, each with the developer's fix and a failing test.
- **Split**: by project, once, before any tuning. **Dev**: pandas, keras, luigi, black, tqdm, httpie, sanic. **Test**: the other ten. The test projects are used only after the model is frozen.
- **Running a case**: the buggy version is checked out in a container, its dependencies installed, and the failing test run with the network off; the fixed version must pass the same test. Cases that do not reproduce are excluded and counted, not hidden.
- **A hit**: the file the developer's fix changed is ranked first (Top-1) or in the top 3 or 5. Test files are never ranked.
- **Baselines**: the top stack frame (the crash line), the most recently changed file, and random order (mean of 20 seeds).

## Held-out test projects

Run `2026-11-24_bugsinpy_test_170310_reanalysed`: 19 reproduced bugs from PySnooper, cookiecutter, thefuck, fastapi and tornado (16 from tornado).

| Method | Top-1 | Top-3 | Top-5 |
|---|---|---|---|
| **FaultSage** | 0.47 [0.26, 0.74] | **0.79** [0.58, 0.95] | **0.84** [0.68, 1.00] |
| Top stack frame | 0.53 [0.32, 0.79] | 0.58 [0.37, 0.79] | 0.58 [0.37, 0.79] |
| Recently changed | 0.11 [0.00, 0.26] | 0.16 [0.00, 0.32] | 0.16 [0.00, 0.32] |
| Random | 0.07 | 0.21 | 0.32 |

- The fixed file is in FaultSage's top 5 for 16 of 19 bugs, against 11 of 19 for the crash line.
- The first guess is about as good as the crash line; the intervals overlap.
- Fix verification (the buggy version fails, the fixed version passes) was correct on 19 of 19.

## Choosing the model (dev only)

Five models over the same seven evidence features, compared by leaving one dev project out at a time (66 dev bugs with candidates):

| Model | Top-1 per bug | Top-1 per project | black | httpie | luigi | tqdm |
|---|---|---|---|---|---|---|
| Logistic regression | 0.55 | 0.58 | 0.91 | 0.50 | 0.28 | 0.62 |
| Gradient boosting | 0.62 | 0.55 | 0.91 | 0.50 | 0.53 | 0.25 |
| Histogram gradient boosting | 0.59 | 0.53 | 0.91 | 0.50 | 0.47 | 0.25 |
| Random forest | 0.67 | 0.57 | 0.91 | 0.50 | 0.62 | 0.25 |
| **Average of logistic regression and random forest** | **0.70** | **0.63** | 0.91 | 0.50 | 0.62 | 0.50 |

The average was best on both summaries, so it was trained on all five dev projects (68 bugs, 986 candidates) and frozen before the single test evaluation. The private repository holds the executed notebook that reproduces this table and checks that retraining gives exactly the shipped model.

## How it got here

| Date | Change | Held-out Top-1 / Top-5 |
|---|---|---|
| 23 Nov 2026 | First model: logistic regression trained on four similar dev projects | 0.11 / 0.58 |
| 24 Nov 2026 | Harness builds old packages that need a C compiler and skips pins deleted from PyPI, so luigi's 32 bugs join the dev set; model chosen by leave-one-project-out on dev | 0.47 / 0.84 |

The first result was published as it was, including that it lost to the crash line. Nothing was tuned on the test projects at any point.

## Limits

- 19 test bugs, mostly from one project: the intervals are wide.
- Most BugsInPy projects still do not install in the harness (long native builds for pandas and keras, network-dependent tests for youtube-dl).
- Coverage-based evidence (Ochiai) is built but not measured here: the benchmark runs do not collect per-test coverage.
