# Design v2 — 台股綜合 R2:FinMind 管線 + 家數帶 + 騰落線

Changelog:
- v1(2026-08-06):初版。
- v2(2026-08-06):design review round 1(0 P0 / 9 P1 / 7 P2,全數 accepted)修入 —
  R1/R2 序列落檔與 restore 的 trade_date 語意釘死;R3 分鐘域 guard 回寫;R4 sentinel
  方向改回既有慣例(預設 None)+ `__main__`/`verify.py` 入表;R5 finmind_token 抽出的
  測試遷移;R6 start() 不阻塞 boot + REST 三態;R7 parity fixture 改全管線口徑;
  R8 useBreadth 改手寫 WS + reconnect/換日契約;R9 map 失敗保前值;R10 失敗退避;
  R11 data dir 錨定 repo root;R12 BootedClient;R13 毫元介面釘死;R14/R15 Known
  Risks / None 分支;R16 config 檔名拍板 `configs/breadth.json`(偏離 brainstorm Q2
  的 `market.json`,理由:與 `breadth_config.py` 同名可尋)。
- v2 amendments(2026-08-06,impl-spec review round 1 連動):disposition query 參數名
  = `start_date`/`end_date`(§4);分鐘鍵改用 `index_engine.minute_key`(floor+1
  終點標記,域 **0901–1330**,與同頁指數分時圖同語意;§5 原 floor/0900 作廢);
  as_of/trade_date 自**原始** snapshot rows 的 `max_tick_datetime` 推導,None 視同
  該輪失敗;useBreadth 呼叫點在 **App 層** props 下傳(§7 原 IndexPage 內呼叫作廢);
  create_app 增 `breadth_data_dir` 注入;verify fake 三元組跳過 token 閘。

- v2 code-review 修訂(2026-08-06,code review round 1:0 P0 / 5 P1 / 15 P2 全 accepted,
  詳 `code-review-round-1.json`):§5 換日改三分法(僅 new==today 清序列;其餘不採用
  日期變更 — P1-1);`max_tick_datetime` 加 `upper_bound=now+10min` 夾制髒時刻(P1-2);
  maps 重取加「成功日 != today」失效 + per-map 退避(60s / quota 300s;P1-3/P2-4);
  disposition 失敗語意字面收斂為**保前值(冷啟動 = 空 set)**(SPEC-5,取代「空 set
  續行」);退避指數 min 夾制防 Overflow(P2-2);REST/WS 對「boot 未完成」回載入中
  語意,enabled=false 只留給 boot 完成後引擎缺席(P2-1);§6 補:counts=null(載入中)
  時 series/trade_date 可能為 restore 還原值,不必為空(SPEC-1);verify 模式落檔
  隔離至 `<repo>/data/market-verify/`(SPEC-2)、失效注入開關 env `VERIFY_BREADTH_FAIL=1`
  (SPEC-3,已記 CLAUDE.md),fake 快照時刻域外 clamp 至當日 13:00 使盤後序列可目視
  (SPEC-4);前端 refetch 以 union-by-t 合併防競態丟格(P2-3)、BreadthBand 顯示
  trade_date(P2-5)。

對應 brainstorm:`.claude/feat/market-overview-r2-finmind/brainstorm.md`(SC-1~SC-5)。
總 spec:`docs/superpowers/specs/2026-08-05-taiwan-market-overview-tab-spec.md` §5 Round 2。
Review JSON:`design-review-round-1.json`。

---

## 1. 架構總覽

```
FinMind(HTTP, stdlib urllib + Bearer)
  ├── taiwan_stock_tick_snapshot(每 poll,10s)────┐
  ├── TaiwanStockInfo(in-memory 24h TTL)─────────┤
  └── TaiwanStockDispositionSecuritiesPeriod(24h)─┤
                                                    ▼
                copycat/server/breadth_engine.py(BreadthEngine,async task)
                  組 type/name/sector map → filter_universe → compute_breadth
                  ├─ counts(scalar)+ rows(engine 內存,R3 用)
                  ├─ 當日分鐘序列 series → <repo>/data/market/breadth-<date>.json
                  └─ WsBroadcaster.publish(10s 節奏)
                       │                         │
              GET /api/market/breadth      WS /ws/breadth(relay helper)
                       │                         │
                frontend useBreadth.ts(手寫 fetch + WS,鏡射 useIndexStream)
                  ├─ BreadthBand.tsx(家數帶,SC-4)
                  └─ AdvanceDeclineChart.tsx(騰落線,SC-4)
```

