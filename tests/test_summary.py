# tests/test_summary_info.py
import types
from src import Summary_info as smod


def test_summary_basic(qapp, monkeypatch):
    monkeypatch.setattr(smod, "cpu_model_name", lambda: "AMD Ryzen")
    monkeypatch.setattr(smod, "fmt_bytes", lambda n: "32.0 GB")
    monkeypatch.setattr(smod, "uptime_str", lambda: "1d 2h 3m")
    monkeypatch.setattr(smod, "read_first", lambda p: "X")

    U = types.SimpleNamespace(system="Linux", release="6.10", version="#1 SMP", machine="x86_64", node="host")
    monkeypatch.setattr(smod.platform, "uname", lambda: U)

    Tcpu = types.SimpleNamespace(current=55.0, label="Tdie")
    Tgpu = types.SimpleNamespace(current=60.0, label=None)
    monkeypatch.setattr(smod.psutil, "sensors_temperatures", lambda: {"k10temp":[Tcpu], "amdgpu":[Tgpu]})

    w = smod.SummaryPage()
    assert isinstance(w, smod.QtWidgets.QWidget)
