---
name: e2e-conventions
description: Playwright E2E 框架慣例(FAKE_FINMIND 三層架構、clock 凍結、fixture rotation、selector 對 snapshot)+ 本機 dev server(:8000 / --reload)驗證前檢查。寫或改 e2e spec、rotate fixture、real-env 驗證 backend 改動前先讀。
---

> 來源:2026-07-06 自 neigui 專案複製。文中「樣板」檔案路徑(services/finmind.py、conftest.py、lib/api.ts 等)指 neigui repo(C:\side-project\neigui)的 code,本專案對應實作落地後再改寫為本地路徑。

# E2E 測試框架慣例(2026-06-30 /feat e2e-tests 沉澱)

## FAKE_FINMIND 三層架構

- `services/finmind.py::FinMindClient.__init__` 在 `FAKE_FINMIND=1` 跳 httpx + token + 用 `NoOpBucket`;`services/finmind_fake.py::FakeFinMindClient(FinMindClient)` 繼承 + override `_get` 讀 `tests_e2e/fixtures/MANIFEST.json` preload。**不要** parse filename heuristic — explicit MANIFEST 對映 filename→{dataset, data_id} 是 6 輪 review 確認的唯一 sound path。新 fixture 寫進 fixtures/ 必同 commit 加 MANIFEST 條目,`backend/tests/test_fake_finmind_manifest.py` 3 個 gate 會抓 drift。Trigger:新增 FinMind dataset / 新 chip route fan-out 時。

## Clock 凍結

- `services/clock.py::today() / now()` indirection:全 backend `date.today()` 已 swap 成 `clock.today()`。`FAKE_FINMIND=1 + FAKE_TODAY=YYYY-MM-DD` 凍 backend 時鐘;production 走預設。**新 code 不准直接呼叫 `date.today()`,一律走 `clock.today()`** — `backend/tests/test_options_routes_clock.py` 鎖著「route 退回 wall-clock 就紅」的 timebomb(fixture 期約日過期後會自然引爆,爆了就是有 route 沒走 clock 或 fixture 該 rotate)。Trigger:新 route / service 用到今天日期時。

## Spec 撰寫紀律

- **痛點註解強制**:每個 `test('...')` 上方必 `// 痛點: <design rationale>` 註解,連回 design round 或 SC edge case。沒寫 = wrong reason 過綠。Trigger:寫任何 e2e spec 時。
- **Selector 必對 page snapshot,不准憑記憶**:第一次 run failure trace 帶 page snapshot,真實 placeholder / aria-label / role 全在。**真實值範例(已校齊)**:SymbolSearch placeholder = `搜尋代號或名稱...`;Mode buttons = `個股 / 選擇權 / 大盤`;Active state = `aria-current="page"`;RangeSelector = `aria-label="設為 N 日"`;ChipBrokersPanel / ChipKlineChart 早期 return path 也要 root testid。Trigger:寫 Playwright spec 任 selector 時。
- e2e 量測 viewport 幾何一律 `test.use({ viewport })` 在導航前固定 — `setViewportSize` 後立即量測會撞 resize relayout race(實測假綠)。Trigger:寫 viewport 量測 spec 時。

## Fixture rotation

- 政策:每季 + release 前。現行 fixture 基準日:trading day = 2026-06-26 (Fri)、no-trading-day = 2026-06-27 (Sat)(**每季 rotation 後更新本行**)。
- **任何 fixture date 寫死前必驗星期**:`python -c "from datetime import date; print(date.fromisoformat('YYYY-MM-DD').strftime('%A'))"` — 曾把週六誤記成週五,cascade 進 ~10 個 fixture filename + clock-pin + visual baseline。Trigger:rotate fixture / 新 fixture 寫死日期時。

## 本機 dev server(:8000)驗證前檢查(三條教訓合併,2026-07-03 定版)

1. **:8000 被占先查 CommandLine 再決定殺**:`(Get-CimInstance Win32_Process -Filter "ProcessId = <pid>").CommandLine`。
2. 帶 `--reload` 的 dev server **不能直接信任**:file watcher 會靜默失效(實測 worker 子行程 3 小時沒 respawn,期間所有 backend 改動沒生效 = 白驗)。**驗證 backend 改動前,對照 python 子行程 creationDate vs 改動時間**;不符就手動重啟。
3. 非 --reload 殘留 zombie(taskkill 殺不死)→ `Get-Process python | Stop-Process -Force` 清掉再跑。
- Trigger:e2e dev loop 撞 port / Phase 5-6 real-env 驗證 backend 改動前。