失效域(SC-3):BreadthEngine 完全不碰 TC4/ZMQ,獨立 `_boot` 邊界且**排 boot 序列
最後**;`start()` 不做任何網路 IO(見 §5)—— FinMind 掛 → 只有 breadth 面板 stale;
TC4 系(index/stock/futures/corr)零波及,反向亦然。

## 2. 檔案組織

| 檔案 | 動作 | 責任 |
|---|---|---|
| `copycat/market.py` | 改 | 補**毫元進出**入口:`limit_up_milli(prev_close_milli: int) -> int` / `limit_down_milli(...)`;既有 float `limit_up_price` 改為薄包裝(行為不變)。`limit_down_milli`:`cand = prev_milli*9//10`,tick 段取 **cand(ceil 前)所在段**(與 neigui `_tick_size(raw)` 同段才等價 — R13),ceil 到 tick |
| `copycat/market_breadth.py` | 新 | **零 IO 純函式**(自 neigui 搬邏輯):`classify_stock_id` / `filter_universe` / `build_type_map` / `build_name_map` / `dedup_sector_map`(含 `PRIMARY_INDUSTRY_OVERRIDE`)/ `parse_active_disposition` / `max_tick_datetime` / `compute_breadth` / `assemble_universe`(白名單→filter 的組裝順序收成一個純函式,parity 測得到 — R7) |
| `copycat/breadth_config.py` | 新 | `BreadthConfig` frozen dataclass + `configs/breadth.json` 覆寫(`signals_config.py` 同款;R16 拍板檔名) |
| `copycat/server/finmind_token.py` | 新(🔵 抽出) | `resolve_token()` + `_dotenv_values`/`_dotenv_cache` 自 `oi_levels.py` 抽出(stdlib-only,conftest 可 import 不拉 fastapi);`oi_levels` 改為呼叫 `finmind_token.resolve_token`(**經模組屬性呼叫**,patch `finmind_token` 即全域生效;不留 re-export — 兩份 patch 目標必漂移,R5) |
| `copycat/server/breadth_fetch.py` | 新 | 阻塞取數層(urllib + Bearer,`oi_levels._fetch_rows` 同款錯誤分類):`fetch_snapshot` / `fetch_stock_info` / `fetch_disposition`;stock_info 記 row 數 log,異常偏低升 warning(R14) |
| `copycat/server/breadth_engine.py` | 新 | `BreadthEngine`:poll loop / map cache / 序列落檔+restore / stale + 退避 / WsBroadcaster |
| `copycat/server/app.py` | 改 | lifespan `_boot` breadth(**序列最後**)、`GET /api/market/breadth`、`WS /ws/breadth`(relay);`create_app` 參數 `breadth_fetchers=None`(**None=不啟動**,沿 DEFAULT_* 既有方向 — R4) |
| `copycat/server/__main__.py` | 改 | prod 分支顯式傳 `DEFAULT_BREADTH`;`--verify` 分支傳 `verify.py` 的 fake 三元組(R4) |
| `copycat/server/verify.py` | 改 | 補 breadth fake fetchers(固定 fixture 快照 + 可注入失敗;SC-3 real-env 的取證通道)。FINMIND_TOKEN 維持不中和,但 verify server 的 breadth 走 fake **不打真 FinMind**(oi-levels 那條照舊真打) |
| `tests/conftest.py` | 改 | FinMind 中和改 patch `finmind_token`(維持既有語意) |
| `tests/server/test_oi_levels.py` | 改 | resolve_token 語意測試整組遷 `tests/server/test_finmind_token.py`,patch 目標改新模組(R5) |
| `frontend/src/types.ts` | 改 | `BreadthState` / `BreadthCounts` 型別(counts 可 null — R15) |
| `frontend/src/hooks/useBreadth.ts` | 新 | **手寫 fetch + WS**(鏡射 `useIndexStream`;R8):onopen refetch 全量、trade_date 變更清 series + refetch |
| `frontend/src/components/index/BreadthBand.tsx` | 新 | 家數帶(上市/上櫃 × 五格;三態文案) |
| `frontend/src/components/index/AdvanceDeclineChart.tsx` | 新 | 騰落線 SVG(dataviz skill 過) |
| `frontend/src/components/index/IndexPage.tsx` | 改 | 中段插入(雙圖之下、下方區塊之上) |
| `CLAUDE.md` | 改 | §0 FinMind 例外、§1 .env FINMIND_TOKEN、結構表(SC-5) |

