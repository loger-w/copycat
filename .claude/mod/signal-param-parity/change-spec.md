# mod/signal-param-parity — change-spec(A8:#101 parity 補完)

需求原文 = `docs/superpowers/specs/2026-08-25-do-batch-review.md` §2.3 Standards 3(`PARAM_DEFAULTS` 與 `PARAM_FIELDS`
分居無鎖、無「預設值落在 [min,max]」斷言)+ Spec 4(`COOLDOWN_MIN/MAX` 前端硬抄未進 parity;後端 `INT_PARAM_KEYS`
拒非整數而前端無對應 → 填 `2.9` 仍拿泛用 INVALID_RULE)+ §5 A8。`/auto` 鏈式第一批第 3 條。

## §0 現況 vs 目標

| 面 | 現況 | 目標 |
|---|---|---|
| 值域 | fixture `specs` 釘 `PARAM_SPECS` ↔ `PARAM_FIELDS.min/max`(N055) | 不變 |
| 整數鍵 | 後端 `INT_PARAM_KEYS` 拒非整數;前端零檢查 → 泛用 INVALID_RULE | fixture 加 `int_keys`;`ParamField.integer`;Dialog 送出前擋並指出欄位「<label>須為整數」;兩邊 parity 各斷言 |
| 冷卻界 | 後端 `COOLDOWN_MIN, MAX = 60, 86_400`;前端 Dialog 內硬寫兩個常數 | fixture 加 `cooldown`;常數搬到 `lib/signal-params.ts` 匯出;兩邊 parity 各斷言 |
| 新規則預設值 | `PARAM_DEFAULTS`(Dialog 內)與 `PARAM_FIELDS`(lib)分居,鍵集無鎖、無值域斷言 | 併進 `ParamField.default`(同一個物件 → 鍵集結構上恆同);parity 斷言預設值 ∈ [min,max]、整數鍵為整數。**預設值不進 fixture**:後端沒有對應概念(種子走 `SignalsConfig`),放進去就是假契約 |

`[auto-default: 預設值併進 ParamField 而非另立一張表 + 鍵集斷言 | reason: 同物件讓「鍵集相同」成為型別事實而非測試事實;
表單初值仍是字串(表單慣例「數字欄以字串存」不動)]`
`[auto-default: 整數檢查文案「<label>須為整數」,與既有「<label>須在 a–b 之間」同形,先於出界檢查 | reason: 非整數多半也在界內,
先報「須為整數」使用者才知道該改的是小數點不是大小]`

## §1 白名單

- 後端 `copycat/signal_rules.py` **零改動**(只加測試斷言)。
- `SignalRulesDialog.tsx` caller:`PARAM_DEFAULTS` 讀者 = `blankForm` / `toForm` / 換 kind 三處 → 改讀 `paramDefaults(kind)`;
  `COOLDOWN_*` 讀者 = `submit` 與冷卻 input 的 min/max。`PARAM_FIELDS` 讀者 = Dialog 三處 + parity 測試。
- 既有測試白名單:`SignalRulesDialog.test.tsx` 全檔(值域文案 / 邊界值可送 / 冷卻界文案「冷卻秒數須在 60–86400 之間」/
  kind 切換欄位 / payload 鍵集)、`signal-param-parity.test.ts` 既有兩案語意、`tests/test_signal_rules.py` 全檔。
- 行為保留:出界文案與閉區間;`step` 不變;預設值字面(2 / 300 / 1.5 / 60 / 3 / 60 / 5 / 100 / 500)不變。

## §2 backward compat

前端內部;零 API / 資料格式改動。唯一可觀察差異:整數欄填小數時前端就擋、文案指出欄位(舊:送出後泛用文案)。
fixture 加兩個頂層鍵,舊讀者只讀 `specs` 不受影響。

## §3 seams

`signal-param-parity.test.ts`(int_keys / cooldown / 預設值三案)+ `tests/test_signal_rules.py` parity 補兩個斷言 +
`SignalRulesDialog.test.tsx` 整數欄一案。

## §4 review round 1 逐條處置

### Standards
- **ST1 P2 預設值搬家無字面鎖(∈ [min,max] 擋不住 3 → 30)** — **接受**:parity 加字面 golden(四 kind + 冷卻預設)。
- **ST2 P3 整數鍵集合 actual 未去重(同鍵兩 kind 都標會假紅)** — **接受**:兩邊都 Set。
- **ST3 P3 CLAUDE.md §4 / artifact 尚未 commit** — 事實;隨 chore commit。
- **ST4 P3 🔴 commit 內含純搬移(PARAM_DEFAULTS / COOLDOWN 進 lib)** — **接受(記錄偏離)**:紅測試已 import 自 lib,拆開會留壞 commit。

### Spec
- **SP1 P2 冷卻秒數整數缺口原樣留著(後端 `_as_int` 拒非整數)** — **接受**:submit 加 `Number.isInteger` + 文案「冷卻秒數須為整數」,
  Dialog 一案釘。
- **SP2 P2 契約擴張未同步 CLAUDE.md §4** — review 期間已改寫(int_keys / cooldown / default 三格),隨 chore commit。
- **SP3 P3 `blankForm.cooldown "300"` 未進 lib、無落界斷言** — **接受**:`COOLDOWN_DEFAULT` 進 lib,parity 釘「落界整數」。
- 核過無問題(reviewer 列):整數檢查與後端 `_normalize_params` 同序、`"2.0"` / `1e3` 兩邊同收、`toForm` 語意等價、
  預設值不進 fixture 的理由成立(後端種子走 `SignalsConfig`,現值本就分歧:rearm_ticks 2 vs 5 等 —— **既存,另案**)。
