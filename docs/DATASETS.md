# FaultSage: Datasets and Evaluation Data

Rule: every reported number comes from real bugs in real projects. No synthetic data, no injected faults, no demo projects in any metric.

---

## 1. Datasets

| Dataset | What it contains | Used for | Ground truth | Source |
|---|---|---|---|---|
| **BugsInPy** (main) | 493 real bugs from 17 open-source Python projects (pandas, keras, luigi, scrapy, matplotlib, fastapi, black and others). Each bug: buggy and fixed commit ids, the developer's patch, failing test(s), setup scripts | Detection, file/function localisation, ranking, blast radius, verification | Lines changed by the developer's fix; tests failing on buggy and passing on fixed version | Paper arXiv:2401.15481; repository `soarsmu/BugsInPy` on GitHub |
| **JunoBench** | 111 reproducible crashes from public Kaggle ML notebooks, each with a verified fix | ML and data pipeline failures (missing columns, shape mismatches, library misuse) | Verified fix and crash location | Paper arXiv:2510.18013, dataset linked from the paper |
| **LogSage dataset** | 367 real CI/CD failures from GitHub repositories with annotated key log evidence | Log-based root cause evidence | Annotated log lines | Paper arXiv:2506.03691 |
| **LogChunks** | 797 Travis CI build logs from 80 repositories with a manually labelled chunk explaining the failure, validated with the developers | Log evidence retrieval | Labelled chunk | Zenodo DOI 10.5281/zenodo.3632351 |
| SWE-bench Verified (optional, later) | Human-validated real GitHub issues from Python repos with fail-to-pass tests | Extra verification and localisation cases | Fix patch and tests | Only if time allows |

Before first use, record each dataset's licence from its official source in `data/LICENSES.md`. We do not redistribute benchmark code or data in this repository; we store only case ids, our predictions and metrics.

---

## 2. Reproducibility reality

- Some BugsInPy bugs no longer build because old dependencies are gone. Published studies report only a subset reproduces.
- FaultSage reports: attempted, reproduced, excluded (with reason), and metrics on reproduced cases only.
- Never write "493 bugs" in the README or resume. Write the number actually reproduced and evaluated.

---

## 3. Splits

To avoid tuning on the same data we report on:

| Split | BugsInPy projects | Use |
|---|---|---|
| dev | Chosen by a fixed seed before any tuning, about 40% of projects | Train ranker weights, set Strong threshold, debug |
| test | Remaining projects | Reported numbers only. Run once per release. |

Split by **project**, not by bug, so the ranker is tested on codebases it never saw. The split file `bench/splits/bugsinpy_v1.json` is committed before the first tuning run and never edited; a new split gets a new version.

Priority projects for the first working slice: pandas, luigi, keras (data, pipeline and ML code). Others follow.

---

## 4. What is measured per dataset

| Dataset | Metrics |
|---|---|
| BugsInPy | Detection rate, File and Function Top-1/3/5, EXAM score, ablations per evidence source, blast-radius test precision and recall, verify correctness on buggy and fixed versions, rule-patch success rate |
| JunoBench | Crash location Top-k, schema-evidence hit rate, rule match rate, rule-patch success rate |
| LogSage / LogChunks | Top-k retrieval of labelled evidence lines vs keyword baseline |

---

## 5. Baselines (always run in the same run)

| Baseline | Description |
|---|---|
| Random | Uniform over candidates, averaged over 20 seeds |
| Top stack frame | Innermost project frame in the traceback |
| Ochiai | Spectrum-based score from per-test coverage |
| Recently changed | Most recently changed function reachable from the failing test |
| All importers (blast radius) | Every module that imports the root module, and all their tests |
| Keyword (logs) | Lines containing error, failed, exception, ranked by position |

---

## 6. Run records

Each run writes `results/runs/<run_id>/run.json`:

```json
{
  "run_id": "2026-12-14_bugsinpy_test_01",
  "faultsage_commit": "abc1234",
  "dataset": "bugsinpy",
  "dataset_version": "git:<commit>",
  "split": "test",
  "split_file": "bench/splits/bugsinpy_v1.json",
  "seed": 7,
  "cases_attempted": 0,
  "cases_reproduced": 0,
  "cases_excluded": {"dependency_install_failed": 0, "test_not_failing_on_buggy": 0},
  "metrics": {},
  "baselines": {},
  "weights_file_sha256": "",
  "started_at": "",
  "finished_at": ""
}
```

The values above are placeholders for the format only. Real runs fill them in.
