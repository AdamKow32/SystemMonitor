# tests/test_disc_info.py
import os, types, builtins
from src import DISC_info as dmod


def test_disk_tables(monkeypatch, tmp_path, qapp):
    def exists(p): return "size" in p or "device/model" in p or "rotational" in p
    monkeypatch.setattr(dmod.os.path, "exists", exists)
    def open_read(path, *a, **k):
        if path.endswith("/size"): return open(os.path.join(tmp_path,"_size"), "w+")
        return builtins.open(path, *a, **k)
    p = tmp_path / "_size"; p.write_text("1048576")
    def _open2(path, mode="r", *a, **k):
        if path.endswith("/device/model"): return builtins.open(p, mode, *a, **k)
        if path.endswith("/queue/rotational"):
            q = tmp_path/"_rot"; q.write_text("0")
            return builtins.open(q, mode, *a, **k)
        return builtins.open(path, mode, *a, **k)
    monkeypatch.setattr(dmod, "open", _open2, raising=False)

    part = types.SimpleNamespace(device="/dev/sda1", mountpoint="/", fstype="ext4")
    monkeypatch.setattr(dmod.psutil, "disk_partitions", lambda all=False: [part])
    usage = types.SimpleNamespace(percent=33.3, used=1000, free=2000, total=3000)
    monkeypatch.setattr(dmod.psutil, "disk_usage", lambda mnt: usage)
    cnt = types.SimpleNamespace(read_bytes=10000, write_bytes=20000)
    monkeypatch.setattr(dmod.psutil, "disk_io_counters", lambda perdisk=True: {"sda": cnt})

    w = dmod.DiskInfoPage()
    w._tick()
    assert w.tbl_dev.rowCount() >= 1
    assert w.tbl_part.rowCount() >= 1
