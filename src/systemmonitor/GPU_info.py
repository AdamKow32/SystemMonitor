import os
import glob
import time
import json
import datetime
import shutil
import subprocess
from PyQt6 import QtWidgets, QtCore
from matplotlib.figure import Figure

# biblioteki do amd
try:
    import pyamdgpuinfo as amd
except Exception:
    amd = None

# biblioteka do nvidia
try:
    import pynvml
except Exception:
    pynvml = None

def read_first(path: str):
    """Bezpieczny odczyt zawartości pliku (trim)."""
    try:
        with open(path, "r") as f:
            s = f.read().strip()
            return s if s else None
    except Exception:
        return None

def read_first_int(path: str):
    try:
        s = read_first(path)
        return int(s) if s is not None else None
    except Exception:
        return None

def timestamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")



def _bytes_to_GB(n: int | float | None):
    if n is None:
        return None
    return float(n) / 1_000_000_000.0

# Sekcja AMD


def _detect_amd_cards():
    """Ścieżki karty AMD i temperatury"""

    cards = []
    for drm in sorted(glob.glob("/sys/class/drm/card[0-9]*")):
        ven = os.path.join(drm, "device", "vendor")
        if not os.path.exists(ven):
            continue
        v = read_first(ven)
        if not v or v.lower() != "0x1002":
            continue
        entry = {"drm": drm, "hwmon": None}
        hwmons = sorted(glob.glob(os.path.join(drm, "device", "hwmon", "hwmon*")))
        if hwmons:
            entry["hwmon"] = hwmons[0]
        cards.append(entry)
    return cards


def edit_AMD_name(drm_path: str) -> str | None:
    """Edytowanie nazwy - dla lepszej czytelności"""

    if not drm_path:
        return None
    uevent = read_first(os.path.join(drm_path, "device", "uevent"))
    slot = None
    if uevent:
        for line in uevent.splitlines():
            if line.startswith("PCI_SLOT_NAME="):
                slot = line.split("=", 1)[1].strip()
                break
    dev_hex = read_first(os.path.join(drm_path, "device", "device"))
    if slot or dev_hex:
        dev_hex = dev_hex or "0x????"
        slot = slot or "????:??:??.? "
        return f"AMD GPU (PCI {slot}, id {dev_hex})"
    return "AMD GPU"


class _AmdGpuReader:
    """
      Odczytywanie kluczowych metryk GPU:
      Zużyce w % pochodzące z katalogu /sys/class/drm/cardX/device/gpu_busy_percent
      vram w B pochodzące z mem_info_vram_total
      temp pochodzące z hwmon/temp1_input
      name z poprzedniej funkcji
    """

    def __init__(self):
        self.cards = _detect_amd_cards()
        self.name = None
        self.busy_path = None
        self.vram_used_path = None
        self.vram_total_path = None
        self.temp_path = None
        self.pci_slot = None  # do JSON

        if self.cards:
            drm = self.cards[0]["drm"]
            self.busy_path = os.path.join(drm, "device", "gpu_busy_percent")
            self.vram_used_path = os.path.join(drm, "device", "mem_info_vram_used")
            self.vram_total_path = os.path.join(drm, "device", "mem_info_vram_total")
            hw = self.cards[0]["hwmon"]
            if hw:
                p = os.path.join(hw, "temp1_input")
                if os.path.exists(p):
                    self.temp_path = p

            name_from_py = None
            if amd:
                try:
                    g = amd.get_gpu(0)
                    name_from_py = g.get_name()
                except Exception:
                    name_from_py = None
            self.name = name_from_py or edit_AMD_name(drm)

            uevent = read_first(os.path.join(drm, "device", "uevent"))
            if uevent:
                for line in uevent.splitlines():
                    if line.startswith("PCI_SLOT_NAME="):
                        self.pci_slot = line.split("=", 1)[1].strip()
                        break

    def read(self):
        """Zwraca dict: name, busy, temp, vram_used, vram_total, pci_slot"""
        d = {"name": self.name, "busy": None, "temp": None,
             "vram_used": None, "vram_total": None, "pci_slot": self.pci_slot}

        if self.busy_path and os.path.exists(self.busy_path):
            v = read_first_int(self.busy_path)
            if v is not None:
                d["busy"] = float(v)

        if self.vram_used_path and os.path.exists(self.vram_used_path):
            vu = read_first_int(self.vram_used_path)
            if vu is not None:
                d["vram_used"] = int(vu)

        if self.vram_total_path and os.path.exists(self.vram_total_path):
            vt = read_first_int(self.vram_total_path)
            if vt is not None:
                d["vram_total"] = int(vt)

        if self.temp_path and os.path.exists(self.temp_path):
            ti = read_first_int(self.temp_path)
            if ti is not None:
                d["temp"] = ti / 1000.0

        return d

