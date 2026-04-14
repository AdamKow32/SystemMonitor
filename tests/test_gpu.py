# tests/test_gpu_info.py
import types


def test_amd_reader_basic(monkeypatch, _ns):
    monkeypatch.setattr(gpu_mod, "read_first", lambda p: "0x1002" if p.endswith("/vendor") else "AMD")
    monkeypatch.setattr(gpu_mod, "read_first_int", lambda p: 42 if p.endswith("gpu_busy_percent") else 1024*1024*1024)
    monkeypatch.setattr(gpu_mod.glob, "glob", lambda pat: ["/sys/class/drm/card1"] if "card[0-9]" in pat else ["/sys/class/drm/card1/device/hwmon/hwmon7"])
    monkeypatch.setattr(gpu_mod.os.path, "exists", lambda p: True)
    r = gpu_mod._AmdGpuReader()
    d = r.read()
    assert d["busy"] == 42.0
    assert d["vram_total"] == 1024*1024*1024

def test_nvidia_nvml_path(monkeypatch, _ns):
    fake = types.SimpleNamespace()
    def init(): pass
    def cnt(): return 1
    class H:
        pass
    def getH(i): return "H0"
    def getMem(h): return _ns(total=8*1024**3, used=2*1024**3)
    def getName(h): return b"RTX"
    def getUtil(h): return _ns(gpu=55)
    def getTemp(h, x): return 66
    def getPci(h): return _ns(busId=b"0000:65:00.0")

    fake.nvmlInit = init
    fake.nvmlDeviceGetCount = cnt
    fake.nvmlDeviceGetHandleByIndex = getH
    fake.nvmlDeviceGetMemoryInfo = getMem
    fake.nvmlDeviceGetName = getName
    fake.nvmlDeviceGetUtilizationRates = getUtil
    fake.nvmlDeviceGetTemperature = getTemp
    fake.nvmlDeviceGetPciInfo = getPci
    fake.NVML_TEMPERATURE_GPU = 0

    monkeypatch.setattr(gpu_mod, "pynvml", fake)
    r = gpu_mod._NvidiaGpuReader()
    d = r.read()
    assert d["name"] == "RTX"
    assert d["busy"] == 55.0
    assert d["temp"] == 66.0

def test_nvidia_smi_fallback(monkeypatch):
    monkeypatch.setattr(gpu_mod, "pynvml", None)
    monkeypatch.setattr(gpu_mod.shutil, "which", lambda cmd: "/usr/bin/nvidia-smi" if cmd=="nvidia-smi" else None)
    def check_output(args, text=True, timeout=1.5):
        if "--query-gpu=memory.total" in args:
            return "8192\n"
        return "GeForce, 50, 70, 8192, 4096, 0000:65:00.0\n"
    monkeypatch.setattr(gpu_mod.subprocess, "check_output", check_output)

    r = gpu_mod._NvidiaGpuReader()
    d = r.read()
    assert d["name"].startswith("GeForce")
    assert d["vram_used"] == 4096*1024*1024


import src.GPU_info as gpu_mod
