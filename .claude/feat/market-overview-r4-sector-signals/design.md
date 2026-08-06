# R4 類股強弱 + 訊號事件流 — design.md

**版本 v2**(2026-08-06)。SC 來源:`brainstorm.md` §3(SC-1~SC-8,含 round 1 後 amendments)。

Changelog:
- v1:初版。
- v3(限縮 round 2,8 條全 accepted):[R2-1] `_diff_limit_events` hub None 早退
  (attach 前不推進狀態機);[R2-2] parity 記載更正(limit_judged 為 copycat-only
  附加鍵,oracle 不比逐鍵、不重錄);[R2-3] `today_signals` 改讀 {engine 日,
  本機日} 聯集 + id 去重,KR-1 改寫;[R2-4] seed unpack 修正;[R2-5] `code =
  row["stock_id"]`;[R2-6] 時間軸分族各 cap;[R2-7] today 端點 `?market=` 後端
  過濾;[R2-8] 分鐘域更正 0901–1330 + 1331–1335 clamp。
- v2:design review round 1(13 條全 accepted;R7 部分)——
  [R1+R6] §6 全面改寫:raw 轉移偵測 + 靜默 baseline → **jsonl 回放 seed +
  `last_emitted` 對帳制**(開盤即鎖照發、冷卻結束補對帳、重啟不重發不漏發);
  [R5] rows 加 `limit_judged` 三態 + 逐筆容錯;[R7] `publish_market_events` 的
  trade_date 由 breadth 顯式傳入,殘餘窗入 Known Risks;[R2/R3] 前端過濾下沉
  feed 層(cap 前)+ useSignalAlerts 過濾;[R4] rows_to_chain_map 忠實照抄
  neigui(缺 sub 整列丟 + sub 內去重);[R8/R9] verify.py 入修改清單 + fake
  可控翻轉 + 失效注入前置;[R10] 量法端點修正 + route 422/404 語意;
  [R11] ctor 初始化明寫;[R12] chain 刷新改獨立 task;[R13] kindLabel 兩案。

---

## 1. 架構概觀與資料流

```
FinMind TaiwanStockIndustryChain ──(獨立刷新 task + 7天 TTL disk cache)──┐
FinMind snapshot(既有 10s poll)                                          │
        │                                                                 ▼
        ▼                                            ┌── compute_sector_rotation ──► /api/market/sector
  BreadthEngine._apply(既有)── universe ────────────┤    compute_sector_members ──► /api/market/sector/members
        │ rows(limit 旗標 + limit_judged)           └──(copycat/sector_rotation.py 零 IO)
        ▼
  _diff_limit_events(新:last_emitted 對帳 + cooldown + jsonl seed)
        │ MarketEvent
        ▼
  SignalHub.publish_market_events(新入口,繞過規則 slots,trade_date 顯式傳入)
        ├─► WS publish(既有 /ws/stock「signal」訊息)──► 前端 signal bus
        └─► jsonl enqueue(notify=False,Discord 零收件)──► data/signals/<date>.jsonl
                                                              │
                              /api/stock/signals/today(既有)◄┘
        前端:SignalTimelineSection(feed 全收)/ SignalRail・useSignalAlerts(feed 排除 market)
              SectorSection(REST 輪詢)
```

失效域(總 spec §3):chain / rotation 壞 → 只有類股面板 degraded(chain 刷新在
獨立 task,最壞不拖慢家數輪);事件層壞 → 只少事件(逐筆容錯 + 批次 never-raise);
FinMind 整組壞 → 沿 R2 既有退避,TC4 系零波及。反向殘餘耦合見 Known Risks KR-1。

## 2. 檔案組織

