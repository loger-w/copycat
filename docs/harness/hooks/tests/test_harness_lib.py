from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import harness_lib


def make_state(**overrides) -> dict:
    state = {
        "slug": "demo-feature",
        "branch": "feat/demo-feature",
        "current_phase": 3,
        "completed_phases": [-1, 0, 1, 2],
        "last_updated": "2026-07-06T10:00:00+08:00",
        "paused": None,
    }
    state.update(overrides)
    return state


def write_state(root: Path, slug: str, state: dict) -> Path:
    d = root / ".claude" / "feat" / slug
    d.mkdir(parents=True)
    p = d / "state.json"
    p.write_text(json.dumps(state), encoding="utf-8")
    return p


class TestIsActive:
    def test_active_state(self):
        assert harness_lib.is_active(make_state()) is True

    def test_paused_not_active(self):
        assert harness_lib.is_active(make_state(paused="user request")) is False

    def test_merged_not_active(self):
        assert harness_lib.is_active(make_state(final_merge_sha="abc123")) is False

    def test_archived_not_active(self):
        assert harness_lib.is_active(make_state(archived="2026-07-06 盤點補收尾")) is False

    def test_completed_85_not_active(self):
        assert harness_lib.is_active(
            make_state(completed_phases=[-1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 8.5])
        ) is False


class TestFindActiveFeature:
    def test_no_feat_dir(self, tmp_path):
        assert harness_lib.find_active_feature(str(tmp_path)) is None

    def test_single_active(self, tmp_path):
        write_state(tmp_path, "demo-feature", make_state())
        found = harness_lib.find_active_feature(str(tmp_path))
        assert found is not None
        _, state = found
        assert state["slug"] == "demo-feature"

    def test_picks_latest_of_multiple(self, tmp_path):
        write_state(tmp_path, "older", make_state(slug="older", last_updated="2026-07-01T10:00:00+08:00"))
        write_state(tmp_path, "newer", make_state(slug="newer", last_updated="2026-07-05T10:00:00+08:00"))
        _, state = harness_lib.find_active_feature(str(tmp_path))
        assert state["slug"] == "newer"

    def test_skips_completed(self, tmp_path):
        write_state(tmp_path, "done", make_state(slug="done", final_merge_sha="abc"))
        assert harness_lib.find_active_feature(str(tmp_path)) is None

    def test_malformed_json_skipped(self, tmp_path):
        d = tmp_path / ".claude" / "feat" / "broken"
        d.mkdir(parents=True)
        (d / "state.json").write_text("{not json", encoding="utf-8")
        assert harness_lib.find_active_feature(str(tmp_path)) is None


class TestGateForPhase:
    def test_known_phase(self):
        assert "TDD" in harness_lib.gate_for_phase(3.0)

    def test_unknown_phase(self):
        assert "未知" in harness_lib.gate_for_phase(99.0)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def make_repo(tmp_path: Path) -> Path:
    git(tmp_path, "init")
    git(tmp_path, "config", "user.email", "t@t.t")
    git(tmp_path, "config", "user.name", "t")
    return tmp_path


class TestStateIsLagging:
    def test_head_newer_and_state_untouched_is_lagging(self, tmp_path):
        repo = make_repo(tmp_path)
        state_path = write_state(repo, "demo-feature", make_state(last_updated="2020-01-01T00:00:00+08:00"))
        (repo / "code.py").write_text("x = 1")
        git(repo, "add", "code.py")
        git(repo, "commit", "-m", "feat: code only")
        state = harness_lib.load_state(state_path)
        assert harness_lib.state_is_lagging(str(repo), state_path, state) is True

    def test_head_commit_touching_state_not_lagging(self, tmp_path):
        repo = make_repo(tmp_path)
        state_path = write_state(repo, "demo-feature", make_state(last_updated="2020-01-01T00:00:00+08:00"))
        git(repo, "add", ".claude/feat/demo-feature/state.json")
        git(repo, "commit", "-m", "chore: sync state")
        state = harness_lib.load_state(state_path)
        assert harness_lib.state_is_lagging(str(repo), state_path, state) is False

    def test_state_fresher_than_head_not_lagging(self, tmp_path):
        repo = make_repo(tmp_path)
        (repo / "code.py").write_text("x = 1")
        git(repo, "add", "code.py")
        git(repo, "commit", "-m", "feat: code")
        state_path = write_state(repo, "demo-feature", make_state(last_updated="2099-01-01T00:00:00+08:00"))
        state = harness_lib.load_state(state_path)
        assert harness_lib.state_is_lagging(str(repo), state_path, state) is False

    def test_not_a_repo_not_lagging(self, tmp_path):
        state_path = write_state(tmp_path, "demo-feature", make_state())
        state = harness_lib.load_state(state_path)
        assert harness_lib.state_is_lagging(str(tmp_path), state_path, state) is False
