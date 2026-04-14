from PyQt6 import QtWidgets, QtCore
import psutil
import time, os, csv

class RamInfoPage(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        v = QtWidgets.QVBoxLayout(self)

        gb = QtWidgets.QGroupBox("Pamięć RAM / SWAP")
        v.addWidget(gb)
        form = QtWidgets.QFormLayout(gb)

        # Etykiety
        self.l_ram   = QtWidgets.QLabel("—")
        self.l_swap  = QtWidgets.QLabel("—")
        self.l_cache = QtWidgets.QLabel("—")

        # Opcjonalny styl
        for w in (self.l_ram, self.l_swap, self.l_cache):
            w.setStyleSheet((w.styleSheet() or "") + "font-family: monospace;")

        form.addRow("RAM:",   self.l_ram)
        form.addRow("SWAP:",  self.l_swap)
        form.addRow("Wolne:", self.l_cache)

        # Przyciski start/stop do rejestrowania
        btn_row = QtWidgets.QHBoxLayout()
        v.addLayout(btn_row)
        self.btn_start = QtWidgets.QPushButton("Start rejestrowania")
        self.btn_stop  = QtWidgets.QPushButton("Zatrzymaj i zapisz CSV")
        self.btn_stop.setEnabled(False)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_stop)

        self.is_recording = False
        self.samples = []
        self.t0 = None

        self.btn_start.clicked.connect(self._start_rec)
        self.btn_stop.clicked.connect(self._stop_rec)

        # timer
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

        # Pierwszy odczyt
        self._tick()

    def _tick(self):
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        used_gb = mem.used / (1024**3)
        total_gb = mem.total / (1024**3)
        available_gb = mem.available / (1024**3)
        percent = mem.percent

        swap_used = swap.used / (1024**3)
        swap_total = swap.total / (1024**3) if swap.total else 0
        swap_percent = swap.percent

        self.l_ram.setText(f"{used_gb:.2f} / {total_gb:.2f} GB ({percent:.0f}%)")
        if swap.total:
            self.l_swap.setText(f"{swap_used:.2f} / {swap_total:.2f} GB ({swap_percent:.0f}%)")
        else:
            self.l_swap.setText("— (brak SWAP)")

        self.l_cache.setText(f"{available_gb:.2f} GB wolne")

        # Rejestracja CSV
        if self.is_recording:
            t_rel = time.time() - (self.t0 or time.time())
            row = {
                "t_rel_s": round(t_rel, 3),
                "ram_used_GB": round(used_gb, 3),
                "ram_total_GB": round(total_gb, 3),
                "ram_used_pct": round(percent, 1),
                "swap_used_GB": round(swap_used, 3),
                "swap_total_GB": round(swap_total, 3),
                "swap_used_pct": round(swap_percent, 1) if swap.total else None,
                "available_GB": round(available_gb, 3),
            }
            self.samples.append(row)

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
            QtWidgets.QMessageBox.information(self, "RAM", "Brak danych do zapisania.")
            return
        os.makedirs("../results", exist_ok=True)
        path = os.path.join("../results", f"ram_recording_{int(time.time())}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=self.samples[0].keys())
            w.writeheader()
            w.writerows(self.samples)
        QtWidgets.QMessageBox.information(self, "RAM", f"Zapisano: {path}")
