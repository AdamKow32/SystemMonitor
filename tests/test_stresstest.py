# tests/test_stresstest.py
import os, json, time, types
from src import stresstest as st


class FakeProc:
    def __init__(self, *a, **k): self._alive = True
    def start(self): self._alive = True
    def terminate(self): self._alive = False
    def is_alive(self): return self._alive

class FakeEvent:
    def __init__(self): self._set=False
    def set(self): self._set=True
    def is_set(self): return self._set

def test_cpu_stress_flow(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(st.multiprocessing, "Process", FakeProc)
    monkeypatch.setattr(st.multiprocessing, "Event", FakeEvent)
    monkeypatch.setattr(st.psutil, "cpu_count", lambda logical=True: 2)
    monkeypatch.setattr(st.psutil, "cpu_percent", lambda interval=None: 50.0)
    monkeypatch.setattr(st.psutil, "cpu_freq", lambda: types.SimpleNamespace(current=3600.0))
    T = types.SimpleNamespace(current=70.0)
    monkeypatch.setattr(st.psutil, "sensors_temperatures", lambda: {"k10temp":[T]})

    t=[1_000_000.0]
    monkeypatch.setattr(time, "time", lambda: t[0])

    os.chdir(tmp_path)
    w = st.StressTestPage()
    w.duration_input.setValue(2)

    w._start_test()
    for _ in range(3):
        t[0]+=1
        w._tick()

    w._stop_test()

    reports = list((tmp_path/"stress_reports").glob("stress_report_*.json"))
    assert reports
    data = json.load(open(reports[0]))
    assert data["results"]["avg_cpu_usage"] >= 0.0

def test_ram_stress_controls(qapp, monkeypatch):
    w = st.StressTestPage()
    w.ram_gb_input.setValue(0.1)
    w.ram_chunk_mb_input.setValue(10)
    w._start_ram_test()
    w._stop_ram_test()
    assert "Zwolniono" in w.ram_status.text()
