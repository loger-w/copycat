"""全市場廣度純函式層(零 IO)—— SC-1。

邏輯自 neigui 搬移(**邏輯全等、實作適配 copycat**),來源:
- `backend/services/market_universe.py`:`classify_stock_id` / `filter_universe` /
  `_parse_active_disposition`
- `backend/services/finmind_realtime.py`:`_build_name_map` / `_build_type_map` /
  `_dedup_sector_map`(含 override 表)/ `_max_tick_date` / `_do_fetch_market_snapshot`
  的白名單→filter 組裝順序(收成 `assemble_universe`)
- `backend/services/market_today.py`:`compute_breadth`

唯一刻意偏離:漲跌停判定改**毫元整數精確等值**(`market.limit_up_milli` /
`limit_down_milli`),取代 neigui 的 float 半 tick 容差 —— 半 tick 內但非停板價的
收盤在此判為一般漲跌。等價性由 `tests/test_market_breadth.py` 的手造邊界與
`tests/fixtures/breadth_parity.json` 全管線 oracle 把關。

本模組不做任何 IO;取數在 `copycat/server/breadth_fetch.py`,編排在
`copycat/server/breadth_engine.py`。
"""

from __future__ import annotations

import datetime as _dt

from copycat.market import limit_down_milli, limit_up_milli

_TAIPEI_TZ = _dt.timezone(_dt.timedelta(hours=8))

#: stock_id → 指定主產業(neigui `_PRIMARY_INDUSTRY_OVERRIDE` 原表)。
#: 同 date 多 row 時 tie-break 走 Unicode codepoint ASC,對台股權值股可能挑出
#: 非直覺 sector;此表覆蓋十檔常用權值股。value 必須是 TaiwanStockInfo 的真實
#: `industry_category` 字串(「金融保險」無「業」尾),否則自成幽靈 sector。
PRIMARY_INDUSTRY_OVERRIDE: dict[str, str] = {
    "2330": "半導體業",
    "2454": "半導體業",
    "2317": "其他電子業",
    "2308": "電子零組件業",
    "2382": "電子工業",
    "2412": "通信網路業",
    "2882": "金融保險",
    "2891": "金融保險",
    "1216": "食品工業",
    "1101": "水泥工業",
}


# ---------------------------------------------------------------------------
# 結構分類 / universe filter(neigui market_universe)
# ---------------------------------------------------------------------------


def classify_stock_id(stock_id: str) -> str | None:
    """只依代號結構分類(不查表)。

    Returns:
        ``"etf"`` — `00` 前綴(ETF / 基金,4–6 位皆涵蓋)
        ``"warrant"`` — 長度非 4 或含非 digit(權證 / 衍生品 / 警示後綴 / 指數 row)
        ``None`` — 4 位純數字且非 `00` 前綴 → 普通股 candidate

    處置股需走 FinMind dataset 對映(非結構檢測),見 `parse_active_disposition`。
    """
    s = (stock_id or "").strip()
    if not s:
        return "warrant"
    if s.startswith("00"):
        return "etf"
    if len(s) != 4 or not s.isdigit():
        return "warrant"
    return None


def filter_universe(candidates: list[str], watch_list: set[str]) -> dict:
    """把候選代號切成 universe + excluded 三桶。

    watch_list(處置股)優先於 classify 結果:同時是普通股 / ETF 與處置股 →
    一律歸 watch_list 桶。
    """
    universe: set[str] = set()
    etf: list[str] = []
    warrant: list[str] = []
    watch_excluded: list[str] = []

    for sid in candidates:
        if sid in watch_list:
            watch_excluded.append(sid)
            continue
        bucket = classify_stock_id(sid)
        if bucket == "etf":
            etf.append(sid)
        elif bucket == "warrant":
            warrant.append(sid)
        else:
            universe.add(sid)

    return {
        "universe": universe,
        "excluded": {"etf": etf, "warrant": warrant, "watch_list": watch_excluded},
    }