## 3. 純函式層(SC-1 對應)

搬移原則:**邏輯全等 neigui、實作適配 copycat**。SC-1 的一致性由「同**原始輸入** →
同分桶」保證,fixture parity 測試把關(全管線口徑,見 §8)。

- `classify_stock_id` / `filter_universe`:自 `market_universe.py` 原樣搬(純函式,
  含 watch_list 優先語意)。
- `build_type_map` / `build_name_map` / `dedup_sector_map`:自 `finmind_realtime.py`
  搬,含 override 表與「date DESC 取最新、industry ASC tie-break」的兩段 stable sort、
  `type in ("twse","tpex")` 前置 filter。
- `parse_active_disposition(rows, today)`:自 `_parse_active_disposition` 搬。
- `max_tick_datetime(universe_rows)`:自 `_max_tick_date` 搬(Z 尾 UTC → 台北;
  回 naive 台北 datetime)。
- `assemble_universe(universe_rows, primary_sector, watch_list) -> list[dict]`(R7):
  把 neigui `_do_fetch_market_snapshot` 的組裝順序收成一個純函式 ——
  白名單(`sid in primary_sector`)→ `filter_universe`(ETF/權證/處置股)→ 過濾後
  rows。engine 與 parity 測試共用同一入口,順序寫反測試就紅。
- `compute_breadth(universe_rows, type_map, name_map) -> dict | None`:自
  `market_today.compute_breadth` 搬,**漲跌停判定改毫元整數**:
  `prev_milli = round((close−change_price)*1000)`,`round(close*1000)` 與
  `market.limit_up_milli(prev_milli)` / `limit_down_milli(prev_milli)` **精確等值**
  (取代 neigui float 半 tick 容差;等價性由手造 limit 邊界 fixture 釘死 — §8)。
  其餘規則原樣:change_rate null 整檔跳過、type_map 查無市場排除、prev/close 缺只按
  正負分桶、五桶互斥、rows 全量輸出(R3 用,本輪不曝露)、**全空回 None**(R15:
  engine 視同該輪失敗)。

## 4. 取數層(breadth_fetch.py)

- 全部阻塞函式(caller `asyncio.to_thread`),`oi_levels._fetch_rows` 同款:
  Bearer header、timeout 30s、402 不重試直接 raise `BreadthFetchError(quota=True)`、
  `TimeoutError` 獨立列、非 JSON 可重試一次(_ATTEMPTS=2)。
- `fetch_snapshot(token) -> list[dict]`:`GET /api/v4/taiwan_stock_tick_snapshot`。
- `fetch_stock_info(token) -> list[dict]`:`dataset=TaiwanStockInfo`;回傳前
  `logger.info` row 數,`< 3000` 升 warning(R14 截斷觀測;T3 實錄 4300 列,
  原估 1.6 萬 / 門檻 5000 均誤,2026-08-06 校正)。
- `fetch_disposition(token, today) -> list[dict]`:
  `dataset=TaiwanStockDispositionSecuritiesPeriod&start=today−60d&end=today`。
- 不做 disk cache;不需 rate limiter(固定節奏單 request)。

## 5. BreadthEngine(SC-2 / SC-3 對應)

```python
class BreadthEngine:
    def __init__(self, *, token: str, config: BreadthConfig,
                 snapshot_fetch, stock_info_fetch, disposition_fetch,   # 注入點(測試 fake)
                 data_dir: Path | None = None,   # None → <repo root>/data/market(R11)
                 today_fn=date.today, now_fn=datetime.now) -> None: ...
    async def start(self) -> None   # 只做:restore 落檔 + 起 poll task;零網路 IO(R6)
    async def close(self) -> None   # cancel task
    def state(self) -> dict         # REST 全量
    def stream(self)                # WsBroadcaster.stream()
```

- **start() 不阻塞 boot**(R6):restore(本地檔讀取)+ `create_task(poll_loop)` 即
  返回;首輪 fetch 是 poll task 第一圈(loop 內 `except Exception: logger.exception
  續行` 傘罩住 —— index `_mis_loop` 同款)。breadth 排 boot 序列**最後**,關機反序
  最先收。
- **poll loop**:第一圈無條件 fetch(填 scalar,任何時刻);之後每圈 sleep 目前
  間隔,僅「台北 08:55–13:40」窗內 fetch(`_in_window(now_fn())`)。
