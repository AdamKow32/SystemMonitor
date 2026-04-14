# tests/test_ram_info.py
import types
import pytest
import csv, time
from PyQt6 import QtWidgets


class _vmem:
    def __init__(self, used_gb, total_gb, available_gb, percent):
        self.used = used_gb * (1024**3)
        self.total = total_gb * (1024**3)
        self.available = available_gb * (1024**3)
        self.percent = percent

class _swap:
    def __init__(self, used_gb, total_gb, percent):
        self.used = used_gb * (1024**3)
        self.total = total_gb * (1024**3)
        self.percent = percent
import src.RAM_info as ram_mod


@pytest.fixture(scope="session")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    return app


def _vmem(used_gb, total_gb, available_gb, percent):
    o = types.SimpleNamespace()
    o.used = int(used_gb * (1024**3))
    o.total = int(total_gb * (1024**3))
    o.available = int(available_gb * (1024**3))
    o.percent = float(percent)
    return o


def _swap(used_gb, total_gb, percent):
    o = types.SimpleNamespace()
    o.used = int(used_gb * (1024**3))
    o.total = int(total_gb * (1024**3))
    o.percent = float(percent)
    return o


def test_tick_updates_labels_and_samples(qapp, monkeypatch):
    monkeypatch.setattr(ram_mod.psutil, "virtual_memory",
                        lambda: _vmem(used_gb=6.0, total_gb=16.0, available_gb=9.5, percent=37.5))
    monkeypatch.setattr(ram_mod.psutil, "swap_memory",
                        lambda: _swap(used_gb=0.5, total_gb=2.0, percent=25.0))

    w = ram_mod.RamInfoPage()
    monkeypatch.setattr(time, "time", lambda: 1_000_000.0)
    w._start_rec()
    w._tick()

    assert "6.00 / 16.00 GB (38%)" in w.l_ram.text()
    assert "0.50 / 2.00 GB (25%)" in w.l_swap.text()
    assert "9.50 GB wolne" in w.l_cache.text()

    assert len(w.samples) == 1
    row = w.samples[0]
    assert set(row.keys()) == {
        "t_rel_s", "ram_used_GB", "ram_total_GB", "ram_used_pct",
        "swap_used_GB", "swap_total_GB", "swap_used_pct", "available_GB"
    }
    assert row["ram_used_GB"] == pytest.approx(6.000, rel=0, abs=1e-3)
    assert row["ram_total_GB"] == pytest.approx(16.000, rel=0, abs=1e-3)
    assert row["available_GB"] == pytest.approx(9.500, rel=0, abs=1e-3)
    assert row["swap_used_GB"] == pytest.approx(0.500, rel=0, abs=1e-3)
    assert row["swap_total_GB"] == pytest.approx(2.000, rel=0, abs=1e-3)
    assert row["ram_used_pct"] == pytest.approx(37.5, rel=0, abs=0.6)


def test_tick_handles_no_swap(qapp, monkeypatch):
    monkeypatch.setattr(ram_mod.psutil, "virtual_memory",
                        lambda: _vmem(used_gb=4.0, total_gb=8.0, available_gb=3.5, percent=50.0))
    monkeypatch.setattr(ram_mod.psutil, "swap_memory",
                        lambda: _swap(used_gb=0.0, total_gb=0.0, percent=0.0))

    w = ram_mod.RamInfoPage()
    w._tick()

    assert w.l_swap.text().startswith("—")
    w._start_rec()
    w._tick()
    assert w.samples[-1]["swap_total_GB"] == 0.0
    assert w.samples[-1]["swap_used_pct"] is None


def test_csv_save(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning",     lambda *a, **k: None)

    monkeypatch.setattr(ram_mod.psutil, "virtual_memory",
                        lambda: _vmem(used_gb=1.0, total_gb=2.0, available_gb=1.0, percent=50.0))
    monkeypatch.setattr(ram_mod.psutil, "swap_memory",
                        lambda: _swap(used_gb=0.2, total_gb=1.0, percent=20.0))

    t = [1_000_000.0]
    monkeypatch.setattr(time, "time", lambda: t[0])

    monkeypatch.chdir(tmp_path)

    w = ram_mod.RamInfoPage()
    try:
        w.timer.stop()
    except Exception:
        pass

    w._start_rec()
    w._tick()
    t[0] += 1.0
    w._tick()
    w._stop_rec()

    results_dir = tmp_path / "results"
    files = list(results_dir.glob("ram_recording_*.csv"))
    assert files, "CSV nie został zapisany"
    p = files[0]

    with open(p, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) >= 2
    cols = rows[0].keys()
    for key in ("ram_used_GB", "ram_total_GB", "swap_used_GB", "swap_total_GB", "available_GB"):
        assert key in cols
