import os
import re
import time
import shutil
import subprocess
import psutil
import glob
import json
from PyQt6 import QtWidgets, QtCore

def _fmt_bytes(n):
    if n is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
        n /= 1024.0

def _fmt_rate(bps):
    if bps is None:
        return "—"
    return _fmt_bytes(bps) + "/s"

def _parent_block(devpath: str) -> str:
    """
        Zwraca nazwę urządzenia
        /dev/nvme0n1p3 - nvme0n1
        /dev/sda1      - sda
        /dev/mmcblk0p1 - mmcblk0
    """

    if not devpath.startswith("/dev/"):
        return os.path.basename(devpath)
    base = os.path.basename(devpath)

    m = re.match(r"^(nvme\d+n\d+)p\d+$", base)
    if m:
        return m.group(1)

    m = re.match(r"^(mmcblk\d+)p\d+$", base)
    if m:
        return m.group(1)

    m = re.match(r"^([a-zA-Z]+)\d+$", base)
    if m:
        return m.group(1)
    return base

def _read_sys_model(devname: str) -> tuple[str|None, str|None]:
    """Próbuje odczytać model urządzenia oraz jego typ (HDD, SSD) z katalogu /sys/block/<dev>/device"""

    sys = f"/sys/block/{devname}"
    model = None
    if os.path.exists(f"{sys}/device/model"):
        try:
            with open(f"{sys}/device/model","r",encoding="utf-8",errors="ignore") as f:
                model = f.read().strip()
        except Exception:
            pass

    medium = None
    rot_path = f"{sys}/queue/rotational"
    if os.path.exists(rot_path):
        try:
            with open(rot_path,"r") as f:
                rotational = f.read().strip() == "1"
            medium = "HDD" if rotational else "SSD"
        except Exception:
            pass

    if devname.startswith("nvme"):
        try:
            with open(f"{sys}/device/model","r",encoding="utf-8",errors="ignore") as f:
                nvme_m = f.read().strip()
            if nvme_m:
                model = nvme_m
        except Exception:
            pass
    return (model, medium)

def _smartctl_available() -> bool:
    return shutil.which("smartctl") is not None

def _smart_read(devname: str) -> tuple[str|None, float|None]:
    """
    Zwraca "zdrowie" dysku, temperaturę dla /dev/<devnmame> - działa poprawnie dla NVME i Sata, ale USB  może nie działać
    """
    devpath = f"/dev/{devname}"

    def _parse_smartctl_json(txt: str) -> tuple[str|None, float|None]:
        health = None
        tempC = None
        try:
            data = json.loads(txt)
        except Exception:
            return (None, None)
        # zdrowie
        st = data.get("smart_status") or {}
        passed = st.get("passed")
        if passed is True:  health = "OK"
        if passed is False: health = "FAIL"
        # temperatura
        try:
            v = data["temperature"]["current"]
            if isinstance(v, (int, float)):
                tempC = float(v)
        except Exception:
            # SATA
            ata = (data.get("ata_smart_attributes") or {}).get("table") or []
            for row in ata:
                if str(row.get("id")) in ("190", "194"):
                    raw = (row.get("raw") or {}).get("value")
                    try:
                        tempC = float(raw.split()[0]) if isinstance(raw, str) else float(raw)
                    except Exception:
                        pass
                    break
        return (health, tempC)

    if shutil.which("smartctl"):
        for args in (
            ["sudo","-n","smartctl","-a","-j",devpath],  # bez pytania o hasło
            ["smartctl","-a","-j",devpath],             # bez sudo
        ):
            try:
                out = subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL, timeout=2.0)
                h, t = _parse_smartctl_json(out)
                if h or t is not None:
                    return (h, t)
            except Exception:
                pass

    if devname.startswith("nvme") and shutil.which("nvme"):
        for args in (
            ["sudo","-n","nvme","smart-log",devpath,"-o","json"],
            ["nvme","smart-log",devpath,"-o","json"],
        ):
            try:
                out = subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL, timeout=2.0)
                data = json.loads(out)
                v = data.get("temperature") or data.get("composite_temperature")
                tempC = None
                if isinstance(v, (int, float)):
                    if v > 2000:
                        tempC = (v / 10.0) - 273.15
                    elif v > 200:
                        tempC = v - 273.15
                    else:
                        tempC = float(v)
                        # Brak błędów = OK "zdrowie"
                return ("OK", tempC)
            except Exception:
                pass

    if devname.startswith("nvme"):
        m = re.match(r"^(nvme\d+)", devname)
        if m:
            ctrl = m.group(1)
            for p in sorted(glob.glob(f"/sys/class/nvme/{ctrl}/device/hwmon/hwmon*/temp1_input")):
                try:
                    with open(p, "r") as f:
                        t_mC = int(f.read().strip())
                    return ("OK", t_mC / 1000.0)
                except Exception:
                    pass

    blk_hwmon = f"/sys/block/{devname}/device/hwmon"
    if os.path.isdir(blk_hwmon):
        for p in sorted(glob.glob(f"{blk_hwmon}/hwmon*/temp1_input")):
            try:
                with open(p, "r") as f:
                    t_mC = int(f.read().strip())
                return ("OK", t_mC / 1000.0)
            except Exception:
                pass

    return (None, None)


