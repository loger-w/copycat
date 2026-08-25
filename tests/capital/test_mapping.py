"""mapping 測試:STOCKORDER/FUTUREORDER 逐欄 + TC4 → 期交所契約碼轉換(SC-2/3)。

證券逐欄案例移植 treading-king tests/test_capital_mapping.py(enum → Literal 改寫)。
FUTUREORDER 用欄依 Task 0 spike 定案(docs/research/2026-07-28-skcom-typelib.md)。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import copycat.stkfut_map as stkfut_map
from copycat.stkfut_map import lookup_product, write_map
from copycat.capital.mapping import (
    contract_from_fill,
    exchange_product_of,
    is_option_contract,
    multiplier_of,
    product_of,
    stock_code_of,
    to_exchange_symbol,
    to_futureorder_fields,
    to_stockorder_fields,
)
from copycat.capital.models import (
    BuySell,
    FutureOrderRequest,
    PriceType,
    StockOrderRequest,
    TimeInForce,
    TradeKind,
)


def _stock(
    buy_sell: BuySell = "buy",
    price: float = 590.0,
    price_type: PriceType = "limit",
    time_in_force: TimeInForce = "ROD",
    trade_kind: TradeKind = "cash",
) -> StockOrderRequest:
    return StockOrderRequest(
        stock_no="2330",
        buy_sell=buy_sell,
        price=price,
        qty=1,
        price_type=price_type,
        time_in_force=time_in_force,
        trade_kind=trade_kind,
    )


def _fut(
    tc4_symbol: str = "TC.F.TWF.TXF.202609",
    buy_sell: BuySell = "buy",
    price: float = 23000.0,
    qty: int = 2,
    price_type: PriceType = "limit",
    time_in_force: TimeInForce = "ROD",
    day_trade: bool = False,
) -> FutureOrderRequest:
    return FutureOrderRequest(
        tc4_symbol=tc4_symbol,
        buy_sell=buy_sell,
        price=price,
        qty=qty,
        price_type=price_type,
        time_in_force=time_in_force,
        day_trade=day_trade,
    )


# ── STOCKORDER 逐欄(treading-king 案例移植)────────────────────


def test_stock_buy_limit_rod_cash_maps_to_capital_enums() -> None:
    f = to_stockorder_fields(_stock(), full_account="1234567890A")
    assert f["bstrStockNo"] == "2330"
    assert f["bstrFullAccount"] == "1234567890A"
    assert f["sBuySell"] == 0  # 買=0
    assert f["nSpecialTradeType"] == 2  # 限價=2
    assert f["nTradeType"] == 0  # ROD=0
    assert f["sFlag"] == 0  # 現股=0
    assert f["bstrPrice"] == "590.00"  # 價格字串,兩位小數
    assert f["nQty"] == 1
    assert f["sPeriod"] == 0  # 盤中
    assert f["sPrime"] == 0  # 上市櫃


def test_stock_sell_market_fok_short_maps() -> None:
    f = to_stockorder_fields(
        _stock(
            buy_sell="sell",
            price_type="market",
            time_in_force="FOK",
            trade_kind="short",
        ),
        full_account="1234567890A",
    )
    assert f["sBuySell"] == 1  # 賣=1
    assert f["nSpecialTradeType"] == 1  # 市價=1
    assert f["nTradeType"] == 2  # FOK=2
    assert f["sFlag"] == 2  # 融券=2
    # review C4:歸零條件只看 price_type、與 TIF 正交 —— 若照抄期貨分支誤寫成
    # `market and ROD` 的組合條件,這一行(FOK 市價)會抓到。
    assert f["bstrPrice"] == "0"


def test_stock_margin_maps_to_one() -> None:
    f = to_stockorder_fields(_stock(trade_kind="margin"), full_account="x")
    assert f["sFlag"] == 1  # 融資=1


def test_stock_daytrade_sell_maps_to_three() -> None:
    f = to_stockorder_fields(_stock(buy_sell="sell", trade_kind="daytrade_sell"), full_account="x")
    assert f["sFlag"] == 3  # 無券=3


# ── FUTUREORDER 逐欄(spike 定案欄位)──────────────────────────


def test_future_limit_full_fields() -> None:
    f = to_futureorder_fields(_fut(), "F0123456789", contract="TXFI6")
    assert f == {
        "bstrFullAccount": "F0123456789",
        "bstrStockNo": "TXFI6",
        "bstrPrice": "23000",  # 整數價去小數
        "sTradeType": 0,  # ROD=0
        "sBuySell": 0,  # 買=0
        "sDayTrade": 0,
        "sNewClose": 2,  # 預設自動
        "nQty": 2,
    }


def test_future_limit_decimal_price_keeps_fraction() -> None:
    f = to_futureorder_fields(_fut(price=96.5), "acc", contract="TXO20000I6")
    assert f["bstrPrice"] == "96.5"  # 有小數保留,無 float 尾差


def test_future_sell_ioc_fok_tradetype() -> None:
    f = to_futureorder_fields(_fut(buy_sell="sell", time_in_force="IOC"), "acc", contract="TXFI6")
    assert f["sBuySell"] == 1
    assert f["sTradeType"] == 1  # IOC=1
    f2 = to_futureorder_fields(_fut(time_in_force="FOK"), "acc", contract="TXFI6")
    assert f2["sTradeType"] == 2  # FOK=2


def test_future_market_forces_ioc_and_m_literal() -> None:
    f = to_futureorder_fields(
        _fut(price_type="market", time_in_force="ROD"), "acc", contract="TXFI6"
    )
    assert f["bstrPrice"] == "M"  # 市價 literal(spike 定案 M,未實測)
    assert f["sTradeType"] == 1  # 市價 ROD(不可市價掛整天)→ 升 IOC


def test_future_market_fok_keeps_fok() -> None:
    # review A9:市價單僅 ROD 升 IOC;使用者明示 FOK(全成或全撤)不可被靜默降成 IOC
    f = to_futureorder_fields(
        _fut(price_type="market", time_in_force="FOK"), "acc", contract="TXFI6"
    )
    assert f["bstrPrice"] == "M"
    assert f["sTradeType"] == 2  # FOK 保留


def test_future_new_close_override() -> None:
    f = to_futureorder_fields(_fut(), "acc", contract="TXFI6", new_close=1)
    assert f["sNewClose"] == 1  # 平倉單由 close.py 傳 1


def test_future_day_trade_flag() -> None:
    f = to_futureorder_fields(_fut(day_trade=True), "acc", contract="TXFI6")
    assert f["sDayTrade"] == 1


# ── to_exchange_symbol:月碼表 ─────────────────────────────────


@pytest.mark.parametrize(
    ("month", "code"),
    [
        (1, "A"),
        (2, "B"),
        (3, "C"),
        (4, "D"),
        (5, "E"),
        (6, "F"),
        (7, "G"),
        (8, "H"),
        (9, "I"),
        (10, "J"),
        (11, "K"),
        (12, "L"),
    ],
)
def test_futures_month_codes(month: int, code: str) -> None:
    assert to_exchange_symbol(f"TC.F.TWF.TXF.2026{month:02d}") == f"TXF{code}6"


@pytest.mark.parametrize(("ym", "code"), [("202603", "C6"), ("202609", "I6"), ("202612", "L6")])
def test_option_call_month_codes(ym: str, code: str) -> None:
    assert to_exchange_symbol(f"TC.O.TWF.TXO.{ym}.C.19500") == f"TXO19500{code}"


@pytest.mark.parametrize(("ym", "code"), [("202601", "M6"), ("202609", "U6"), ("202612", "X6")])
def test_option_put_month_codes(ym: str, code: str) -> None:
    assert to_exchange_symbol(f"TC.O.TWF.TXO.{ym}.P.20000") == f"TXO20000{code}"


def test_year_code_is_last_digit() -> None:
    assert to_exchange_symbol("TC.F.TWF.TXF.202712") == "TXFL7"


def test_option_strike_string_kept_verbatim() -> None:
    assert to_exchange_symbol("TC.O.TWF.TXO.202609.C.20000") == "TXO20000I6"


def test_weekly_option_product_same_rule() -> None:
    assert to_exchange_symbol("TC.O.TWF.TX5.202607.C.23000") == "TX523000G6"


# ── to_exchange_symbol:HOT 與解析失敗 ─────────────────────────


def test_hot_with_resolved_ym() -> None:
    assert to_exchange_symbol("TC.F.TWF.TXF.HOT", resolved_ym="202609") == "TXFI6"


def test_hot_without_resolved_ym_raises() -> None:
    with pytest.raises(ValueError):
        to_exchange_symbol("TC.F.TWF.TXF.HOT")


@pytest.mark.parametrize("bad_ym", ["2026-09", "20269"])
def test_hot_resolved_ym_bad_format_raises(bad_ym: str) -> None:
    # review C6:resolved_ym 非 YYYYMM 形(帶分隔/長度不足)不可靜默組出錯誤契約碼
    with pytest.raises(ValueError):
        to_exchange_symbol("TC.F.TWF.TXF.HOT", resolved_ym=bad_ym)


def test_month_zero_raises() -> None:
    # review C6:月份 00 過得了 \d{6} regex,月碼表必須擋(chr 位移會算出 '@')
    with pytest.raises(ValueError):
        to_exchange_symbol("TC.F.TWF.TXF.202600")


@pytest.mark.parametrize(
    "symbol",
    [
        "TC.S.TWS.2330",  # 個股非期權
        "TXF202609",  # 非 TC4 格式
        "TC.F.TWF.TXF.202613",  # 月份越界
        "TC.O.TWF.TXO.2026W1.C.20000",  # 週選 token 非 YYYYMM(spike 未定)
        "",
    ],
)
def test_unparseable_symbol_raises(symbol: str) -> None:
    with pytest.raises(ValueError):
        to_exchange_symbol(symbol)


# ── multiplier_of / exchange_product_of / product_of ──────────


@pytest.mark.parametrize(
    ("product", "mult"),
    [("TXF", 200), ("MXF", 50), ("TMF", 10), ("TXO", 50)],
)
def test_multiplier_of_base_products(product: str, mult: int) -> None:
    assert multiplier_of(product) == mult


@pytest.mark.parametrize(
    "product",
    ["TX1", "TX2", "TX3", "TX4", "TX5", "TXY", "TXZ", "MX1", "MX2", "MX3", "MX4", "MX5"],
)
def test_multiplier_of_weekly_family_is_50(product: str) -> None:
    assert multiplier_of(product) == 50


def test_multiplier_of_unknown_raises() -> None:
    with pytest.raises(ValueError):
        multiplier_of("ZZZ")


class TestMultiplierStkfutFallback:
    """個股期乘數 = 契約單位(股數),來源是版控的 stkfut 對映表(SC-2)。

    沒有這條 fallback,個股期送單在 `multiplier_of` 就 400 —— 而那個錯誤碼
    (INVALID_ORDER)完全指不到真因「乘數表沒有這個產品」。
    """

    def _map(self, tmp_path: Path) -> Path:
        path = tmp_path / "map.json"
        write_map(
            path,
            {
                "2330": {
                    "prod": "CDF",
                    "name": "台積電",
                    "unit": 2000,
                    "mini": {"prod": "QFF", "unit": 100},
                },
                "1234": {"prod": "BBF", "name": "壞單位", "unit": 0, "mini": None},
            },
        )
        return path

    def test_standard_and_mini_units(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(stkfut_map, "DEFAULT_PATH", self._map(tmp_path))
        assert multiplier_of("CDF") == 2000
        assert multiplier_of("QFF") == 100

    def test_known_products_still_win(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(stkfut_map, "DEFAULT_PATH", self._map(tmp_path))
        assert multiplier_of("TXF") == 200

    def test_bad_unit_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """查得到但單位 ≤0 → ValueError(→400):乘數是名目金額閘的分母,猜不得。"""
        monkeypatch.setattr(stkfut_map, "DEFAULT_PATH", self._map(tmp_path))
        with pytest.raises(ValueError):
            multiplier_of("BBF")

    def test_stale_map_version_degrades_to_unknown(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """對映檔版本不符 → load_map 回空 → 個股期一律拒單(不是靜默用錯乘數)。"""
        path = tmp_path / "map.json"
        path.write_text(
            json.dumps({"_cache_version": 1, "map": {"2330": {"prod": "CDF", "name": "台積電"}}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(stkfut_map, "DEFAULT_PATH", path)
        with pytest.raises(ValueError):
            multiplier_of("CDF")


@pytest.mark.parametrize(
    ("contract", "product"),
    [("TXFI6", "TXF"), ("MXFL5", "MXF"), ("TMFA6", "TMF"), ("TXO20000I6", "TXO")],
)
def test_exchange_product_of(contract: str, product: str) -> None:
    assert exchange_product_of(contract) == product


@pytest.mark.parametrize(
    ("contract", "product"),
    [("TX422000T6", "TX4"), ("MXFI6", "MXF"), ("TXO20000I6", "TXO"), ("MX523000G6", "MX5")],
)
def test_exchange_product_of_known_prefix_wins(contract: str, product: str) -> None:
    # 週選契約(TX422000T6)的「去尾 2 碼取字母段」啟發式會截成 "TX" →
    # 乘數反查 ValueError → fallback 1,金額閘鬆 50 倍(review A1)
    assert exchange_product_of(contract) == product


def test_stock_code_of() -> None:
    """部位列 → 股號(SC-1)。**打真 `stkfut_map.DEFAULT_PATH` 不 monkeypatch**:

    這條 helper 的價值就在「版控對映表現在真的認得這個契約碼」,拿 tmp map 測等於
    只測了自己寫的假資料;版控表哪天沒 refresh 掉了 CDF,這條要跟著紅。
    """
    # 證券:stock_no 本身就是股號
    assert stock_code_of("sec", "2330") == "2330"
    # 個股期:標準(CDF)與小型(QFF)契約碼都反查到同一檔股號
    assert stock_code_of("fut", "CDFI6") == "2330"
    assert stock_code_of("fut", "QFFI6") == "2330"
    # 除權息調整後商品代號第三碼由 F 改數字(EE1)→ 進不了對映表 → 不猜
    assert stock_code_of("fut", "EE1I6") is None
    # 契約碼壞到 exchange_product_of 都 raise → 吞成 None,不擋整條 positions API
    assert stock_code_of("fut", "1") is None


class TestIsOptionContract:
    """送單分流(SendOptionOrder vs SendFutureOrder)的單一定義,直接單元測試。

    先前只有 client 層的間接覆蓋(`test_client.py`),判準本身的邊界(調整後
    契約碼、ETF 期貨、對映表降級)沒有一條測試指得到 —— 分流錯的代價是真錢面。
    """

    def _map(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """個股期對映表注入(隔離版控真檔;CDF=標準 2000、NYF=ETF 10000)。"""
        path = tmp_path / "map.json"
        write_map(
            path,
            {
                "2330": {
                    "prod": "CDF",
                    "name": "台積電",
                    "unit": 2000,
                    "mini": {"prod": "QFF", "unit": 100},
                },
                "0050": {"prod": "NYF", "name": "元大台灣50ETF", "unit": 10000, "mini": None},
            },
        )
        monkeypatch.setattr(stkfut_map, "DEFAULT_PATH", path)

    @pytest.mark.parametrize(
        ("contract", "option"),
        [
            ("TXO20000I6", True),  # 月選(已知產品)
            ("TX422000T6", True),  # 週選 Put 月碼(已知家族;啟發式會截成 "TX")
            ("ZZZ20000I6", True),  # 未知產品、body 含履約價 = 選擇權形
            ("TXFI6", False),  # 指數期貨
            ("CDFI6", False),  # 個股期標準腿(對映表命中)
            ("SXFI6", False),  # 未知產品、body 純字母 = 期貨形(費半)
            ("NYFI6", False),  # ETF 期貨(單位非標準,但仍是期貨)
            ("EE1I6", False),  # 除權息調整後個股期:第三碼變數字,不是履約價
            ("CD1I6", False),
        ],
    )
    def test_classification(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contract: str, option: bool
    ) -> None:
        """調整後契約(EE1/CD1)必須留在期貨側:第三碼的**單一**數字是流水碼不是履約價。

        期交所股票期貨經契約調整(除權息等)後商品代號第三碼由 F 改為數字,這種碼
        不可能出現在 `stkfut_map`(`_parse_rows` 只組 XXF 形)→ 一路掉到結構判別;
        「body 含任何數字 = 選擇權」會把它判成選擇權,與本輪 P0 同一個失效樣態
        (送單 + 平倉全走 SendOptionOrder,真錢面)。
        """
        self._map(tmp_path, monkeypatch)
        assert is_option_contract(contract) is option

    def test_structural_fallback_survives_stale_map(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """對映表版本不符降級空表時,個股期仍判期貨 —— 結構判別是真安全網。

        `lookup_product` 那層只是快路徑:對映檔失效(版本 bump / 檔案損毀)時
        分流不可以跟著翻面,否則「對映表過期」會靜默升級成「送單走錯通道」。
        """
        path = tmp_path / "map.json"
        path.write_text(
            json.dumps({"_cache_version": 1, "map": {"2330": {"prod": "CDF", "name": "台積電"}}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(stkfut_map, "DEFAULT_PATH", path)
        assert lookup_product("CDF") is None  # 前提:這條測的確實是降級路徑
        assert is_option_contract("CDFI6") is False


def test_product_of_takes_fourth_segment() -> None:
    assert product_of("TC.F.TWF.TXF.HOT") == "TXF"
    assert product_of("TC.F.TWF.MXF.202609") == "MXF"
    assert product_of("TC.O.TWF.TXO.202609.C.20000") == "TXO"


def test_product_of_bad_symbol_raises() -> None:
    with pytest.raises(ValueError):
        product_of("TC.S.TWS.2330")  # 個股段非期權
    with pytest.raises(ValueError):
        product_of("not-a-symbol")


# 🔴 2026-08-24 prod 實錄:市價單帶估價 → SKCOM 1068
# SK_ERROR_SPECIAL_TRADE_TYPE_IS_MARKETPRICE_AND_ORDERPRICE_SHOULD_BE_ZERO
# (user 5608 市價賣 ×5 / 6770 市價買 ×1 全數被拒;audit data/audit/capital-20260824.jsonl)。
# 現股市價單 bstrPrice 必須為 "0";req.price 仍供 safety 金額閘估算,不動。
def test_stock_market_order_price_field_must_be_zero() -> None:
    f = to_stockorder_fields(_stock(price_type="market"), full_account="x")
    assert f["nSpecialTradeType"] == 1  # 市價
    assert f["bstrPrice"] == "0"  # 1068:委託價必須為 0(已實證);字面 "0" 為推定,首單驗


def test_stock_limit_order_price_field_unchanged() -> None:
    f = to_stockorder_fields(_stock(), full_account="x")
    assert f["bstrPrice"] == "590.00"  # 對照組:限價路徑不受市價歸零影響


def test_contract_from_fill_builds_exchange_code_from_reply_fields() -> None:
    assert contract_from_fill("QEF06", "202606") == "QEFF6"
    assert contract_from_fill("TXF09", "202609") == "TXFI6"
    assert contract_from_fill("CDF12", "202612") == "CDFL6"


def test_contract_from_fill_returns_none_when_any_piece_is_missing() -> None:
    assert contract_from_fill(None, "202606") is None
    assert contract_from_fill("QEF06", None) is None
    assert contract_from_fill("QEF06", "HOT") is None
    assert contract_from_fill("QEF06", "202613") is None
    # review F-04:調整碼 / 未白名單選擇權 / 兩碼月與 idx33 不合 → None(不捏契約碼)
    assert contract_from_fill("EE106", "202606") is None
    assert contract_from_fill("TE122000", "202606") is None
    assert contract_from_fill("QEF06", "202609") is None
