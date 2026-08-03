# 項 10/11 設計方案 — 十字線 + 軸標籤 + 常駐資訊列

> 來源:2026-07-29 fable 5 顧問 dispatch(user 於 /mod args 項 11 明確指定「請用 fable 5 思考」)。
> 原文照錄,未編輯。實作規格已吸收進 `change-spec.md` SC-7 與 §4 的 B9/B10/N3–N6。

## 1. 核心設計理念

**「軸上讀位置,面板讀資料」——把游標資訊拆成兩個去處,而不是塞進一個跟著滑鼠跑的浮窗。**

- **十字線水平臂 = 自由量尺**(跟滑鼠 y),配左緣價位標籤 + 右緣 % 標籤。盤中最常見的動作是
  「量距離」:現價到 CDP 線多遠、跌到某支撐是 −幾%。snap 到 bar 收盤的水平線做不到這件事,
  而且跟價格線本身重合、資訊冗餘。這也正面回答了 user 原話「左邊顯示目前滑鼠位置的價位」。
- **十字線垂直臂 = 資料錨**(snap 到分鐘 bucket / 蠟燭),對應的 bar 資料顯示在**圖上方固定
  位置的單行資訊列**,不是浮窗。固定停靠讓眼睛學會位置、零遮圖、零抖動;浮窗要眼睛追、
  會蓋掉 260 高江波圖約 13% 的可視區。
- **資訊列常駐**:沒 hover 時顯示即時最新 bar(江波圖 = 進行中的當分鐘;K 線 = 最後一根),
  hover 時切換成游標所在 bar。固定高度、固定欄位順序,絕無空白閃爍或版面跳動。
- 取捨結論:資訊**不**跟游標走(拒絕浮窗)、數值**分工**——位置類黏在軸上、bar 資料類集中在
  面板。兩張圖同一套規則,降低切換模式時的認知成本。

## 2. 具體版面規格

### 2.1 十字線(兩圖同規則)

| | 垂直線 | 水平線 |
|---|---|---|
| 江波圖 | snap 到分鐘 bucket(`g.minuteOf`,無資料 bucket 回 null 就**不畫**——白名單第 3 條不動) | **跟滑鼠 y**,只要游標在繪圖區(y ≤ 246)就畫,不依賴資料 |
| K 線 | snap 到蠟燭 `cx`(`g.indexOf`) | 同上(y ≤ 306) |

- 線型:兩臂皆 `stroke-ink-muted`、`strokeDasharray="2 2"`、`strokeWidth 0.7`——沿用現有
  hover 線樣式,不引入新視覺語彙。
- 江波圖加一顆**資料點**:hover 分鐘的收盤價位置畫 `<circle r={2.5} className="fill-ink">`
  (價格線是 accent 桃紅,點用 ink 亮白才浮得出來)。這顆點承接原本「水平線鎖收盤價」的
  語意——水平線變自由量尺後,分鐘收盤的視覺錨由它提供。K 線不需要,蠟燭本身就是錨。
- 江波圖垂直線**延伸進內外盤副圖**:副圖 svg 內同 x 畫一條(`toX(hoverMin)`,樣式同上),
  讓該分鐘的內外盤 bar 可對位。副圖不加標籤。
- 整個 hover 層包在 `<g pointerEvents="none">`(現慣例,維持)。

**兩圖水平線規則相同**的理由:項 10 明說「同樣顯示」,而且量尺功能在 K 線同樣成立
(量前波高低距離)。不做兩套。

### 2.2 滑鼠位置軸標籤

**左緣價位標籤(兩圖都有)**——貼左軸,蓋在靜態刻度文字之上:

| | 江波圖(viewBox 800×260) | K 線(viewBox 1400×320) |
|---|---|---|
| rect | `x=0, w=46, h=14, rx=2` | `x=0, w=56, h=16, rx=2` |
| 背景 | `fill-bg-deep` + `stroke-line`(**全不透明**,不要學現 tooltip 的 `/90`——半透明會跟底下刻度字疊字) | 同左 |
| 文字 | `x=4`,`fill-ink`,`fontSize="0.625rem"`,font-mono | 同左 |
| 值 | 滑鼠 y 反演成價格後 **snap 到合法 tick**(`snapDown`,`stock-tick` 已有)再 `fmt()` | 同左 |
| 夾制 | `top = clamp(ySvg − 7, 0, 232)`(232 = 260 − 14 時間帶 − 14 框高) | `top = clamp(ySvg − 8, 0, 290)` |

snap 到合法 tick 的理由:顯示的價位要「可下單」,42.15 這種非法 tick 對操作者是噪音。

**右緣 % 標籤(僅江波圖)**:`rect x=754, w=46, h=14`,`textAnchor="end" x=796`,值 = 同一個
滑鼠價換算 `(p−ref)/ref`,文字依正負 `fill-bull` / `fill-bear` / `fill-ink-dim`。`ref` 不存在
(pct null 的 fallback 域)就整塊不畫。**與既有右緣靜態 % 刻度共存**:不取代,hover 標籤
不透明背景暫時蓋過底下的刻度或 CDP/MA 疊線 label(x=width−32),移開即恢復——transient
遮蔽可接受,比重排版面便宜。K 線無 ref 語意(跨多日),不做 % 標籤。

