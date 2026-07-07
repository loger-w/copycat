# 「達錢 4」與台股看盤 API 調查報告

- 發起時間:2026-06-26
- 方法:`/deep-research` workflow(5 search angles × 6 results,21 sources fetched,86 claims extracted,25 verified with 3-vote adversarial verification → 24 confirmed / 1 refuted)
- Workflow run ID: `wf_27b05d84-b37`
- 完整原始 output:`C:\Users\USER\AppData\Local\Temp\claude\C--side-project-trash-cmoney\d389a032-f304-49af-95b7-d14840cd7ec8\tasks\w4532zb0t.output`(2508 行,session-scoped 暫存)

---

## TL;DR(三句話)

1. **「達錢 4」= Touchance 4.0**,獨立第三方程式交易平台,**不是任何券商產品**,跟我原本以為的「統一證券 / Fubon Neo」都無關。
2. Touchance 是 **付費訂閱**(NT$9,000 / 年)、**ZMQ 介面**、必須本機常駐 Windows app,而且 **沒有 TXO 期權鏈 / 三大法人 / 主力券商等籌碼資料**。
3. 以「個人散戶 + 偏權證 / 選擇權 + Python 後端」場景,**推薦改走 Fubon Neo(主即時)+ Shioaji(備案)+ FinMind Sponsor(TXO snapshot 補強)**,跳過 Touchance。

---

## 1. 「達錢 4」身份確認

| 項目 | 內容 |
|------|------|
| 中文名 | 達錢 4 / Touchance 4.0 |
| 開發商 | 艾揚資訊(獨立第三方,非券商) |
| 官網 | https://www.touchance.com.tw/ |
| 文件 | https://touchance-1.gitbook.io/touchance/ |
| 定位 | 「快速穩定的程式交易平台」— 跨多家券商的程式下單抽象層 |
| 代表合作 | 台新期貨「台新期貨 X TOUCHANCE 4.0」(被券商授權整合,不是被券商持有) |
| Confidence | high(3-0 vote) |

**注意:容易混淆的他牌**
- **DQ2 國際贏家**:精誠資訊 SYSTEX 開發的金融資訊看盤軟體,首頁無 API/SDK 描述,只有子站子產品有 DDE → Excel(不適合 service 化部署)。
- **XQ 全球贏家**:嘉實資訊(SysJust)的程式交易平台,7 萬用戶,B2B 佔台灣前 20 大券商八成市占,但 SDK 形式是「XScript 嵌入式」,**沒有 pip install 套件、沒有 REST/WebSocket 端點**。

---

## 2. Touchance Python API 技術細節

| 項目 | 內容 |
|------|------|
| 通訊協定 | **ZMQ**(Quote Port 51171、Trade Port 51141),不是 REST/WebSocket/COM/DDE |
| Python 安裝 | `pip install zmq` + Touchance 官方 Python wrapper |
| 部署形態 | **必須本機常駐 Touchance Windows app**,Python client 透過 ZMQ socket 跟它溝通。不是無頭 server 友善。 |
| 涵蓋資料 | 期貨即時行情(國內外)、歷史(1 分 K 一年、日 K 十年)、下單 `new_order/replace_order/cancel_order`、帳務查詢 |
| **沒有的** | TXO 期權鏈、三大法人籌碼、主力券商買賣超、權證資料 |
| 訂閱定價 | 3 個月 NT$2,550 / 1 年 NT$9,000(2026-06 時點) |
| 下單前提 | 仍要再向所屬期貨商申請 API 交易權限,Touchance 不解決券商授權 |
| GitHub | `TOUCHANCE/TCPY` 官方 Python wrapper repo |

---

## 3. 台股 Python 券商 SDK 同類比較

| SDK | 隸屬 | Python 版本 | 平台 | 即時資料 | 籌碼 / 期權鏈 | 認證 | 費用 | 個人散戶友善度 |
|-----|------|------------|------|---------|-------------|------|------|--------------|
| **Fubon Neo** v2.2.8 | 富邦證券 | 3.8–3.13 | Win / macOS / Linux | Tick + 五檔 + Real-time + 歷史 K + Adjusted Price | 有(股 / 期 / 選 / Stock Affairs) | 開戶 + CATool 取得 `.pfx` 憑證(Windows 工具) | 免費 | ★★★★★(權證視角最佳:富邦本身權證發行量大) |
| **Shioaji** | 永豐金證券 | 3.x 跨平台 | Win / macOS / **Linux**(manylinux wheel) | 串流 tick/bid_ask/quote、snapshot、Kbars+Ticks 歷史 | 股 / 期 / 選 / 組合單 / 盤中零股 | 開戶 + token + `Sinopac.pfx`(Linux 友善) | 免費 | ★★★★★(Linux Docker 部署 best,但永豐權證量 < 富邦) |
| **KGI SUPER PY** | 凱基證券 | Python | — | 即時 + 盤中盤後 + 回測模組 | 含台股 + 美股即時 | 開戶 | 免費 | ★★★★(多市場、自帶回測) |
| **群益 Touch Prime / 元大易策略** | — | — | — | 看盤 + 下單 | — | 開戶 | 免費 | 文件較少,社群規模小於上述三家 |
| **Touchance 4.0** | 艾揚(獨立) | 3.x | Win 主、需常駐 app | ZMQ pub 期貨即時 + 歷史 | **無 TXO 鏈 / 無 chip** | 訂閱碼 + 期貨商授權 | **NT$9K/yr** | ★★(費用 + 範圍 + 部署複雜度) |
| **FinMind Sponsor** | 第三方資料商 | 3.x | 跨平台 | `taiwan_options_snapshot` / `taiwan_futures_snapshot`(~30 秒 polling) | TXO + TX1-TX5 + 三大法人 + 主力券商(EOD)+ snapshot 即時 | API token(user 已持有) | 訂閱(user 已付) | ★★★★★(已熟悉,持續用) |

