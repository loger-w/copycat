from __future__ import annotations

from copycat.market import (
    limit_down_milli,
    limit_up_milli,
    limit_up_price,
    tick_size,
    tick_size_milli,
)


def test_tick_size_six_zones() -> None:
    assert tick_size(9.99) == 0.01
    assert tick_size(10.0) == 0.05
    assert tick_size(49.95) == 0.05
    assert tick_size(50.0) == 0.1
    assert tick_size(99.9) == 0.1
    assert tick_size(100.0) == 0.5
    assert tick_size(499.5) == 0.5
    assert tick_size(500.0) == 1.0
    assert tick_size(999.0) == 1.0
    assert tick_size(1000.0) == 5.0


def test_tick_size_milli_zones() -> None:
    assert tick_size_milli(9_990) == 10  # 9.99 元 → 0.01 元檔
    assert tick_size_milli(23_450) == 50  # 23.45 元 → 0.05 元檔
    assert tick_size_milli(123_450) == 500  # 123.45 元落 100–500 元段 → 0.5 元檔
    assert tick_size_milli(1_500_000) == 5_000  # 1500 元 → 5 元檔


def test_tick_size_milli_matches_float_version() -> None:
    for price_milli in (9_990, 23_450, 123_450):
        assert tick_size_milli(price_milli) == round(tick_size(price_milli / 1000) * 1000)


def test_limit_up_known_cases() -> None:
    assert limit_up_price(100.0) == 110.0
    assert limit_up_price(29.1) == 32.0  # 32.01 → tick 0.05 向下貼
    assert limit_up_price(99.0) == 108.5  # 108.9 → 過 100 tick 0.5
    assert limit_up_price(9.5) == 10.45  # 10.45 → 過 10 tick 0.05
    assert limit_up_price(56.2) == 61.8  # 61.82 → tick 0.1


def test_limit_up_zone_boundary_and_float_residue() -> None:
    # candidate 過 zone 邊界:45.5×1.1 = 50.05 → 50-100 段 tick 0.1 → 50.0
    assert limit_up_price(45.5) == 50.0
    # 10.01×1.1 = 11.011 → tick 0.05 → 11.0
    assert limit_up_price(10.01) == 11.0
    # 回傳值 ×100 必為整數(毫元運算無二進位殘差)
    for pc in (29.1, 56.2, 9.5, 45.5, 10.01, 123.5):
        v = limit_up_price(pc)
        assert abs(v * 100 - round(v * 100)) < 1e-9


def test_limit_up_milli_hand_computed() -> None:
    # 9.99 元:cand 10989(過 10 元 → tick 50)→ 向下貼 10950
    assert limit_up_milli(9_990) == 10_950
    # 45.5 元:cand 50050(過 50 元 → tick 100)→ 50000
    assert limit_up_milli(45_500) == 50_000
    # 90.9 元:cand 99990(50–100 元段 → tick 100)→ 99900
    assert limit_up_milli(90_900) == 99_900
    # 111.1 元:cand 122210(100–500 元段 → tick 500)→ 122000
    assert limit_up_milli(111_100) == 122_000
    # 999 元:cand 1098900(過 1000 元 → tick 5000)→ 1095000
    assert limit_up_milli(999_000) == 1_095_000


def test_limit_down_milli_hand_computed() -> None:
    # 9.99 元:cand 8991(10 元以下 → tick 10)→ 向上貼 9000
    assert limit_down_milli(9_990) == 9_000
    # 45.5 元:cand 40950 恰為 tick 50 整數倍 → 原值不動
    assert limit_down_milli(45_500) == 40_950
    # 90.9 元:cand 81810(50–100 元段 → tick 100)→ 81900
    assert limit_down_milli(90_900) == 81_900
    # 999 元:cand 899100(500–1000 元段 → tick 1000)→ 900000
    assert limit_down_milli(999_000) == 900_000


def test_limit_down_milli_tick_zone_taken_before_ceil() -> None:
    """tick 段取 cand(ceil 前)所在段 —— 與 neigui float 版 `_tick_size(raw)` 同語意."""
    # 111.1 元:cand 99990 落 50–100 元段 → tick 100 → ceil 至 100000(跨段而上)
    assert limit_down_milli(111_100) == 100_000
    # 110.57 元:cand 99513 仍在 tick 100 段 → 99600;若誤取 ceil 後所在段(tick 500)
    # 會得 100000
    assert limit_down_milli(110_570) == 99_600
    # 上界對稱案例:cand 恰等於段上界 50000 → 取上一段 tick 100,結果不變
    assert limit_up_milli(45_455) == 50_000


def test_limit_up_price_is_thin_wrapper_of_milli() -> None:
    for pc in (100.0, 29.1, 99.0, 9.5, 56.2, 45.5, 10.01, 123.5):
        assert limit_up_price(pc) == round(limit_up_milli(round(pc * 1000)) / 1000, 2)
