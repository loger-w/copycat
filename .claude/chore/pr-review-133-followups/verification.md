# chore/pr-review-133-followups — verification

worktree `.worktrees/pr-133-followups`;branch 自 `origin/master d34d372c` 開(主 tree 被另一 session 佔在 chore/test-hygiene-batch
→ pr-134 followups)。來源 = `docs/superpowers/specs/pr-133-review.md` 14 條 finding(auto-fix 10 / ask-user 2 / no-op 2,
全 Nice to Have、零 Must / Should);handoff 見同目錄 `change-spec.md`。兩條 ask-user(F-11 / F-12)user 2026-08-28 開場拍板**皆做**。

## 1. commit 分組(三類不混;無 🔴 行為改動)

| commit | 類 | 內容 |
|---|---|---|
| `3a4e007b` | 🔵 | F-10 `FuturesChart.tsx` `liveSlotOf` / `tradeSlotOf` 的 `holidays` 選配 → 必填可 `undefined`(lib 側維持選配) |
| `c99f869b` | 🟢 test | F-06 `FuturesChart.test.tsx`「同一份日曆」條補「日曆已載」屏障(08-20 09:00 成交只在 slice 錨定 08-20 後才畫) |
| `e071f038` | chore | F-03 錨定方向 / 近全軸窗 / 四段軸;F-08 snap 推導 1139→1365、1.6→1.9(取「維持 3、回校數字」;`stock-intraday-svg.ts:159` 同一句同根一併);F-07 三處「死區」→「空檔 / 一天之外」 |
| `3b204af3` | chore(docs) | F-01 / F-02 W12 P5 後修訂;F-04 七檔 it( 實數 36/22/54/13/16/53/39 = 233;F-05 W1 改寫;F-09 round-1 SHA 5316f857;F-13 next-time「issue #132 / PR #133」 |
| `d197cb4a` | chore(docs) | `/pr-review #133` 兩份報告落 `docs/superpowers/specs/pr-133-review{,.audit}.md` |
| `0fc58092` | 🔵 | F-11 adapter Σ / high-low 移到插橋之前,刪 `k === ALLDAY_GAP.end` 哨兵 |
| `90cc27bb` | 🔵 | F-12 `txfBarsToSeries` 第一圈 `dayMinuteOf` 結果存陣列給第二圈(不改「由尾往前找」) |

| `19b1fab5` | 🔵 | review S-4:`dms` → `dayMinutes`;`== null` 加註(noUncheckedIndexedAccess) |
| `73bca78f` | chore | review S-1 四段軸註解改對 / S-2 snap 數字只留常數 doc / S-5 n2 段措辭 |

SHA 為 rebase 到 `origin/master a55927c2` 後的值(rebase 前 30bab1d2 … 17e92cc6 / aa07df94 / bd242918;round-1 json 的
`reviewed_head` 17e92cc6 = rebase 前);依 pr-131 拍板 (b),commit 也可以「第 n 筆 + subject」指認。
F-14(commit subject 錯)no-op:已 rebase merge 進 master,不重寫歷史。
`stock-intraday-svg.ts:159` 不在 PR #133 內但同一句推導,一併回校(review Spec P-2 判可接受的同根漂移)。

## 2. 紅先行 / mutation 證據

| 突變 | 結果 |
|---|---|
| F-10:caller `liveSlotOf(new Date(), holidaySet)` → `liveSlotOf(new Date())` | `tsc -b` **TS2554 Expected 2 arguments, but got 1**(FuturesChart.tsx:286);還原後 exit 0 |
| F-06:`liveSlotOf(new Date(), holidaySet)` → `liveSlotOf(new Date(), undefined)` + **舊**測試 ×3 | 3/3 紅(1.65 s,`waitFor(length 3)` 逾時)—— jsdom 下 mock fetch 讓日曆先於 bars 落地,舊條的紅靠 mock 解析順序,不靠結構(review「時序運氣」是結構推演,實跑未觀察到綠) |
| F-06:同突變 + **新**測試 ×3 | 3/3 紅 `AssertionError: expected 2 to be 3`(屏障後同步斷言,不再等) |
| F-06:正本 + 新測試 | `FuturesChart.test.tsx` 54/54 綠 |

還原後 `git status` 乾淨(FuturesChart.tsx 不在 diff --stat)。

## 3. 白名單核對(handoff:行為逐 bit 不變)

1. F-11 零行為差:`futures-accum-adapter.test.ts` 22/22 綠(含橋節四條 +「橋不是成交:量 / 金額 / 價位別量 / 高低都不含它」);
   live 佔位格 v=0 不進量、h/l=p 進高低,與從前相同(順序無關的 Σ / max / min 改走 `rows.values()`)。
2. F-12 `txf-overlay-series.test.ts` 13/13 綠零改;anchor 仍取全 bars 日期最大者、`p` / `lastMinute` 仍依分鐘最大者。
3. F-10 lib 側 `anchorDateOf` / `sliceCurrentAllday` / `alldayFillPoints` 簽名不動(`git diff -- allday.ts fill-marks.ts` 空)。
4. 後端零 diff:`git diff d34d372c...HEAD -- copycat/ tests/` 空。

## 4. 自動化 gate(worktree)

| 指令 | 結果 |
|---|---|
| `npx vitest run`(全量,review 收修前 17e92cc6) | **152 檔 / 2873 passed**(本輪無 App.test flake) |
| rebase 後(73bca78f)`tsc -b` / `eslint src` / `vitest run` 全量 | exit 0 / 0 / **152 檔 2873 passed**;後端與 origin/master 逐 byte 相同(另一 session 的 pr-134 gate 已證),pytest 不重跑 |
| `npx vitest run` 本案六檔(fill-marks / FuturesChart / SIC.futures / stock-intraday-svg / adapter / txf) | 279 + 35 passed |
| `npx tsc -b` | exit 0 |
| `npx eslint src` | 0 |
| `npx react-doctor@latest --scope changed --no-telemetry` | Scanned 7 files, No issues found |
| `pytest -q -p no:cacheprovider`(借主 tree venv;後端零 diff,只證沒連帶) | **3136 passed, 3 skipped**(190 s;worktree 內跑,venv editable 指主 tree code —— 後端零 diff 所以同一份) |
| `ruff` / `pyright` / `copycat validate` | 未跑:後端零 diff |

## 5. two-axis review round 1(opus × 2;見 `code-review-round-1.json`)

- Standards 6 條(P2 ×1 / P3 ×5):S-1 **四段軸註解寫錯**(e071f038 新寫「夜盤 / 空檔 / 日盤 / 收盤撮合」,實為
  夜盤前半 / 夜盤後半 / 空檔 / 日盤)→ 73bca78f;S-2 數字散寫 → 只留常數 doc;S-4 `dms` 改名;S-5 措辭;S-3 / S-6 accepted。
  無 hard 違規(frontend-conventions / frontend-testing 逐條比對)。
- Spec 3 條全 P3:14 條 finding 逐條 PASS;P-1 pytest 待填(已填);P-2 svg.ts 越界判可接受;nit「`=== null`」**rejected**
  —— tsc 實證 noUncheckedIndexedAccess 下得 TS18048 ×2(我先照改、tsc 紅、`reset --soft` 重打兩筆;教訓:review 收修的
  gate 鏈用 `&&` 不用 `;`,tsc 紅時 commit 不該先進)。
- 兩軸各自獨立推證 F-11 零行為差(rows 落 1064 不可能 / Σ 整數順序無關 / live 佔位格同從前)。

## 6. 真環境

不適用:純結構 / 測試 / 註解 / 文件,無畫面或 API 行為差。SC-13 (b)–(e)(15:01 翻頁 / 08:46 水平橋 / CDP 對 APP / 個股頁夜盤疊線)
仍屬 PR #133 的待窗口項,不在本輪 scope。
