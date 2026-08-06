# design — 群組多檔即時分時圖 v1

changelog:
- v1(2026-08-06):初版。
- v2(2026-08-06):review round 1 十一條全修 — **R1(P0)棄用 `/api/stock/state/{code}`
  (該 route 會 `set_main`,群組檢視會每分鐘搶主檔 30 次令主圖凍結)→ 新唯讀 batch
  `GET /api/stock/group-state?codes=…`**;R2 payload 只回 minutes/meta/no_data(不含
  數千筆 ticks);R3 quotes_fn 帶名稱;R4 _states 迭代 C-level 快照;R5 mini 幾何
  viewBox 平移裁軸帶;R6 pill 掛 main 頂層兩條件外;R7 輪詢 inTradingHours gate;
  R8 quotes 走 _quote_payload/_watchlist 單一定義;R9 排序鍵與 N 明定;R10 延伸規則
  明定;R11 卡片價 p ?? ref。
- v3(2026-08-06,限縮輪 R12-R19 全修):**R12(P0)群組成員補回補** — group_snapshot
  對今日未回補成員入列 job;backfill 套用 guard 改「job 自帶 code」不綁 _main;
  `_backfilled` set 防重;payload 帶 backfilling;R13 幾何補償改 height=H+X_LABEL_H、
  viewBox y=0;R15 payload 形寫死 + minutesFromRecord 共用;R16 quotes 風險敘述更正;
  R17 空群組零請求空態;R18 錯誤碼測試列更正;R19 SC-2 擴充註記;R14 檔案表補齊。

**Goal**:群組成員 mini 分時圖牆 + Discord 同群摘要(brainstorm SC-1..5)。

**架構**:後端零新增廣播 — hub 注入 `groups_fn`/`quotes_fn` 兩個 callable,同群摘要在
**Discord worker**(離熱路徑)組裝,WS/jsonl payload 零改。前端群組檢視純組合既有件:
snapshot API(TQ per-code)+ `watchlist_quote` 現價延伸 + `buildIntradayGeometry`
小尺寸重用。

## 檔案組織

| 檔 | 變更 | SC |
|---|---|---|
| `copycat/server/signal_hub.py` | `groups_fn`/`quotes_fn` 注入;`on_watchlist` 刷新 `_groups`;`_send_discord` 組同群尾綴 `_group_suffix(row)` | SC-1/2 |
| `copycat/server/stock_engine.py` | 新公開 `quotes() -> dict[str, tuple[str, float \| None]]`(R19:相對 brainstorm SC-2 擴充帶名稱 — 摘要要印成員名,只有 `state.meta.name` 拿得到);新公開 `group_snapshot(codes) -> dict`(R12/R14:輕量形 + 未回補成員入列 backfill);**backfill 套用 guard 改 job 自帶 code**(:653 的 `code == self._main` → job code + generation)+ `_backfilled: set[str]`(rollover stage2 清空) | SC-2/4 |
| `copycat/server/app.py` | hub 建構傳 `groups_fn`/`quotes_fn`;**新 route `GET /api/stock/group-state`(R1/R2)** | SC-2/4 |
| `frontend/src/components/stock/GroupGridView.tsx`(新) | 群組下拉 + 卡片 grid + 空態 | SC-3 |
| `frontend/src/components/stock/MiniIntradayChart.tsx`(新) | mini 分時線(平盤虛線+紅綠面積,無軸) | SC-3 |
| `frontend/src/hooks/useGroupSnapshots.ts`(新) | batch query,盤中輪詢,enabled gate,回傳含 backfilling | SC-4 |
| `frontend/src/lib/stock-accum.ts` | 抽 `minutesFromRecord` 共用(fromSnapshot 改呼叫;🔵 獨立 commit,R12) | SC-4 |
| `frontend/src/components/stock/StockPage.tsx` | 檢視切換「單檔｜群組」+ GroupGridView 掛載 + onPick 切單檔 | SC-3 |
| 測試 | test_signal_hub 同群摘要組 / test_stock_engine quotes / 前端三新件 colocated + StockPage | 全 |

## SC-1/2 後端

