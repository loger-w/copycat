# change-spec — mod/overview-subtabs-breadth-colors

日期:2026-08-14。分流判定:**已成形**(user 指名檔案 / UI 形式 / 約束,且兩件事均已拍板)
→ grilling 姿態、決策點逐題 `[auto-default]`,無方向性抉擇需停等。
現況表:`current-state.md`(同目錄)。

## Auto-defaults(收尾回報必列)

- **AD-1**:subtab 恆有一顆 active,**預設「漲跌停」**,不提供「全收」態。
  [auto-default: 恆一顆 active | reason: 「記住上次選的 subtab」語意 + subtab UI 慣例;
  代價 = 有一個 panel 常駐輪詢(active gate 仍擋主 tab 切走的情境)]
  [amendment 2026-08-14: review P2-1 — 代價敘述補正:index 是**預設落地 tab**(App.tsx
  L48-50 fallback "index"),漲跌停 payload 全市場約 2800 列 / 10 秒;改版前預設全收合 =
  零輪詢。此為**刻意接受的新常態成本**(本頁核心就是廣度發現,使用者正看著它),
  收尾回報明列,不當未預期流量回歸。]
- **AD-2**:新 key `INDEX_SUBTAB_KEY = "copycat-index-subtab"`,值域
  `"limit" | "sector" | "timeline" | "corr"`。[auto-default: 沿 RAIL_TAB_KEY 命名慣例]
- **AD-3**:舊四支 OPEN_KEY 的既有值**不遷移**,直接廢止 + 進 `ORPHAN_STORAGE_KEYS` purge。
  [auto-default: 不遷移 | reason: 四顆獨立 bool(可同時 0-4 顆展開)對映不到單選,
  任何對映規則都是猜;純 UI 偏好,丟失代價 = 首訪回預設 subtab 一次]
- **AD-4**:subtab 列造型沿 `RightRail.tsx` 樣板(`role="tablist"` + `role="tab"` +
  `aria-selected`,active = `bg-bg-deep text-ink`);四個 panel 與 tab 列共用**一個**
  `section` 外框盒(rounded border bg-surface)。[auto-default: repo 內唯一 subtab 既例]
  [amendment 2026-08-14: review P2-2 — 新 tablist 必帶 `aria-label="台股綜合分頁"`
  (repo 已有「主要分頁」「交易面板分頁」兩個具名 tablist,全域 getAllByRole("tab") 撞名
  是寫進 App.test.tsx L436-441 註解的教訓);測試以該 label 收斂查詢。]
- **AD-5**:BreadthBand 平盤數字維持 `text-ink`(「中性」= 現況 token,不另創灰階)。
  [auto-default: 最小變更]

## 成功條件(SC)

- **SC-1 家數帶字色**:上市/上櫃兩列中,「上漲」格數字紅字(`text-bull`)、「下跌」格
  數字綠字(`text-bear`);「平盤」與「漲停」「跌停」格數字維持 ink;漲停格紅底、跌停格
  綠底不變;上漲/下跌/平盤格**無**底色。畫面可指認:家數帶第二格數字(如 512)為紅字、
  第四格(如 401)為綠字,首尾格底色照舊、數字非紅非綠。
  驗證:`BreadthBand.test.tsx` 新斷言(紅先行)+ 截圖 `evidence/SC-1-*.png`。
- **SC-2 subtab 列**:騰落線下方一列四顆 subtab(漲跌停 / 類股強弱 / 訊號時間軸 /
  相關係數),點選即切換下方 panel,**一次只掛載一個**;上方常駐區(基差列 / 兩張指數圖 /
  家數帶 / 騰落線)原樣。畫面可指認:原本四條各自「展開/收合」列消失,改為一列四顆
  分頁鈕 + 其下單一內容區。
  驗證:`IndexPage.test.tsx` 新 describe + 截圖 `evidence/SC-2-*.png`。
- **SC-3 記憶與還原**:切到某 subtab 後重新 mount(reload)仍停在該 subtab;寫入
  `copycat-index-subtab`;localStorage 值非法或缺 → fallback「漲跌停」;getItem/setItem
  拋例外(Safari 私密視窗)→ 不白屏、fallback 預設。
  驗證:`IndexPage.test.tsx`(含 throw stub 一條)。
