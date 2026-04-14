# tests/test_cpu_info.py
import types
import pytest
import csv
import os
import glob
from src import CPU_info as cpu_mod
from PyQt6 import QtWidgets

class FakeTimes:
    __slots__ = ("user","system","idle","iowait")
    def __init__(self, u,s,i,iw=0.0): self.user=u; self.system=s; self.idle=i; self.iowait=iw
    def __iter__(self): return iter((self.user,self.system,self.idle,self.iowait))

def test_cpu_usage_math(qapp, monkeypatch):
    monkeypatch.setattr(cpu_mod.psutil, "cpu_times",
                        lambda percpu=True: [FakeTimes(10, 10, 80, 0.0)])
    w = cpu_mod.CpuInfoPage()

    monkeypatch.setattr(cpu_mod.psutil, "cpu_times",
                        lambda percpu=True: [FakeTimes(15, 15, 90, 0.0)])

    w._tick()
    val = float(w.instant_lbl.text().strip("%"))
    assert 45.0 <= val <= 55.0

def test_cpu_temp_avg_paths(qapp, monkeypatch):
    T = types.SimpleNamespace(current=65.3, label="Tdie")
    monkeypatch.setattr(cpu_mod.psutil, "sensors_temperatures",
                        lambda: {"k10temp":[T]})
    w = cpu_mod.CpuInfoPage()
    t = w._cpu_temp_avg()
    assert t == pytest.approx(65.3, abs=0.1)

def test_cpu_csv_save(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: None)

    monkeypatch.chdir(tmp_path)

    page = cpu_mod.CpuInfoPage()
    try:
        page._timer.stop()
    except Exception:
        pass

    page.is_recording = False
    page.samples = [
        {
            "t_rel_s": 0.0,
            "cpu_total_pct": 12.3,
            "cpu_freq_MHz": 3456.0,
            "cpu_per_core_pct": "10.0;15.0",
            "cpu_temp_C": 44.8,
        },
        {
            "t_rel_s": 1.0,
            "cpu_total_pct": 18.7,
            "cpu_freq_MHz": 3500.0,
            "cpu_per_core_pct": "12.0;25.0",
            "cpu_temp_C": 45.0,
        },
    ]

    page._stop_rec()

    files = glob.glob(os.path.join("results", "cpu_recording_*.csv"))
    assert files, "nie znaleziono pliku CSV w ./results/"
    csv_path = files[0]

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2
    expected_cols = set(page.samples[0].keys())
    assert expected_cols.issubset(rows[0].keys())
    assert rows[0]["cpu_total_pct"] in ("12.3", "12.30")

    files = list((tmp_path/"results").glob("cpu_recording_*.csv"))
    assert files
    rows = list(csv.DictReader(open(files[0], encoding="utf-8")))
    assert rows and "cpu_total_pct" in rows[0] and "cpu_temp_C" in rows[0]
