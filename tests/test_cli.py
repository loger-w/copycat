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

    def test_notify_test_without_webhook_returns_one(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr("copycat.notify.resolve_webhook_url", lambda: None)
        monkeypatch.chdir(tmp_path)  # 避免讀到 repo root 的 .env
        assert cli.main(["notify-test"]) == 1