**新增**:
- `copycat/sector_rotation.py` — 零 IO 純函式(SC-1)
- `copycat/server/chain_store.py` — chain cache 落檔/回讀(SC-2)
- `frontend/src/components/index/SectorSection.tsx` — 類股強弱區塊(SC-3)
- `frontend/src/components/index/SignalTimelineSection.tsx` — 時間軸區塊(SC-7)
- `frontend/src/lib/sector-model.ts` — sector TS 型別 + fetchers(SC-3)
- `tests/test_sector_rotation.py` / `tests/server/test_chain_store.py` /
  engine・hub 測試擴充(實名:`tests/server/test_breadth_engine.py` /
  `tests/server/test_signal_hub.py`)
- 前端對應 `.test.tsx`

**修改**:
- `copycat/server/breadth_fetch.py` — `fetch_industry_chain`(SC-2)
- `copycat/breadth_config.py` — `event_cooldown_secs` / `chain_ttl_hours`(SC-2/5)
- `copycat/market_breadth.py` — rows_out 加 `limit_judged`(SC-5;copycat-only
  附加鍵,parity fixture 不比逐鍵、不需重錄 — R2-2)
- `copycat/server/breadth_engine.py` — chain 刷新 task + rotation 計算 + diff 事件源 +
  attach(SC-2/4/5)
- `copycat/server/signal_hub.py` — `publish_market_events` + `market_event_state` +
  `_kind_text` 兩案(SC-6)
- `copycat/server/app.py` — 兩條 route + attach/detach 接線 + fetchers 五元組(SC-3/6)
- `copycat/server/verify.py` — fake 五元組(chain fake 附小型固定 chain 表;
  `VERIFY_BREADTH_FAIL` 涵蓋 chain)+ fake snapshot 可控翻轉(SC-7 取證)
- `frontend/src/lib/signal-model.ts` — kind union 擴充 + `isMarketKind` +
  `kindLabel` 兩案 + `mergeSignals` 前置過濾配合(SC-7/8)
- `frontend/src/hooks/useSignalFeed.ts` — kind 過濾參數(cap **之前**)(SC-8)
- `frontend/src/hooks/useSignalAlerts.ts` — market kinds 早退(SC-8)
- `frontend/src/lib/constants.ts` — `SECTOR_OPEN_KEY` / `SIGNAL_TIMELINE_OPEN_KEY`
- `frontend/src/components/index/IndexPage.tsx` — 掛兩個新區塊(SC-3/7)
- `frontend/src/components/stock/StockPage.tsx` — SignalRail 餵入 feed 的排除 market
  版本(SC-8)
- `docs/superpowers/specs/2026-08-05-taiwan-market-overview-tab-spec.md` — 收尾回寫
  推翻假設(§5 R4「industry override 表」記載對 rotation 不適用)
- `CLAUDE.md` — breadth_engine/新檔案一行描述 + FinMind dataset 補記

## 3. SC-1:sector_rotation 純函式(`copycat/sector_rotation.py`)

neigui `market_today.py:242-312/:425-467` + `industry_chain.py:114-128` 邏輯全等搬移,
適配 copycat 慣例(sync、dict in/out、docstring 記偏離):

```python
ChainMap = dict[str, dict[str, list[str]]]  # {industry: {sub_industry: [stock_id]}}

def rows_to_chain_map(rows: list[dict]) -> ChainMap: ...
    # neigui _rows_to_map **逐行等價**:sid/industry/sub 任一缺(falsy)→ 整列丟棄
    # (不是進 "" 桶 — R4);同 (industry, sub) 內同 sid 去重(防上游重複列)。
    # probe 實證欄位:date/industry/stock_id/sub_industry;6861 rows/47/512。

def compute_sector_rotation(universe_rows: list[dict], chain_map: ChainMap | None) -> dict | None: ...
    # 輸出 {"industries":[{"name","members","avg_change_rate","vol_ratio","subs":[...]}]}
    # industry 層 = 全 subs stock_id 聯集去重;avg desc 排序;members=0 skip;
    # chain_map None/空 → None。universe_rows 需 stock_id/change_rate/
    # total_volume/yesterday_volume(= assemble_universe 輸出,非 compute_breadth rows_out)

def compute_sector_members(
    universe_rows: list[dict], chain_map: ChainMap | None,
    name_map: dict[str, str], industry: str, sub_industry: str | None = None,
) -> dict | None: ...
    # {"industry","sub_industry","members":[{"stock_id","name","change_rate",
    #  "vol_ratio","total_amount"}]};未知 sector → None
```

