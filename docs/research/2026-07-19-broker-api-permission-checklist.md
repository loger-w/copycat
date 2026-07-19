# 期貨商 API 交易權限申請 Checklist(Touchance 4.0 下單前置)

日期:2026-07-19
方法:deep-research workflow(5 路搜索 → 15 源抽取 → 3 票對抗查證)。
證據等級標註:
- ✅ = 通過對抗查證(3-0 或 2-0 票,無反駁)
- ⚠ = 單一來源、查證票因額度中斷未完成複核(**非被證偽**,引用前建議向營業員或原始頁面二次確認)

背景:copycat 下一階段接 Touchance 4.0(達錢 4,艾揚資訊)下單。Touchance 只是下單抽象層 —— ✅ 官方 GitBook 明載:「使用達錢 TOUCHANCE 的內建下單機時,你必須先向你所屬的期貨商申請 API 交易權限,不然無法在達錢 TOUCHANCE 登入你的交易帳號。」對應 CLAUDE.md §7 與錯誤碼分流 `TOUCHANCE_DOWN` vs `BROKER_REJECTED`。

---

## TL;DR 行動 Checklist

- [ ] **0. 確認所屬期貨商**(repo / memory 均未記錄 user 開戶券商 —— 這是第一個待 user 確認的空格)並比對下方支援清單。
- [ ] **1. 期貨開戶 + 電子交易帳戶開通**(若未有)。✅ 國泰明文:API 僅限已申請電子(網路)交易帳戶者;其他家慣例相同。
- [ ] **2. 簽署 API 風險預告 / 使用同意文件**(線上或 APP)。✅ 凱基:「API 電子交易風險預告書暨使用同意書」;✅ 元大:「API 風險預告暨申請使用聲明書」;⚠ 群益:同意書專區線上簽「期貨API服務下單聲明書」。
- [ ] **3. 營業員聯絡確認用途**(自行開發程式 / 程式交易)。✅ 官方五步流程之一。
- [ ] **4. (視期貨商)登記程式名稱**。⚠ 國泰:下單/報價程式名稱僅英數字 6-15 字元,測試與正式環境登入都以程式名稱控管 —— 自行開發的 ZMQ client 也在控管內,命名要先想好。
- [ ] **5. 在期貨商 API 測試環境完成委託測試**。✅ 官方五步流程:「會請你在 API 的測試環境進行一些委託測試,證明你有能力使用 API」。
- [ ] **6. 繳交交易記錄(Log)→ 期貨商審核**。✅ 官方五步流程收尾;⚠ 凱基 lead time 約 3 個工作天、完成後 email 通知。
- [ ] **7. 匯入期貨商交易憑證到跑 Touchance 的 Windows 機器**。✅ 綁定交易帳號前置 = 開通權限 + 匯入憑證;**新舊憑證不能同時存在**,過期憑證要先移除,否則出現「找不到憑證」。
- [ ] **8. Touchance 交易連線設定綁定帳號,驗證可登入**(此時才輪到 copycat 端 `DQ4_LIVE` 閘門與模擬環境接線)。

---

## Q1:哪些期貨商支援 Touchance 下單通路

| 期貨商 | 證據等級 | 說明 |
|--------|---------|------|
| 群益期貨 | ✅ | 達錢 4.0 v2026.06.26.00 版更明列「群益期貨下單 API 交易與回報優化」— 通路已上線且持續維護 |
| 統一期貨 | ✅ | 官網將「Touchance(下單機)」列為 API 產品,涵蓋國內外期貨報價 / 下單 / 帳務查詢 |
| 台新期貨 | ⚠ | 「台新TC」品牌 = 台新 X TOUCHANCE 4.0(2026-06-26 調查已見官方合作 EDM);申請路徑 = 洽所屬營業員 |
| 凱基期貨 | ⚠ | Touchance 官方 partner 頁列名(五家:台新、群益、富邦、統一、凱基) |
| 富邦期貨 | ⚠(注意陷阱) | ✅ 富邦官網刊載《TOUCHANCE gTrade API 使用說明書》,但那是 **COM/OCX 舊版 gTrade 架構(IceGlobalTradeAPI.ocx),不是 TC4 的 ZMQ OpenAPI** — 富邦通路是否支援 TC4 新架構要另行確認。且 user 已排除 Fubon Neo(自家 SDK),與經 Touchance 通路屬不同路徑 |
| 華南期貨 | ⚠ | 下單大師文件列「艾揚 API」為其通路之一 |
| 康和期貨 | ⚠ | API 權限預設未開通,錯誤訊息指示洽營業員開通(佐證「營業員開通」為業界慣例) |

結論:**群益、統一為最強證據的 TC4 下單通路**;若 user 所屬期貨商不在清單內,選項是在支援清單內的期貨商另行開戶(lead time 要加上開戶時間)。

## Q2:要準備什麼

