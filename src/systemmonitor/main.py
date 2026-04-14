import sys, platform, time, socket
from PyQt6 import QtWidgets, QtCore, QtGui
from .CPU_info import CpuInfoPage
from .GPU_info import GpuInfoPage
from .RAM_info import RamInfoPage
from .stresstest import StressTestPage
from .Summary_info import SummaryPage
from .DISC_info import DiskInfoPage

try:
    import pyqtgraph as pg
except Exception:
    pg = None

try:
    import psutil
except ImportError:
    psutil = None

try:
    import pyamdgpuinfo
except ImportError:
    pyamdgpuinfo = None

class Header(QtWidgets.QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)

        title = QtWidgets.QLabel("System Monitor")
        title.setStyleSheet("font-weight:600; font-size:14px;")
        lay.addWidget(title)

        u = platform.uname()
        sub = QtWidgets.QLabel(f"• {u.system} {u.release} — {u.machine}")
        sub.setStyleSheet("color:#9aa3b2;")
        lay.addWidget(sub)
        lay.addStretch(1)

        def kpi(label):
            w = QtWidgets.QWidget()
            hl = QtWidgets.QHBoxLayout(w)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(4)
            lab = QtWidgets.QLabel(label)
            lab.setStyleSheet("color:#9aa3b2;")
            val = QtWidgets.QLabel("--")
            val.setStyleSheet("font-family:monospace; font-weight:600;")
            hl.addWidget(lab)
            hl.addWidget(val)
            return w, val

        self._cpuWrap, self.cpu = kpi("CPU:")
        self._ramWrap, self.ram = kpi("RAM:")
        for w in (self._cpuWrap, self._ramWrap, ):
            lay.addWidget(w)

        self._last_t = time.time()

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    def _tick(self):
        if not psutil:
            return
        try:
            self.cpu.setText(f"{psutil.cpu_percent():.0f}%")
            self.ram.setText(f"{psutil.virtual_memory().percent:.0f}%")

            now = time.time()
            dt = max(0.1, now - self._last_t)
        except Exception:
            pass

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("System Monitor")
        self.resize(1100, 700)
        cw = QtWidgets.QWidget()
        self.setCentralWidget(cw)
        layout = QtWidgets.QVBoxLayout(cw)

        self.header = Header()
        layout.addWidget(self.header)
        self.header.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.header.setMaximumHeight(56)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        label = QtWidgets.QLabel("Zakładki")
        label.setStyleSheet("color:#9aa3b2; font-weight:600;")
        self.nav = QtWidgets.QListWidget()
        self.nav.addItems(["Summary", "CPU", "RAM", "GPU", "Discs", "Stress test"])
        lv.addWidget(label)
        lv.addWidget(self.nav)
        splitter.addWidget(left)

        self.stack = QtWidgets.QStackedWidget()
        self.page_cpu = CpuInfoPage()
        self.page_ram = RamInfoPage()
        self.page_gpu = GpuInfoPage()
        self.page_disc = DiskInfoPage()
        self.page_stress = StressTestPage()
        self.page_sum = SummaryPage()
        self.stack.addWidget(self.page_sum)
        for p in (self.page_cpu, self.page_ram, self.page_gpu, self.page_disc, self.page_stress):
            self.stack.addWidget(p)
        splitter.addWidget(self.stack)
        splitter.setSizes([220, 880])

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self._apply_dark()

    def _apply_dark(self):
        pal = self.palette()
        pal.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#0f1420"))
        pal.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor("#151c2e"))
        pal.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor("#e6eaf7"))
        self.setPalette(pal)


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    font = app.font()
    font.setPointSize(10)
    app.setFont(font)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