#Sekcja NVIDIA
class _NvidiaGpuReader:
    """
    Czytniki dla Nvidia
    """
    def __init__(self):
        self.available = False
        self.use_nvml = False
        self.idx = 0

        if pynvml:
            try:
                pynvml.nvmlInit()
                n = pynvml.nvmlDeviceGetCount()
                if n > 0:
                    self.use_nvml = True
                    self.available = True

                    best_i, best_m = 0, -1
                    for i in range(n):
                        h = pynvml.nvmlDeviceGetHandleByIndex(i)
                        m = pynvml.nvmlDeviceGetMemoryInfo(h).total
                        if m > best_m:
                            best_m, best_i = m, i
                    self.idx = best_i
            except Exception:
                self.use_nvml = False

        if not self.available and shutil.which("nvidia-smi"):
            try:
                out = subprocess.check_output(
                    ["nvidia-smi","--query-gpu=memory.total","--format=csv,noheader,nounits"],
                    text=True, timeout=1.5
                ).strip().splitlines()
                if out:
                    self.available = True
                    vals = [int(x.strip()) for x in out]
                    self.idx = max(range(len(vals)), key=lambda i: vals[i])
            except Exception:
                self.available = False

    def _read_nvml(self):
        try:
            h = pynvml.nvmlDeviceGetHandleByIndex(self.idx)
            name = pynvml.nvmlDeviceGetName(h).decode("utf-8","ignore")
            util = float(pynvml.nvmlDeviceGetUtilizationRates(h).gpu)
            temp = float(pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU))
            mem  = pynvml.nvmlDeviceGetMemoryInfo(h)
            vtot = int(mem.total)
            vused= int(mem.used)
            pci  = pynvml.nvmlDeviceGetPciInfo(h).busId.decode("utf-8","ignore")
            if len(pci) >= 12:
                pci = pci[-12:]
            return {"name": name, "busy": util, "temp": temp,
                    "vram_used": vused, "vram_total": vtot, "pci_slot": pci}
        except Exception:
            return None

    def _read_smi(self):
        try:
            q = "name,utilization.gpu,temperature.gpu,memory.total,memory.used,pci.bus_id"
            out = subprocess.check_output(
                ["nvidia-smi", f"--query-gpu={q}", "--format=csv,noheader,nounits"],
                text=True, timeout=1.5
            ).strip().splitlines()
            if not out:
                return None
            parts = [p.strip() for p in out[self.idx].split(",")]
            if len(parts) < 6:
                return None
            name = parts[0]
            busy = float(parts[1])
            temp = float(parts[2])
            vtot = int(parts[3]) * 1024 * 1024
            vused= int(parts[4]) * 1024 * 1024
            pci  = parts[5]
            if len(pci) >= 12:
                pci = pci[-12:]
            return {"name": name, "busy": busy, "temp": temp,
                    "vram_used": vused, "vram_total": vtot, "pci_slot": pci}
        except Exception:
            return None

    def read(self):
        base = {"name": None, "busy": None, "temp": None,
                "vram_used": None, "vram_total": None, "pci_slot": None}
        if not self.available:
            return base
        if self.use_nvml:
            d = self._read_nvml()
            if d:
                return d
        d = self._read_smi()
        return d or base