測試:neigui `test_market_today.py:239-360` 八案等價搬 + `_rows_to_map` 案
(`test_industry_chain.py` parse 相關案)+ **缺 `sub_industry` row → 整列丟棄**
斷言(R4)。手算 fixture 沿 neigui 同數字。

## 4. SC-2:chain 取數 + 快取

### 4.1 `breadth_fetch.fetch_industry_chain(token) -> list[dict]`

`dataset=TaiwanStockIndustryChain` 無其他參數;`_ATTEMPTS=2` / 402 →
`BreadthFetchError(quota=True)` 全沿既有慣例;rows < 1000 降 warning
(實測 6861,腰斬即異常)。

### 4.2 `chain_store.py`

```python
def load_chain(path: Path) -> tuple[list[dict], float] | None: ...  # (rows, fetched_at epoch)
def save_chain(path: Path, rows: list[dict], fetched_at: float) -> None: ...
```
檔:`<data_dir>/industry_chain.json`,`{"_version":1,"fetched_at",rows}`,
tmp + `os.replace` 原子寫;版本/形狀不符 → None(沿 `_restore` 慣例)。
fetched_at 用 epoch(`time.time()`)—— TTL 以掛鐘算,跨重啟有效(單調鐘不可落檔)。

### 4.3 engine 刷新紀律(獨立 task — R12)

ctor 加 `chain_fetch: ChainFetch | None = None`(None = rotation 停用,面板
`rotation: null`)+ 明確初始化(R11):

```python
self._chain_map: ChainMap = {}
self._chain_fetched_at: float | None = None   # epoch;None = 從未成功
self._chain_task: asyncio.Task[None] | None = None
self._chain_retry_at: float | None = None     # 單調鐘
self._rotation: dict | None = None
self._universe_rows: list[dict] = []
```

`start()` 時 `load_chain` 進 `_chain_map`(**過期也先用** — stale 勝於無)。
poll loop 每圈 `_maybe_arm_chain()`(武裝判定,同 streak task 形狀):
`chain_fetch 有 and task 不在跑 and TTL(chain_ttl_hours,預設 168.0)過期
and retry 冷卻已過` → 起 fire-and-forget task。task 內:`asyncio.to_thread(fetch)`
→ `rows_to_chain_map` 非空 → `save_chain` + 換 `_chain_map`;失敗 → 沿用舊表,
`_chain_retry_at = mono + 60s`(quota → `quota_backoff_secs`)。**poll loop 不
await chain task**,家數輪零阻塞(§1 失效域宣稱的前提)。`close()` 一併 cancel。

## 5. SC-4:rotation 計算掛點與端點

`_apply` 成功路徑(`_rows_date` 更新處)加:

```python
self._rotation = compute_sector_rotation(universe, self._chain_map)
self._universe_rows = universe  # members drill-down 原料(與 rows 同輪同源)
```

新對外方法:

```python
def sector_state(self) -> dict:
    # {"enabled": True, "trade_date": _rows_date, "as_of", "stale": _stale(),
    #  "rotation": self._rotation}   # 首輪未成 / chain 缺 → rotation None
def sector_members(self, industry: str, sub_industry: str | None) -> dict | None:
    # compute_sector_members(self._universe_rows, self._chain_map, self._name_map, ...)
```

routes(app.py,三態判式與 `/api/market/breadth` 同款):
- `GET /api/market/sector` → `sector_state()`;引擎 None → `{"enabled": loading 三態,
  "rotation": None, ...}`。**三態測試含「boot 完成、首輪未成 → 200 且
  rotation=null」案(R11)**。
- `GET /api/market/sector/members?industry=&sub=` → 回 members。語意(R10):
  `industry` **缺席** → 422(FastAPI required);`industry` 空字串或查無 →
  404 `{"detail":{"error":"SECTOR_NOT_FOUND"}}`;`sub` 空字串**當未指定**
  (chain_map 無 "" 桶 — §3 缺 sub 整列丟)。