**底部時間標籤(兩圖都有)**:垂直線落點的 x 軸帶上畫小框。江波圖 `w=34, h=13, y=247`,
內容 `HH:MM`;K 線 `w=48, h=14, y=307`,內容 `shortStamp(bar.t)`。水平夾制:
`cx = clamp(lineX, w/2, width − w/2)`。K 線價值特別高——現在 x 軸標籤是每 labelStep 根才一個,
hover 讀不到精確時間。

### 2.3 資訊列(取代浮窗)

**位置**:圖表 svg 正上方、圖框外的**單行 HTML 條**(不放 svg 內——viewBox 縮放會讓字級不可控)。

- 江波圖:塞進**既有 toggle 列的左半**——該列現在 `justify-end`,改 `justify-between`,
  左資訊右按鈕,不增高度。
- K 線:`CandleChart` 內、svg 上方新增一行(K 線目前圖內無頂列)。現有圖下方 `figcaption`
  tooltip **移除**(內容併入資訊列)。兩圖資訊列都在頂部,切換模式時視線不跳。

**樣式**:`font-mono text-xs`,固定高度(h-5),`gap-x-3`,欄位順序固定、缺值顯示 `-` 不移除
欄位(防寬度跳動;font-mono 本身即等寬)。

**欄位**:

| | 江波圖 | K 線 |
|---|---|---|
| 1 | 時間 `HH:MM` | 時間 `bar.t` 全字串 |
| 2 | 價(該分鐘 c;vs ref 著色 bull/bear) | 開 高 低 收(收 vs 開著色——沿用現 figcaption 邏輯) |
| 3 | 漲跌 %(同色) | 漲跌 %(vs 前一根收盤,著色) |
| 4 | 量(該分鐘 v) | 量 |
| 5 | **外 o / 內 i**(外 `text-bull`、內 `text-bear`) | — |

江波圖第 5 欄是新增的高價值項:每分鐘內外盤張數是本專案的核心訊號(CLAUDE.md §0a),
`MinuteAgg` 的 `o`/`i` 現成就有,原 tooltip 卻沒顯示。

**預設態(沒 hover)= 即時**:江波圖顯示最新分鐘的 agg(`last` 所在分鐘);K 線顯示最後一根
bar。hover 態顯示游標 bar。**態區分線索**:hover 時「時間」欄文字改 `text-accent`(十字線
在場 = 時間亮起),即時態用 `text-ink-muted`——零版面位移的最小提示。不跟 header 的現價列
搶戲:header 是全日摘要(現價/總量/期現價差),資訊列是「單一 bar 的解剖」,語意不重複。

江波圖底部既有 figcaption(累積外內盤 / 外盤比 / VWAP)是全日累計資訊,**保留不動**。

### 2.4 共用程度

**同一套規格,兩份實作;只抽兩個小共用件**:

1. `ChartReadout`(純 presentational HTML 元件:`fields: {label, value, tone}[]` +
   `hovering: boolean`)——兩圖共用。
2. 十字線常數 + `clampTag(y, boxH, plotBottom)` 夾制 helper(幾行的純函數)。

svg 內的 crosshair/標籤層**不抽共用元件**:兩圖幾何型別(`IntradayGeometry` vs
`CandleGeometry`)、座標系、資料 shape 都不同,泛化成本高於各自 ~40 行的 hover 層,
違反 scope 紀律(不為未來可能加 abstraction)。

## 3. hover 離開 / 觸控 / 資料缺口

- **離開**:`onPointerLeave` 清 hover state → 十字線與標籤消失、資訊列**立即**回即時態。
  禁止 fade/transition——盤中快速掃視時任何動畫都是判讀延遲。
- **觸控**:主場景是 Windows 桌機滑鼠,不做手勢工程。但把 `onMouseMove`/`onMouseLeave`
  換成 `onPointerMove`/`onPointerLeave`(一行等價替換),觸控「點一下即查、放開即清」免費
  拿到;svg 加 `touch-action: pan-y` 保頁面可捲。資訊列常駐設計本身就保證觸控使用者不 hover
  也看得到即時資料。
- **資料缺口**(江波圖某分鐘無成交):`minuteOf` 回 null 的行為不動(白名單)。**分解退化**:
  水平量尺 + 左價標 + 右 % 標只依賴滑鼠 y,照畫;垂直線、資料點、資訊列 hover 態需要資料,
  缺就不畫/回即時態。副作用是游標滑到最新資料右側的「未來區」時量尺仍可用(對著 CDP 線
  量價位)——這是 feature 不是 bug。K 線 `indexOf` 超界回 null 同理。

