# A1 handoff:TXO spot 0 價閘(/bug)

> 2026-08-21 從 next-time「2026-08-19 txo-snapshot 節」升級開工。本檔自足:
> 新 session 讀完即可跑 `/bug`,不需回讀原對話。

## 一句話

`ChainAggregator.route` 的 spot(台指期)分支缺 `price_millipts > 0` 閘 —— 鎖停時
TC4 會在簿第一檔推「市價佇列」0 價,0 會被記成現價、拿去內插 TXO 損益,且在
R1(PR #68「只在內容有變才推」)的同價短路下「0 ↔ 真價」交替每筆都算價變。

## 證據與錨點(2026-08-20 已查證,直接可用)

- **缺閘處**:`copycat/live/aggregate.py:75-79` —— `route()` 的 `_SPOT_PREFIX` 分支
  只比對同價短路,任何值(含 0)都直接 `self.spot_millipts = tick.price_millipts`。
- **對照組(閘與理由現成)**:同檔 `_ingest()` `aggregate.py:96-100` ——
  `if tick.price_millipts > 0:` 才記價,註解已寫明「0 不是價格;鎖停時 TC4 於簿
  第一檔推市價佇列;前端 `?? null` 擋不住 0」。spot 分支要的就是同一條語意。
- **影響鏈**:spot=0 → snapshot `spot.price=0.0` → payoff / `spot_pnl` 拿 0 點內插
  (全鏈假損益);「0↔真價」交替每筆觸發 changed → 整包推播
  (2026-08-20 實測每則中位 **17.1 KB**)= 鎖停日推播風暴。
- **來源 review**:mod/txo-snapshot-no-redundant-push code review C2(既有問題,
  當輪標記另案)。next-time 條目在 `docs/next-time.md` 2026-08-19 txo-snapshot 節。

## 修法候選(當時已擬)

spot 分支開頭 `if tick.price_millipts <= 0: return False`。
注意:spot 無量無內外盤,不涉 `_ingest` 的「只閘記價、量照舊」白名單 —— 整筆
early return 即可;丟棄要不要計數(`totals`)由 spec 階段決定(spot 目前無丟棄計數欄)。

## Scope

- In:route spot 分支的 0/負價閘 + 紅測試。
- Out:`_ingest` 既有行為、R1 內容比對機制、TXO 推播 delta 化(next-time B13 另案)。

## 驗證

- 紅測試先行:餵 spot tick price=0 → `route` 回 False 且 `spot_millipts` 不變;
  0↔真價交替只有真價那筆算 changed。既有測試檔:`tests/live/` 下搜 `aggregate`。
- 真環境不可等鎖停,以單元測試為主;完成 gate = pytest + ruff + pyright +
  `copycat validate`(TXO 面有 golden,動 aggregate 要跑)。

## Traps

- 先讀 skill `tc4-market-facts`「鎖停市價佇列」節與 `backend-conventions`。
- S 級可主 session 直做(2026-08-11 收窄判準);流程照 `/bug`(root cause 已定,
  重心在紅測試與 blast radius:`route` 的呼叫端 `EngineRuntime._consume` 拿回傳值標 changed)。

## 分支與排程(2026-08-21 夜間無人值守鏈:A1 → B3 → B1)

- **分支**:`bug/txo-spot-zero-price-gate`(branch-lifecycle 開在 master 最新)。
- **鏈位**:第 1 棒,無前置,直接開。
- **完成訊號(給第 2 棒 B3 輪詢)**:PR 已 merge → `git fetch && git log origin/master --oneline | grep spot` 有輸出
  (或 `gh pr list --state merged --search "txo-spot-zero-price-gate"`)。
- **prod 重啟**:本案是鏈上唯一的後端改動 —— merge 後由**本 session** 重啟 8721
  (port → PID taskkill,再 `.venv\Scripts\python -m copycat.server` 背景起;夜間無盤,
  in-memory 資料可棄),重啟後 `curl localhost:8721/api/health` 的 `git_sha` 必須是含本案的 master。
  B3/B1 不得再動 server。
- 工作樹:串行鏈不開 worktree;開工前 `git status` 必須乾淨(前一 session 收尾已保證)。

## 起跑 prompt

```
/bug TXO spot 0 價閘:ChainAggregator.route 的 spot 分支(copycat/live/aggregate.py:75-79)缺 price_millipts > 0 閘,鎖停時 TC4 推 0 價會記成現價、拿 0 內插損益,且在 R1 同價短路下 0↔真價交替每筆都算價變。先讀 docs/superpowers/specs/2026-08-21-a1-txo-spot-zero-price-handoff.md(證據與錨點已備齊)。
```