**社群規模:**
- Shioaji:GitHub `Sinotrade/Shioaji` 官方 repo,證交所市占近 5 成,Threads / 中文社群活躍。
- Fubon Neo:社群 wrapper 多(`chuangtc/quant-fubon` / `Mofesto/fubon-api-mcp-server` / `eyetrading.github.io` 教學)。

---

## 4. 推薦架構(個人散戶 + 偏權證 / 選擇權)

```
┌──────────────────────────────────────────────────────────────┐
│ trash-mr-warrant 後端                                          │
│                                                                │
│  ┌─────────────────┐  ┌──────────────────────────────────┐   │
│  │ 即時 tick + 五檔  │  │ TXO snapshot + 籌碼 EOD          │   │
│  │ (push, <100ms)  │  │ (~30 秒 polling / EOD)            │   │
│  │                 │  │                                    │   │
│  │ Fubon Neo       │  │ FinMind Sponsor                    │   │
│  │  (主即時源)     │  │  ├─ taiwan_options_snapshot       │   │
│  │  + Stock        │  │  ├─ taiwan_options_institutional…  │   │
│  │    Affairs      │  │  ├─ TaiwanOptionOpenInterest…      │   │
│  │                 │  │  └─ (沿用 trash-cmoney 資料層)     │   │
│  │ ── 備案 ──     │  │                                    │   │
│  │ Shioaji         │  │                                    │   │
│  │  (若 Fubon      │  │                                    │   │
│  │   權證鏈不全)   │  │                                    │   │
│  └─────────────────┘  └──────────────────────────────────┘   │
│                                                                │
└──────────────────────────────────────────────────────────────┘
```

**理由:**
1. Touchance 付費 NT$9K/yr 但缺 TXO 鏈 / 籌碼 → 對權證視角投報率不高。
2. Fubon Neo 免費 + Python 3.8–3.13 + 跨平台 + 即時 tick + 五檔 + Stock Affairs,**最匹配「Python 後端 + React 前端 + 偏權證」三條件** — 富邦本身權證發行量大,SDK 含證券 Stock Affairs API。
3. Shioaji 備案:Linux Docker 部署比 Fubon Neo 友善,但永豐權證量 < 富邦。
4. FinMind 既有專案(trash-cmoney)直接複用,Sponsor tier 對 TXO snapshot 已夠廣。

---

## 5. Open Questions / Caveats

1. **「達錢 4」命名歧義**:研究在 Touchance 4.0 + DQ2 兩條線都驗了,沒看到第三條符合「達錢 4」的中文證據鏈。若 user 確定是某券商內部軟體(統一 / 國票 / 群益期內部用),需要截圖或券商名才能再確認。
2. **「即時」定義差異**:Fubon Neo / Shioaji 是 push tick,Touchance 是 ZMQ pub,FinMind 是 ~30 秒 polling snapshot。權證做 gamma / theta 監看 snapshot 夠;高頻權證 spread 套利就要 push 串流。user 需要先界定自己交易頻率。
3. **Fubon Neo 權證鏈完整度**:官方文件主打 stocks/futures/options,但台股權證的 underlying tracking + 隱含波動率資料散落在哪個 endpoint 沒有獨立驗證,要實裝後實測。
4. **憑證痛點**:Fubon Neo 的 CATool 是 Windows 工具(C++/.NET 寫成),憑證只能在 Windows 取得後再搬到其他 OS — 對 Linux-only 開發者是隱性門檻。Shioaji 比較友善。
5. **時效性**:Fubon Neo v2.2.8、Shioaji 1.x、Touchance 訂閱定價、FinMind Sponsor 涵蓋面都是 2025–2026 上半的狀態,半年內可能變動。
6. **DDE 不算公開 API**:DQ2 子產品有 DDE 拖拉到 Excel,但 Python 整合脆弱、效能差、不適合服務化。

---

## 6. Sources(21 個,verified)

**Primary**:
- https://touchance-1.gitbook.io/touchance/(Touchance 官方文件)
- https://www.touchance.com.tw/python / `/python/purchase`(Touchance 訂閱)
- https://tc4.touchance.com.tw/python.php / `/purchase-python-api.php`
- https://www.fbs.com.tw/TradeAPI/en/(Fubon Neo 官方)
- https://www.fbs.com.tw/TradeAPI/en/docs/download/download-sdk/
- https://github.com/Sinotrade/Shioaji(Shioaji 官方)
- https://sinotrade.github.io/
- https://ai.sinotrade.com.tw/python/Main/index.aspx
- https://finmind.github.io/tutor/TaiwanMarket/RealTime/
- https://www.sysjust.com.tw/Products/XQ.aspx / `/XS.aspx`(XQ)
- http://www.idq.com.tw/ / https://tw.systex.com/國際贏家dqii/(DQ2)
- https://developer.fugle.tw/(玉山富果)

**Secondary**:
- https://github.com/chuangtc/quant-fubon
- https://github.com/Mofesto/fubon-api-mcp-server
- https://github.com/twjackysu/TWSEMCPServer

**Blog**(輔助佐證):
- https://gorich.tw/api-python-02/(凱基 SUPER PY)
- https://jasonchuang.substack.com/p/api(富邦 vs 永豐 API 比較)
- https://eyetrading.github.io/about/