```python
# signal_hub.SignalHub.__init__ 新參數(keyword-only,預設 None = 停用摘要,測試免接):
groups_fn: Callable[[], list[dict]] | None = None,   # [{name, codes}](Watchlist["groups"] 形)
quotes_fn: Callable[[], dict[str, tuple[str, float | None]]] | None = None,
# code → (名稱, chg_pct);名稱可空字串(R3 — 摘要要印成員名,來源 = engine 的 meta.name)

# on_watchlist(codes) 尾端:groups_fn 非 None → self._groups = groups_fn()
#(try/except log — 檔案讀取失敗不影響 membership 更新;_groups 保舊值)

def _group_suffix(self, row: dict) -> str:
    """同群摘要(SC-1)。在 Discord worker 呼叫 — 離熱路徑,quotes 取發送當下快照。
    code 不屬任何群組(取第一個含它的群組)/ 群組僅它一檔 / 兩 fn 未注入 → ""。
    其他成員排序鍵 = (chg is None, -abs(chg or 0))(R9 — 無行情排最後),取前 4;
    chg None → "-";名稱空 → 只印代碼;群組成員總數(含觸發者)> 5 → 尾加「…共 N 檔」
    (N = 群組成員總數,R9)。格式:｜同群 {群組名}:{code}{名} {+x.x%}、…
    任何例外 → "" + log(摘要失敗不影響訊號送出)。"""

# _send_discord:text = format_signal_text(row) + self._group_suffix(row)
```
- `stock_engine.quotes() -> dict[str, tuple[str, float | None]]`(R8/R16):
  開頭取 local 參照 `codes = self._watchlist`(該欄位以**整份重新指派**更新 —
  迭代中 `set_watchlist` 換名單時 local 參照保證一致快照;R16 更正 R4 的錯誤風險
  敘述 — `_states` 在此寫法下無 dict 迭代,無 size-change 風險)。domain 天然排除
  `F:` 期貨偽鍵;chg_pct 走 `_quote_payload(code)["chg_pct"]` 唯一定義;名稱 =
  `state.meta.name`(缺 → ""）。測試鎖:迭代中換名單不炸不漏鍵。
- app 接線:兩 callable 皆輕同步(groups 檔案讀僅 on_watchlist 時)。

## SC-4 唯讀 batch 端點(R1/R2 — **不得重用 `/api/stock/state/{code}`,它會 set_main**)

```
GET /api/stock/group-state?codes=2330,2317,…
→ 200 {"states": {code: {minutes: {"540": {c,v,i,o,u,h,l}, …},
                          meta: {name, ref, upper, lower, y_vol} | null,
                          no_data: bool, backfilling: bool}}}
```
- **payload 形寫死(R15)**:後端 `snap = state.snapshot()` 後**只挑** minutes/meta/
  no_data 三鍵(沿 `StockDayState.snapshot()` 的鍵名對映單一定義 — 直接丟 dataclass
  會讓前端 `meta.ref` undefined → hasRef=false → 紅綠面積靜默消失)+ `backfilling`。
- **不 set_main、不改訂閱池**;但 `group_snapshot` 對「今日尚未回補」的**已訂閱**成員
  `_backfill_jobs.put_nowait((code, generation))`(R12 — queue put 非訂閱變更):
  - backfill 套用 guard(:653)由 `code == self._main` 改為「**job 自帶的 code** +
    generation 相符」;`_backfilled: set[str]` 防重複入列(rollover stage2 / reconnect
    generation bump 時清空)。
  - 未回補完成前該 code 回 `backfilling: true`,卡片顯示「回補中…」不呈現半截圖。
- codes 空參數 → 200 `{"states": {}}`(R17);上限 30 超過 → 400 `BAD_CODES`;
  單碼格式錯 → 400 `BAD_CODE`;引擎未起 → 503 NOT_READY。**無 404 路徑**(R18):
  未知/未訂閱 code → `no_data: true` 空 minutes。
- R2 量法:`curl …/group-state?codes=<熱門股>` bytes 記入 evidence。
- 測試(R18):fake engine `set_main` 呼叫**恆 0** / 超量 BAD_CODES / 壞碼 BAD_CODE /
  未知 code no_data / 503 / payload 形狀 / 未回補成員 job 入列一次(重打不重複)/
  **主圖回補行為零退化**(set_main 路徑照舊)。
- Known Risk:群組回補與主圖回補共用序列 worker(FIFO)— 先開 30 檔群組再切主檔,
  主檔回補會排在其後(秒~分鐘級);接受,记 next-time 若實用上卡再做優先權。

## SC-3/4 前端

- `StockPage`:檢視切換 pill(「單檔」「群組」;localStorage `copycat-stock-view`)
  掛在 **main 頂層、`code === null` 與 `accum === null` 兩個條件分支之外**(R6 —
  未選股 / 主圖 snapshot 失敗時群組檢視仍可達);群組檢視時整段 header + 圖表 +
  下半列不渲染,換 `GroupGridView`;訊號欄/自選欄不動。`onPick(code)` = 既有選股
  setter + 切回單檔。vitest:`code={null}` 仍可切群組見卡片(R6 鎖)。
- `GroupGridView` props:`{ groups, quotes, onPick }`;內部 selected group
  (localStorage `copycat-stock-group`;失效 fallback 第一個;零群組 → 空態
  「尚無群組 — 到自選欄建立群組」;**空群組(成員 0)→ 「這個群組還沒有成員」+
  hook enabled=false 零請求**,R17)。grid:`repeat(auto-fill,minmax(15rem,1fr))`。
- 卡片:上列 `{code} {name}`(左)+ 價格(右)— **`p ?? ref`**(R11:`watchlist_quote`
  的 p/ref 互斥;p 態紅漲綠跌 + chg%、ref 態中性色 + 小字「參考」,判斷序與側欄同);
  下方 `MiniIntradayChart`;no_data / 失敗 → 「無資料」占位。點卡片 → `onPick(code)`
  (整卡 button,aria-label)。
- `MiniIntradayChart` props:`{ minutes, meta, liveP }` — 幾何補償(R5/R13):
  `buildIntradayGeometry(input, { width: W + Y_AXIS_W + R_AXIS_W, height: H + X_LABEL_H })`
  後 svg `viewBox="${Y_AXIS_W} 0 ${W} ${H}"`(此時 plotH = H − 2·PAD_Y,內容落
  [PAD_Y, H−PAD_Y] 上下對稱各留一份 — R13 修正 v2 的「上緣 0 下緣 4px」不對稱,
  漲停貼頂線不被裁半條 stroke)。lock test:x 滿版 + **所有 priceLine y ∈
  [PAD_Y, H−PAD_Y]**。
- minutes 轉換:`minutesFromRecord(rec)`(自 `fromSnapshot` 抽共用或新純函式,
  `Number(k)` + `h/l ?? null` 正規化;R15)+ lock test「meta.ref 有值 →
  geometry.hasRef === true」。
  **liveP 延伸規則(R10)**:分鐘鍵 = 本機時鐘分鐘,僅當 `∈ [X_START_MIN, X_END_MIN]`
  且 `liveP > 0` 才延伸;淺拷 Map 後 — 既有 bucket **只覆寫 `c`**(v/o/i/u/h/l 原樣),
  無 bucket → `{c: liveP, v: 0, i: 0, o: 0, u: 0, h: null, l: null}`。
  只畫 refY 虛線(hasRef)+ priceLine + 紅綠面積;無 y 刻度、無 hover、無 VP。
- `useGroupSnapshots(codes: string[], enabled: boolean)`:TanStack `useQueries` 或單一
  query 打 **`GET /api/stock/group-state?codes=…`**(batch 一次;R1/R2),
  `refetchInterval: () => (inTradingHours() ? 60_000 : false)`(R7 — 函式形,沿
  useStockBars 慣例與其閉包坑教訓),`staleTime: 55_000`,`enabled` gate;
  回 `{code: {minutes: Map, meta, noData}}`。

## 邊界

- 群組成員 ≤30(watchlist 上限)→ 最多 30 個 query;60s 週期 + staleTime,負荷可控。
- 檢視切換保留 DOM?— 否:群組檢視條件 render(mini 圖無累積狀態,重掛成本 = 一輪
  query cache 命中);`hidden` 慣例僅適用 nav tab 層,此處資料由 TQ cache 承接。
- 主圖 code 的 tick 流不受檢視影響(useStockStream 照跑;切回單檔零重建)。
- Discord 摘要與 WS/jsonl 解耦:摘要組裝失敗(任何例外)→ 空字串 + log,不影響送出。

## Known Risks

- **群組卡片為分鐘級 + 現價點**(非 tick 級):60s 輪詢(盤中才輪)+ quote 延伸;
  精度取捨已拍板(brainstorm auto-default)。
- **同群摘要為 Discord 專屬**:WS/jsonl 無此欄;前端 feed 不顯示同群資訊(群組檢視
  本身承載)。
