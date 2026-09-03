# pr-188 review 收修(`fix/pr-188-review-followups`)— verification

來源:`docs/superpowers/specs/pr-188-review.md`(/pr-review #188,CC 單軸 + 同軸內部複查)findings F-01–F-11,
全 Nice to Have;user 拍板「全修」,F-02 依白話說明後改為**知情接受 + CLAUDE.md §4 補一句**(不改程式)。
分支自 master `55295c65` 切出(worktree `.claude/worktrees/fix-pr-188-review-followups`)。

## 1. commits(🟢 test → 🔴 fix → 🟢 docs,三類不混)

| sha | 類 | 內容 |
|---|---|---|
| `4a06972a` | 🟢 test | F-04/F-05 `test_single_drop_window_settles_without_second_warning` 取代與既有逐字重複的 `…first_of_window_then_window_total` / F-09 `useGroupLiveAccums.test.tsx` 跨檔撞號案(斷言 refetch 2 次)/ F-10 同組不重送案先 `expect(before).toBe(1)` + 拿掉無 await 的 async / F-11 `test_prod_wiring_keeps_default_tick_flush_interval` 搬進 `TestStockWs` |
| `061a98eb` | 🔴 fix | F-03 刪 `ws.py::_note_drop` 內死的 `_settle_drop_window(now)`;`_settle_drop_window` docstring 標唯一呼叫點 = `publish` 入口與 `dropped += 1` 順序陷阱 |
| `bbbbf663` | 🟢 docs | F-01 CLAUDE.md §4 兩道閘改述為同一 race / F-02 §4 補「收盤前最後一窗結算延到翌日推播,知情接受」/ F-06 `_flush_ticks` 取消 timer 註解改述孤兒 handle / F-07 `app.py` `stock_state` + `stock_group_state` 兩條 route docstring 補 flush 副作用 / F-08 `stock-accum.ts` 刪 `watchlist_changed` 自癒路徑 |
| `ec73e7e7` | 🟢 docs/test | review r1 spec 軸收修:269 行 async / 空白行 / §4 標題口徑 |
| `fbe088f4` | 🟢 docs/test | review r1 標準軸收修:ws.py 絕對句 / 兩條 route docstring 收成一行 / stock-accum 殘餘句 / 測試 docstring / 註解移位;F-06 入 next-time |

## 2. 紅 → 綠(測試面四條為 lock,紅以突變體證)

| finding | 突變體 | 結果 |
|---|---|---|
| F-04 | `ws.py` `if self.window_dropped > 1:` → `> 0` | 新案 **FAILED**(1 failed);還原後 PASS |
| F-09 | `stock-accum.ts::seqsByCode` 改成「每檔都拿整則打包的全域 Set」 | 新案 **FAILED** 於 `expect(fetchMock).toHaveBeenCalledTimes(2)`;還原後 PASS |
| F-10 | `GroupGridView.tsx` 刪掉兩支 `setTickView` effect | 加強案 **FAILED** 於 `expect(before).toBe(1)`;還原後 PASS |
| F-11 | 搬動(無行為);第一次搬錯位置(落到模組層 `_next_of_type` 之後成巢狀 def,pytest 找不到 node id)→ 重搬進 `TestStockWs`,node id `tests/server/test_stock_routes.py::TestStockWs::test_prod_wiring_keeps_default_tick_flush_interval` **1 passed** | — |

突變體工具:`scratchpad/mutcheck.py`(套用 → 跑 → byte-for-byte 還原,每次印 `RESTORED_OK`)。

## 3. 完成前 gate(全綠;`bbbbf663` 工作樹)

| 指令 | 結果 | exit |
|---|---|---|
| `C:/side-project/copycat/.venv/Scripts/python -m pytest -q` | **3367 passed, 3 skipped**(226.40 s) | 0 |
| `… -m ruff check copycat tests` | All checks passed | 0 |
| `… -m pyright` | 0 errors, 0 warnings | 0 |
| `… -m copycat validate --run-five …/out/five_tigers --run-four …/out/four_tigers` | **42/42 PASS** | 0 |
| `vitest run`(frontend/,worktree 自裝 `npm ci`) | **154 files / 2966 tests passed**(+1 = F-09 新案) | 0 |
| `tsc -b` | PASS | 0 |
| `eslint src` | PASS | 0 |
| `react-doctor --scope changed --no-telemetry` | No issues found | 0 |

**review 收修後最終重跑(`fbe088f4` 工作樹)**:pytest **3367 passed, 3 skipped**(223.43 s)/ ruff 0 / pyright 0 / validate **42/42** /
vitest **154 files / 2966 passed** / tsc 0 / eslint 0 / react-doctor No issues found(全部 exit 0)。

## 4. 真實環境

本批為 review 收修(一行死碼刪除 + 文件 + 測試強度),無新盤中判準;F-03 刪的是不可達呼叫,`WsBroadcaster` 行為不變
(`TestWsBroadcasterBackpressure` + `TestWebSockets` 13 passed)。F-02 知情接受後的可觀測樣態已寫進 CLAUDE.md §4:
收盤前最後一分鐘內開的丟包窗,「上一窗共丟 n 則」延到翌日試撮翻轉那一則推播才印。

**流程事故(與本批無關但發生在本批期間,記錄供對帳)**:review worktree `.worktrees/review-pr-188` 的
`frontend/node_modules` 是 `mklink /J` junction 指向主樹;`git worktree remove --force` 順著 junction 遞迴刪進主樹
`frontend/node_modules`(`.bin`、`@asamuzakjp` 等被刪,`lightningcss` 因 `vite preview` / `npm run dev` 持有而 EPERM 停住)。
主樹以 `npm install` 補回(不刪被鎖檔;user 開著的 preview / dev 未動);本 worktree 改 `npm ci` 自裝真的 node_modules。
教訓已入 memory / ops-discipline 候選:**worktree 內 node_modules 一律 `npm ci`,不用 junction;或刪 worktree 前先 `cmd /c rmdir` 拆 junction。**

## 5. Review(two-axis,fixed point `55295c65`,reviewed head `bbbbf663`)

- spec 軸 3 條(全 LOW):F-01 GroupGridView.test 269 行殘留 async / F-02 搬移多一行空白 / F-03 §4 標題「雙邊不變式」與內文口徑相反 → 全修(`ec73e7e7`)。11 條逐條對帳全到位,三個突變體由 reviewer 自己重跑、皆被指名新案殺掉。
- 標準軸 7 條(MED 1 / LOW 6):F-01 ws.py docstring 絕對句改「幾乎不可能跨窗界」/ **F-02 MED** route docstring 與 engine docstring 六處同文案 → route 收成一行指回 engine / F-03 stock-accum 殘餘句補「flush 是壓窗非必要條件」/ F-04 測試 docstring「逐字重複」改述為由 `…relogs_after_window` 承接 / F-05 三行空白(= spec F-02,已修)/ **F-06 否決**:抽五份 broadcaster 測試骨架成 fixture 要動四支既有測試,鐵則 B 順手 refactor → `docs/next-time.md` 2026-09-04 節 / F-07 行尾 144 字元註解移到 `it` 上方 → 修。
- 收修 commit:`ec73e7e7`(spec 軸)+ `fbe088f4`(標準軸);收修後全 gate 重跑見 §3 末列。
- 逐條原文與處置:`code-review-round-1.json`。