SC-4 盤中對照量法(R10 修正):側車 server(R2 樣板)起 fake TXO + 真 fetchers →
同一分鐘 `curl "http://<neigui>/api/market/snapshot?refresh=true"` 與 copycat
`/api/market/sector` 各落檔,記兩端 `as_of`(差 ≤ 10s 才比),比 industries
名稱序列全等 + 逐業 avg_change_rate 差 ≤ 0.01pp。窗外降級:錄同一份 snapshot
rows 餵兩邊純函式(fixture parity)。

## 6. SC-5:diff 事件源(engine 內)— last_emitted 對帳制(R1/R5/R6 改版)

### 6.1 rows 端前置(`market_breadth.py`)

`compute_breadth` rows_out 加一鍵:

```python
"limit_judged": prev_close is not None and prev_close > 0 and close is not None
```

= 「本輪這檔的 limit 旗標是判定結果而非缺值預設」。`limit_judged=False` 的列
diff **整列跳過**(不發事件、`last_emitted` 不動)— 缺欄輪不得產假 open(R5)。
`limit_judged` 是 **copycat-only 附加鍵**(R2-2):parity oracle 只比 counts +
逐檔桶推導,不做逐鍵 dict 比對 → fixture **不需重錄**;新鍵正確性由本節
單元測試(prev_close/close 缺值三態)把關。

### 6.2 engine 狀態(ctor 初始化)

```python
self._mkt_last_emitted: dict[tuple[str, str], bool] = {}  # (code, direction) → 已發布狀態
self._mkt_emitted_date: str | None = None                 # last_emitted 服務的資料日
self._mkt_cooldown: dict[tuple[str, str, str], float] = {}  # (code, kind, dir) → 單調 deadline
self._mkt_touch: dict[tuple[str, str, str], int] = {}       # 當日第 N 次
self._signal_hub: SignalHub | None = None
```

`attach_signal_hub(hub)` / `detach_signal_hub()`(鏡射 stock_engine)。

### 6.3 觸發 gate 與 seed

`_apply` 內 `_append` 回傳**非 None**(= trade_date == today 且分鐘鍵在
**0901–1330 域內,1331–1335 clamp 進 1330** — R2-8)才呼叫
`_diff_limit_events(trade_date, rows, as_of)` —— 盤前試撮輪(09:01 前分鐘域外)
天然不觸發,消掉「試撮殘留假事件」分支(R1 第二式);「開盤即鎖」最早在
**09:01 分鐘的輪次**發出;13:31–13:35 的收盤定盤 clamp 輪**仍會對帳**
(定盤改變 limit 狀態時收盤後補發)— 刻意行為。

**`_diff_limit_events` 開頭:`if self._signal_hub is None: return`**(R2-1)——
不 seed、不 latch `_mkt_emitted_date`、不動 `last_emitted`/cooldown。狀態機
推進與發布通道不得解耦:attach 前的任何一輪(含 `_poll_loop` first=True 那圈)
若推進了狀態,事件會被「假發布」且當日不再回放 seed。§8 的 attach 時序因此
只是效能偏好不是正確性前提。

`_mkt_emitted_date != trade_date` 時(首輪 / 換日 / 重啟)先 **seed**(R2-4):

```python
self._mkt_last_emitted, self._mkt_touch = hub.market_event_state(trade_date)
self._mkt_cooldown.clear(); self._mkt_emitted_date = trade_date
```

- 開盤首輪:當日 jsonl 尚無 market 事件 → seed 全空(視同全 False)→ 開盤即鎖
  的檔在首輪就發 `market_limit_lock`(**R1 主修**:一價到底不再靜默)。
- 盤中重啟:seed 回放出已發布狀態 → 已鎖且已發過的檔不重發;停機期間發生的
  轉移(latch 與 seed 不符)自然補發一則(帶當下 as_of,jsonl 缺角自癒)。