# Wybór czytnika
class _GpuReader:
    """Jeden reader - próbuje najpierw AMD potem Nvidia"""
    def __init__(self):
        self.amd = _AmdGpuReader()
        self.nv  = _NvidiaGpuReader()
        self.last = {"name": None, "busy": None, "temp": None,
                     "vram_used": None, "vram_total": None, "pci_slot": None}
        self.last = self._read_once()

    @property
    def name(self):
        return self.last.get("name")

    @property
    def pci_slot(self):
        return self.last.get("pci_slot")

    def read(self):
        self.last = self._read_once()
        return self.last

    def _read_once(self):
        # AMD
        try:
            d = self.amd.read() or {}
            if d.get("name") or d.get("vram_total"):
                return d
        except Exception:
            pass
        # Nvidia
        try:
            d = self.nv.read() or {}
            if d.get("name") or d.get("vram_total") or d.get("busy") is not None:
                return d
        except Exception:
            pass
        return {"name": None, "busy": None, "temp": None,
                "vram_used": None, "vram_total": None, "pci_slot": None}


# Budowanie GUI

class GpuInfoPage(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.reader = _GpuReader()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick_live)
        self.timer.setInterval(1000)
        self.timer.start()

        self.is_recording = False
        self.samples = []
        self.t0 = None
        self.session_stamp = None

        v = QtWidgets.QVBoxLayout(self)

        g = QtWidgets.QGroupBox("GPU")
        v.addWidget(g)
        form = QtWidgets.QFormLayout(g)

        self.l_name = QtWidgets.QLabel(self.reader.name or "Nie wykryto GPU")
        self.l_busy = QtWidgets.QLabel("—")
        self.l_vram = QtWidgets.QLabel("—")
        self.l_temp = QtWidgets.QLabel("—")
        for w in (self.l_name, self.l_busy, self.l_vram, self.l_temp):
            w.setStyleSheet("font-family: monospace;")
        form.addRow("Urządzenie:", self.l_name)
        form.addRow("Obciążenie:", self.l_busy)
        form.addRow("VRAM (GB):", self.l_vram)
        form.addRow("Temperatura:", self.l_temp)

        btn_row = QtWidgets.QHBoxLayout()
        v.addLayout(btn_row)
        self.btn_start = QtWidgets.QPushButton("Rozpocznij rejestrowanie")
        self.btn_stop  = QtWidgets.QPushButton("Zatrzymaj i zapisz")
        self.btn_stop.setEnabled(False)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_stop)

        self.btn_start.clicked.connect(self._start_recording)
        self.btn_stop.clicked.connect(self._stop_and_autosave)

        self._tick_live()

    def _tick_live(self):
        try:
            d = self.reader.read()

            # Zużycie
            self.l_busy.setText(f"{d['busy']:.0f} %" if d["busy"] is not None else "—")

            # VRAM (w GB i w %)
            vt_gb = _bytes_to_GB(d["vram_total"]) if d["vram_total"] is not None else None
            vu_gb = _bytes_to_GB(d["vram_used"])  if d["vram_used"]  is not None else None

            if vu_gb is not None and vt_gb is not None and vt_gb > 0:
                pct = 100.0 * vu_gb / vt_gb
                self.l_vram.setText(f"{vu_gb:.2f} / {vt_gb:.2f} GB ({pct:.0f} %)")
            elif vt_gb is not None:
                self.l_vram.setText(f"— / {vt_gb:.2f} GB")
            else:
                self.l_vram.setText("—")

            # Temperatura
            self.l_temp.setText(f"{d['temp']:.1f} °C" if d["temp"] is not None else "—")

            # Zbieranie
            if self.is_recording:
                now = time.time()
                if self.t0 is None:
                    self.t0 = now
                sample = {
                    "t_rel_s": round(now - self.t0, 3),
                    "busy_pct": float(d["busy"]) if d["busy"] is not None else None,
                    "temp_C": float(d["temp"]) if d["temp"] is not None else None,
                    "vram_used_GB": float(vu_gb) if vu_gb is not None else None,
                    "vram_total_GB": float(vt_gb) if vt_gb is not None else None,
                }
                if sample["vram_used_GB"] is not None and sample["vram_total_GB"] not in (None, 0.0):
                    sample["vram_used_pct"] = 100.0 * sample["vram_used_GB"] / sample["vram_total_GB"]
                else:
                    sample["vram_used_pct"] = None
                self.samples.append(sample)
        except Exception:
            pass


    def _start_recording(self):
        self.is_recording = True
        self.samples.clear()
        self.t0 = None
        self.session_stamp = timestamp()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._tick_live()

    def _stop_and_autosave(self):
        self.is_recording = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

        if not self.samples:
            QtWidgets.QMessageBox.information(self, "GPU", "Brak zarejestrowanych danych.")
            return

        out_dir = os.path.abspath(os.path.join("..", "results"))
        os.makedirs(out_dir, exist_ok=True)
        stamp = self.session_stamp or timestamp()

        # JSON
        json_path = os.path.join(out_dir, f"gpu_recording_{stamp}.json")
        payload = {
            "device": self.reader.name,
            "pci_slot": self.reader.pci_slot,
            "recording_started_iso": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "samples": self.samples,
            "note_units": {
                "busy_pct": "%",
                "temp_C": "°C",
                "vram_used_GB": "GB (1 GB = 1e9 B)",
                "vram_total_GB": "GB (1 GB = 1e9 B)",
                "vram_used_pct": "%"
            }
        }
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "GPU", f"Nie udało się zapisać JSON:\n{e}")
            json_path = None

        # plik PNG
        png_path = os.path.join(out_dir, f"gpu_plots_{stamp}.png")
        try:
            self._render_and_save_plots(png_path)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "GPU", f"Nie udało się zapisać wykresów:\n{e}")
            png_path = None

        msg = "Zapisano wyniki:\n"
        if json_path:
            msg += f"• JSON: {json_path}\n"
        if png_path:
            msg += f"• PNG:  {png_path}\n"
        QtWidgets.QMessageBox.information(self, "GPU", msg.strip())

    def _render_and_save_plots(self, out_png_path: str):
        """Generuje figurę z Busy, Temp, VRAM% vs czas i zapisuje do PNG."""
        xs = [s["t_rel_s"] for s in self.samples]
        busy = [s["busy_pct"] for s in self.samples]
        temp = [s["temp_C"] for s in self.samples]
        vram_pct = [s.get("vram_used_pct") for s in self.samples]

        fig = Figure(figsize=(7.5, 6.0), tight_layout=True)
        ax1 = fig.add_subplot(311)
        ax2 = fig.add_subplot(312, sharex=ax1)
        ax3 = fig.add_subplot(313, sharex=ax1)

        ax1.set_title("GPU Busy [%]")
        ax1.set_ylabel("%")
        ax1.set_ylim(0, 100)
        ax1.grid(True, alpha=0.25)
        ax1.plot(xs, busy, label="Busy %")
        ax1.legend(loc="upper left")

        ax2.set_title("Temperatura [°C]")
        ax2.set_ylabel("°C")
        ax2.grid(True, alpha=0.25)
        ax2.plot(xs, temp, label="Temp", linestyle="-")
        ax2.legend(loc="upper left")

        ax3.set_title("VRAM użycie [%]")
        ax3.set_xlabel("Czas [s]")
        ax3.set_ylabel("%")
        ax3.set_ylim(0, 100)
        ax3.grid(True, alpha=0.25)
        ax3.plot(xs, vram_pct, label="VRAM %", linestyle="-")
        ax3.legend(loc="upper left")

        fig.savefig(out_png_path, dpi=150)
