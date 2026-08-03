# Automated Verification(Phase 5)— txo-tquote-cursor

Round 1(2026-07-18,HEAD 284977b)全綠,exit code 逐一檢查(無管線後綴,§8 教訓):

| # | 指令(來源:.claude/harness.json verify + 專案 CLAUDE.md §1) | cwd | exit | 摘要 |
|---|---|---|---|---|
| 1 | `.venv\Scripts\python -m pytest -q` | repo root | 0 | 509 passed |
| 2 | `.venv\Scripts\python -m ruff check copycat tests` | repo root | 0 | All checks passed |
| 3 | `.venv\Scripts\python -m pyright` | repo root | 0 | 0 errors / 0 warnings |
| 4 | `.venv\Scripts\python -m copycat validate` | repo root | 0 | 42/42 PASS |
| 5 | `npx tsc -b` | frontend/ | 0 | 0 errors |
| 6 | `npx vitest run` | frontend/ | 0 | 42 passed(8 files) |
| 7 | `npx eslint src` | frontend/ | 0 | 0 issues |
| 8 | `npm run build` | frontend/ | 0 | built(index 279.47 kB / gzip 87.51 kB) |

E2E:本 repo 無 Playwright(vitest only)→ 無條件 gate。
Golden regen idempotency 另證:`regen.py` 重跑 old-keys diff = NONE、golden 檔零變動(Phase 4 CR-3 修正後)。
