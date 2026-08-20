# B3 handoff:合併訊號列截字(/mod)

> 2026-08-21 從 next-time「2026-08-18 signal-denoise 節」兩條(截字 + 逐段 title)
> 升級開工。本檔自足:新 session 讀完即可跑 `/mod`。

## 一句話

SignalRail 的同 tick 合併列在 ~200px rail 內固定單行 truncate,真實資料下描述段
被切近四成 —— 改成可讀(換行或縮字)+ 逐段 hover 提示。

## 證據(2026-08-20 MCP 對 prod 真資料量測)

當日兩條真實合併列雙雙被切:

- 「跌破 CDP 中軸・爆跌 -2.06%」需 **154px** 只分到 **95px**(38% 被切);
- 規則名段「CDP 穿越・爆拉爆跌」需 **92px** 只分到 **57px**。

列總寬 189px。full text 目前在整列 title(「跌破 CDP 中軸・爆跌 -2.06%(CDP 穿越・爆拉爆跌)」),
但 hover 提示看不出 kind 段與規則名段的一對一對應(next-time T-12 partial)。

## 檔案地圖

- `frontend/src/components/stock/SignalRail.tsx` —— 合併列渲染(分隔符「・」、
  aria-hidden 已處理;合併組 key 取最早到達、段序 = 到達序,這些是 2026-08-18
  denoise 輪拍過的行為契約,**不得動**)。
- `frontend/src/components/stock/SignalRail.test.tsx` —— 段序/key 既有 lock。
- 合併口徑(groupSignals)在 lib 層 —— 只改「顯示」,不改分組。

## 修法候選(spec 階段拍板)

- (a) 合併列允許換行(clamp 2 行?);(b) 縮字級;(c) 兩者組合(先縮再折)。
- 順手項(next-time T-12):逐段 span 各帶自己的 title「kind(rule)」,
  取代整列單一 title。

## Scope

- In:合併列的顯示寬度策略 + 逐段 title。
- Out:toast/桌面通知合併(另案 B4)、groupSignals 分組口徑、Discord 文案、
  單則(非合併)列的樣式。

## 驗證(SC 候選)

- 機械判定:以 08-20 兩條實錄字串(上方)為 fixture,渲染於 200px 容器 →
  描述段完整可見(換行方案)或 clipped 量 < 拍板閾值(縮字方案);
  逐段 title 斷言各段對應。
- 真資料過目:prod 今日 jsonl 若有合併列直接看;沒有就側車注入同 tick 多則。
- 完成 gate:`npm test` + `npx tsc -b` + `npx eslint src` + react-doctor。

## Traps

- 先讀 `frontend-conventions` 與 `frontend-testing`(RTL selector / 本專案無 jest-dom)。
- SignalRail 列同時是 rail 寬 200px 的既定版面 —— 換行會改變列高,注意 rail
  滾動區與新訊號插入動畫(合併組「新成員前插不 remount」是 denoise 輪的行為契約)。
- S 級可主 session 直做。

## 分支與排程(2026-08-21 夜間無人值守鏈:A1 → B3 → B1)

- **分支**:`mod/signal-merged-row-wrap`。
- **鏈位**:第 2 棒。**前置 = A1 已 merge**:用 `/loop` 輪詢
  `git fetch && git log origin/master --oneline | grep spot`(或 `gh pr list --state merged --search "txo-spot-zero-price-gate"`),
  有輸出才 `git checkout master && git pull` 後開分支;輪詢間隔 10–15 分鐘即可。
- **完成訊號(給第 3 棒 B1 輪詢)**:本案 PR merge → `git log origin/master --oneline | grep merged-row`。
- **不動 prod server**(8721 由 A1 重啟過,本案純前端)。前端驗證 = `npm run dev`(vite,port 5173)
  + claude-in-chrome;盤後 server 有全日回補資料,今日 jsonl 的合併列可直接當真資料。
  viewport host 臨時檔(若用)收尾刪;收 vite 用 port → PID,**不要 taskkill node.exe**。
- 工作樹:串行鏈不開 worktree;開工前 `git status` 乾淨。
- 若 A1 逾時未 merge(卡在鐵則 F 三次上限停下等 user):本案**仍可開工** —— A1 純後端
  (aggregate.py)、本案純前端(SignalRail),檔案零重疊;從當下 master 開分支即可。
  等待上限建議 90 分鐘,超過就走這條。

## 起跑 prompt

```
/mod 合併訊號列截字:SignalRail 同 tick 合併列在 200px rail 單行 truncate,真實資料 38% 被切(「跌破 CDP 中軸・爆跌 -2.06%」154→95px);改可讀(換行或縮字,spec 拍板)+ 逐段 span title「kind(rule)」。先讀 docs/superpowers/specs/2026-08-21-b3-signal-merged-row-truncation-handoff.md(實測 fixture 與行為契約清單已備齊);不得動合併分組口徑與段序契約。
```
