# feat/premarket-screen(#173)驗證證據(2026-09-01)

## 自動化

- 後端:`pytest -q` **3295 passed, 3 skipped**(收修後全量重跑);`ruff check copycat tests` PASS;`pyright` 0 errors。
- 前端(動 constants.ts + 兩支文案測試):`npm test` **2925 passed(153 檔)**;`npx tsc -b` PASS;`npx eslint src` PASS;`npx react-doctor@latest --scope changed` **No issues found**。
- `copycat validate` **42/42 PASS**(replay 模組零改動;於主樹既有 replay 產物驗)。

## 真實環境(FinMind 實打)

`python -m copycat screen`(worktree,2026-09-01 22:5x,資料日 = 2026-09-01):

- 21 個交易日全市場 EOD 取齊(2026-08-04..09-01),硬條件 **64 檔 → 資格後 60 檔**(非當沖 0 / 處置剔 4)。
- 排序驗證:2426 鼎元(+76.8%,6 次鎖板,最近 09-01)> 2455 全新 > 3105 穩懋 > … —— 最近鎖板日新→舊、同日比還原漲幅,與拍板一致;user 當日盤中點名的鼎元/合晶/穩懋/全新全數在榜。
- ~~probe 實證:`TaiwanStockDayTrading` / `TaiwanStockPriceAdj` data_id 必填(無 data_id 回空 200);2330 樣本含當日列。~~
  **勘誤(2026-09-02,pr-175 review F-02)**:上句是**週六**(08-29)探測拿到非交易日空回應的誤判 ——
  交易日全市場單日查詢兩個 dataset 都通(DayTrading 2,076 列 / PriceAdj 2,812 列)。資格查已於
  fix/pr-175-review-followups 收斂為單次全市場查詢;逐檔 vs 全市場一致性抽驗 5/5(2426/6182/8111/3406/2330)。

## Prod 重啟後判準(server 路徑,merge 後下次啟動)

1. 啟動補跑:boot log 出現「盤前篩選 <日期>:硬條件 N 檔 → 資格後 M 檔」+「盤前篩選群組「盤前篩選」已更新:K 檔」。
2. 前端側欄出現群組「盤前篩選」約 60 檔,排序同 CLI 輸出。
3. 次一交易日 21:00(server 開著時)自動重算一輪,`data/market/premarket_screen.json` 的 `data_date` 前進。