- **一輪**:`to_thread(fetch_snapshot)`;maps(stock_info + disposition)in-memory
  TTL 24h —— **成功才寫入與刷新時戳;失敗保前值、不動時戳、下一輪即重試**(R9,
  neigui「失敗不寫 cache」同語意);冷啟動失敗(無前值)→ degraded,每輪重試。
  組 universe(`assemble_universe`)→ `compute_breadth` → None 視同失敗(R15),
  否則更新 `counts / rows / as_of / trade_date`。
- **失敗退避**(R10):連續失敗 → 有效 poll 間隔指數退避(10s → 20 → 40 → 60s 上限);
  402(quota)→ 直接 300s(oi-levels `NEGATIVE_TTL_SECS` 同量級);成功即復位。
  stale 旗標不受退避影響照常拉起。
- **trade_date 語意(R1/R2,釘死)**:
  - restore **同時還原 `trade_date` 與 series**;換日判定僅「舊值非 None 且 ≠ 新值」
    時觸發清 series。
  - **append 與落檔僅在 `trade_date == today_fn()` 時發生**(brainstorm Q9 語意):
    盤前/假日/跨午夜重啟讀到上一交易日 snapshot → 只更新 counts/as_of,**不 append、
    不寫檔** —— 前一日完整落檔絕不會被單點覆寫。
  - restore 檔名 = `breadth-<today_fn()>.json`(與 append 條件同源,鍵一致)。
- **序列 append**:minute key = tick 時刻 floor `HHMM`;**域 guard(R3)**:
  `0900 <= key <= 1330` 收,`1331–1335` clamp 至 `1330`(收盤末筆延遲,index
  `minute_key` 同款),其餘(盤後定盤 14:30、盤前)**丟棄**。每分鐘 last-wins 覆寫
  一格 `{t, twse:[lu,u,f,d,ld], tpex:[...]}`(桶序固定)。域常數與前端 x 軸同一份
  語意(0900–1330),types.ts 註解記載。
- **落檔**:append 後 `<repo root>/data/market/breadth-<trade_date>.json`
  `{"_version": 1, "trade_date": ..., "series": [...]}`,tmp + `os.replace` 原子寫;
  data_dir 以 repo root 錨定(R11,`__main__` logs/ 同慣例),測試注入 tmp_path。
  restore 版本不符 / 壞檔 → 空序列 + warning(never-raise)。
- **stale 判定**(SC-3):`stale = degraded or (in_window and now−last_success >
  stale_secs)`。`degraded` = sector_map 空(白名單會剃光)或 disposition 失敗
  (空 set 續行)。fetch 失敗:counts/series 保前值,只動 stale。
- **廣播**:每輪結束 publish scalar payload(§6);poll task 在 loop 上,publish
  天然安全。

## 6. API / WS 契約

- `GET /api/market/breadth` → 恆 200,三態(R6/R15):

```json
// 正常(enabled=true 且已有資料)
{ "enabled": true, "trade_date": "2026-08-06", "as_of": "10:23:45", "stale": false,
  "counts": { "twse": {"limit_up":3,"up":512,"flat":88,"down":401,"limit_down":1},
              "tpex": {...} },
  "series": [ {"t":"0901","twse":[3,512,88,401,1],"tpex":[...]}, ... ] }
// 引擎在但首輪未成(載入中):enabled=true, counts=null, series=[](trade_date/as_of null)
// 引擎缺席(token 未設 / boot 失敗):enabled=false,其餘同上空值
```

  前端文案三態分開:「FinMind 未設定」(enabled=false)/「載入中」(enabled=true,
  counts=null)/ 正常(R6)。series 桶序 = `[limit_up, up, flat, down, limit_down]`。
  rows 本輪不曝露。

- `WS /ws/breadth`:relay helper;首則 seed = scalar payload,之後每輪一則:

```json
{ "type": "breadth", "trade_date": "...", "as_of": "...", "stale": false,
  "counts": {...}, "last_minute": {"t":"0931","twse":[...],"tpex":[...]} }
```

  (`last_minute` = 本輪有 append 才帶,否則 null。)engine None → accept 後即
  close(`/ws/index` 對 engine 缺席的處置同款,PLAN 對齊現碼)。

- lifespan:獨立 `_boot("breadth", ...)` 排最後;`make` 內 `resolve_token()` 為
  None → log「FINMIND_TOKEN 未設定,家數帶停用」→ 回 None。`create_app` 參數
  `breadth_fetchers: BreadthFetchers | None = None`(**None=不啟動**;R4);
  `__main__` prod 傳 `DEFAULT_BREADTH`(→ 真取數層)、`--verify` 傳 verify.py 的
  fake 三元組(固定 fixture + 可注入失敗)。