- jsonl 壞/缺:seed 空 → 最壞重發一次 lock(id 不同,前端多一則),degraded 可接受。

### 6.4 對帳發布(取代 raw 轉移偵測 — R6)

每輪對每檔 `limit_judged` 列、每方向 `direction ∈ {up, down}`
(**`code = row["stock_id"]`** — rows 鍵名是 `stock_id`,事件層才改名 `code`
與 SignalMsg 契約對齊,R2-5):

```python
desired = row["limit_up"] if direction == "up" else row["limit_down"]
key = (code, direction)
if desired == self._mkt_last_emitted.get(key, False): continue
kind = "market_limit_lock" if desired else "market_limit_open"
bucket = (code, kind, direction)
if cooling(bucket): continue          # 本輪不發;desired 持續不符則冷卻結束後補發
arm(bucket, event_cooldown_secs)      # 預設 600.0(configs/breadth.json)
self._mkt_last_emitted[key] = desired
touch = bump((code, kind, direction))
events.append({kind, code, name, price: round(close*1000), time: as_of,
               direction, touch_count: touch})
```

語意:`last_emitted` 是「事件流已對外宣告的狀態」,冷卻只**延後**對帳不丟棄 ——
lock→open→relock(open 後 600s 內)會在 lock 桶冷卻結束後補發 relock,
事件流最終狀態恆收斂到實況(R6);抖動上界仍是每桶每 600s 一則。
row 本輪缺席(暫停交易)→ `last_emitted` 保留,恢復後照常對帳。
逐筆 try/except(單列壞值只丟該筆 — R5),批次層再包一層保 poll 不死;
整批交 `hub.publish_market_events(events, trade_date=trade_date)`(hub None → 跳過)。

`adopt_date=False` 輪與 `_apply` 失敗輪:不呼叫 diff,狀態不推進(既有 gate 天然涵蓋)。

## 7. SC-6:hub 新入口

```python
def publish_market_events(self, events: list[dict], *, trade_date: str) -> None:
    """全市場廣度事件(breadth diff)入匯流排:WS + jsonl,硬性不進 Discord。

    trade_date 由 breadth 端傳入(R7):純 FinMind 事件不得綁 TC4 engine 日別。
    與 self._trade_date_fn() 不符 → warning(每日別一次),仍以傳入值落檔。
    繞過規則 slots;never-raise;_closing 時丟棄。
    """
    for ev in events:
        payload = {
            "type": "signal",
            "id": f"{trade_date}-breadth-{ev['code']}-{ev['kind']}-{ev['direction']}-{ev['time']}",
            "kind": ev["kind"], "code": ev["code"], "name": ev["name"],
            "price": ev["price"], "time": ev["time"], "levels": [],
            "direction": ev["direction"], "pct": None,
            "touch_count": ev["touch_count"],
        }
        self._publish(payload)
        self._enqueue({**payload, "trade_date": trade_date}, notify=False)

def market_event_state(self, trade_date: str) -> tuple[dict[tuple[str, str], bool], dict[tuple[str, str, str], int]]:
    """讀當日 jsonl 的 market_* rows(依檔內順序後者勝)→
    ((code,direction) → 已發布鎖定狀態, (code,kind,direction) → 事件計數)。
    engine seed 專用;檔缺/壞 → (空, 空)(read_signals 既有壞行跳過)。"""
```

**`today_signals` 改版(R2-3)**:讀取日集合 = `{self._trade_date_fn(),
self._now_fn().date().isoformat()}`(通常同一天 = 單檔讀),多檔時 concat 後以
`id` 去重、保檔內順序 —— stock engine 的 trade_date 只在 stage2(當日首 tick)
前進,**空自選 / 訂閱零推播時它會靜默停在昨日**(非可見大故障),廣度事件
(純 FinMind,寫在本機日檔)不得因此從 today 端點消失。

