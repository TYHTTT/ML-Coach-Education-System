from pathlib import Path

import pytest

from app.cli import seed_curriculum as cli


@pytest.mark.parametrize("custom_seed", [None, "custom.json"])
def test_cli_preserves_default_four_course_sync_and_custom_seeds(monkeypatch, capsys, custom_seed):
    calls = []
    repository = object()
    monkeypatch.setattr(cli, "LearningRepository", lambda url: repository)

    def seed(value, paths):
        assert value is repository
        calls.append(paths)
        return {"machine_learning": 30, "advanced_mathematics": 23, "linear_algebra": 10, "probability_statistics": 11}

    monkeypatch.setattr(cli, "seed_curriculum", seed)
    args = ["--database-url", "postgresql://test"]
    if custom_seed:
        args.extend(["--seed", custom_seed])
    assert cli.main(args) == 0
    assert calls == [[Path(custom_seed)] if custom_seed else None]
    assert "linear_algebra 10" in capsys.readouterr().out