# ---------------------------------------------------------------------------
# TaiwanStockInfo 對映表(neigui finmind_realtime)
# ---------------------------------------------------------------------------


def build_name_map(rows: list[dict]) -> dict[str, str]:
    """TaiwanStockInfo rows → `stock_id` → `stock_name`(同代號取最新 date 那筆)。

    snapshot endpoint 不回 name,前端顯示需靠這張表。
    """
    out: dict[str, str] = {}
    sorted_rows = sorted(rows, key=lambda r: r.get("date") or "", reverse=True)
    for row in sorted_rows:
        sid = row.get("stock_id")
        name = row.get("stock_name")
        if sid and name and sid not in out:
            out[sid] = name
    return out


def build_type_map(rows: list[dict]) -> dict[str, str]:
    """TaiwanStockInfo rows → `stock_id` → `"twse"` / `"tpex"`(取最新 date 那筆)。

    `type` 非兩市值域的 row 既不寫入也不佔位(較舊的合法 row 仍會勝出)。
    """
    out: dict[str, str] = {}
    sorted_rows = sorted(rows, key=lambda r: r.get("date") or "", reverse=True)
    for row in sorted_rows:
        sid = row.get("stock_id")
        t = row.get("type")
        if sid and t in ("twse", "tpex") and sid not in out:
            out[sid] = t
    return out


def dedup_sector_map(rows: list[dict]) -> dict[str, str]:
    """TaiwanStockInfo rows → `stock_id` → 主產業(決定性去重)。

    Tie-break 順序:
    1. `PRIMARY_INDUSTRY_OVERRIDE` 命中直接取
    2. 先 filter `type in ("twse", "tpex")`
    3. stable 兩段排序:industry_category ASC 先、date DESC 後
    4. 每個 stock_id 取第一列;industry 空 → `"其他"`
    """
    out: dict[str, str] = {}
    filtered = [r for r in rows if r.get("type") in ("twse", "tpex")]
    # Python stable sort 兩段:secondary key ASC 先,primary key DESC 後
    sorted_rows = sorted(
        sorted(filtered, key=lambda r: r.get("industry_category") or ""),
        key=lambda r: r.get("date") or "",
        reverse=True,
    )
    for row in sorted_rows:
        sid = row.get("stock_id")
        if not sid or sid in out:
            continue
        if sid in PRIMARY_INDUSTRY_OVERRIDE:
            out[sid] = PRIMARY_INDUSTRY_OVERRIDE[sid]
        else:
            cat = row.get("industry_category")
            out[sid] = cat if cat else "其他"
    return out


# ---------------------------------------------------------------------------
# 處置股 / tick 時刻
# ---------------------------------------------------------------------------


def parse_active_disposition(rows: list[dict], today: _dt.date) -> set[str]:
    """TaiwanStockDispositionSecuritiesPeriod rows → 處置期間涵蓋 today 的代號集合。

    區間**含頭含尾**;缺欄或日期無法解析的 row 略過(never-raise)。
    """
    active: set[str] = set()
    for row in rows:
        sid = row.get("stock_id")
        ps = row.get("period_start")
        pe = row.get("period_end")
        if not (sid and ps and pe):
            continue
        try:
            ps_d = _dt.date.fromisoformat(ps)
            pe_d = _dt.date.fromisoformat(pe)
        except ValueError:
            continue
        if ps_d <= today <= pe_d:
            active.add(sid)
    return active