class DiskInfoPage(QtWidgets.QWidget):
    """
    Zakładka dyski
    Tabela urządzeń
    Tabela partycji
    Zmienne live + prędkości odczytu/zapisu na urządzenie
    """
    def __init__(self, parent=None):
        super().__init__(parent)

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)

        self.prev_io = {}

        layout = QtWidgets.QVBoxLayout(self)

        gb_dev = QtWidgets.QGroupBox("Urządzenia blokowe")
        layout.addWidget(gb_dev)
        v1 = QtWidgets.QVBoxLayout(gb_dev)

        self.tbl_dev = QtWidgets.QTableWidget(0, 7, self)
        self.tbl_dev.setHorizontalHeaderLabels([
            "Urządzenie", "Model", "Typ", "Rozmiar", "Temp [°C]", "Health", "R/W [MB/s]"
        ,])
        self.tbl_dev.horizontalHeader().setStretchLastSection(True)
        self.tbl_dev.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        v1.addWidget(self.tbl_dev)

        gb_part = QtWidgets.QGroupBox("Partycje i punkty montowania")
        layout.addWidget(gb_part)
        v2 = QtWidgets.QVBoxLayout(gb_part)

        self.tbl_part = QtWidgets.QTableWidget(0, 7, self)
        self.tbl_part.setHorizontalHeaderLabels([
            "Urządzenie", "Punkt mont.", "FS", "Użycie [%]", "Zajęte", "Wolne", "Łącznie"
        ])
        self.tbl_part.horizontalHeader().setStretchLastSection(True)
        self.tbl_part.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        v2.addWidget(self.tbl_part)

        self._refresh_static()
        self.timer.start()
        self._tick()

    def _refresh_static(self):
        devs = {}
        for p in psutil.disk_partitions(all=False):
            parent = _parent_block(p.device)
            if parent not in devs:
                try:
                    size = None
                    sz_path = f"/sys/block/{parent}/size"
                    if os.path.exists(sz_path):
                        with open(sz_path,"r") as f:
                            sectors = int(f.read().strip())
                        size = sectors * 512
                    devs[parent] = {"size": size}
                except Exception:
                    devs[parent] = {"size": None}

        rows = []
        for dev in sorted(devs):
            model, medium = _read_sys_model(dev)
            health, tempC = _smart_read(dev)
            rows.append((dev, model or "—", medium or "—", devs[dev]["size"], tempC, health or "—"))

        self.tbl_dev.setRowCount(len(rows))
        for r, (dev, model, medium, size, tempC, health) in enumerate(rows):
            self.tbl_dev.setItem(r, 0, QtWidgets.QTableWidgetItem(dev))
            self.tbl_dev.setItem(r, 1, QtWidgets.QTableWidgetItem(model))
            self.tbl_dev.setItem(r, 2, QtWidgets.QTableWidgetItem(medium))
            self.tbl_dev.setItem(r, 3, QtWidgets.QTableWidgetItem(_fmt_bytes(size) if size else "—"))
            self.tbl_dev.setItem(r, 4, QtWidgets.QTableWidgetItem(f"{tempC:.0f}" if tempC is not None else "—"))
            self.tbl_dev.setItem(r, 5, QtWidgets.QTableWidgetItem(health))
            self.tbl_dev.setItem(r, 6, QtWidgets.QTableWidgetItem("—"))

        parts = []
        for p in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(p.mountpoint)
            except Exception:
                continue
            parts.append((
                _parent_block(p.device),
                p.mountpoint,
                p.fstype or "—",
                usage.percent,
                usage.used,
                usage.free,
                usage.total
            ))
        self.tbl_part.setRowCount(len(parts))
        for r, (dev, mnt, fs, pct, used, free, total) in enumerate(parts):
            self.tbl_part.setItem(r, 0, QtWidgets.QTableWidgetItem(dev))
            self.tbl_part.setItem(r, 1, QtWidgets.QTableWidgetItem(mnt))
            self.tbl_part.setItem(r, 2, QtWidgets.QTableWidgetItem(fs))
            self.tbl_part.setItem(r, 3, QtWidgets.QTableWidgetItem(f"{pct:.0f}"))
            self.tbl_part.setItem(r, 4, QtWidgets.QTableWidgetItem(_fmt_bytes(used)))
            self.tbl_part.setItem(r, 5, QtWidgets.QTableWidgetItem(_fmt_bytes(free)))
            self.tbl_part.setItem(r, 6, QtWidgets.QTableWidgetItem(_fmt_bytes(total)))

        self.prev_io = {}
        now = time.time()
        io = psutil.disk_io_counters(perdisk=True)
        for dev, cnt in io.items():
            base = dev
            self.prev_io[base] = (cnt.read_bytes, cnt.write_bytes, now)


    def _tick(self):
        now = time.time()
        io = psutil.disk_io_counters(perdisk=True)
        rates = {}
        for dev, cnt in io.items():
            base = dev
            rb, wb = cnt.read_bytes, cnt.write_bytes
            if base in self.prev_io:
                prb, pwb, pts = self.prev_io[base]
                dt = max(1e-6, now - pts)
                r_rate = (rb - prb) / dt
                w_rate = (wb - pwb) / dt
                rates[base] = f"{_fmt_rate(r_rate)} / {_fmt_rate(w_rate)}"
            self.prev_io[base] = (rb, wb, now)

        for r in range(self.tbl_dev.rowCount()):
            dev_item = self.tbl_dev.item(r, 0)
            if not dev_item:
                continue
            dev = dev_item.text()
            val = rates.get(dev) or "—"
            self.tbl_dev.setItem(r, 6, QtWidgets.QTableWidgetItem(val))
