# Handoff — 台股綜合 tab 計畫(2026-08-06,R1 收尾後)

給接手 session:讀完本檔 + 總 spec 即可開工,不需重建討論脈絡。

## 1. 現況

- **總 spec**:`docs/superpowers/specs/2026-08-05-taiwan-market-overview-tab-spec.md`
  (四段計畫、D-1~D-7 拍板決策、資料源分工、各段 SC 草案 — **不重新討論**)。
- **進度 1/4**:R1(tab 整併 + 雙圖 + basis + corr 併入)已出貨 — PR #23 rebase-merge,
  artifacts 在 `.claude/feat/market-overview-r1-tab/`(brainstorm / design v2 / PLAN v2 /
  三層 review JSON / 截圖證據)。R1 期間推翻 spec 假設的回寫都已完成(design §7 白名單
  三檔 amendment)。
- memory `market-overview-tab-plan` 已同步 1/4。

## 2. R1 殘項(不阻塞 R2)

- **user 過目待做**:四條 UI SC(tab 列 / 雙圖獨立 / basis 列 / corr 收合)+ **盤中**
  看 basis 色標(夜盤驗不到,vitest fixture 已蓋)。
- **既有 bug 候選修(一行 + lock test,可 /bug 或 /chore)**:`MarketChart.tsx:69`
  y 刻度 `key={t.priceMilli}` 空資料時三刻度全 0 → console duplicate key 每 5 秒刷。
  根因已定位,詳 `docs/next-time.md` 2026-08-06 節(已與另一 session 的同症狀條目合併)。
- **建議排 /feat meta-review**:`~/.claude/feat-improvements.md` 10 條未 resolved,
  Phase 8 / tag 驗證族群 ≥3 條(觸發強烈建議門檻)。

## 3. 下一步:R2 開工 prompt(直接貼)

```
/feat 台股綜合 R2 FinMind 管線:照 docs/superpowers/specs/2026-08-05-taiwan-market-overview-tab-spec.md §5 Round 2 做(neigui 搬移 + 家數帶 + 騰落線)。拍板決策見 spec §2 不重議;open questions 2、3 在 Phase 0/1 拍板。前情見 .claude/feat/market-overview-r1-tab/handoff.md。
```

## 4. R2 關鍵事實(省你重查)

- **搬移來源(neigui,C:\side-project\neigui)**:
  - `backend/services/finmind_realtime.py` — universe snapshot 5s TTL / sector_map 24h /
    market_value 24h,inflight dedup + cache 慣例。
  - `backend/services/market_today.py` — **零 IO 純函式**:`compute_breadth`(:349,
    上市/上櫃 × 漲停/上漲/平盤/下跌/跌停五桶互斥;漲停價 tick 精確判定 :338;
    prev_close = close − change_price)+ 強弱卡/市值分層/sector_rotation(R4 才用)。
    fixture 測試一併搬。
  - 搬**邏輯**不整檔貼:neigui 是 httpx/async + 自家 cache utils,copycat runtime
    stdlib-only(HTTP 層選型 = open question 2,Phase 1 拍板)。
- **配額**:兩專案共用同一顆 FINMIND_TOKEN(Sponsor 6000 req/hr);snapshot 一個
  request 回全市場;建議預設 10s poll(360/hr)進 config 可調。
- **R2 責任內的文件債**:CLAUDE.md §0 補 FinMind 例外記載 + §1 .env 補 FINMIND_TOKEN。
- **設計約束(spec §5 R2 已寫)**:當日家數序列 in-memory + **當日 JSON 落檔**
  (防重啟歸零 — 櫃買序列教訓);新 WS 一律走 `server/ws.py` relay helper
  (ws-zombie 教訓);breadth WS 併入 index WS 或獨立 = open question 3。
- **驗證紀律**:盤中不起第二台連 TC4 的後端;驗 HTTP 層用
  `python -m copycat.server --verify`(fake source + port 8722,自動中和 env);
  家數真值對照 = 盤中與 neigui MarketBreadthPanel 同時刻比對(窗口外 fixture)。
- FinMind poller 不碰 ZMQ,但活在同一 server process — 落地後要 prod 生效需重啟,
  遵守「盤後才重啟」紀律。

## 5. 其他 session 並行注意

- 開工時照常 branch-lifecycle(從 master 開分支);master 變動頻繁(今日已有
  PR #21/#22/#23),收尾 rebase 大概率撞 `docs/next-time.md`,合併時**先 grep 同根因
  條目再新增**(§8 教訓,R1 剛真踩過一次:duplicate key bug 兩 session 各記一條)。
- 若 stop hook 抱怨 `intraday-volume-profile` 的 state.json 落後 — 那是另一個
  session 的 flow,不要代寫它的 state。
