from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import check_feat_tags


def git(repo: Path, *args: str) -> str:
    res = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return res.stdout.strip()


def make_repo(tmp_path: Path) -> tuple[Path, str]:
    """回傳 (repo, start_sha) — start_sha 是初始 commit。"""
    git(tmp_path, "init")
    git(tmp_path, "config", "user.email", "t@t.t")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "base.txt").write_text("base")
    git(tmp_path, "add", "base.txt")
    git(tmp_path, "commit", "-m", "chore: init")
    return tmp_path, git(tmp_path, "rev-parse", "HEAD")


_N = 0


def commit(repo: Path, subject: str, body: str = "") -> None:
    global _N
    _N += 1
    f = repo / f"f{_N}.txt"
    f.write_text(str(_N))
    git(repo, "add", f.name)
    msg = subject if not body else f"{subject}\n\n{body}"
    git(repo, "commit", "-m", msg)


def write_state(repo: Path, start_sha: str, wave: bool = False) -> Path:
    d = repo / ".claude" / "feat" / "demo"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "state.json"
    p.write_text(
        json.dumps(
            {
                "slug": "demo",
                "start_sha": start_sha,
                "scope_overrides": {"goal_efficiency_mode": wave},
            }
        ),
        encoding="utf-8",
    )
    return p


class TestStandardMode:
    def test_red_then_green_passes(self, tmp_path):
        repo, start = make_repo(tmp_path)
        commit(repo, "🟢 test(x): failing test for SC-1 [red]")
        commit(repo, "🟢 feat(x): implement SC-1 [green]")
        ok, lines = check_feat_tags.check_standard(
            check_feat_tags.read_commits(repo, start)
        )
        assert ok, lines

    def test_green_without_red_fails(self, tmp_path):
        repo, start = make_repo(tmp_path)
        commit(repo, "🟢 feat(x): implement SC-1 [green]")
        ok, lines = check_feat_tags.check_standard(
            check_feat_tags.read_commits(repo, start)
        )
        assert not ok
        assert any("[green]" in ln for ln in lines)

    def test_green_before_red_fails(self, tmp_path):
        repo, start = make_repo(tmp_path)
        commit(repo, "🟢 feat(x): implement SC-1 [green]")
        commit(repo, "🟢 test(x): failing test for SC-1 [red]")
        ok, _ = check_feat_tags.check_standard(
            check_feat_tags.read_commits(repo, start)
        )
        assert not ok

    def test_two_greens_one_red_fails(self, tmp_path):
        repo, start = make_repo(tmp_path)
        commit(repo, "🟢 test(x): failing test [red]")
        commit(repo, "🟢 feat(x): impl SC-1 [green]")
        commit(repo, "🟢 feat(x): impl SC-2 [green]")
        ok, _ = check_feat_tags.check_standard(
            check_feat_tags.read_commits(repo, start)
        )
        assert not ok

    def test_design_amend_green_exempt(self, tmp_path):
        repo, start = make_repo(tmp_path)
        commit(
            repo,
            "🟢 feat(x): amend per real-env [green]",
            body="Phase 6 real-env finding",
        )
        ok, lines = check_feat_tags.check_standard(
            check_feat_tags.read_commits(repo, start)
        )
        assert ok, lines

    def test_lock_with_mutation_verified_passes(self, tmp_path):
        repo, start = make_repo(tmp_path)
        commit(repo, "🟢 test(x): failing [red]")
        commit(repo, "🟢 feat(x): impl [green]")
        commit(repo, "🟢 test(x): lock behavior [lock]", body="mutation-verified")
        ok, lines = check_feat_tags.check_standard(
            check_feat_tags.read_commits(repo, start)
        )
        assert ok, lines

    def test_lock_without_mutation_verified_fails(self, tmp_path):
        repo, start = make_repo(tmp_path)
        commit(repo, "🟢 test(x): failing [red]")
        commit(repo, "🟢 feat(x): impl [green]")
        commit(repo, "🟢 test(x): lock behavior [lock]")
        ok, lines = check_feat_tags.check_standard(
            check_feat_tags.read_commits(repo, start)
        )
        assert not ok
        assert any("mutation-verified" in ln for ln in lines)

    def test_no_tagged_commits_fails(self, tmp_path):
        repo, start = make_repo(tmp_path)
        commit(repo, "chore: something untagged")
        ok, _ = check_feat_tags.check_standard(
            check_feat_tags.read_commits(repo, start)
        )
        assert not ok


class TestWaveMode:
    def test_wave_commit_passes_and_maps_sc(self, tmp_path):
        repo, start = make_repo(tmp_path)
        commit(repo, "🟢 feat(x): batch [wave1]", body="covers SC-1, SC-2")
        ok, lines = check_feat_tags.check_wave(
            check_feat_tags.read_commits(repo, start)
        )
        assert ok, lines
        joined = "\n".join(lines)
        assert "SC-1" in joined and "SC-2" in joined

    def test_no_wave_commit_fails(self, tmp_path):
        repo, start = make_repo(tmp_path)
        commit(repo, "🟢 feat(x): impl [green]")
        ok, _ = check_feat_tags.check_wave(check_feat_tags.read_commits(repo, start))
        assert not ok


class TestMain:
    def test_main_reads_state_and_passes(self, tmp_path, capsys):
        repo, start = make_repo(tmp_path)
        commit(repo, "🟢 test(x): failing [red]")
        commit(repo, "🟢 feat(x): impl [green]")
        state = write_state(repo, start)
        rc = check_feat_tags.main(["--state", str(state), "--repo", str(repo)])
        assert rc == 0
        assert "PASS" in capsys.readouterr().out

    def test_main_wave_mode_from_state(self, tmp_path, capsys):
        repo, start = make_repo(tmp_path)
        commit(repo, "🟢 feat(x): batch [wave1]", body="covers SC-1")
        state = write_state(repo, start, wave=True)
        rc = check_feat_tags.main(["--state", str(state), "--repo", str(repo)])
        assert rc == 0
        assert "wave" in capsys.readouterr().out

    def test_main_fail_exit_1(self, tmp_path, capsys):
        repo, start = make_repo(tmp_path)
        commit(repo, "🟢 feat(x): impl [green]")
        state = write_state(repo, start)
        rc = check_feat_tags.main(["--state", str(state), "--repo", str(repo)])
        assert rc == 1
        assert "FAIL" in capsys.readouterr().out

    def test_main_missing_state_exit_2(self, tmp_path):
        rc = check_feat_tags.main(
            ["--state", str(tmp_path / "nope.json"), "--repo", str(tmp_path)]
        )
        assert rc == 2
