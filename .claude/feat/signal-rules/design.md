# design — 訊號規則化 v2

changelog:
- v1(2026-08-05):初版。
- v2(2026-08-05):design review round 1 十五條全修 — R1 params 值域表 + per-rule
  try/except;R2 單一 `_RuleSlot` dict 原子替換;R3 basis cache 帶日別;R4 staged
  日別三動作明文 + drop 雙 cache;R5 now_fn 注入;R6 唯一名排除自身 + PUT id 語意;
  R7 檔案表補 StockPage、消費點更正;R8 既有測試遷移節;R9 壞檔 = _boot 降級;
  R10 錯誤碼值域;R11 MAX_RULES;R12 id 單調計數 + save 失敗語意;R13 升級當日
  雙列 Known Risk;R14 filterKinds 移除記 🔴 + Discord 文案帶規則名;R15 邊界逐 edge
  + load_rules 三態。
- v2.1(2026-08-05,限縮輪 R16-R25 全修):rules 檔綁 data_dir;_seed_slot 明文 +
  swap/seed 同步區塊;過期基準改丟棄;映射/route 表內嵌;版本與 MAX_RULES load 語意;
  RULE_SAVE_FAILED;測試遷移拆兩類 commit + 補 StockPage.test;int 鍵驗證。

**Goal**:具名規則 CRUD + 熱重載 + per-rule 參數/CDP 線/cooldown/notify_discord
(brainstorm SC-1..9)。

**架構**:組合式 — 每條規則一顆**未改動的** `SignalDetector`(per-rule
`SignalsConfig`);hub 持單一 `_RuleSlot` dict + 帶日別的 basis cache。

## 檔案組織

| 檔 | 變更 | SC |
|---|---|---|
| `copycat/signal_rules.py`(新) | 模型/驗證(值域表)/存取三態/預設規則/config 映射 | SC-1/4 |
| `copycat/server/signal_hub.py` | 規則引擎化(slots、cache、CRUD、fanout;docstring id 格式同步) | SC-2/3/5 |
| `copycat/server/app.py` | rules CRUD routes;移除 enabled routes + `SignalsEnabledBody`;RuleError handler(與 WatchlistError 同區) | SC-4/6 |
| `frontend/src/lib/signal-model.ts` | `SignalMsg`+`rule_id?/rule_name?`;刪 `SignalEnabled`/`SignalSwitchKey`/`KIND_SWITCH`/`filterKinds`;id 格式註解同步 | SC-8 |
| `frontend/src/hooks/useSignalRules.ts`(新) | TQ CRUD hooks | SC-7 |
| `frontend/src/hooks/useSignalsConfig.ts` | **刪除** | SC-4 |
| `frontend/src/components/stock/StockPage.tsx` | `useSignalsConfig`/`toggleKind` → `useSignalRules`/rule 切換;SignalRail props 改 rules 契約(R7 — 唯一 useSignalsConfig 消費者,漏改 tsc 必紅) | SC-7 |
| `frontend/src/components/stock/SignalRail.tsx` | 四 toggle → 規則列;「規則」鈕;feed 帶規則名;`filterKinds` 呼叫移除(:95,唯一產品端消費) | SC-7/8 |
| `frontend/src/components/stock/SignalRulesDialog.tsx`(新) | 列表 + 編輯表單(dialog 樣板 = WatchlistManagerDialog) | SC-7 |

## SC-1 規則模型 — `copycat/signal_rules.py`(全簽名)

