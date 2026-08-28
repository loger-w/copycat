# verification — bug/futures-tab-reactivate-refetch(2026-08-28)

分支 commit(引「第 n 筆 + subject」):第 1 筆 `test(frontend): 期貨 tab 切回立即重抓 + bars fetch timeout / 慢請求 warn —— 紅先行` →
第 2 筆 `fix(frontend): 期貨 tab 切回立即重抓(useFuturesBars 改走 TQ subscribed: active)+ bars fetch 30 s timeout + 慢請求 console.warn` →
第 3 筆 `test(frontend): active=false 掛載不抓為事前標該變` → 第 4 筆 `test(frontend): review round 1 收修 ——…` →
第 5 筆 `fix(frontend): review round 1 收修 —— gcTime: Infinity …` → 第 6 筆 `refactor(frontend): refetchInterval 拿掉 active && …` →
第 7 筆 `fix(frontend): fetchWithTimeout 的 aborted 出口掛 no-op catch` → 第 8 筆 artifacts。

## 1. 自動化 gate(worktree `.worktrees/fut-reactivate/frontend`,`npm ci` 自裝)

| gate | 指令 | 結果 | exit |
|---|---|---|---|
| 紅先行(第 1 筆,fix 前) | `vitest run useFuturesBars.test.ts fetch-timeout.test.ts` | **4 failed**(active=false 掛載 `1≠0`、切回 `1≠2`、signal `undefined`、warn 0 次)+ fetch-timeout 檔缺模組 | 1 |
| 綠(第 2 筆後) | 同上 + `FuturesChart.test.tsx` | 2 failed(事前標該變兩條)→ 第 3 筆改口後 72 passed | 0 |
| 收修後四檔 | `vitest run useFuturesBars / fetch-timeout / FuturesChart / useBreadthRows` | 84 passed | 0 |
| 全量(第 7 筆前) | `vitest run` | 2885 passed 但 **3 Unhandled Rejection**(`aborted` promise 無人接)| 1 |
| 全量(最終樹) | `vitest run` | **2885 passed**(153 files),零 Unhandled | 0 |
| 型別 | `tsc -b` | 無輸出 | 0 |
| lint | `eslint src` | 無輸出 | 0 |
| doctor | `react-doctor@latest --scope changed --no-telemetry` | 新增 1 條 `no-fetch-response-used-without-status-check`(`fetch-timeout.ts:46`)→ triage 誤報(wrapper 刻意不分 status 緩衝 body,`res.ok` 由 caller 判、非 2xx body 留給 `parseError`)→ 行內 `react-doctor-disable-next-line` 附理由(不動專案 config)→ No issues found | 0 |
| 後端 | 未動 → 不跑 | — | — |

## 2. 反向驗證(mutation)

- 切回立即重抓:紅先行本身即證(fix 前 `expected 1 to be 2`;`subscribed: active` 是唯一改動點)。
- timeout:`fetch-timeout.test.ts` 在檔案不存在時整檔紅;`hangingFetch` 治具只在 signal abort 時拒絕,沒有計時器就永遠懸著(`Promise.race` 證 29,999 ms 仍 pending)。
- 慢請求 warn:fix 前 `warn 0 次`(紅先行)。
- gcTime(review P1):拿掉 `gcTime: Infinity` → `離開超過 5 分鐘再切回` 案紅(`expected undefined to be defined`);還原後綠。
- error 態保留舊圖(review Spec F-3):`if (isError && data === undefined)` 換回 `if (isError)` → `重抓失敗但舊圖還在` 案紅;還原後綠。
- body 停住(review Spec F-2):新案用永不 close 的 `ReadableStream` 當 body,只包 fetch 的舊版會懸著(紅先行形態);現版 30 s 後 TimeoutError。

## 3. 白名單逐條(change-spec §3)

| # | 既有行為 | 證據 |
|---|---|---|
| 1 | 切回不閃「載入中」 | `subscribed:false` 不是 `enabled:false`;TQ `useBaseQuery` 退訂時 `_optimisticResults` undefined → 原樣回 cache(review 兩軸親核);**加 `gcTime: Infinity` 才在 >5 分鐘成立**(新案釘 10 分鐘) |
| 2 | 60 s 節奏 / 窗 / days / key 不變 | `refetchInterval` 只拿掉 `active &&`(退訂本無計時器);「夜盤時段照 60s」「停輪詢窗」「換商品換料」三案綠 |
| 3 | 日 K 重訂不重抓 | gcTime 新案斷 `tf=D` 只 1 發 |
| 4 | `enabled=false` 掛載不打、回焦不打 | 「enabled=false」案綠(參數形狀改成 active 與 enabled 同值 = App 真實呼叫) |
| 5 | `retry: 1` 不變 | 零 diff;FuturesChart 新案走 retry 一次後 error 態 |

## 4. 行為改動

change-spec §4 六條(1–3 原案、4–6 review 追加);事前標該變的斷言:`useFuturesBars.test.ts` active=false 案 1 → 0、`FuturesChart.test.tsx` LF-2 案 2 → 0、enabled 案改參數形狀。

## 5. 真實環境

**未部署**(user 盤中下單,prod 8721 / preview 4173 不碰;user 拍板後才 merge + 重 build)。部署後判準:
- 個股頁待 ≥ 10 分鐘(> 舊 gcTime)→ 切期貨 tab(微台):舊圖立即在、不閃「載入中」、「分時資料落後 N 根」不亮(或 < 1 s),server log 切回當下即有一發 `bars/TMF … session=allday`。
- 若再發生凍結:瀏覽器 console 會有 `bars: 慢請求 … N s 才回` 或提示列「K 線更新失敗:請求 30 秒未回應,已中止(沿用上一份,每分鐘重試)」;把時刻 + 商品交給 session 對 server log。
- 未改功能抽查:個股頁「台指期」疊線開 / 關(App 觀察者 `enabled=subscribed=txfWanted`)、期貨 tab 日 K 模式、台股綜合 tab 家數帶輪詢(`useBreadthRows` 只改註解)。

## 6. 留尾

- 「永不回的那一趟」根因未證(前端 warn 落地後等真事件)。
- 後端 `build_minute` 慢請求 WARNING;`useMarketBars` / `useStockBars` 同款 timeout。
- 30 s timeout 後 retry 一次(TQ 預設退避 1 s)再 30 s:凍結上界 ≈ 61 s + 60 s 輪詢;要更緊可 `retry: 0`(未拍板)。