## 4. 給實作者的注意事項

1. **ChartStatic memo 邊界**:hover state 一律不得進 `ChartStatic` props。⚠ **現況有一個既存
   破洞會被本改動放大**:`CandleChart.tsx:187-188` 的 `ma5Line = showMa ? maLine(ma5) : []`
   在 render body 內每次產生新 array identity(含 `[]` 字面量),`ChartStatic` 的 memo 實際上
   被每次 render 打穿。現在 hover 只在換根蠟燭時 setState 所以不痛;水平線改跟滑鼠 y 後
   **每個 mousemove 都 render**,700 根蠟燭會每動一下重建。落地前必須先把
   `ma5Line`/`ma20Line` 包進 `useMemo`(依 `[g, ma5, ma20, showMa]`)。江波圖側 `g`/`oLines`
   已是 useMemo,無此問題。
2. **hover state 收斂**:江波圖 state 從 `hoverMin: number|null` 改
   `{min: number|null, y: number} | null`;`y` 先 `Math.round` 再 setState,並用
   `setHover(prev => 相同就回 prev)` 讓 React bail out,砍掉亞像素抖動的無效 render。
   K 線同規則。
3. **座標換算**:`ySvg = ((e.clientY − rect.top) / rect.height) × VB_H`。這條線性映射成立的
   前提是 svg 高度由 viewBox 比例決定(現況 `className="w-full"` + 無高度 class);若未來有人
   加固定高度 class 就會失真——在 onMove 旁留註解。
4. **價格反演**:兩份幾何 lib 各新增 `priceAtY(ySvg): number`(`toY` 的逆函數;江波圖
   `p = yTop − (y/H)(yTop−yBottom)`,K 線記得扣 `PAD_Y` 與 `usable`),clamp 進 y 域後
   `snapDown`。放 lib 純函數層,可單測。
5. **字級一律 rem**(專案鐵則):標籤文字 `0.625rem` 對齊既有刻度。注意兩圖 viewBox 寬不同
   (800 vs 1400),同 rem 在螢幕上的實際大小不同——這是既存條件,框尺寸(§2.2 表)已按各自
   user units 給定,不要跨圖抄數字。
6. **夾制數學**已在 §2.2 給齊:垂直 `top = clamp(ySvg − H/2, 0, plotBottom − H)`,
   水平 `cx = clamp(lineX, W/2, width − W/2)`;`plotBottom` = 圖高 − 14(時間帶)。
7. **測試連動**:移除 K 線 `figcaption`(`data-testid="candle-tooltip"`)會動到既有測試;
   資訊列給新 testid,依 `frontend-testing` skill 慣例補「預設即時態 / hover 態切換 /
   缺口分鐘退化」三個案例。江波圖 122×34 svg tooltip 一併移除。
8. `select-none`(白名單第 10 條)與 hover 層 `pointerEvents="none"` 維持。

## 5. 否決的替代方案

1. **跟游標跑的浮動 tooltip**(現江波圖做法的延伸)——遮圖(260 高的圖被 34 高的框蓋掉可觀
   面積,而且常蓋在開盤跳空最需要看的左上區)、眼睛要追著框跑、貼近右緣時還要翻面防裁切。
   每天用的工具,固定停靠的判讀速度完勝。
2. **雙臂皆 snap 到 bar 收盤**(treading-king `IntradayChart.tsx:209-261` 的做法)——水平線與
   價格線重合、資訊冗餘,失去量尺功能,且直接違反 user 要的「滑鼠位置的價位」。
   treading-king 值得抄的是它的**軸標籤小色塊**(`:244-258`)與 marker dot,不是 snap 策略。
3. **資訊面板放 svg 圖內固定角落**——viewBox 縮放使 HTML 字級鐵則(rem)失效、佔掉圖區、
   欄位增減要重算框尺寸。HTML 條零成本解決全部三點。
4. **抽一個泛用 `CrosshairChart` 共用元件包兩張圖**——兩圖幾何與資料 shape 差異大,抽象要
   引入一層 adapter,成本超過各自 ~40 行 hover 層;且會攪動 `ChartStatic` memo 邊界
   (白名單第 4 條)。共用停在 `ChartReadout` + 夾制 helper 這一層就好。

---

## 主 session 對本方案的偏離(實作時以 change-spec 為準)

- **K 線 viewBox 高度**:fable 假設維持 320(其夾制數字 `290` / `y=307` 據此推導)。
  change-spec B8 因 SC-6.7「兩圖渲染高度相同」把 K 線 viewBox 改為 **1400×578**
  → K 線的夾制上界改 `578 − 14 − 16 = 548`、底部時間標 `y = 565`。
  **fable 給的 K 線座標數字全部作廢,以 change-spec §4 N6 為準。**
- **主圖量 bar**:fable 讀到的是改動前的檔;SC-5 已決定砍掉主圖底部量 bar,
  江波圖 `plotBottom` 的推導不受影響(時間標籤帶仍是 14)。