- **SC-4 舊 key 廢止**:四支 `*_OPEN_KEY` 常數自 `constants.ts` 刪除;四個字串進
  `ORPHAN_STORAGE_KEYS`(App 啟動 purge);全 repo 無殘留引用。
  驗證:`App.test.tsx` purge 斷言擴充 + `grep -r "corr-open\|limit-list-open\|sector-open\|signal-timeline-open"` 僅剩 ORPHAN 清單與註解。
- **SC-5 unmount 語意保留**:切走 subtab = 舊 panel unmount —— corr 的兩條 WS 真斷線、
  漲跌停/類股的輪詢 query 隨之消失(原「收合 = unmount」設計的等價轉移)。
  驗證:`IndexPage.test.tsx`(CorrPage stub mount/unmount 計數)+
  `CorrSection.lazy.test.tsx`(unmount → FakeWS 全 closed)。
  [amendment 2026-08-14: review P1-2 — 補回歸保護缺口:既有「預設收合 → CorrPage 零
  mount、零 WebSocket 建構」兩條鎖(CorrSection.test (a) / lazy (b))被改寫掉後,
  「非 corr subtab 時零 WS」需在**新的唯一掛載點**補鎖。]
  [amendment 2026-08-14 round-2 P1-1: 補鎖分兩層才閉環 — stub 層 (s1)「CorrPage stub
  零 mount」(IndexPage.test.tsx);**真身層**新檔 `IndexPage.corr-lazy.test.tsx`
  (不 mock CorrPage):預設 subtab=limit → FakeWS.instances 為空(檔案級 mock 下
  「stub WS 建構數 0」恆真無鑑別力,不採)。]

UI SC 驗證窗口:無盤中依賴(subtab 結構與字色盤後可驗;家數帶數字盤後仍掛當日 EOD 值,
server 無資料時降級 = jsdom 測試 + user 過目截圖以 mock 資料頁面)。

## 不能破壞的既有行為白名單

- **W1** 上方常駐區零觸及:BasisRow / 雙 MarketPane(含 localStorage key 組、重疊鈕僅左)/
  BreadthBand 三態文案與桶序 / AdvanceDeclineChart,DOM 相對順序不變。
  [amendment 2026-08-14: review P0-1 — 措辭修正:常駐區**彼此**的相對順序與行為不變;
  但既有測試以「相關係數收合鈕」當**下錨**驗常駐區落點((f2) 等),改版後該錨消失,
  這些斷言屬「該紅 → 換錨點」,不是常駐區被動到。新錨 = subtab 列容器
  (`getByRole("tablist", { name: "台股綜合分頁" })` 或容器 testid `index-subtabs`)。]
- **W2** 非 active subtab = unmount(輪詢 query / WS 隨之消失);corr 重進有 lazy +
  WS 重連短暫空窗(既有 KR-2 可接受代價,語意不變)。
- **W3** active gate 全鏈:LimitList / Sector 的 `active=false`(主 tab 切走)停背景輪詢;
  SignalTimeline **刻意無** gate(一次性 query + WS bus)維持。
- **W4** SectorBody 的 FE-7 排序凍結與展開鑽取零觸及;LimitListBody 的篩選
  (`LIMIT_LIST_FILTER_KEY`)與空狀態判別零觸及。
- **W5** CorrSection 的 lazy chunk 邊界(`lazy(import CorrPage)`)與 Suspense fallback
  文字「相關係數載入中…」鑑別度保留。
- **W6** BreadthBand:漲停紅底 / 跌停綠底、停板數字 ink(既有測試 (f)(g) 原文不動仍綠);
  檔頭「紅底紅字難讀」設計理由保留並更新(非刪除)。
- **W7** App 跳轉全鏈:漲跌停列 / 類股成員列 / 時間軸列 → 個股(期)頁照常
  (App.test.tsx 僅改 seed 方式,斷言主體不動)。
- **W8** Safari localStorage try/catch 防白屏慣例:新 initializer 與 setItem 照抄四殼寫法。
- **W9** 孤兒鍵 purge 既有兩鍵照清;`FUT_CHART_MODE_KEY` 等活鍵不得入清單
  (fut-chart-mode.test.ts L82-86 不動仍綠)。

## Backward compat / migration

- localStorage:舊四鍵廢止,purge 於 App 啟動清除;不遷移(AD-3)。
- **可逆性**:git revert 還原 code;使用者瀏覽器中被 purge 的舊鍵值不可還原,但其內容
  僅「展開/收合」偏好,revert 後回「預設收合」一次,無資料損失 —— 判定可逆性可接受。