**`GET /api/stock/signals/today` 加 `?market=exclude` 參數**(R2-7,預設
`include` 向後相容):後端以 kind 前綴過濾 —— exclude 端(SignalRail feed)
不再整包下載後 client 丟棄。量級記載:market 事件/日上界 ≈ 漲停+跌停+觸及
轉移數 × 對帳上限(600s/桶),R3 實測漲停日常態數十~百餘檔 → 每日數百則、
每則 ~200B,jsonl 總量數十~百餘 KB,read_signals 全讀仍輕;前端 payload 靠
參數過濾與分族 cap(§9.3)守住。

- 無 `rule_id`/`rule_name` 鍵(前端型別 optional);`_kind_text` 補兩案
  「全市場鎖漲停/跌停」「全市場漲停/跌停打開」(依 direction)防未來誤用。
- id 的 rule_id 段固定 `breadth`:與規則 id(`r-<epoch>-<seq>`)不撞。
- 測試:發兩則 → `_publish` 收到、jsonl 佇列有、Discord 佇列 `qsize()==0`;
  `_closing` 零入列;trade_date 不符 → warning + 落傳入值檔;
  `market_event_state` 回放 lock→open 序列得 False。

## 8. 接線與生命週期(app.py / verify.py)

- boot 序:signals hub 先起(:485-515)、breadth 最後 boot(:685)→ breadth boot
  成功且 hub 存在時 `breadth.attach_signal_hub(hub)`(緊接 :692 之後)。
- 關機序既有為 breadth 最先收(:725-732)→ close 前先 `detach_signal_hub()`,
  hub 此刻尚活著,無 use-after-close 窗。
- `BreadthFetchers` 四元組 → **五元組**(+ `fetch_industry_chain`);
  `_make_breadth` 長度 guard 與訊息同步改;既有測試注入點全數跟進。
- `verify.py`(R8):fake 五元組 — chain fake 回小型固定 chain 表(涵蓋 fake
  snapshot 的股票,SC-3 截圖 anytime 可出畫面);fake snapshot 加**可控翻轉**
  (`VERIFY_BREADTH_FLIP=1` 時 1101 依分鐘奇偶在 鎖漲停↔非鎖 間切換)→ SC-7
  的 WS→bus→時間軸鏈路在 verify server 上取得證。`VERIFY_BREADTH_FAIL=1` 時
  chain fake 同拋;**verify data_dir 為隔離空目錄(無 industry_chain.json)是
  失效注入的前置**(R9),量法明寫先確認該檔不存在。

## 9. SC-3/SC-7:前端

### 9.1 SectorSection(類股強弱)

- 收合區塊沿 `LimitListSection` pattern:localStorage `SECTOR_OPEN_KEY =
  "copycat-sector-open"`(try/catch 讀寫),收合 = unmount。
- Body:TanStack Query `GET /api/market/sector`,`refetchInterval: 10s`,
  gate = `open && active`(R3 rows 同款;`active` prop 自 App 傳入既有)。
- 三層清單(neigui `MarketSectorRotation` 形式適配):產業列 = `▸/▾` + 名 +
  `(members)` + 著色 `avg_change_rate`(紅漲綠跌沿專案慣例)+ 量比;展開 →
  subs 列同欄位;成員層 lazy query `GET /api/market/sector/members`(只在鑽取
  時帶 `sub`,空字串一律不送),表頭 名稱/漲跌/量比/成交額,列點擊
  `onOpenStock(stock_id)`。展開態 `useState`(不持久化)。
- degraded:`rotation: null` → 區塊內顯示「類股資料未就緒」;`stale` → 沿
  家數帶 stale 標記慣例。

### 9.2 SignalTimelineSection(時間軸)

- 收合區塊同 pattern:`SIGNAL_TIMELINE_OPEN_KEY = "copycat-signal-timeline-open"`。
- 資料:`useSignalFeed({ market: "include" })`(見 §9.3;baseline
  `/api/stock/signals/today` + bus live;**queryKey 帶模式**
  `["stock-signals-today", market] `— exclude/include 兩掛載點各自 cache,
  `onWsOpen` invalidate 用 prefix key 兩族一起自癒;impl-spec R1)。
