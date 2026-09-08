from __future__ import annotations

from pathlib import Path

import pytest

from copycat import cli


class TestRefreshStockNames:
    """`refresh-stock-names` 的 dispatch(change-spec 🟢-7)。

    有這支才會發現「`args.command` 字串打錯」或「import 路徑寫錯」—— 兩者都只在真的
    跑那個子命令時才會炸,而 CLI 沒有任何其他測試會走到 dispatch(self-review MC-5)。
    """

    def test_prints_count_and_exits_zero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        called: list[str] = []

        def fake_refresh(*_args: object, **_kwargs: object) -> dict[str, str]:
            called.append("refresh")
            return {"2330": "台積電", "2317": "鴻海"}

        monkeypatch.setattr("copycat.stock_names.refresh", fake_refresh)
        assert cli.main(["refresh-stock-names"]) == 0
        assert called == ["refresh"]
        assert "2" in capsys.readouterr().out

    def test_refresh_failure_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """守門拋錯要傳到 CLI 外(保留舊檔的語意靠拋出來讓 exit code 非 0)。"""

        def boom(*_args: object, **_kwargs: object) -> dict[str, str]:
            raise ValueError("名稱表 42000 筆不在 [1800, 6000]")

        monkeypatch.setattr("copycat.stock_names.refresh", boom)
        with pytest.raises(ValueError, match=r"\[1800, 6000\]"):
            cli.main(["refresh-stock-names"])


class TestRefreshStkfutMap:
    """順手把同形狀的既有子命令也鎖住(兩者共用 dispatch 尾段)。"""

    def test_prints_count_and_exits_zero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(
            "copycat.stkfut_map.refresh",
            lambda *_a, **_k: {"2330": {"prod": "CDF", "name": "台積電"}},
        )
        assert cli.main(["refresh-stkfut-map"]) == 0
        assert "1" in capsys.readouterr().out


class TestUnknownCommand:
    def test_missing_subcommand_exits_nonzero(self) -> None:
        with pytest.raises(SystemExit):
            cli.main([])


class TestScreenCommand:
    def test_screen_date_on_non_trading_day_exits_with_explicit_error(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """pr-211 F-07:`screen --date <非交易日>` 要在取數前擋下並講明原因 —— 否則 `data_date_of` 會
        算出與週一相同的資料窗、當沖 fetch 週六回空,錯誤訊息把「你給的日子不是交易日」講成
        「FinMind 未更新?」。prod 不受影響(`expected_target_date` 只回交易日)。"""
        from copycat import trading_calendar
        from copycat.server import screen_engine

        monkeypatch.setattr(
            trading_calendar, "load_trading_calendar", lambda: trading_calendar.WEEKEND_ONLY
        )
        monkeypatch.setattr(cli, "_resolve_finmind_token", lambda: "tok")

        async def boom(self: object, target: object) -> list[object]:
            raise AssertionError("非交易日不得走到取數")

        monkeypatch.setattr(screen_engine.ScreenEngine, "compute", boom)
        assert cli.main(["screen", "--date", "2026-09-05"]) == 2  # 週六
        err = capsys.readouterr().err
        assert "2026-09-05" in err and "非交易日" in err

    def test_notify_test_without_webhook_returns_one(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr("copycat.notify.resolve_webhook_url", lambda: None)
        monkeypatch.chdir(tmp_path)  # 避免讀到 repo root 的 .env
        assert cli.main(["notify-test"]) == 1