- API / 後端:零觸及。

## Out of scope

- 四個 panel body 的任何行為 / 樣式(排序、篩選、鑽取、WS 協定)。
- 家數帶以外的紅綠配色(基差列 / 騰落線既有配色不動)。
- RightRail 的 initialTab 沒包 try/catch(既有債,不順手修 — 記 next-time 候選)。
- MarketPane 的四處裸 `localStorage.getItem`(L255-281,同 RightRail 類既有債,本輪不修;
  round-2 P0-1 — (s5) throw 測試因此必須按 key 部分 stub,不得全域 throw)。
- subtab 內容的 lazy 化擴張(僅 corr 維持既有 lazy)。

## Edge cases

1. `copycat-index-subtab` 存了非法值(舊 "1"、亂碼)→ 白名單比對 fallback "limit"。
2. Safari 私密視窗:initializer getItem 拋 → catch 回 "limit" 不白屏;點切換 setItem 拋 →
   state 內存照切,偏好不落檔。
3. active=false(使用者切去期貨 tab)時掛載中的 limit / sector panel 停輪詢(W3 全鏈)。
4. corr subtab 首次點入:Suspense fallback「相關係數載入中…」→ CorrPage mount 建兩條 WS;
   切走再回 → WS 重建(W2)。
5. breadth 資料未達 / FinMind 未設:家數帶三態文案照舊(W6),字色改動不影響三態分支。

## Diff 級章節(逐檔;三類標記)

### 🔴 A. BreadthBand 字色(SC-1)

- `frontend/src/components/index/BreadthBand.tsx`:`BUCKETS` 加 `valueTone` 欄
  (up=`text-bull` / down=`text-bear` / 其餘 null→`text-ink`);數字 span 的 class 由
  `valueTone ?? "text-ink"` 決定;檔頭 6-8 行註解更新:保留「停板格底染色、停板數字 ink
  (紅底紅字難讀)」理由,補「上漲/下跌格無底色 → 數字承擔紅綠識別,不與底色互斥」。
- `frontend/src/components/index/BreadthBand.test.tsx`:**既有 (a)-(k) 全部不該紅**;
  新增(紅先行):上漲數字 text-bull / 下跌數字 text-bear / 平盤數字 text-ink 無 bull・bear /
  停板數字仍 ink(與 (g) 互補驗 limit_down)。

### 🔴 B. subtab 轉換(SC-2/3/4/5)

- `frontend/src/lib/constants.ts`:刪 `CORR_OPEN_KEY` / `LIMIT_LIST_OPEN_KEY` /
  `SECTOR_OPEN_KEY` / `SIGNAL_TIMELINE_OPEN_KEY` 四常數(註解一併);
  `ORPHAN_STORAGE_KEYS` 追加四字串 + 註記(2026-08-14 subtab 改版廢止);
  新增 `INDEX_SUBTAB_KEY = "copycat-index-subtab"` + doc 註解(值域、消費者 IndexPage)。
- `frontend/src/components/index/IndexPage.tsx`:騰落線 section 之後改渲染單一
  `section`(rounded border bg-surface)= subtab 列(AD-4 樣板)+ 當前 panel;
  `useState` initializer 白名單還原(try/catch,W8)、select 寫回 try/catch;
  四 section 依 subtab 條件 render,`onOpenStock` / `active` 傳遞不變。
- `frontend/src/components/index/LimitListSection.tsx`:卸收合殼(open state / toggle /
  button / OPEN_KEY import),改 `<div data-testid="limit-list" className="px-4 pb-4">` 包
  `LimitListBody`;props 不變;檔頭「收合 = unmount」註解改寫為「subtab 非 active =
  unmount(IndexPage 掛載閘),省輪詢設計不變」。
- `frontend/src/components/index/SectorSection.tsx`:同款卸殼(testid `sector-section`);
  SectorBody 以下零觸及(W4)。
- `frontend/src/components/index/SignalTimelineSection.tsx`:同款卸殼(testid
  `signal-timeline`);「無 active gate」檔頭理由保留。
- `frontend/src/components/corr/CorrSection.tsx`:卸殼,保留 lazy + Suspense(W5),
  wrapper 加 `data-testid="corr-section"`。