- 每列:時刻 + 代號名稱 + `kindLabel` 文案(R13:補「全市場鎖漲停/鎖跌停」
  「全市場漲停/跌停打開」兩案,vitest 斷言字串,與後端 `_kind_text` 對齊)+
  `market_*` 列帶「廣度」badge(`title` 註記「FinMind 快照精度 5-10s,非 tick 級」)。
  列點擊 `onOpenStock(code)`。
- kind 篩選 chips:全部/CDP/爆拉跌/爆量/鎖板(自選)/全市場鎖板 —— chip 集合
  以 kind 群組定義,`useState` 不持久化。

### 9.3 SC-8:market kinds 過濾(feed 層,cap 之前 — R2/R3)

- `signal-model.ts`:`SignalKind` union 擴充 `"market_limit_lock" |
  "market_limit_open"`;export `isMarketKind(kind: string): boolean`。
- `useSignalFeed(opts?: { market?: "include" | "exclude" })`(預設 `"exclude"`,
  既有呼叫端零改動語意):
  - `"exclude"`:baseline 帶 `?market=exclude`(後端過濾,R2-7)+ live 過濾,
    再進 `mergeSignals` —— cap 200 發生在過濾之後(R3)。
  - `"include"`(時間軸):**分族各自 cap**(market 族與自選族各 200,合併後
    依 time 排序,R2-6)—— 漲停潮日 market 族不得獨佔清單,chip 切「自選」
    仍見自選訊號。vitest:250 則 market + 3 則自選 → 「自選」chip 見 3 則。
- `useSignalAlerts`:bus handler 開頭 `if (isMarketKind(sig.kind)) return;`
  (R2)—— toast / beep / 桌面通知全免疫。vitest:發 `market_limit_lock` →
  toast 佇列不變、`playBeep` 未呼叫。
- `StockPage`:維持 `useSignalFeed()` 預設(exclude)→ SignalRail 天然不含
  market 列(SC-8)。

## 10. 邊界與失效樣態(brainstorm §4 對應機制)

| 邊界 | 機制 |
|---|---|
| chain 全不可得 | rotation=null,面板 degraded,家數/事件不受影響(§4.3) |
| 開盤即鎖(一價到底) | seed 空 + 對帳 → 首輪即發 lock(§6.3,R1) |
| 盤中重啟 | jsonl seed 回放,不重發已發布、補發停機期轉移(§6.3) |
| 停板邊緣抖動 | per 桶 600s cooldown;冷卻延後對帳不丟棄,終態收斂(§6.4,R6) |
| 缺欄輪(close/change_price)| `limit_judged=False` 整列跳過,不產假 open(§6.1,R5) |
| 換日 | `_mkt_emitted_date` 不符 → re-seed(當日 jsonl 空 → 全 False)(§6.3) |
| 盤前試撮殘留 | 分鐘域 gate(0901 前不觸發;1331–1335 clamp 輪照對帳)(§6.3) |
| attach 前的輪 | hub None 早退,狀態機零推進(§6.3,R2-1) |
| 髒 row / 全空輪 | `_apply` 失敗早退,diff 不被呼叫 |
| 幽靈 industry | members=0 skip(SC-1 純函式既有行為) |
| 事件層例外 | 逐筆 try/except + 批次傘;hub 入口 never-raise |
| 非自選 code 跳轉 | `setStockCode` 既有任意代號路徑 |

## Known Risks

- **KR-1(R7/R2-3 殘餘,降為外觀級)**:today 端點聯集讀(§7)解掉「廣度事件
  消失」的功能性風險;殘餘外觀風險 = stock engine trade_date 停滯日(空自選 /
  零推播)時,聯集會把**昨日的自選訊號**一併回傳,時間軸出現舊時刻列(id 去重
  防重覆,不防跨日混列)。該情境本身已是上游訊號鏈停擺,混列可稽核(hub
  mismatch warning 每日別一次),不單獨修。
