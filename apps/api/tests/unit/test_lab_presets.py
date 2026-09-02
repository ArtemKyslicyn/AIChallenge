from pathlib import Path

from app.adapters.lab.presets import load_lab_presets


def test_load_repo_lab_presets():
    lab_dir = Path(__file__).resolve().parents[4] / "configs" / "lab"
    presets = load_lab_presets(lab_dir)
    assert len(presets) >= 3
    ids = {p.id for p in presets}
    assert "discount-math" in ids
    discount = next(p for p in presets if p.id == "discount-math")
    assert "1440" in discount.golden_answer
    assert discount.task.strip()


def test_missing_lab_dir_returns_empty(tmp_path: Path):
    assert load_lab_presets(tmp_path / "nope") == []