1. ✅ 期貨帳戶 + 電子(網路)交易帳戶(國泰明文為 API 申請前提)。
2. ✅ 簽署 API 風險預告書 / 使用同意書(主管機關規範,各家名稱略異,見 checklist 第 2 步)。
3. ✅ 通過 API 測試環境委託測試 + 提供交易 Log(官方五步流程)。
4. ✅ 期貨商交易憑證(匯入至跑 Touchance 的機器;新舊憑證互斥)。
5. ⚠ 程式名稱登記(國泰式控管:英數 6-15 字元;且須先完成下單程式連結才可申請報價程式連結,或兩者同時申請)。
6. Touchance 端自身前提(本專案已具備):訂閱授權碼 + Windows app 常駐 + ZMQ 通(登入 port 50774)。✅ 官方 Python API 功能含下單與帳務查詢(含部位查詢)。

## Q3:Lead time

- ⚠ 凱基:權限申請作業約 **3 個工作天**,完成後 email 通知;開通後須完成測試並回覆(即非簽完即用)。
- ⚠ 群益:線上簽署聲明書後即可使用(頁面未提及測試考核)— 各家嚴格度差異大。
- ✅ 含測試考核的流程(官方五步)另需**自行完成測試環境委託測試**的時間,取決於自己的開發進度。
- **規劃建議:從送件到正式環境可用,保守抓 1–2 週**(簽署 1-3 工作天 + 測試環境開通 + 自行委託測試 + Log 審核 3 工作天級),純線上簽署型(群益式)可能當天。

## Q4:模擬戶 vs 正式戶

- ✅ 期貨商申請流程**內建測試環境階段**:簽署申請後先在期貨商的 API 測試環境做委託測試、繳 Log,審核過才開正式環境 —— 「模擬」不是可選項而是必經關卡(至少在採官方五步流程的期貨商)。
- ⚠ 國泰:首次使用 API 者必須先在測試(模擬)環境留下該程式名稱的登入及下單紀錄,經資訊單位審核後才開正式;使用「下單大師」「MultiCharts」等已知軟體者豁免 —— **自行開發的 copycat client 不在豁免名單,應假設要過考核**。
- 模擬環境取得方式:隨 API 權限申請由期貨商發配(測試環境帳號/端點),非獨立申請項目;細節(端點、測試時段、是否常駐開放)各家不同,**簽署時直接向營業員問清楚**。
- copycat 對應設計(CLAUDE.md §7,已拍板):第一階段只接模擬戶;`DQ4_LIVE=1` 閘門先實作但預設關;正式戶啟動 banner 印環境名 + 帳號末 4 碼。

## 對 copycat 實作的直接影響

1. **錯誤碼分流有實據**:期貨商端擋單(權限未開 / 憑證失效 / 測試環境未過)都屬 `BROKER_REJECTED` 家族,與 Touchance app 斷線(`TOUCHANCE_DOWN`)是不同修復路徑(前者找營業員,後者重啟 app / 查 ZMQ)。
2. **憑證是部署面依賴**:交易憑證綁機器,換機 / 憑證到期都會讓下單斷頭 —— 啟動時的環境檢查(§7 第一道閘)應包含「憑證可用性」的健檢與明確錯誤訊息。
3. **程式名稱控管(若所屬期貨商採國泰式)**:client 識別名要進 config,不 hardcode。
4. **開發排程**:API 權限申請 lead time(1–2 週)與 copycat 第一階段開發(模擬戶)可並行 —— 先送件再開發,測試環境開通後正好接上聯調。

## 來源

- Touchance 官方 GitBook「交易連線」:https://touchance-1.gitbook.io/touchance/touchance-jie-mian-1/she-ding/jiao-yi-lian-xian(✅ 五步流程 / 憑證規則主源)
- Touchance 官網 Python API:https://www.touchance.com.tw/python
- Touchance 官網版更(v2026.06.26.00):https://www.touchance.com.tw/
- Touchance partner 頁:https://www.touchance.com.tw/partner(⚠)
- 統一期貨 Touchance 下單機:https://www.pfcf.com.tw/software/detail/1223
- 富邦期貨 TOUCHANCE gTrade API 說明:https://www.fubon.com/futures/home/teaching/program/1fa1f4b0-ebe2-4363-8b4f-c2a6719987c2
- 凱基期貨 API 專區:https://www.kgifutures.com.tw/content/order04.html
- 元大期貨 API 下載頁:https://www.yuantafutures.com.tw/ytf/easywin/api/download.html
- 國泰期貨 API 風險預告書暨使用同意書(PDF):https://cathayfut.com.tw/download/4/(4-15)API 電子交易風險預告書暨使用同意書.pdf
- 台新期貨 TOUCHANCE 4.0 EDM:https://www.tsfutures.com.tw/edm/TOUCHANCE4/(⚠)
- 下單大師支援券商文件:https://www.order-master.com/docs/t03/(⚠)
- 群益 API 簽署教學(第三方 blog):https://www.topbroker.tw/blog.php?act=view&id=61(⚠)

## Open items(待 user / 營業員確認)

1. user 所屬期貨商是誰(決定走哪一家的流程與嚴格度)。
2. 該期貨商的 TC4(ZMQ OpenAPI)通路是否確定可用(尤其富邦 — 官網文件是舊 gTrade 架構)。
3. 測試環境的端點 / 帳號發配方式、開放時段。
4. 是否需要登記程式名稱(影響 client 命名與 config 設計)。
