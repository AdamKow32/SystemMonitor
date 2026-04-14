from src import GPU_info as gpu_mod
import os


def test_bytes_to_GB():
    assert gpu_mod._bytes_to_GB(1_000_000_000) == 1.0
    assert gpu_mod._bytes_to_GB(2_500_000_000) == 2.5
    assert gpu_mod._bytes_to_GB(None) is None


def test_detect_amd_cards(monkeypatch):
    fake_paths = ["/sys/class/drm/card0"]

    def fake_glob(pattern):
        assert "card" in pattern
        return fake_paths

    def fake_read_first(path):
        if path.endswith("/device/vendor"):
            return "0x1002"
        return None

    def fake_exists(path):
        return True

    monkeypatch.setattr("glob.glob", fake_glob)
    monkeypatch.setattr(gpu_mod, "read_first", fake_read_first)
    monkeypatch.setattr(os.path, "exists", fake_exists)

    cards = gpu_mod._detect_amd_cards()
    assert len(cards) == 1
    assert cards[0]["drm"] == "/sys/class/drm/card0"


def test_edit_AMD_name(monkeypatch):
    uevent_content = "PCI_SLOT_NAME=0000:01:00.0\nOTHER=foo\n"
    dev_content = "0x7340\n"

    def fake_read_first(path):
        if path.endswith("/device/uevent"):
            return uevent_content
        if path.endswith("/device/device"):
            return dev_content
        return None

    monkeypatch.setattr(gpu_mod, "read_first", fake_read_first)
    name = gpu_mod.edit_AMD_name("/sys/class/drm/card0")
    assert "AMD GPU" in name
    assert "0000:01:00.0" in name
    assert "0x7340" in name


def test_amd_reader_read(monkeypatch):
    def fake_detect():
        return [{"drm": "/sys/class/drm/card0", "hwmon": "/sys/class/drm/card0/device/hwmon/hwmon0"}]

    def fake_exists(path):
        return True

    def fake_read_first_int(path):
        if "gpu_busy_percent" in path:
            return 50
        if "mem_info_vram_used" in path:
            return 2_000_000_000
        if "mem_info_vram_total" in path:
            return 8_000_000_000
        if "temp1_input" in path:
            return 55000
        return None

    def fake_read_first(path):
        if path.endswith("/device/uevent"):
            return "PCI_SLOT_NAME=0000:01:00.0\n"
        if path.endswith("/device/device"):
            return "0x7340"
        return None

    monkeypatch.setattr(gpu_mod, "_detect_amd_cards", fake_detect)
    monkeypatch.setattr(os.path, "exists", fake_exists)
    monkeypatch.setattr(gpu_mod, "read_first_int", fake_read_first_int)
    monkeypatch.setattr(gpu_mod, "read_first", fake_read_first)
    monkeypatch.setattr(gpu_mod, "amd", None)

    r = gpu_mod._AmdGpuReader()
    data = r.read()
    assert data["busy"] == 50.0
    assert data["vram_used"] == 2_000_000_000
    assert data["vram_total"] == 8_000_000_000
    assert data["temp"] == 55.0
    assert data["pci_slot"] == "0000:01:00.0"


def test_nvidia_reader_smi_path(monkeypatch):
    def fake_which(name):
        if name == "nvidia-smi":
            return "/usr/bin/nvidia-smi"
        return None

    def fake_check_output(args, text=True, timeout=None):
        cmd = " ".join(args)
        if "--query-gpu=memory.total" in cmd and "csv,noheader,nounits" in cmd:
            return "8192\n"
        if "--query-gpu=name,utilization.gpu,temperature.gpu,memory.total,memory.used,pci.bus_id" in cmd:
            return "Fake GPU, 45, 70, 8192, 4096, 0000:02:00.0\n"
        raise AssertionError(f"Nieoczekiwane wywołanie: {cmd}")

    monkeypatch.setattr(gpu_mod, "pynvml", None)
    monkeypatch.setattr("shutil.which", fake_which)
    monkeypatch.setattr("subprocess.check_output", fake_check_output)

    reader = gpu_mod._NvidiaGpuReader()
    assert reader.available is True  # teraz przejdzie

    d = reader.read()
    assert d["name"] == "Fake GPU"
    assert d["busy"] == 45.0
    assert d["temp"] == 70.0
    assert d["vram_total"] == 8192 * 1024 * 1024
    assert d["vram_used"] == 4096 * 1024 * 1024
    assert d["pci_slot"].endswith("02:00.0")


def test_gpu_reader_prefers_amd(monkeypatch):
    class DummyAMD:
        def __init__(self):
            self._d = {"name": "AMD-Dummy", "busy": 10.0,
                       "temp": 50.0, "vram_used": 1_000_000_000,
                       "vram_total": 4_000_000_000, "pci_slot": "0000:01:00.0"}
        def read(self):
            return dict(self._d)

    class DummyNV:
        def __init__(self):
            self.available = True
        def read(self):
            return {"name": "NV-Dummy", "busy": 99.0,
                    "temp": 90.0, "vram_used": None,
                    "vram_total": None, "pci_slot": "0000:02:00.0"}

    monkeypatch.setattr(gpu_mod, "_AmdGpuReader", DummyAMD)
    monkeypatch.setattr(gpu_mod, "_NvidiaGpuReader", DummyNV)

    g = gpu_mod._GpuReader()
    d = g.read()
    assert d["name"] == "AMD-Dummy"
    assert d["busy"] == 10.0