- **IndexPage.test.tsx 逐 describe 盤點**[amendment 2026-08-14: review P0-1/P0-2/P1-3 —
  本檔是唯一被大改的測試檔,不得概括]:
  - **測試腳手架契約(P0-2 / P1-1)**:預設 subtab=漲跌停 → **每次 render 都真掛
    LimitListBody 並 fetch**。現行 `stubFetch(DK_BODY)` 對所有 URL 回同一 body →
    `data.rows` undefined → `buildEntries` TypeError 整頁炸。故 `stubFetch` **改路由式**
    (App.test.tsx L120-133 樣板):`/api/market/breadth/rows` → 合法 BreadthRowsState
    (rows 可空陣列);**`/api/market/sector`(state)→ 合法 SectorState 為硬需求**
    (比照 App.test.tsx L67-83 SECTOR_STATE;industries 可空但 `rotation` 不得缺 —
    SectorSection.tsx L303-307 對 `rotation === null` 分支判別,undefined 直接拋,
    與 P0-2 同型;round-2 P1-2)— 路由表寫死在 beforeEach,不留「依測試需要」;
    其餘 fallback DK_BODY。
    CorrPage 用**檔案級 hoisted `vi.mock("@/components/corr/CorrPage")`** 計數 stub
    (CorrSection.test.tsx L20-32 樣板);掛載斷言一律 `findBy*` 等真身、卸載斷言
    unmount 計數 +1,**不用 `queryBy === null`**(lazy 下 vacuous pass,
    CorrSection.test.tsx 檔頭教訓)。
  - **不該紅但需改 fixture 維持綠**:(a)(b)(b2)(d)(d2)(d3)(c)(c2)(c3)(c4)(f)(f3) —
    斷言主體不動,靠路由式 stub 續綠。
  - **該紅 → 換錨/汰換**:(e)(e2) 相關係數收合鈕 describe 整組汰換;(g)(g2)(h)(h2)(i)(i2)
    收合鈕 + 落點 describe 汰換;(f2) **兩條斷言分開處理**(round-2 P2-1):
    `market-pane-left → breadth-band` 原文不動;`breadth-band → 相關係數鈕` 換錨為
    `breadth-band → subtab 列容器`(`getByRole("tablist", { name: "台股綜合分頁" })`)。
    (f2) 與新 (s6)(subtab 列在騰落線之後)語意互補、不重複。
  - **新 subtab describe(編號 (s1)-(s7),避免與檔內既有 (a)-(i2) 撞名;round-2 P2-2)**:
    (s1) tablist(aria-label 台股綜合分頁)四顆 tab、預設「漲跌停」`aria-selected` 且
    limit panel 掛載、sector/timeline panel 不在、**CorrPage stub 零 mount**(「stub WS
    建構數 0」已撤 — 檔案級 mock 下 stub 不建線,恆真 = vacuous,round-2 P1-1);
    (s2) 點「類股強弱」→ sector 掛載 / limit 卸載、localStorage 寫入 "sector";
    (s3) 預存 "corr" → corr active(stub findBy);(s4) 非法值("1"/亂碼)fallback
    漲跌停;(s5) getItem 拋 → 不炸、fallback — **部分 stub:僅對 `copycat-index-subtab`
    拋,其餘 key 走真實 localStorage**(`vi.spyOn(Storage.prototype, "getItem")` 按 key
    分流;全域 throw 會先炸在 MarketPane 的四處裸 getItem,測不到目標且誘發 out-of-scope
    修補,round-2 P0-1);(s6) subtab 列位於騰落線之後(compareDocumentPosition);
    (s7) corr → limit 切換:CorrPage stub unmount 計數 +1(SC-5)。
  - **真身級零 WS 鎖(round-2 P1-1 閉環)**:新檔 `IndexPage.corr-lazy.test.tsx`
    (**不** mock CorrPage;FakeWS 樣板沿 CorrSection.lazy.test.tsx):render IndexPage
    (路由式 stub 同上)→ 預設 subtab=limit 時 `FakeWS.instances` 為空、查無
    「等待六腿資料…」— 原 lazy (b) 的「收合態零建線」保護搬到新的唯一掛載點。
