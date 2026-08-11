# verification — mod/stock-names-error-poll-stop(2026-08-11)

> review round 1 修畢後最終 gate 見文末「最終 gate」節;中段數字為 round 1 前快照。

## 自動化 gate(auto-verify 前端形狀;皆於 frontend/)

| 步驟 | 指令 | 結果 |
|---|---|---|
| 測試 | `npm test`(vitest run) | 108 檔 / **1698 passed**(baseline 1693 + 新 5)exit 0 |
| 型別 | `npx tsc -b` | exit 0 |
| Lint | `npx eslint src` | exit 0(GATE_EXIT=0,三步 `if ($?)` 串聯) |

Python 側(pytest/ruff/pyright/validate)未跑:本輪 diff 僅 frontend/ + docs,零 .py 觸及。

## TDD 證據

- `[red]` f4cebf4c:白盒「達上限 → false」紅(expected 3000 to be false);整合紅
  (100s 內 51 次且持續增長 vs 封頂 40)。
- `[green]` 6c2c4d4e:同兩條轉綠,7/7。
- `[lock]` 27ab6ce8:mutation 抽驗兩刀 — 3000→1 紅 4 條;移除成功即停分支紅 2 條;
  還原(Edit 成對,非 git checkout)後 10/10 綠,`git diff --stat` 對 hook 零殘留。

## 白名單逐條核

- W-1 啟動窗自動復原:既有測試「啟動窗內連續失敗後應自動復原」綠(真 timer,4.0s)。
- W-2 成功即停:白盒「拿到資料(含空表)→ false」+ fake-timer「成功後推進 10s 不增」綠。
- W-3 錯誤碼契約:既有「404 → NOT_READY」「JSON null → HTTP_500」綠。
- W-4 names 缺失空表:既有測試綠。
- W-5 caller 零感知:hook signature 未動(僅新增 export);tsc -b 全 repo 過 = 兩 caller 編譯無恙。
- W-6 refocus backstop:refetchOnWindowFocus 未觸碰(diff 無此鍵),預設行為保留;
  review round 1 精確化為「分頁 visibilitychange 後門」並補整合測試雙向鎖
  (再失敗仍停 / 成功即復原;mutant refetchOnWindowFocus:false 紅)。

## 真實環境節

本 mod 為輪詢終止條件收斂(錯誤終態才可觀察),UI 無畫面級 SC;真實環境等價驗證由
fake-timer 整合測試承擔(server 永久不可用情境在真環境需 60s+ 觀察 devtools network,
與整合測試同一可觀察面)。未改功能抽樣:全量 1698 測試涵蓋(含 WatchlistSidebar /
WatchlistManagerDialog 既有測試)。

migration:無(無資料格式 / API 契約改動)→ 可逆性 N/A。

## 最終 gate(review round 1 修畢後,2026-08-11)

| 步驟 | 指令 | 結果 |
|---|---|---|
| 測試 | `npm test` | 108 檔 / **1698 passed** exit 0 |
| 型別 | `npx tsc -b` | exit 0 |
| Lint | `npx eslint src` | exit 0(GATE_EXIT=0) |

round 1 後追加 mutation:`refetchOnWindowFocus: false` → 後門整合測試紅 1 條,還原後 10/10 綠。
測試總數不變(1698):round 1 補強為改寫既有 10 條內的結構(探針/後門段併入既有兩條整合測試)。

## 回頭核 goal(§7,對照 change-spec)

- SC-1 錯誤終態停止:白盒 + 整合(收斂恰 40 次、+60s 不增)綠 ✓
- SC-2 節奏/停止條件鎖:literal 3000 白盒 + t=2500/5500 探針 + 成功案 data 斷言後不增;
  mutation 四刀(3000→1 / 移除成功即停 / refetchOnWindowFocus:false / [red] 前的停止條件缺席)皆紅 ✓
- SC-3 註解對齊:retry 註解改述現實 + docstring 77s/visibilitychange(review 兩輪校準)✓
- SC-4 next-time 兩條 P2 勾銷(含算術更正註記)✓
- 白名單 W-1~W-6 逐條:見上節 + round JSON `verified_green` ✓