def max_tick_datetime(
    rows: list[dict], *, upper_bound: _dt.datetime | None = None
) -> _dt.datetime | None:
    """snapshot rows 的 `date` 欄最大值 → **台北 naive** datetime;無有效值回 None。

    `Z` 尾(UTC ISO)先當 aware UTC 再拉到台北,避免 strip Z 後被當台北時刻而
    產生 8 小時偏移;任何帶 tzinfo 的值一律歸一成台北 naive,否則 `max()` 會在
    aware/naive 混用時拋 TypeError。

    `upper_bound`(台北 naive,**含等值**)= 越過即視為髒 row 忽略:單一列偶發帶著
    收盤時刻(或未來日期)時,`max()` 會讓整份快照的時刻被那一列決定 —— 呼叫端的
    分鐘鍵因此恆定,整個交易日的序列塌成一格(同鍵 last-wins),而檔案還在、格式還對,
    沒有任何錯誤訊號。**歸一成台北 naive 之後才比界**,否則 Z 尾的正常列會被 8 小時
    偏移判成越界。全部越界 → None(= 該輪無可用時刻,呼叫端視同失敗)。
    """
    parsed: list[_dt.datetime] = []
    for row in rows:
        raw = row.get("date")
        if not raw:
            continue
        try:
            s = str(raw).replace("T", " ")
            has_z = s.endswith("Z")
            if has_z:
                s = s[:-1]
            dt = _dt.datetime.fromisoformat(s)
        except ValueError:
            continue
        if has_z:
            dt = dt.replace(tzinfo=_dt.timezone.utc)
        if dt.tzinfo is not None:
            dt = dt.astimezone(_TAIPEI_TZ).replace(tzinfo=None)
        if upper_bound is not None and dt > upper_bound:
            continue
        parsed.append(dt)
    if not parsed:
        return None
    return max(parsed)


# ---------------------------------------------------------------------------
# universe 組裝 + 廣度統計
# ---------------------------------------------------------------------------


def assemble_universe(
    rows: list[dict],
    primary_sector: dict[str, str],
    watch_list: set[str],
) -> list[dict]:
    """snapshot 原始 rows → 可統計的普通股 rows(順序即 neigui 組裝順序)。

    1. **白名單**:`stock_id in primary_sector` —— 天然排除 tick snapshot 內的
       指數 row(001 加權 / 036 類股 等 3 位代號,TaiwanStockInfo 未收錄)。
    2. **結構 + 處置股 filter**:`filter_universe`(ETF `00` 前綴 / 權證 / 處置股)。

    兩步順序寫反(先 filter 再白名單)結果會不同,parity 測試會抓到。
    `primary_sector` 為空(sector map 冷啟動失敗)→ 回空 list,呼叫端以 degraded
    處理。
    """
    whitelisted = [r for r in rows if r.get("stock_id") in primary_sector]
    result = filter_universe(
        [r.get("stock_id", "") for r in whitelisted],
        watch_list=watch_list,
    )
    allowed = result["universe"]
    return [r for r in whitelisted if r.get("stock_id") in allowed]


def _is_limit(close: float, prev_close: float) -> tuple[bool, bool]:
    """毫元精確等值判漲停 / 跌停(取代 neigui 的 float 半 tick 容差)。"""
    prev_milli = round(prev_close * 1000)
    close_milli = round(close * 1000)
    return (
        close_milli == limit_up_milli(prev_milli),
        close_milli == limit_down_milli(prev_milli),
    )


