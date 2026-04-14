import csv
import os
from collections import deque
from PyQt6 import QtWidgets, QtCore
import time

try:
    import psutil
except Exception:
    psutil = None

try:
    import pyqtgraph as pg
except Exception:
    pg = None

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

class CpuInfoPage(QtWidgets.QWidget):
    """
    CPU - model, rdzenie, częstotliwość, obciążenie, średnie obciążęnie w ostatnich 30 sekundach + wykresy na rdzeń
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        v = QtWidgets.QVBoxLayout(self)

        # CPU - informacje
        info = QtWidgets.QGroupBox("CPU – informacje")
        v.addWidget(info)
        form = QtWidgets.QFormLayout(info)

        # Zakładki
        def add_row(label):
            l = QtWidgets.QLabel(label + ":"); l.setStyleSheet("color:#9aa3b2;")
            val = QtWidgets.QLabel("--"); val.setStyleSheet("font-family:monospace;")
            form.addRow(l, val)
            return val

        # Dodawania poszczególnych "zakładek"
        self.model = add_row("Model procesora")
        self.cores = add_row("Rdzenie (fizyczne / logiczne)")
        self.freq  = add_row("Taktowanie")
        self.temp  = add_row("Temperatura")
        self.avg30 = add_row("Średnie (30 s)")
        self.instant_lbl = add_row("Obciążenie ogólne")

        # Model cpu - funkcja importowana z utils.py
        self.model.setText(cpu_model_name())
        if psutil:
            self.cores.setText(f"{psutil.cpu_count(logical=False)} / {psutil.cpu_count(logical=True)}")

        # Wykresy na poszczególny rdzeń logiczny procesora (zużycie w czasie)
        charts = QtWidgets.QGroupBox("Użycie CPU na rdzeń")
        v.addWidget(charts, 1)
        grid = QtWidgets.QGridLayout(charts)

        self.per_core_curves = []
        self.per_core_hist = []
        self.history_len = 60

        self.ncores = (psutil.cpu_count(logical=True) or 1) if psutil else 1
        cols = 4

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_start = QtWidgets.QPushButton("Start rejestrowania")
        self.btn_stop = QtWidgets.QPushButton("Zatrzymaj i zapisz CSV")
        self.btn_stop.setEnabled(False)
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_stop)
        v.addLayout(btn_row)


        # Wykresy na poszczególny rdzeń
        if pg is None:
            note = QtWidgets.QLabel("Zainstaluj pyqtgraph, aby zobaczyć wykresy")
            note.setStyleSheet("color:#ffb020;")
            grid.addWidget(note, 0, 0)
        else:
            pg.setConfigOptions(antialias=True, background=None, foreground='w')
            for i in range(self.ncores):
                pw = pg.PlotWidget()
                pw.setMinimumHeight(100)
                pw.setYRange(0, 100)
                pw.showGrid(x=True, y=True, alpha=0.2)
                pw.setMenuEnabled(False); pw.setMouseEnabled(x=False, y=False)
                pw.setLabel('left', f'cpu{i} %')
                pw.hideButtons()
                curve = pw.plot(pen=pg.mkPen(width=2))
                grid.addWidget(pw, i // cols, i % cols)
                self.per_core_curves.append(curve)
                self.per_core_hist.append(deque([0]*self.history_len, maxlen=self.history_len))

        # Pasek ładowania
        self.pb = QtWidgets.QProgressBar()
        self.pb.setMaximumHeight(18)
        self.pb.setFormat("%p%")
        v.addWidget(self.pb)

        # Obliczanie zużycia CPU
        self._prev_times = psutil.cpu_times(percpu=True) if psutil else []
        self._avg_hist = deque(maxlen=30)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

        self.is_recording = False
        self.samples = []
        self.t0 = None
        self.btn_start.clicked.connect(self._start_rec)
        self.btn_stop.clicked.connect(self._stop_rec)

    def _cpu_temp_avg(self):
        if not psutil:
            return None
        try:
            temps = psutil.sensors_temperatures()
            if not temps:
                return None

            if "k10temp" in temps:
                for t in temps["k10temp"]:
                    lbl = (t.label or "").lower()
                    if "tctl" in lbl or "tdie" in lbl:
                        return t.current
                return temps["k10temp"][0].current

            if "coretemp" in temps:
                for t in temps["coretemp"]:
                    if "package id 0" in (t.label or "").lower():
                        return t.current
                return temps["coretemp"][0].current

            if "cpu_thermal" in temps:
                return temps["cpu_thermal"][0].current

            for arr in temps.values():
                for t in arr:
                    if t.current is not None:
                        return t.current

        except Exception:
            return None


    def _tick(self):
        if not psutil:
            return
        try:
            # Obciążenie na rdzeń
            cur = psutil.cpu_times(percpu=True)
            usages = []
            for p, c in zip(self._prev_times, cur):
                total_p = sum(p); total_c = sum(c)
                idle_p = p.idle + getattr(p, "iowait", 0.0)
                idle_c = c.idle + getattr(c, "iowait", 0.0)
                dt = total_c - total_p
                didle = idle_c - idle_p
                u = 0.0 if dt <= 0 else (1.0 - (didle / dt)) * 100.0
                usages.append(max(0.0, min(100.0, u)))
            self._prev_times = cur

            if usages:
                # Aktualne + średnie zużycie
                instant = sum(usages) / len(usages)
                self.instant_lbl.setText(f"{instant:.1f}%")
                self.pb.setValue(int(round(instant)))

                # Zużycie w ostatnich 30 sekundach
                self._avg_hist.append(instant)
                avg30 = sum(self._avg_hist) / len(self._avg_hist)
                self.avg30.setText(f"{avg30:.1f}%")

                if pg is not None and len(usages) == len(self.per_core_hist):
                    for hist, val in zip(self.per_core_hist, usages):
                        hist.append(val)
                    x = list(range(len(self.per_core_hist[0])))
                    for curve, hist in zip(self.per_core_curves, self.per_core_hist):
                        curve.setData(x, list(hist))

            self._last_instant_cpu = instant
            self._last_per_core_cpu = list(usages)


            # Częstotliwość
            try:
                f = psutil.cpu_freq()
                if f and f.current:
                    self.freq.setText(f"{f.current/1000:.2f} GHz (max {f.max/1000:.2f})")
                else:
                    self.freq.setText("—")
            except Exception:
                self.freq.setText("—")
            self._last_freq_mhz = (f.current if f and f.current else None)

            # Temperatura
            t = self._cpu_temp_avg()
            self.temp.setText(f"{t:.1f} °C" if t is not None else "—")
            self._last_temp_c = t

        except Exception:
            pass

        if self.is_recording:
            now = time.time()
            if self.t0 is None:
                self.t0 = now

            # używamy wartosci policzonych wyżej w TYM samym ticku
            total_pct = getattr(self, "_last_instant_cpu", None)
            per_core  = getattr(self, "_last_per_core_cpu", None)
            freq_mhz  = getattr(self, "_last_freq_mhz", None)
            temp_c    = getattr(self, "_last_temp_c", None)

            sample = {
                "t_rel_s": round(now - self.t0, 3),
                "cpu_total_pct": round(float(total_pct), 1) if total_pct is not None else None,
                "cpu_freq_MHz": float(freq_mhz) if freq_mhz is not None else None,
                "cpu_per_core_pct": ";".join(f"{c:.1f}" for c in per_core) if per_core else None,
                "cpu_temp_C": round(float(temp_c), 1) if temp_c is not None else None,
            }
            self.samples.append(sample)


    def _start_rec(self):
        self.samples.clear()
        self.is_recording = True
        self.t0 = time.time()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

    def _stop_rec(self):
        self.is_recording = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

        if not self.samples:
            QtWidgets.QMessageBox.information(self, "CPU", "Brak danych do zapisania.")
            return

        rows = list(self.samples)
        if not isinstance(rows[0], dict):
            fixed = []
            for r in rows:
                if isinstance(r, (tuple, list)) and len(r) >= 2:
                    fixed.append({"t_rel_s": r[0], "cpu_total_pct": r[1]})
            if fixed:
                rows = fixed
            else:
                QtWidgets.QMessageBox.warning(self, "CPU", "Dane w buforze nie są w formacie słowników.")
                return

        fieldnames = []
        seen = set()
        for r in rows:
            for k in r.keys():
                if k not in seen:
                    seen.add(k)
                    fieldnames.append(k)

        os.makedirs("../results", exist_ok=True)
        path = os.path.join("../results", f"cpu_recording_{int(time.time())}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in rows:
                w.writerow(r)

        QtWidgets.QMessageBox.information(self, "CPU", f"Zapisano: {path}")
