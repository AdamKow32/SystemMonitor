from src import DISC_info as dmod
import os
import json


def test_fmt_bytes_and_rate():
    assert dmod._fmt_bytes(0) == "0.0 B"
    assert dmod._fmt_rate(0) == "0.0 B/s"
    assert dmod._fmt_bytes(1024) == "1.0 KB"
    assert dmod._fmt_bytes(1024**2) == "1.0 MB"
    assert dmod._fmt_bytes(1024**3) == "1.0 GB"
    assert dmod._fmt_bytes(None) == "—"
    assert dmod._fmt_rate(None) == "—"


def test_parent_block_variants():
    assert dmod._parent_block("/dev/nvme0n1p3") == "nvme0n1"
    assert dmod._parent_block("/dev/mmcblk0p1") == "mmcblk0"
    assert dmod._parent_block("/dev/sda1") == "sda"
    assert dmod._parent_block("sdb") == "sdb"


def test_read_sys_model_hdd_ssd(monkeypatch, tmp_path):
    devname = "sda"
    base = tmp_path / "sys" / "block" / devname / "device"
    q = tmp_path / "sys" / "block" / devname / "queue"
    os.makedirs(base, exist_ok=True)
    os.makedirs(q, exist_ok=True)

    (base / "model").write_text("TEST_DISK\n", encoding="utf-8")
    (q / "rotational").write_text("1\n")

    real_exists = os.path.exists
    real_open = open

    def fake_exists(path):
        if path.startswith("/sys/block/"):
            rel = path[len("/sys"):]
            return (tmp_path / "sys" / rel.strip("/")).exists()
        return real_exists(path)

    def fake_open(path, *args, **kwargs):
        if path.startswith("/sys/block/"):
            rel = path[len("/sys"):]
            return real_open(tmp_path / "sys" / rel.strip("/"), *args, **kwargs)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(os.path, "exists", fake_exists)
    monkeypatch.setattr("builtins.open", fake_open)

    model, medium = dmod._read_sys_model(devname)
    assert model == "TEST_DISK"
    assert medium == "HDD"

    (q / "rotational").write_text("0\n")
    model2, medium2 = dmod._read_sys_model(devname)
    assert medium2 == "SSD"


def test_smart_read_smartctl_json(monkeypatch, tmp_path):
    sample_json = {
        "smart_status": {"passed": True},
        "temperature": {"current": 40}
    }
    called = {"cnt": 0}

    def fake_which(name):
        if name == "smartctl":
            return "/usr/bin/smartctl"
        return None

    def fake_check_output(args, text=True, stderr=None, timeout=None):
        called["cnt"] += 1
        assert "smartctl" in args[0]
        return json.dumps(sample_json)

    monkeypatch.setattr("shutil.which", fake_which)
    monkeypatch.setattr("subprocess.check_output", fake_check_output)

    health, temp = dmod._smart_read("sda")
    assert called["cnt"] >= 1
    assert health == "OK"
    assert temp == 40.0