def _to_number(value: object) -> float | None:
    """數值欄 → float;缺值 / 非數值 → None(`limit_streaks._to_float` 同語意)。

    `bool` 明確排除(True 靜默變 1.0)。snapshot 的 `high` / `low` 不保證是數值 ——
    未成交的檔位實務上會是空字串或 `"-"`,而 `round(x * 1000)` 對 str 直接 TypeError:
    那個例外從 `compute_breadth` 一路逃到 `_poll_loop` 的傘罩被吞掉,`_fail()` 沒被
    呼叫 → 退避不動、stale 不亮,整片家數只是凍在最後一則且零錯誤訊號。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _is_touched(high: object, low: object, prev_close: float) -> tuple[bool, bool]:
    """毫元等值判「盤中曾觸及停板」;high/low 缺或非數值 → (False, False)。

    只回「是否摸到」;「觸及**未鎖**」= 本結果 and not `_is_limit` 同向,由呼叫端合成
    (本函式拿不到 close)。
    """
    prev_milli = round(prev_close * 1000)
    high_f = _to_number(high)
    low_f = _to_number(low)
    touched_up = high_f is not None and round(high_f * 1000) == limit_up_milli(prev_milli)
    touched_down = low_f is not None and round(low_f * 1000) == limit_down_milli(prev_milli)
    return touched_up, touched_down


def compute_breadth(
    rows: list[dict],
    type_map: dict[str, str],
    name_map: dict[str, str],
) -> dict | None:
    """上市 / 上櫃 × 漲停 / 上漲 / 平盤 / 下跌 / 跌停 家數 + 全量 rows。

    - 五桶**互斥**(漲停不重複計入上漲)。
    - `prev_close = close − change_price`(snapshot 精確欄位,不用 change_rate 反推);
      `close` / `change_price` 缺或 `prev_close <= 0` → 不判 limit,只按 change_rate
      正負分桶。
    - `change_rate` 為 None 的整檔跳過;`type_map` 查無市場的代號排除。
    - rows 另帶 `close`(直通)與 `touched_limit_up` / `touched_limit_down`
      (`high`/`low` 摸到停板但收盤未鎖;缺欄或前收不可用 → False)。touched 不影響
      五桶家數 —— 觸及未鎖仍按 change_rate 分桶。
    - rows 另帶 `limit_judged` = 「本輪這檔的 limit 旗標是**判定結果**而非缺值
      預設」。缺值列的 `limit_up` / `limit_down` 恆 False,與「真的沒鎖」同形 ——
      diff 事件源(`breadth_engine`)靠這鍵整列跳過,缺欄輪才不會產假 open。
      **copycat-only 附加鍵**:parity oracle 只比 counts + 逐檔桶推導,不做逐鍵
      dict 比對,fixture 不需重錄。
    - 全空 → `None`(呼叫端視同該輪失敗)。
    """
    counts: dict[str, dict[str, int]] = {
        m: {"limit_up": 0, "up": 0, "flat": 0, "down": 0, "limit_down": 0}
        for m in ("twse", "tpex")
    }
    rows_out: list[dict] = []

    for r in rows:
        sid = r.get("stock_id")
        market = type_map.get(sid or "")
        chg = r.get("change_rate")
        if not sid or market not in counts or chg is None:
            continue

        close = r.get("close")
        change_price = r.get("change_price")
        prev_close = (
            close - change_price if close is not None and change_price is not None else None
        )
        limit_up = False
        limit_down = False
        touched_up = False
        touched_down = False
        limit_judged = False
        # 條件寫在 `if` 內(不抽成布林變數再 `if flag:`)—— pyright 只在條件式當場
        # narrow `close` / `prev_close`,經布林變數轉一手就會退回 `... | None`。
        if prev_close is not None and prev_close > 0 and close is not None:
            limit_judged = True
            limit_up, limit_down = _is_limit(close, prev_close)
            touched_up, touched_down = _is_touched(r.get("high"), r.get("low"), prev_close)

        if limit_up:
            bucket = "limit_up"
        elif limit_down:
            bucket = "limit_down"
        elif chg > 0:
            bucket = "up"
        elif chg < 0:
            bucket = "down"
        else:
            bucket = "flat"
        counts[market][bucket] += 1

        tv = r.get("total_volume")
        yv = r.get("yesterday_volume")
        vol_ratio = (tv / yv) if (tv is not None and yv) else None
        rows_out.append(
            {
                "stock_id": sid,
                "name": name_map.get(sid) or sid,
                "market": market,
                "close": close,
                "change_rate": chg,
                "volume_ratio": vol_ratio,
                "total_amount": r.get("total_amount"),
                "limit_up": limit_up,
                "limit_down": limit_down,
                "limit_judged": limit_judged,
                "touched_limit_up": touched_up and not limit_up,
                "touched_limit_down": touched_down and not limit_down,
            }
        )

    if not rows_out:
        return None
    return {"twse": counts["twse"], "tpex": counts["tpex"], "rows": rows_out}
