import math, multiprocessing, time, json, os, psutil, threading, gc
from datetime import datetime
from PyQt6 import QtWidgets, QtCore
import matplotlib.pyplot as plt


def timestamp() -> str:
    """Znacznik czasu do nazw plików."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def _float_heavy_task(stop_event):
    """Intensywna pętla obliczeniowa zmiennoprzecinkowa obciążająca procesor."""
    x = 1.000001
    while not stop_event.is_set():
        x = math.sin(x) * math.cos(x) * math.sqrt(x * x + 1.0) / (x + 0.000001)
        if x > 1e6:
            x = math.log(x)


class StressTestPage(QtWidgets.QWidget):
    """
    Tworzenie zakładki Stress Test
    CPU obciąża wszystkie rdzenie intensywną pętlą obliczeniową
    RAM alokuje zadane ilości pamięci w GB w wielkościach podanej wielkości
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.output_dir = "../stress_reports"
        os.makedirs(self.output_dir, exist_ok=True)

        v = QtWidgets.QVBoxLayout(self)

        # Zakładka stress test CPU
        box = QtWidgets.QGroupBox("Stress Test CPU")
        v.addWidget(box)
        form = QtWidgets.QFormLayout(box)

        self.core_count = psutil.cpu_count(logical=True)
        self.duration_input = QtWidgets.QSpinBox()
        self.duration_input.setRange(1, 600)
        self.duration_input.setValue(30)
        self.duration_input.setSuffix(" s")
        form.addRow("Czas trwania testu:", self.duration_input)

        self.info_label = QtWidgets.QLabel(
            f"Test obciąża {self.core_count} logicznych rdzeni (operacje zmiennoprzecinkowe).\n"
        )
        self.info_label.setStyleSheet("color:#9aa3b2;")
        v.addWidget(self.info_label)

        btns = QtWidgets.QHBoxLayout()
        self.btn_start = QtWidgets.QPushButton("Start testu")
        self.btn_stop = QtWidgets.QPushButton("Zatrzymaj")
        self.btn_stop.setEnabled(False)
        btns.addWidget(self.btn_start)
        btns.addWidget(self.btn_stop)
        v.addLayout(btns)

        self.progress = QtWidgets.QProgressBar()
        v.addWidget(self.progress)

        self.result_label = QtWidgets.QLabel("")
        self.result_label.setStyleSheet("font-family:monospace; color:#e6eaf7;")
        v.addWidget(self.result_label)

        # stan procesora
        self.processes = []
        self.stop_events = []
        self._running = False
        self.start_time = None
        self.end_time = None
        self.data_points = []

        self.btn_start.clicked.connect(self._start_test)
        self.btn_stop.clicked.connect(self._stop_test)

        # Stress test pamięci RAM
        box_ram = QtWidgets.QGroupBox("Stress Test RAM")
        v.addWidget(box_ram)
        form_ram = QtWidgets.QFormLayout(box_ram)

        self.ram_gb_input = QtWidgets.QDoubleSpinBox()
        self.ram_gb_input.setDecimals(1)
        self.ram_gb_input.setRange(0.1, 64.0)
        self.ram_gb_input.setSingleStep(0.1)
        self.ram_gb_input.setValue(2.0)
        self.ram_gb_input.setSuffix(" GB")
        form_ram.addRow("Ilość pamięci do alokacji:", self.ram_gb_input)

        self.ram_chunk_mb_input = QtWidgets.QSpinBox()
        self.ram_chunk_mb_input.setRange(10, 1024)
        self.ram_chunk_mb_input.setValue(100)
        self.ram_chunk_mb_input.setSuffix(" MB")
        form_ram.addRow("Wielkość pojedynczego bloku:", self.ram_chunk_mb_input)

        self.ram_info = QtWidgets.QLabel(
            "Test alokuje pamięć w blokach i utrzymuje ją zajętą do zatrzymania przez użytkownika."
        )
        self.ram_info.setStyleSheet("color:#9aa3b2;")
        v.addWidget(self.ram_info)

        ram_btns = QtWidgets.QHBoxLayout()
        self.btn_ram_start = QtWidgets.QPushButton("Start testu")
        self.btn_ram_stop = QtWidgets.QPushButton("Koniec testu")
        self.btn_ram_stop.setEnabled(False)
        ram_btns.addWidget(self.btn_ram_start)
        ram_btns.addWidget(self.btn_ram_stop)
        v.addLayout(ram_btns)

        self.ram_progress = QtWidgets.QProgressBar()
        v.addWidget(self.ram_progress)

        self.ram_status = QtWidgets.QLabel("")
        self.ram_status.setStyleSheet("font-family:monospace; color:#e6eaf7;")
        v.addWidget(self.ram_status)

        v.addStretch(1)

        # stan pamięci RAM
        self._ram_running = False
        self._ram_stop = threading.Event()
        self._ram_blocks = []
        self._ram_target_bytes = 0
        self._ram_allocated = 0

        self.btn_ram_start.clicked.connect(self._start_ram_test)
        self.btn_ram_stop.clicked.connect(self._stop_ram_test)

        # Procesor - dane co 1 sekunde
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

        # RAM - dane co 200 ms
        self._ram_timer = QtCore.QTimer(self)
        self._ram_timer.timeout.connect(self._tick_ram)
        self._ram_timer.start(200)

    # Stress test CPU
    def _start_test(self):
        if self._running:
            return

        self._running = True
        self.result_label.setText("")
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.data_points.clear()

        duration = self.duration_input.value()
        self.progress.setValue(0)
        self.start_time = time.time()
        self.end_time = self.start_time + duration

        # rozpoczynanie procesów
        self.stop_events = []
        self.processes = []
        for _ in range(self.core_count):
            e = multiprocessing.Event()
            p = multiprocessing.Process(target=_float_heavy_task, args=(e,))
            p.daemon = True
            p.start()
            self.stop_events.append(e)
            self.processes.append(p)

        self.result_label.setText("Test w toku")

    # Logika zatrzymana testu
    def _stop_test(self):
        if not self._running:
            return

        for e in self.stop_events:
            e.set()
        for p in self.processes:
            if p.is_alive():
                p.terminate()

        self._running = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress.setValue(0)

        # Generowanie raportu w pliku JSON
        report_path = self._generate_report()
        self.result_label.setText(f"Test zakończony. Raport zapisano:\n{report_path}")

    def _tick(self):
        if not self._running:
            return

        now = time.time()
        remaining = self.end_time - now
        elapsed = now - self.start_time
        pct = (elapsed / max(1e-6, (self.end_time - self.start_time))) * 100
        self.progress.setValue(min(100, int(pct)))

        # Zapisywanie danych co sekundę
        usage = psutil.cpu_percent(interval=None)
        freq = psutil.cpu_freq()
        freq_val = (freq.current / 1000.0) if freq else 0.0
        temp = self._get_avg_temp()

        self.data_points.append({
            "time_s": int(elapsed),
            "cpu_usage": usage,
            "temp": temp,
            "freq": freq_val
        })

        if remaining <= 0:
            self._stop_test()

    # Logika wyliczania średniej temperatury
    def _get_avg_temp(self):
        try:
            temps = psutil.sensors_temperatures()
            if not temps:
                return None
            for key in ("coretemp", "k10temp", "zenpower", "cpu_thermal"):
                if key in temps:
                    vals = [t.current for t in temps[key] if t.current is not None]
                    if vals:
                        return sum(vals) / len(vals)
            vals = [t.current for v in temps.values() for t in v if t.current is not None]
            return sum(vals) / len(vals) if vals else None
        except Exception:
            return None


    def _generate_report(self):
        """Logika która tworzy raport JSON + wykresy w PNG do testu procesora CPU"""
        base_name = f"stress_report_{timestamp()}"
        json_path = os.path.join(self.output_dir, f"{base_name}.json")

        # Analiza danych
        times = [p["time_s"] for p in self.data_points]
        usage_vals = [p["cpu_usage"] for p in self.data_points if p["cpu_usage"] is not None]
        temp_vals = [p["temp"] for p in self.data_points if p["temp"] is not None]
        freq_vals = [p["freq"] for p in self.data_points if p["freq"] is not None]

        avg_usage = sum(usage_vals) / len(usage_vals) if usage_vals else 0.0
        avg_temp = sum(temp_vals) / len(temp_vals) if temp_vals else 0.0
        avg_freq = sum(freq_vals) / len(freq_vals) if freq_vals else 0.0
        max_temp = max(temp_vals) if temp_vals else 0.0

        # Wykresy
        usage_png = os.path.join(self.output_dir, f"{base_name}_usage.png")
        temp_png = os.path.join(self.output_dir, f"{base_name}_temp.png")

        try:
            plt.figure(figsize=(6, 3))
            plt.plot(times, usage_vals, label="CPU usage [%]")
            plt.xlabel("Time [s]"); plt.ylabel("Usage [%]"); plt.title("CPU Usage")
            plt.grid(True); plt.legend(); plt.tight_layout()
            plt.savefig(usage_png); plt.close()

            plt.figure(figsize=(6, 3))
            plt.plot(times, temp_vals, label="Temperature [°C]")
            plt.xlabel("Time [s]"); plt.ylabel("Temperature [°C]"); plt.title("CPU Temperature")
            plt.grid(True); plt.legend(); plt.tight_layout()
            plt.savefig(temp_png); plt.close()
        except Exception as e:
            print("Błąd generowania wykresów:", e)

        report = {
            "metadata": {
                "cpu_model": self._cpu_model(),
                "logical_cores": self.core_count,
                "test_duration_s": int(self.duration_input.value()),
                "start_time": datetime.fromtimestamp(self.start_time).strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            },
            "results": {
                "avg_cpu_usage": round(avg_usage, 1),
                "avg_temp": round(avg_temp, 1),
                "max_temp": round(max_temp, 1),
                "avg_freq_GHz": round(avg_freq, 2)
            },
            "timeline": self.data_points,
            "charts": {"cpu_usage_png": usage_png, "temperature_png": temp_png}
        }

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        return json_path

    def _cpu_model(self):
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":", 1)[1].strip()
        except Exception:
            pass
        return f"{self.core_count}x CPU"

    # Stress test pamięci RAM
    def _start_ram_test(self):
        if self._ram_running:
            return
        self._ram_running = True
        self._ram_stop.clear()
        self._ram_blocks.clear()
        gc.collect()

        total_gb = float(self.ram_gb_input.value())
        chunk_mb = int(self.ram_chunk_mb_input.value())
        self._ram_target_bytes = int(total_gb * (1024**3))
        self._ram_allocated = 0
        self.ram_progress.setValue(0)
        self.ram_status.setText(f"Alokuję ~{total_gb:.1f} GB (bloki {chunk_mb} MB)...")

        self.btn_ram_start.setEnabled(False)
        self.btn_ram_stop.setEnabled(True)

        t = threading.Thread(target=self._ram_worker, args=(self._ram_target_bytes, chunk_mb), daemon=True)
        t.start()

    def _ram_worker(self, target_bytes: int, chunk_mb: int):
        try:
            chunk = chunk_mb * 1024 * 1024
            loops = max(1, target_bytes // chunk)
            for _ in range(int(loops)):
                if self._ram_stop.is_set():
                    break
                self._ram_blocks.append(bytearray(chunk))
                self._ram_allocated += chunk
                # minimalna przerwa w celu płynnego wykazywania postępu
                time.sleep(0.02)
            # zaokrąglanie
            remainder = target_bytes - self._ram_allocated
            if remainder > 0 and not self._ram_stop.is_set():
                self._ram_blocks.append(bytearray(remainder))
                self._ram_allocated += remainder
        except MemoryError:
            self.ram_status.setText("Błąd: MemoryError)")
        finally:
            # zajmowanie pamięci dopóki użytkownik samodzielnie jej nie odda (kliknie guzik)
            pass

    def _stop_ram_test(self):
        if not self._ram_running:
            return
        self._ram_stop.set()
        # Zwolnienie pamięci
        self._ram_blocks.clear()
        gc.collect()
        self._ram_running = False
        self.btn_ram_start.setEnabled(True)
        self.btn_ram_stop.setEnabled(False)
        self.ram_progress.setValue(0)
        self.ram_status.setText("Zwolniono pamięć.")

    def _tick_ram(self):
        if not self._ram_running:
            return
        tgt = max(1, self._ram_target_bytes)
        pct = min(100, int(self._ram_allocated * 100 / tgt))
        self.ram_progress.setValue(pct)
        used_gb = self._ram_allocated / (1024**3)
        target_gb = self._ram_target_bytes / (1024**3)
        self.ram_status.setText(f"Zajęto: {used_gb:.2f} / {target_gb:.2f} GB ({pct}%)")
