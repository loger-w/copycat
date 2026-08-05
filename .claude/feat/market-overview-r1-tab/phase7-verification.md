# Phase 7 verification — market-overview-r1-tab

日期:2026-08-06。對照 brainstorm.md SC 定義逐條核證(brainstorm 於本 session 內
兩次 amendment 後重讀;證據皆本 session 新鮮執行)。

| SC-N | 實作檔案:行號 | 自動化測試名 + pass count | real-env 證據路徑 | regression 抽樣對象 |
|---|---|---|---|---|
| SC-1 tab 整併 | App.tsx:34(Tab union 四值)/ :45-50(initialTab corr fallback)/ :175-181(nav 四顆「台股綜合」) | App.test.tsx「tab 列恰四顆…」「copycat-tab=corr → 台股綜合」等 28 passed(檔內全數;全套 1157) | evidence/SC-1_tabs.png(四顆依序、無相關係數)+ user 過目待 | 選擇權/期貨 tab 切換(Phase 6 subagent 實走)、TAB_KEY 其餘四舊值還原案例綠 |
| SC-2 雙圖並排 | MarketPane.tsx:299(section data-testid)/ :238-264(雙 fallback 同源 state)/ IndexPage.tsx:85-106(LEFT/RIGHT_STORES 接線) | MarketPane.test.tsx 30 passed((a)-(g) + 搬遷 17 案)+ IndexPage.test.tsx (a)(b)(b2)(d)(d2)(d3) 獨立性/接線雙向持久化 | evidence/SC-2_dual-pane.png(左日K右分時並排;DOM aria-pressed 佐證獨立)+ user 過目待 | 舊單圖全部行為案例(標的/週期/櫃買降級/重疊/meta)以單 pane 形態全綠 |
| SC-3 basis 保留 | IndexPage.tsx:45-66(BasisRow 原樣搬遷,testid=basis-row) | IndexPage.test.tsx (c)(c2)(c3)(c4):存在/唯一/色標三態/缺值「價差 -」 | evidence/SC-3_basis.png(夜盤 fallback 分支「價差 -」+ 格式正確;色標方向盤中窗口 → 降級 = (c3) fixture 已綠)+ user 過目(日盤順眼補看色標) | MarketPane.test「basis 列不屬 pane」負向鎖 |
| SC-4 corr 併入 | CorrSection.tsx:15-60(open gate + lazy)/ IndexPage.tsx:107 | CorrSection.test.tsx (a)(c)(d) mount/unmount 計數 + lazy.test (b) 真身 + (c) 收合斷線 lock(mutation-verified) | evidence/SC-4_corr-collapsed.png + SC-4_corr-expanded.png(預設收合/展開見六腿真資料/收合恢復)+ user 過目待 | corr/river hook 與 CorrPanel/RiverPanel 零 diff;展開後六腿江波圖真資料 = 遷移無損 |
| SC-5 regression | (全 diff)11 檔清單見下 | 全套:pytest 1731 / vitest 1157 / tsc 0 / eslint 0 / ruff 0 / pyright 0 / validate 42/42(Phase 5 round 1,單輪全綠) | `git diff --stat a858dec..HEAD` 本 phase 新鮮執行:11 檔全在白名單(App 2 + corr 4〔CorrPage 僅註解 3 行,獨立 🔵〕+ index 4 + constants),stock/futures/capital/rail/後端零 diff | Phase 6 subagent 抽走選擇權/期貨頁操作路徑無異常 |

無 FAIL 條目 → 不寫分流敘述。

附註(不構成 SC 失敗,收尾回報 user):
- Console 既有 bug(MarketChart 空資料 y 刻度 duplicate key,master 同觸發)已記
  docs/next-time.md 2026-08-06 節。
- 「展開」提示字位置貼標題右側(design 未指定位置),user 過目時裁量。
