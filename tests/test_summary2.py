from src import Summary_info as smod


def test_motherboard_string_all_fields(monkeypatch, tmp_path):
    base = tmp_path / "sys" / "devices" / "virtual" / "dmi" / "id"
    base.mkdir(parents=True, exist_ok=True)
    (base / "board_vendor").write_text("ASUS", encoding="utf-8")
    (base / "board_name").write_text("B650-E", encoding="utf-8")
    (base / "board_version").write_text("1.0", encoding="utf-8")

    real_read_first = smod.read_first

    def fake_read_first(path):
        if "board_vendor" in path:
            return "ASUS"
        if "board_name" in path:
            return "B650-E"
        if "board_version" in path:
            return "1.0"
        return real_read_first(path)

    monkeypatch.setattr(smod, "read_first", fake_read_first)

    s = smod._motherboard_string()
    assert "ASUS" in s
    assert "B650-E" in s
    assert "1.0" in s


def test_gpu_string_prefers_amd(monkeypatch):
    class DummyGPU:
        def get_name(self):
            return "AMD Dummy GPU"

    class DummyAMDModule:
        def get_gpu(self, idx):
            return DummyGPU()

    monkeypatch.setattr(smod, "amd", DummyAMDModule())

    g = smod._gpu_string()
    assert g == "AMD Dummy GPU"

def test_gpu_string_falls_back_to_lspci(monkeypatch):
    monkeypatch.setattr(smod, "amd", None)

    lspci_cut_output = " NVIDIA Corporation Dummy 1234\n"

    def fake_check_output(args, text=True, **kwargs):
        assert args[0] == "bash" and args[1] == "-lc"
        assert "lspci" in args[2] and "cut -d: -f3-" in args[2]
        return lspci_cut_output

    monkeypatch.setattr("subprocess.check_output", fake_check_output)

    g = smod._gpu_string()
    assert "Dummy 1234" in g



def test_temperatures_summary_cpu_and_gpu(monkeypatch):
    class T:
        def __init__(self, current, label=""):
            self.current = current
            self.label = label

    def fake_sensors():
        return {
            "k10temp": [T(60.0, "Tdie"), T(55.0, "Tctl")],
            "amdgpu": [T(70.0)]
        }

    monkeypatch.setattr(smod.psutil, "sensors_temperatures", fake_sensors)

    temps = smod._temperatures_summary()
    # CPU – powinien wybrać Tdie/Tctl
    assert "°C" in temps["cpu"]
    assert "°C" in temps["gpu"]