## 7. 前端(SC-4 對應)

- `useBreadth.ts`:**手寫 fetch + WS**(`useIndexStream` 同款;TQ 不適用常駐推播 —
  該檔檔頭慣例)。merge 契約(R8):WS `onopen` → refetch `/api/market/breadth`
  全量(斷線期間漏格補回);訊息 `trade_date` 與本地不同 → 清 series + refetch;
  `last_minute` 依 `t` upsert。
- `BreadthBand.tsx`:兩列(上市/上櫃)× 五格,順序「漲停/上漲/平盤/下跌/跌停」;
  漲停格紅底、跌停格綠底(台股紅漲綠跌),中間三格中性;`stale` → 「資料延遲」
  徽章;三態文案見 §6。
- `AdvanceDeclineChart.tsx`:x = 分鐘 0900–1330、y = net(=(limit_up+up)−
  (down+limit_down),上市+上櫃合計,前端一行運算);0 軸可見;域外/未知鍵不產生
  點(R3 第二層防禦);SVG 走 `lib/svg-points` 共用;**實作前過 `dataviz` skill**。
- `IndexPage.tsx`:中段插入 `<BreadthBand/>` + `<AdvanceDeclineChart/>`。

## 8. 測試策略

- **parity(SC-1,R7 口徑)**:fixture = **原始** snapshot rows + 原始 TaiwanStockInfo
  rows + 原始 disposition rows(錄自真 FinMind,存
  `tests/fixtures/breadth_parity.json`);expected 由 neigui 端跑**完整組裝**
  (`_dedup_sector_map`→白名單→`filter_universe`→`compute_breadth`)產出並存入
  fixture;產生腳本 `tests/fixtures/record_breadth_parity.py`(檔頭註記重跑方式)。
  copycat 側從原始 rows 走 `dedup_sector_map`→`assemble_universe`→`compute_breadth`
  比對 counts 全等 + rows 逐檔 bucket 全等。
- **limit 邊界手造 fixture(R7/R13)**:漲停 / 跌停 / 差半 tick / 差一 tick /
  prev_close 跨 tick 段邊界(9.99 / 45.5 / 90.9 / 111.1 / 999)固定兩桶語意;
  `limit_up_milli`/`limit_down_milli` 對照 neigui float 版手算值。
- engine(fake fetch 注入):正常輪 / fetch 拋錯保前值+stale / 402 退避 300s /
  連續失敗退避與復位 / sector 空 degraded / map 失敗保前值不動 TTL(R9)/
  **today=T+1、snapshot=T → 不 append 不寫檔,breadth-T.json 未被截短**(R1)/
  **落檔 → 新 engine start + 首輪 fake fetch(同日)→ 序列 = 落檔 + 本輪**(R2)/
  tick 14:30、08:59 不進序列(R3)/ 窗外不 fetch / 換日清序列。
- app 層:**`tests/helpers/boot.BootedClient`**(R12)+ fake fetchers —— REST 三態
  形狀 / WS 首則 seed 與增量 / engine None 時 WS close / breadth fake 拋錯時
  `/api/index/state` 照常 200(SC-3 隔離)。
- 前端:vitest —— BreadthBand 三態與 stale、ADL net 計算與 upsert 與域外鍵防禦、
  useBreadth 合併(onopen refetch / 換日清空 / last_minute upsert)。

## 9. Known Risks

1. **FinMind snapshot 欄位漂移**:compute_breadth 逐欄 `.get` 防禦。
2. **盤中對照(SC-1 真值層)有時效窗口**:落地日窗口外 → fixture 全等 + 盤中對照
   記 pending 待下一交易日。
3. **兩專案共用 token 配額**:copycat +360 req/hr,合計 <25%;可 config 上調間隔。
4. **處置股集合兩邊時間差**:各自 24h cache,換日邊界短暫不同 → SC-1 盤中對照容差
   已寫(同分鐘逐格差 ≤ 該分鐘變動量)。
5. **TaiwanStockInfo 分頁截斷(R14)**:`/data` 大表可能靜默截斷(oi_levels
   `_log_freshness` 已記錄同上游特性)→ 白名單少尾段股、十個數字對不上且難歸因。
   觀測 = fetch 層 row 數 log + warning 門檻;parity fixture 記錄錄製當下 row 數。
