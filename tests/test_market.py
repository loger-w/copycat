from __future__ import annotations

from copycat.market import limit_up_price, tick_size, tick_size_milli


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