- **其餘測試檔(該紅的 → 本次 🔴 通道改 assertion)**:
  - `LimitListSection.test.tsx`:「收合閘門」describe 刪除,換「直接掛載 body、零 OPEN_KEY
    讀寫」smoke;body 測試開場拿掉 `setItem(LIMIT_LIST_OPEN_KEY,"1")`(openWith /
    openWithTimers / HTTP 失敗);FE-2 gate describe 斷言主體不動;**同步刪 `header()`
    helper 與 OPEN_KEY import**(殘留 = tsc/eslint 紅,P2-4)。
  - `SectorSection.test.tsx` / `SignalTimelineSection.test.tsx`:同款(seed 行拿掉、
    閘門 describe 汰換、header()/OPEN_KEY import 刪除,body 斷言不動)。
  - `CorrSection.test.tsx`:殼閘門三條汰換:render 即 mount stub(counts.mount=1)、
    RTL `unmount()` → counts.unmount=1(W2 元件層最小鎖;「非 corr subtab 零 mount」
    的鎖已上移 IndexPage 層);header() helper 與 CORR_OPEN_KEY import 刪除。
  - `CorrSection.lazy.test.tsx`:(b) 改「render 即真身 mount(等待六腿資料…)+ 兩條 WS
    建線」;(c) 改「unmount() → 兩條 WS 皆 closed、無第三條」。
  - `App.test.tsx`:L229/259 舊 seed 刪除(預設 subtab 即漲跌停);L308/365 改 setItem
    `copycat-index-subtab`="sector";L319 改 ="timeline";purge 單元測擴充斷言四舊鍵被清;
    L127 註解更新(「列表預設收合」→「預設 subtab 即漲跌停,停在 index tab 的測試恆走
    此分支」,P2-3);跳轉斷言主體不動(W7)。
- **註解漂移同步(P2-3)**:`frontend/src/hooks/useBreadthRows.ts` L11「收合即 unmount」
  → 「非 active subtab 即 unmount(IndexPage 掛載閘)」。
- **不該紅的(全量)**:BreadthBand (a)-(k) 原文、fut-chart-mode.test.ts、
  useBreadthRows.test.ts、SectorSection/SignalTimeline body 層斷言、App.test 其餘
  describe、其餘 108 個測試檔。

### 新測試清單(對應 SC)

| 測試 | SC | 檔 |
|---|---|---|
| 上漲/下跌/平盤/停板數字字色四斷言 | SC-1 | BreadthBand.test.tsx |
| subtab 列 + 預設 + 切換 + 互斥掛載 | SC-2 | IndexPage.test.tsx |
| 記憶 / 非法值 / throw fallback | SC-3 | IndexPage.test.tsx |
| purge 四舊鍵 + 新鍵不在孤兒清單 | SC-4 | App.test.tsx(或 constants 級)|
| 切換 unmount(stub 計數)/ WS 斷線 | SC-5 | IndexPage.test.tsx / CorrSection.lazy.test.tsx |
| 非 corr subtab 真身零 WS(round-2 P1-1)| SC-5 | IndexPage.corr-lazy.test.tsx(新檔)|

[amendment 2026-08-14: Phase 4 implementer 判斷追加,main session 裁決採納 —
(1) IndexPage.corr-lazy.test.tsx 補正向對照(點「相關係數」→ 等待六腿資料… + 建
/ws/corr /ws/river 兩條):單獨「零建線」半條在紅波恆綠(改版前預設收合也零建線),
無紅先行且擋不住 corr 路徑整條壞掉;(2) purgeOrphanKeys 測試另鎖
`copycat-index-subtab`(活鍵)purge 後仍在(fut-chart-mode L82-86 同型反向保護)。]

## Commit 計畫(🔵 → 🔴 → 🟢;本輪無 🔵)

1. `🔴 test(frontend): 綜合頁 subtab 語意 + 家數字色斷言先紅 [red]` — 上述該紅測試改寫
   + SC-1 新斷言(同一紅波;跑紅證據入 progress.md)。
2. `🔴 fix(frontend): 家數帶上漲/下跌字色(拍板配色) [green]` — A 節實作。
3. `🔴 mod(frontend)…` 實際 type 用 `fix`:四收合區塊改 subtab(constants + IndexPage +
   四殼)[green](body 註 red→green for <red-sha>)。
4. 若 review / 收尾產生補強鎖:`🟢 test(...)` 依 core-flow tag 判準。

## self_review_head

self_review_head: 71272009e7129ccf92bef4526068263139ba2291
(2026-08-14 自評 round-1:2 lens(impl-bug / spec-whitelist)→ 0 P0 / 0 P1 / 9 P2;
8 accepted 已修(066e5b1f + 71272009)、1 rejected(A-4 ARIA 半套 → next-time);
白名單 W1-W9 全 PASS。詳見 code-review-round-1.json)