```python
RULE_KINDS = ("cdp_cross", "surge_crash", "vol_burst", "limit_lock")
CDP_LEVELS = ("ah", "nh", "cdp", "nl", "al")
COOLDOWN_MIN, COOLDOWN_MAX = 60, 86_400
MAX_RULES = 30                       # R11:REST 可寫入的無界量要有上限
_CACHE_VERSION = 1
# R16:檔案路徑由 hub 決定(self._data_dir / "signal_rules.json",_ENABLED_FILE 同款);
# 本模組不設 CWD 相對 DEFAULT_PATH — 測試 harness 注入 tmp_path 才不會污染真檔

class RuleError(ValueError): ...
# str(e) ∈ {"INVALID_RULE", "RULE_NOT_FOUND"}(R10;唯一對外契約,route handler 對照)

class Rule(TypedDict):
    id: str; name: str; kind: str; enabled: bool; notify_discord: bool
    cooldown_secs: int; params: dict[str, float]; cdp_levels: list[str]

#: R1:params 逐鍵(型別 = int/float 實體,bool 排除)+ 值域;多鍵/缺鍵/違域 → INVALID_RULE
PARAM_SPECS: dict[str, dict[str, tuple[float, float]]] = {
    "cdp_cross":  {"rearm_ticks": (0, 50)},
    "surge_crash": {"pct": (0.1, 50), "window_secs": (10, 3600)},
    "vol_burst":  {"ratio": (1, 100), "window_secs": (10, 3600),
                   "min_elapsed_min": (0, 240), "min_window_lots": (0, 1e6),
                   "min_day_lots": (0, 1e7)},
    "limit_lock": {},
}

def normalize_rule(rule: Rule, others: dict[str, Rule]) -> Rule
    # others = 全集合**排除自身 id**(R6);驗 kind/values/levels(cdp_cross 非空⊆五線
    # 保序去重;其他 kind 必 [])/名稱 strip 非空且不撞 others/cooldown 界內。
    # R25:整數鍵(rearm_ticks / min_window_lots / min_day_lots)拒非整數值(2.5 → INVALID_RULE)
def new_rule_id(epoch: int, seq: int) -> str   # f"r-{epoch}-{seq:03d}";seq = hub 單調計數(R12)
def default_rules(cfg: SignalsConfig, legacy_flags: dict[str, bool]) -> list[Rule]
def load_rules(path) -> list[Rule] | None
    # R15/R20:缺檔 → None(hub 遷移);檔在且合法(含空陣列)→ list(使用者刪光
    # 不得復活預設);壞檔 / 驗證失敗 / **版本不符** / **規則數 > MAX_RULES** → raise
    #(版本 bump 屬開發期動作,屆時必須同時寫轉換;raise 走 R9 的 503 降級,大聲不靜默)
def save_rules(path, rules) -> None   # atomic;OSError **往外拋**(R12/R21 — route 500
                                      # RULE_SAVE_FAILED,記憶體不得先於落檔更新)

def rule_config(rule: Rule, base: SignalsConfig) -> SignalsConfig
    # R19:映射表(dataclasses.replace;int 欄位取 int() — R25):
    # kind=cdp_cross  → cdp_rearm_ticks=int(params.rearm_ticks)、cdp_cooldown_secs=cooldown_secs
    # kind=surge_crash→ surge_pct=params.pct、surge_window_secs=params.window_secs、
    #                   surge_cooldown_secs=cooldown_secs
    # kind=vol_burst  → vol_ratio=params.ratio、**surge_window_secs=params.window_secs**
    #                  (SignalsConfig 無 vol_window_secs;detector 滾動窗由 surge_window_secs
    #                   裁切後餵 _eval_volume — per-rule detector 讓此共用欄安全解耦)、
    #                   vol_min_elapsed_min=params.min_elapsed_min、
    #                   vol_min_window_lots=int(params.min_window_lots)、
    #                   vol_min_day_lots=int(params.min_day_lots)、vol_cooldown_secs=cooldown_secs
    # kind=limit_lock → limit_cooldown_secs=cooldown_secs
    # cooldown_secs 依 kind 落到對應 *_cooldown_secs — 漏映射 = per-rule cooldown 靜默套全域
```

## SC-2/3/5 hub — `signal_hub.py`

```python
@dataclass(frozen=True)
class _RuleSlot:            # R2:rule/detector/enabled 單一結構,不可分割
    rule: Rule
    detector: SignalDetector
    enabled: frozenset[str]  # rule.enabled ? {rule.kind} : frozenset()

self._slots: dict[str, _RuleSlot]      # 插入序;熱路徑唯一讀取點
self._rule_seq: int                    # R12 id 單調計數(初始 = len(rules))
self._basis_cache: dict[str, tuple[str, dict[str, int] | None]]   # code → (basis_date, cdp)(R3)
self._staged_cache: dict[str, dict[str, int] | None]
self._staged_date: str | None          # R4:staged 整批日別
self._rules_lock = asyncio.Lock()
```

- **不變式(R2)**:熱路徑(`on_tick`/`on_book`,同步)只讀 `self._slots`;CRUD 在鎖內
  組好**完整新 slot / 新 dict**,`await asyncio.to_thread(save_rules, ...)` **成功後**
  才以單一賦值替換(dict 賦值原子;失敗 → 記憶體零變更、RuleError/OSError 往外拋)。
  任何時刻熱路徑看到的都是自洽快照。
- **建 detector 一律** `SignalDetector(rule_config(rule, self._base_cfg),
  now_fn=self._now_fn)`(R5 — 初始化 / 遷移 / upsert 三處同式)。
- **評估迴圈(R1)**:ctx 每 tick 一次;`for rid, slot in self._slots.items():` 內
  **per-rule try/except**(`logger.exception` 帶 rule 名;單條炸只跳過該規則該 tick,
  其餘照評)。停用規則 enabled 空集照 evaluate(狀態推進與產出分離,重開不誤發)。
