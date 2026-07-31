"""執行中 server 的建置身分(git sha + 啟動時刻)。

**存在理由**(docs/next-time.md 2026-07-29 紅標):stock-ui-fixes 那輪「K 線沒有資料」的
根因是 :8721 跑的是舊版 build(`openapi.json` 根本沒有 `/api/stock/bars` 這條 route),
但前端與人都無從辨識執行中的 server 是哪一版 —— 花了一輪才發現「不是 code 沒寫,是
server 沒重啟」。有了 sha + 啟動時刻,`git log <sha>..HEAD -- copycat/` 一句話就答完
「這台是不是舊的」。

**降級紀律**:git 不可得(未裝 / 非 repo / 打包部署)一律回 `None`,絕不讓 server 起不來。
這是觀測性資訊,不是正確性依賴 —— 但半殘狀態(拿得到 sha、問不到 dirty)必須誠實回
`None` 而不是預設 `False`,假的「乾淨」比沒有更糟。
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# copycat/server/build_info.py → repo root。刻意不與 `live/tc4.py` 等處的 TCPY 路徑運算式
# 共用常數(那條收斂記在 next-time.md,收斂條件未達)。
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_GIT_TIMEOUT_SECS = 3.0


@dataclass(frozen=True)
class BuildInfo:
    """`git_dirty` 三態:True/False = 問到了;None = 問不到(git 不可得)。"""

    git_sha: str | None
    git_dirty: bool | None
    started_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "git_sha": self.git_sha,
            "git_dirty": self.git_dirty,
            "started_at": self.started_at,
        }

    def banner(self) -> str:
        sha = self.git_sha or "unknown"
        dirty = " +dirty" if self.git_dirty else ""
        return f"copycat server build {sha}{dirty} started_at={self.started_at}"


def _git(*args: str) -> str | None:
    """跑一條 git,任何取不到的情況一律 `None`。

    catch 的處理邏輯就是降級本身(鐵則 E:catch 後要有具體處理)—— 呼叫端靠 `None`
    區分「問不到」與「問到了空字串」(後者 = 工作區乾淨)。
    """
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def capture(*, now: datetime | None = None) -> BuildInfo:
    """在 lifespan 啟動時呼叫一次;之後整個行程回同一份。

    刻意**不**每次請求重算:sha 是「這個行程跑的是哪一版 code」,啟動後才 commit 不該
    讓它的答案跟著跑 —— 那正好會抹掉這個 endpoint 唯一要偵測的落差。
    """
    stamp = (now or datetime.now()).isoformat(timespec="seconds")
    sha = _git("rev-parse", "--short", "HEAD")
    dirty: bool | None = None
    if sha is not None:
        status = _git("status", "--porcelain")
        dirty = None if status is None else bool(status)
    return BuildInfo(git_sha=sha, git_dirty=dirty, started_at=stamp)
