# change-spec:合併訊號列截字(S 級,0 輪 review)

分流判定:已成形(handoff 指名落點檔案 + 候選做法)→ grilling 姿態,全題 auto-default。

## 拍板
- D1 換行 vs 縮字:`[auto-default: 換行 clamp 2 行 | reason: 154px 需求在 189px 列內縮字要 <0.75x 才單行,盤中可讀性反而更差;2 行 clamp 涵蓋實測兩條(154、92px)且 rail 列數損失有界]`
- D2 規則名段位置:`[auto-default: 合併列改堆疊於 kind 段下方 | reason: 並排時兩段搶同一行寬,kind 154 + rule 92 > 150 可用,任一都還是被切]` `[amendment 2026-08-21: review L1-4 —— 規則名段固定單行 truncate(不 clamp-2),列高上限 1+2+1 行]`
- D3 適用範圍:`[auto-default: 只對 segments.length > 1 的合併列換版;單則列 truncate 不變 | reason: handoff Out 明列單則列樣式]` `[amendment 2026-08-21: review L1-3 —— 判準改 segments>1 || ruleNames>1,同 kind 兩規則(edge 3)亦為合併列]`
- D4 逐段 title:`[auto-default: kind span title = label(rule_name)(rule 缺值只 label);規則名 span title = rule(該規則發出的 kind labels)| reason: T-12 一對一對應]`;整列 title 移除(逐段已涵蓋)。單則列也套逐段 title(內容與原整列 title 等價,非樣式改動)。

## SC
- SC-1 合併列 kind 段容器無 `truncate`、有 `line-clamp-2`(+ `whitespace-normal` / `break-words`);單則列仍 `truncate`。驗:`SignalRail.test.tsx` className 斷言。
- SC-2 逐段 title:fixture 08-20 實錄(cdp_cross from_above ["cdp"] + crash -2.06,rule「CDP 穿越」/「爆拉爆跌」)→ 「跌破 CDP 中軸」span title=「跌破 CDP 中軸(CDP 穿越)」、「爆跌 -2.06%」title=「爆跌 -2.06%(爆拉爆跌)」;規則名 span「CDP 穿越」title=「CDP 穿越:跌破 CDP 中軸」。驗:RTL getByText(...).getAttribute("title")。
- SC-3 畫面可指認:vite dev + claude-in-chrome,200px rail 內合併列「跌破 CDP 中軸・爆跌 -2.06%」完整可見(無「…」),規則名另起一行灰字;價格仍靠右同列。驗:截圖 evidence/SC-3-*.png + user 過目。
- SC-4 既有 24 測試全綠。`[amendment 2026-08-21: 「段間分隔符 aria-hidden」一則為該紅 —— 規則名段改逐段 span 後分隔符由 1 個變 2 個,exact getByText 撞多元素(selector 過鬆,非行為破壞);斷言改為 getAllByText 長度 2 且全 aria-hidden(加強,非放寬)]`

## 白名單(不得破壞)
- W1 合併列 textContent 仍含「爆跌 -2.10%・突破 CDP 中軸」與「爆拉爆跌・CDP 穿越」(段序到達序)。
- W2 「・」aria-hidden;逐段 tone class。W3 key = 最早到 id(不改 groupSignals)。W4 點列 onSelect(code)。
- W5 rule_name 缺值 → 不渲染規則名段、不留分隔符。W6 單則列**版型 class** 不變(仍 flex + truncate;DOM 因逐段 title 多一層 span —— review L1-5 措辭收斂)。

## Edge cases
1. 合併列 rule_name 全缺 → 無規則名行,kind 段仍 clamp 2。
2. 三段以上(cdp+crash+vol_burst)→ clamp 2 行截第三行末,title 逐段仍完整。
3. 同 kind 兩規則(kind 段去重 1、規則名 2)→ kind span title 取首見 sig 的 rule_name;規則名 span 各自 title 指回同一 kind label。

## Out of scope
toast/通知合併(B4)、groupSignals 口徑、Discord 文案、單則列樣式、rail 寬度。

## Diff 級
- 🟢 `SignalRail.test.tsx`:新增 SC-1/SC-2 測試 [red]
- 🔴 `SignalRail.tsx`:合併列第二行改版 + 逐段 title [green](行為改動屬顯示層;既有測試不該紅)

## Review
- round-1:`code-review-round-1.json`(2 lens,P1×3 / P2×8;全部處置完畢)。
- self_review_head: 0d4543a8
