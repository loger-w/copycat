# fix/pr-175-review-followups 驗證證據(2026-09-02)

pr-175 review 收修批(user 拍板:auto-fix 13 條 + F-02 收斂 + F-08(c);追認一接受、追認二隨 F-02 消失)。

## 自動化

- 後端:全量 `pytest -q` **3299 passed, 3 skipped**(收尾 review 收修後再跑受影響 42 條 + ruff + pyright 全綠;最終全量見 push 前 gate);`ruff check copycat tests` PASS;`pyright` **0 errors**。
- 前端(只動註解):`npm test` **2925 passed(153 檔)**;`npx tsc -b` / `npx eslint src` PASS;react-doctor `--scope changed` 1 warning = GroupGridView.tsx:70 `only-export-components` **存量**(本批僅動該檔註解,規則 = 新增才擋)。
- `copycat validate` **42/42 PASS**(replay 模組零改動,主樹驗)。
- 紅先行 ×2:F-04 界值測試(修前 FAILED 實錄)、IncompleteRead 重試測試(修前 FAILED 實錄)。

## 真實環境(FinMind 實打,2026-09-02 凌晨,資料日 2026-09-01)

- **F-02 收斂後 CLI 實跑**:`python -m copycat screen` → 硬條件 64 檔 → 資格後 **60 檔**(非當沖 4 / 處置 4,兩集合重疊 —— 處置股當日停當沖,單日查如實反映),**終榜與 09-01 逐檔版逐字一致**(2426 領頭序列同)。
- **逐檔 vs 全市場一致性抽驗 5/5**:2426 / 6182 / 8111 / 3406 / 2330 逐檔 data_id 查有列 ⇔ 全市場集合含,全一致。
- **意外收穫**:第二遍 CLI 撞 `http.client.IncompleteRead`(4.5MB 全市場回應截斷)→ 實證 `_get_rows` 重試 except 集合漏接(非 OSError 子類)→ 紅先行補殺(52e30294)。
- 週六誤判勘誤:交易日全市場單日查 DayTrading 2,076 列 / PriceAdj 2,812 列(09-02 re-probe);舊 artifact 已附勘誤。

## Prod 重啟後判準

1. 21:00(或啟動補跑)log:「盤前篩選 <日>:硬條件 N → 資格後 M(非當沖 x / 處置 y)」—— 資格段耗時應自 ~20 秒(60 次)降到 ~2 秒(1 次)。
2. `grep 盤前篩選.*回聲不符` 平日應零命中(命中 = 上游回錯日,閘在工作)。
3. F-08(b) user 體感項:盤中點開「盤前篩選」群組圖牆(~60 張卡),卡頓與否回報再議。