- **basis(R3/R18)**:`_resolve_basis` 非 staged:`basis_date !=
  self._trade_date_fn()` → **丟棄 + log(不寫 cache、不分發、不餵 None)** — 與 staged
  分支的 MFS-2 丟棄同語意;餵 None 會把 rollover 已 promote 的正確基準洗掉且不自癒。
  日別符 → `_basis_cache[code] = (basis_date, cdp)` → `_distribute(code)`(對 cdp 規則
  依 levels 過濾 set_basis)。staged:`basis_date != self._staged_date` 丟棄,否則入
  `_staged_cache`。
- **`_seed_slot(slot)`(R17,upsert 的反向軸)**:掃 `_basis_cache`,只取
  `basis_date == self._trade_date_fn()` 的 entry,依 `slot.rule.cdp_levels` 過濾後
  `set_basis`;非 cdp 規則 no-op。
- **rollover(R4)**:stage1 = `_staged_cache.clear()` + `_staged_date = new_date` +
  request(staged);stage2 = 逐 slot `detector.reset_day()` → `_staged_cache 非空且
  _staged_date == expected` → `_basis_cache = {code: (expected, cdp) …}` 全碼分發;
  否則 **`_basis_cache.clear()`** + 重抓;兩路徑後皆清 staged + date。
- **drop_code(SC-5,R4)**:逐 slot `detector.drop_code(code)` + `_basis_cache.pop` +
  `_staged_cache.pop`。
- **CRUD**:`rules()` / `async upsert_rule(payload, rule_id=None)`(None=POST 配新 id
  並斷言不撞既有;有=PUT,缺 → RULE_NOT_FOUND;`MAX_RULES` 超 → INVALID_RULE)/
  `async delete_rule(rule_id)`。**順序(R17)**:鎖內驗證 + 建好新 slot →
  `await asyncio.to_thread(save_rules, ...)` 成功 → **同一個不含 await 的同步區塊內**
  swap `self._slots`(新 dict 單一賦值)+ `_seed_slot(new_slot)` — seed 與 swap 間
  basis worker 插不進來,新 slot 必帶最新快照。失敗 → 記憶體零變更、例外往外拋。
  其他 slot 實例不動(cooldown/latch 保留);被編輯規則狀態歸零 = 接受(edge 3)。
- **fanout**:payload + `rule_id`/`rule_name`;`_event_id(trade_date, rule_id, event)`;
  Discord 佇列僅 `notify_discord` 入列;`format_signal_text` 於 `rule_name` 存在時
  文末附 `｜{rule_name}`(R14b — 同 kind 多規則在 Discord 可辨識);模組 docstring 的
  id 格式敘述同步改(R13)。
- **遷移(SC-4)**:`load_rules()` → None → `default_rules(cfg, legacy)`(legacy 讀
  `signals_enabled.json`,fail-open 全開)+ `save_rules`;之後不再讀舊檔。
  **壞 rules 檔實際語意(R9)**:建構拋 → `app.py` 的 `_boot("signals", …)` 傘吞 →
  `signal_hub = None`、signals routes 503 NOT_READY、log「訊號引擎啟動失敗」——
  驗收斷言以此為準,**非** lifespan fail-fast。

## SC-4/6 routes — `app.py`

- 刪 `GET/PUT /api/stock/signals/enabled` + `SignalsEnabledBody`。
- 新四條(R19 內嵌):
  ```
  GET    /api/stock/signals/rules            → 200 {"rules": [Rule...]}
  POST   /api/stock/signals/rules            body RuleBody(無 id)→ 201 Rule
  PUT    /api/stock/signals/rules/{rule_id}  body RuleBody       → 200 Rule
  DELETE /api/stock/signals/rules/{rule_id}  → 204
  ```
- `RuleBody`(pydantic 形狀:name/kind/enabled/notify_discord/cooldown_secs/
  params: dict/cdp_levels: list;語意驗證單一定義在 normalize_rule)。
- 錯誤碼(R10/R21):`INVALID_RULE` → 400、`RULE_NOT_FOUND` → 404、落檔 OSError →
  500 `{"detail": {"error": "RULE_SAVE_FAILED"}}`(跨檔契約 shape);`RuleError`
  handler 註冊在 WatchlistError handler 同區。
- PUT 以 **path 的 rule_id 為準**;body 帶 id 且不一致 → 400 INVALID_RULE(R6)。

## SC-7/8 前端(v1 基礎 + R7 修正)

- `StockPage.tsx`:`useSignalsConfig`/`toggleKind`(:9/:44/:89-92)→ `useSignalRules` +
  `toggleRule(rule)`(useSaveRule PUT `{...rule, enabled: !enabled}`);SignalRail props
  由 `enabled/onToggle` 改 `rules/onToggleRule/onOpenManager`。
- `SignalRail.tsx`:規則列(名 + 開關)、「規則」鈕、feed 列副標 `rule_name`(缺 →
  kind 文案 fallback);`filterKinds` 呼叫移除。**🔴 行為改動(R14a)**:關閉規則後
  「該規則今日已發的列」仍顯示(帶規則名可辨識來源);原 filterKinds 的隱藏語意取消 —
  視覺弱化記 next-time,不在本輪。
