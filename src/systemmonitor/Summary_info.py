# Summary_Info.py
import os
import platform
import subprocess
import datetime
from PyQt6 import QtWidgets
import psutil

try:
    import pyamdgpuinfo as amd
except Exception:
    amd = None


def cpu_model_name() -> str:
    """Dokładna nazwa CPU z /proc/cpuinfo (pewniejsze niż platform.processor())."""
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if "model name" in line or "Model Name" in line:
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    # fallback
    import platform
    return platform.processor() or "Nieznany"
def read_first(path: str):
    """Bezpieczny odczyt zawartości pliku (trim)."""
    try:
        with open(path, "r") as f:
            s = f.read().strip()
            return s if s else None
    except Exception:
        return None

def uptime_str() -> str:
    """Czas działania systemu (HH:MM:SS lub z dniami)."""
    try:
        boot = psutil.boot_time()
        delta = datetime.datetime.now() - datetime.datetime.fromtimestamp(boot)
        return str(delta).split(".", 1)[0]
    except Exception:
        return "—"

def fmt_bytes(n: int | float) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    f = float(n)
    i = 0
    while f >= 1024 and i < len(units) - 1:
        f /= 1024.0
        i += 1
    return f"{f:.2f} {units[i]}"

def _motherboard_string() -> str:
    """
    Bez sudo: /sys/devices/virtual/dmi/id/* (jeśli kernel eksportuje DMI).
    """
    vendor = read_first("/sys/devices/virtual/dmi/id/board_vendor")
    name   = read_first("/sys/devices/virtual/dmi/id/board_name")
    ver    = read_first("/sys/devices/virtual/dmi/id/board_version")
    parts = [p for p in [vendor, name, ver] if p]
    return " ".join(parts) if parts else "Nieznana"


def _gpu_string() -> str:
    """
    Preferuj pyamdgpuinfo, w przeciwnym razie spróbuj lspci (pciutils).
    """
    # pyamdgpuinfo (AMD)
    if amd:
        try:
            g = amd.get_gpu(0)
            nm = g.get_name()
            if nm:
                return nm
        except Exception:
            pass
    # lspci
    try:
        out = subprocess.check_output(
            ["bash", "-lc", "lspci | grep -E 'VGA|3D' -m1 | cut -d: -f3-"],
            text=True
        )
        s = out.strip()
        if s:
            return s
    except Exception:
        pass
    return "Nieznana"


def _temperatures_summary() -> dict:
    """
    Zwraca słownik { 'cpu': 'xx.x °C' | '—', 'gpu': 'xx.x °C' | '—' }.
    psutil.sensors_temperatures() wymaga wsparcia w kernelu/sterownikach.
    Typowe nazwy: 'k10temp' (AMD CPU), 'amdgpu' (GPU AMD).
    """
    cpu_s = "—"
    gpu_s = "—"
    try:
        temps = psutil.sensors_temperatures()
        # CPU (AMD często: k10temp, label 'Tctl' lub 'Tdie')
        for key in ("k10temp", "coretemp", "cpu_thermal"):
            if key in temps and temps[key]:
                # preferuj Tctl/Tdie
                chosen = None
                for t in temps[key]:
                    if (t.label or "").lower() in ("tctl", "tdie"):
                        chosen = t
                        break
                if not chosen:
                    chosen = temps[key][0]
                if chosen and chosen.current is not None:
                    cpu_s = f"{chosen.current:.1f} °C"
                    break
        # GPU (AMD: 'amdgpu')
        if "amdgpu" in temps and temps["amdgpu"]:
            t = temps["amdgpu"][0]
            if t.current is not None:
                gpu_s = f"{t.current:.1f} °C"
    except Exception:
        pass
    return {"cpu": cpu_s, "gpu": gpu_s}


# ----------------- UI page -----------------

class SummaryPage(QtWidgets.QWidget):
    """
    Zakładka Summary: podstawowe informacje o systemie (bez sudo),
    z czytelnymi fallbackami i temperaturami (jeśli dostępne).
    """
    def __init__(self, parent=None):
        super().__init__(parent)

        v = QtWidgets.QVBoxLayout(self)

        box = QtWidgets.QGroupBox("Podstawowe informacje o systemie")
        v.addWidget(box)

        # USTAWIAMY layout TYLKO RAZ przez przypisanie do box
        form = QtWidgets.QFormLayout(box)

        uname = platform.uname()
        os_str = f"{uname.system} {uname.release}"
        # Kernel: utnij nr buildu po '#'
        kernel = uname.version.split("#")[0].strip()

        # CPU i RAM
        cpu_name = cpu_model_name()
        cores_ph = psutil.cpu_count(logical=False)
        cores_lg = psutil.cpu_count(logical=True)
        ram_total = fmt_bytes(psutil.virtual_memory().total)

        # GPU / MB
        mb = _motherboard_string()
        gpu = _gpu_string()

        # Temperatures (jeśli są)
        temps = _temperatures_summary()

        # Uptime
        up = uptime_str()

        # helper do dodawania wierszy
        def add_row(label: str, value: str):
            lab = QtWidgets.QLabel(label + ":")
            lab.setStyleSheet("color:#9aa3b2;")
            val = QtWidgets.QLabel(value or "—")
            val.setStyleSheet("font-family: monospace;")
            form.addRow(lab, val)

        add_row("Nazwa hosta", uname.node)
        add_row("System operacyjny", os_str)
        add_row("Architektura", uname.machine)
        add_row("Płyta główna", mb)
        add_row("Procesor", cpu_name)
        add_row("Rdzenie fizyczne", str(cores_ph))
        add_row("Wątki logiczne", str(cores_lg))
        add_row("Karta graficzna", gpu)
        add_row("Pamięć RAM", ram_total)
        add_row("Temperatura CPU", temps["cpu"])
        add_row("Temperatura GPU", temps["gpu"])
        add_row("Uptime", up)

        v.addStretch(1)