- `SignalRulesDialog.tsx`:dialog 樣板 = WatchlistManagerDialog(display 隨 open 切 +
  onClose 同步 — §8 dialog 坑);列表(名稱/種類中文/摘要)+ 刪除 confirm +
  「新增規則」+ 編輯表單:名稱 input、種類 select(四類中文)、kind 專屬數字欄位
  (PARAM_SPECS 對應)、CDP 線五勾選(僅 cdp_cross 顯示)、cooldown 秒 input
  (min 60 max 86400)、Discord 通知 checkbox(欄位清單 = brainstorm SC-7)。
- `useSignalRules.ts`:`useSignalRules()`(GET)+ `useSaveRule()`(POST/PUT 依有無 id)
  + `useDeleteRule()`;成功 invalidate `["signal-rules"]`;errText 解 `detail.error`。
- `signal-model.ts`:`SignalMsg` + `rule_id?/rule_name?`;刪四鍵型別與 filterKinds;
  id 格式註解同步(R13)。

## 既有測試遷移(R8;事前標記。R23 拆兩類 commit:**純刪除** = 清理 commit 無 TDD
tag;**改寫成新契約**(key set / id 格式 / staged 斷言 / SignalRail 重寫)= 併入對應
SC 的 `[red]` 紅測試 commit,紅先行證據保留)

| 檔 | 處置 |
|---|---|
| `tests/server/test_signal_hub.py` | 刪/重寫:enabled/set_enabled 3 條(:461/:494/:527);`hub._detector` monkeypatch 1 條(:343)改逐 slot;id 硬編與 `set(msg) == _SIGNAL_KEYS` 4 條(:225/:272/:378/:406)→ 新 key set = 舊 ∪ {rule_id, rule_name}、新 id 含 rule 段;staged/rollover 3 條(:730/:756/:779)改 hub cache 斷言 |
| `tests/server/test_signal_routes.py`(**既有檔**) | `TestSignalsEnabledRoute` 5 條刪;503 清單兩處(:169-175/:251-261)enabled route 換 rules route |
| `frontend useSignalsConfig.test.tsx` | 整檔刪 |
| `frontend signal-model.test.ts` | `filterKinds` describe(6 case)+ ALL_ON fixture 刪 |
| `frontend SignalRail.test.tsx` | ≥3 條重寫(停用 kind 不入列 / 四 toggle onToggle / 提示音分組)+ fixture 改 rules 契約 |
| `frontend StockPage.test.tsx`(R24) | fetch stub(:51-65)補 `/api/stock/signals/rules` 分支(回 `{rules:[…]}`);過目兩條訊號欄斷言 |

## 邊界(R15 — 逐 brainstorm edge)

1. 規則 0 條:`_slots` 空 → 迴圈零次,不炸;`load_rules` 空陣列 ≠ 缺檔(不復活預設)。測:`test_zero_rules_no_events`、`test_empty_rules_file_not_remigrated`。
2. 同 kind 兩規則同 tick:兩則事件、id 因 rule 段不撞、各自 cooldown。測:`test_two_rules_same_kind_both_fire`。
3. 編輯規則:該顆重建歸零、他顆 cooldown 保留。測:`test_upsert_preserves_other_rules_state`。
4. 部分 CDP 線:hub 過濾分發,rearm/suppress 僅該線(detector 只認得被餵的線)。測:`test_cdp_levels_subset`。
5. 壞檔:R9 語意(hub None + 503)。測:`test_bad_rules_file_degrades`。
6. 非法輸入:PARAM_SPECS 逐鍵 + 名稱/kind/levels/cooldown → INVALID_RULE。測:parametrized。
7. limit latch per-rule:各顆 detector 自有 `_latch`,lock/open 配對在規則內閉合。測:`test_limit_rule_latch_isolated`。
8. 遷移 legacy 壞/缺:fail-open 全開四條。測:`test_migration_defaults`。
- 熱路徑成本:N ≤ 30(MAX_RULES);per-tick N × evaluate,ctx 共用一次。

## Known Risks

- **升級當日單日雙列(R13)**:id 格式變更 → 當日已存 jsonl 舊 id 與重啟後新 id 不同,
  `mergeSignals` 去重不到 → 同事件兩列一天。接受(僅升級當日;不清 jsonl)。
- **關閉規則的歷史列仍顯示(R14a,🔴)**:filterKinds 移除的行為改動;列帶規則名可
  辨識;弱化選項記 next-time。
- **編輯規則狀態歸零**:該規則 cooldown/latch 重置,理論上可立即重發同訊號(edge 3
  接受 — 規則參數變了,舊冷卻無意義)。
