"""
configure.py – Global configuration, constants, frequency databases, and hardware detection.
Harmony-Healing
"""
import json
import os
import subprocess
import platform
import configparser

# =============================================================================
# APP CONSTANTS
# =============================================================================
APP_TITLE = "Harmony-Healing"

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_BASE_DIR    = os.path.dirname(_SCRIPTS_DIR)
DATA_DIR     = os.path.join(_BASE_DIR, "data")

CONFIG_PATH          = os.path.join(DATA_DIR, "persistent.json")   # window size, global
VIRAL_CONFIG_PATH    = os.path.join(DATA_DIR, "viral.json")
FUNGAL_CONFIG_PATH   = os.path.join(DATA_DIR, "fungal.json")
HEALING_CONFIG_PATH  = os.path.join(DATA_DIR, "healing.json")
CONSTANTS_INI_PATH   = os.path.join(DATA_DIR, "constants.ini")

DEFAULT_HARMONIC_MULTIPLIER = 11
WAVEFORM_OPTIONS = ["sine"]

# Discrete duration options (minutes) — slider index 0..5
DURATION_OPTIONS = [15, 30, 60, 90, 120, 180]

# Volume: UI shows 10..100 step 10; audio uses value/100
VOLUME_MIN = 10
VOLUME_MAX = 100
VOLUME_STEP = 10
VOLUME_DEFAULT = 50   # → 0.50 gain

# =============================================================================
# VIRUS / ANTI-VIRAL FREQUENCY DATABASE
# =============================================================================
FREQUENCY_DATA = [
    {"label": "Cancer – generic lower band (Holland)",  "base": 100000},
    {"label": "Cancer – generic mid band (Holland)",  "base": 200000},
    {"label": "Cancer – generic upper band (Holland)",  "base": 300000},
    {"label": "Pancreatic cancer – mid",  "base": 200000},
    {"label": "Leukemia (ALL) – lower DCRFF",  "base": 153000},
    {"label": "Leukemia (ALL) – center DCRFF",  "base": 160000},
    {"label": "Leukemia (ALL) – upper DCRFF",  "base": 165000},
    {"label": "Cancer (breast) – 1",  "base": 27500},
    {"label": "Cancer (breast) – 2",  "base": 85000},
    {"label": "Cancer (breast) – 3",  "base": 95750},
    {"label": "Cancer (breast) – 4",  "base": 150000},
    {"label": "Cancer (breast) – 5",  "base": 525710},
    {"label": "Cancer carcinoid tumor – 1",  "base": 520},
    {"label": "Cancer carcinoid tumor – 2",  "base": 600},
    {"label": "Cancer carcinoid tumor – 3",  "base": 930},
    {"label": "Cancer carcinoid tumor – 4",  "base": 12690},
    {"label": "Cancer carcinoid tumor – 5",  "base": 125000},
    {"label": "Cancer carcinoid tumor – 6",  "base": 269710},
    {"label": "Cancer cervical – 1",  "base": 466},
    {"label": "Cancer cervical – 2",  "base": 907},
    {"label": "Meningioma – 1",  "base": 446},
    {"label": "Meningioma – 2",  "base": 535},
    {"label": "Meningioma – 3",  "base": 537},
    {"label": "Cancer gliomas – 1",  "base": 543},
    {"label": "Cancer gliomas – 2",  "base": 641},
    {"label": "Cancer gliomas – 3",  "base": 857},
    {"label": "Cancer rhabdomyosarcoma – 1",  "base": 2586},
    {"label": "Cancer rhabdomyosarcoma – 2",  "base": 4445},
    {"label": "Cancer rhabdomyosarcoma – 3",  "base": 5476},
    {"label": "Cancer neuroblastoma – 1",  "base": 878},
    {"label": "Cancer neuroblastoma – 2",  "base": 1757},
    {"label": "Cancer neuroblastoma – 3",  "base": 2635},
    {"label": "Cancer neuroblastoma – 4",  "base": 3513},
    {"label": "Cancer neuroblastoma – 5",  "base": 4392},
    {"label": "Cancer neuroblastoma – 6",  "base": 5270},
    {"label": "Cancer neuroblastoma – 7",  "base": 6148},
    {"label": "Cancer lymphoma – 1",  "base": 120},
    {"label": "Cancer lymphoma – 2",  "base": 350},
    {"label": "Cancer lymphoma – 3",  "base": 930},
    {"label": "Cancer lymphoma – 4",  "base": 12330},
    {"label": "Cancer lymphoma – 5",  "base": 25230},
    {"label": "Cancer lymphoma – 6",  "base": 35680},
    {"label": "Cancer leukemia – 1",  "base": 424},
    {"label": "Cancer leukemia – 2",  "base": 830},
    {"label": "Cancer leukemia – 3",  "base": 901},
    {"label": "Cancer leukemia – 4",  "base": 918},
    {"label": "Cold feet and hands – 1",  "base": 200},
    {"label": "Cold feet and hands – 2",  "base": 727},
    {"label": "Cold feet and hands – 3",  "base": 787},
    {"label": "Cold feet and hands – 4",  "base": 880},
    {"label": "Cold feet and hands – 5",  "base": 5000},
    {"label": "Cold in head or chest – 1",  "base": 880},
    {"label": "Cold in head or chest – 2",  "base": 1550},
    {"label": "Cold in head or chest – 3",  "base": 5000},
    {"label": "Cold in head or chest – 4",  "base": 10000},
    {"label": "Cold sores – 1",  "base": 664},
    {"label": "Cold sores – 2",  "base": 785},
    {"label": "Cold sores – 3",  "base": 822},
    {"label": "Cold sores – 4",  "base": 895},
    {"label": "Cold sores – 5",  "base": 944},
    {"label": "Cold sores – 6",  "base": 1043},
    {"label": "Flu / grippe / influenza – 1",  "base": 727},
    {"label": "Flu / grippe / influenza – 2",  "base": 787},
    {"label": "Flu / grippe / influenza – 3",  "base": 800},
    {"label": "Flu / grippe / influenza – 4",  "base": 880},
    {"label": "Adenovirus (colds / flu-type virus) – 1",  "base": 333},
    {"label": "Adenovirus (colds / flu-type virus) – 2",  "base": 523},
    {"label": "Adenovirus (colds / flu-type virus) – 3",  "base": 666},
    {"label": "Adenovirus (colds / flu-type virus) – 4",  "base": 768},
    {"label": "Adenovirus (colds / flu-type virus) – 5",  "base": 786},
    {"label": "Adenovirus (colds / flu-type virus) – 6",  "base": 959},
    {"label": "Adenovirus (colds / flu-type virus) – 7",  "base": 962},
    {"label": "Influenza virus B – 1",  "base": 468},
    {"label": "Influenza virus B – 2",  "base": 530},
    {"label": "Influenza virus B – 3",  "base": 532},
    {"label": "Influenza virus B – 4",  "base": 536},
    {"label": "Influenza virus B – 5",  "base": 537},
    {"label": "Influenza virus B – 6",  "base": 568},
    {"label": "Influenza virus B – 7",  "base": 722},
    {"label": "Influenza virus B – 8",  "base": 740},
    {"label": "Influenza virus B – 9",  "base": 742},
    {"label": "Influenza virus B – 10",  "base": 744},
    {"label": "Influenza virus B – 11",  "base": 746},
    {"label": "Influenza virus B – 12",  "base": 748},
    {"label": "Influenza virus B – 13",  "base": 750},
    {"label": "Influenza virus B – 14",  "base": 1186},
    {"label": "Influenza virus B Hong Kong – 1",  "base": 555},
    {"label": "Influenza virus swine – 1",  "base": 413},
    {"label": "Influenza virus swine – 2",  "base": 432},
    {"label": "Influenza virus swine – 3",  "base": 663},
    {"label": "Influenza virus swine – 4",  "base": 839},
    {"label": "Influenza virus swine – 5",  "base": 995},
    {"label": "Influenza virus British – 1",  "base": 558},
    {"label": "Influenza virus British – 2",  "base": 932},
    {"label": "Rhinitis (nasal issues) – 1",  "base": 20},
    {"label": "Rhinitis – 2",  "base": 120},
    {"label": "Rhinitis – 3",  "base": 1550},
    {"label": "Rhinitis – 4",  "base": 802},
]

# =============================================================================
# FUNGUS / ANTI-FUNGAL FREQUENCY DATABASE
# =============================================================================
FUNGUS_FREQUENCY_DATA = [
    {"label": "Candida albicans – Clark primary",  "base": 386000},
    {"label": "Candida albicans – Clark low",  "base": 384200},
    {"label": "Candida albicans – Clark high",  "base": 388400},
    {"label": "Candida albicans – Rife general 1",  "base": 464},
    {"label": "Candida albicans – Rife general 2",  "base": 728},
    {"label": "Candida albicans – Rife general 3",  "base": 1550},
    {"label": "Candida albicans – Rife general 4",  "base": 2128},
    {"label": "Candida albicans – Rife general 5",  "base": 3375},
    {"label": "Aspergillus niger – Rife primary",  "base": 374},
    {"label": "Aspergillus niger – Rife secondary",  "base": 697},
    {"label": "Aspergillus niger – Clark derived",  "base": 288000},
    {"label": "Aspergillus niger – Bioresonance set 1",  "base": 1823},
    {"label": "Aspergillus niger – Bioresonance set 2",  "base": 2411},
    {"label": "Aspergillus flavus – Rife primary",  "base": 374},
    {"label": "Aspergillus flavus – Rife secondary",  "base": 414},
    {"label": "Aspergillus flavus – Clark aflatoxin",  "base": 177000},
    {"label": "Aspergillus flavus – Clark aflatoxin alt",  "base": 188000},
    {"label": "Aspergillus flavus – Bioresonance",  "base": 1333},
    {"label": "Aspergillus fumigatus – Rife primary",  "base": 374},
    {"label": "Aspergillus fumigatus – Rife secondary",  "base": 743},
    {"label": "Aspergillus fumigatus – Bioresonance 1",  "base": 2411},
    {"label": "Aspergillus fumigatus – Bioresonance 2",  "base": 4442},
    {"label": "Aspergillus fumigatus – Clark derived",  "base": 295000},
    {"label": "Aspergillus glaucus – Rife primary",  "base": 337},
    {"label": "Aspergillus glaucus – Rife secondary",  "base": 555},
    {"label": "Aspergillus glaucus – Bioresonance",  "base": 1155},
    {"label": "Aspergillus terreus – Rife primary",  "base": 339},
    {"label": "Aspergillus terreus – Rife secondary",  "base": 743},
    {"label": "Aspergillus terreus – Bioresonance",  "base": 1833},
    {"label": "Mucor mucedo – Clark primary",  "base": 288000},
    {"label": "Mucor racemosus – Rife derived",  "base": 2140},
    {"label": "Mucor plumbeus – Rife derived",  "base": 1510},
    {"label": "Mucor general – Bioresonance",  "base": 942},
    {"label": "Penicillium rubrum – Bioresonance",  "base": 1016},
    {"label": "Penicillium general – Rife set 1",  "base": 321},
    {"label": "Penicillium general – Rife set 2",  "base": 592},
    {"label": "Penicillium general – Rife set 3",  "base": 866},
    {"label": "Trichophyton mentagrophytes – Rife",  "base": 344},
    {"label": "Trichophyton rubrum – Rife",  "base": 464},
    {"label": "Dermatophyte general – Bioresonance",  "base": 774},
    {"label": "Dermatophyte general – Clark derived",  "base": 254000},
    {"label": "Mold general – Rife low band",  "base": 132},
    {"label": "Mold general – Rife mid band 1",  "base": 242},
    {"label": "Mold general – Rife mid band 2",  "base": 374},
    {"label": "Mold general – Rife mid band 3",  "base": 512},
    {"label": "Mold general – Rife high band 1",  "base": 880},
    {"label": "Mold general – Rife high band 2",  "base": 1130},
    {"label": "Mold general – Rife high band 3",  "base": 1333},
    {"label": "Mold general – Rife ultra band 1",  "base": 1823},
    {"label": "Mold general – Rife ultra band 2",  "base": 2411},
    {"label": "Mold general – Rife ultra band 3",  "base": 4442},
    {"label": "Mycotoxin general – Clark sterigmatocystin 1",  "base": 88000},
    {"label": "Mycotoxin general – Clark sterigmatocystin 2",  "base": 96000},
    {"label": "Mycotoxin general – Clark sterigmatocystin 3",  "base": 126000},
    {"label": "Mycotoxin general – Clark sterigmatocystin 4",  "base": 133000},
    {"label": "Mycotoxin – Clark zearalenone",  "base": 100000},
    {"label": "Mycotoxin – Clark cytochalasin B 1",  "base": 77000},
    {"label": "Mycotoxin – Clark cytochalasin B 2",  "base": 91000},
    {"label": "Slime mold – Arcyria",  "base": 81000},
    {"label": "Slime mold – Lycogala",  "base": 126000},
    {"label": "Slime mold – Stemonitis",  "base": 211000},
]

# =============================================================================
# HEALING FREQUENCY DATABASE
# =============================================================================
HEALING_FREQUENCY_DATA = [
    {"group": "Core Sacred", "label": "Release",        "base": 396,
     "desc": "Clears fear, guilt, and heaviness — one of the most cited Solfeggio tones"},
    {"group": "Core Sacred", "label": "Connection",     "base": 639,
     "desc": "Harmony and relationships — used widely for social and emotional themes"},
    {"group": "Core Sacred", "label": "Unity",          "base": 963,
     "desc": "Awareness, meditation, and divine connection — the highest Solfeggio tone"},
    {"group": "Solfeggio",   "label": "Foundation",     "base": 174,
     "desc": "Grounding and comfort — widely included in modern 9-tone Solfeggio lists"},
    {"group": "Solfeggio",   "label": "Repair",         "base": 285,
     "desc": "Restoration and regeneration — common in the expanded Solfeggio set"},
    {"group": "Solfeggio",   "label": "Release",        "base": 396,
     "desc": "Clearing fear and negativity — Solfeggio UT tone"},
    {"group": "Solfeggio",   "label": "Change",         "base": 417,
     "desc": "Undoing patterns and transition — Solfeggio RE tone"},
    {"group": "Solfeggio",   "label": "Transformation", "base": 528,
     "desc": "Love, vitality, and the 'miracle tone' — Solfeggio MI tone"},
    {"group": "Solfeggio",   "label": "Connection",     "base": 639,
     "desc": "Relationships and communication — Solfeggio FA tone"},
    {"group": "Solfeggio",   "label": "Expression",     "base": 741,
     "desc": "Clarity and self-expression — Solfeggio SOL tone"},
    {"group": "Solfeggio",   "label": "Intuition",      "base": 852,
     "desc": "Insight and inner balance — Solfeggio LA tone"},
    {"group": "Solfeggio",   "label": "Unity",          "base": 963,
     "desc": "Awareness, meditation, and spiritual focus — Solfeggio TI tone"},
    {"group": "Angel Numbers", "label": "Alignment",    "base": 111,
     "desc": "Meditation and focus — 111 alignment frequency"},
    {"group": "Angel Numbers", "label": "Balance",      "base": 222,
     "desc": "Calm and partnership — 222 balance frequency"},
    {"group": "Angel Numbers", "label": "Guidance",     "base": 333,
     "desc": "Creativity and support — 333 guidance frequency"},
    {"group": "Angel Numbers", "label": "Protection",   "base": 444,
     "desc": "Stability and reassurance — 444 protection frequency"},
    {"group": "Angel Numbers", "label": "Change",       "base": 555,
     "desc": "Transition and growth — 555 change vibration"},
    {"group": "Angel Numbers", "label": "Rebalance",    "base": 666,
     "desc": "Shadow work and centring — 666 rebalance frequency"},
    {"group": "Angel Numbers", "label": "Wisdom",       "base": 777,
     "desc": "Insight and intuition — 777 wisdom frequency"},
    {"group": "Angel Numbers", "label": "Abundance",    "base": 888,
     "desc": "Flow, completion, and prosperity — 888 abundance frequency"},
    {"group": "Angel Numbers", "label": "Closure",      "base": 999,
     "desc": "Completion and release — 999 closure frequency"},
    {"group": "Earth",       "label": "Schumann",       "base": 7.83,
     "desc": "Schumann resonance — relaxation and grounding; often used in meditation audio"},
    {"group": "Brainwave",   "label": "Delta",          "base": 2,
     "desc": "Deep rest — centre of 0.5–4 Hz delta band; sleepy, restorative ambience"},
    {"group": "Brainwave",   "label": "Theta",          "base": 6,
     "desc": "Meditation — centre of 4–8 Hz theta band; deep relaxation and imagery"},
    {"group": "Brainwave",   "label": "Alpha",          "base": 10,
     "desc": "Calm focus — centre of 8–12 Hz alpha band; relaxed alertness"},
    {"group": "Brainwave",   "label": "Beta",           "base": 21,
     "desc": "Alert focus — centre of 12–30 Hz beta band; attention and activity"},
]

# =============================================================================
# HARDWARE CONSTANTS
# =============================================================================
def _read_constants_ini() -> dict | None:
    if not os.path.exists(CONSTANTS_INI_PATH):
        return None
    try:
        cfg = configparser.ConfigParser()
        cfg.read(CONSTANTS_INI_PATH, encoding="utf-8")
        if "system" not in cfg:
            return None
        s = cfg["system"]
        return {
            "cpu_name":         s.get("cpu_name",         "unknown"),
            "cpu_count":        int(s.get("cpu_count",    str(os.cpu_count() or 0))),
            "total_ram_gb":     int(s.get("total_ram_gb", "0")),
            "windows_version":  s.get("windows_version",  "unknown"),
            "python_version":   s.get("python_version",   "unknown"),
            "webview2_version": s.get("webview2_version", "unknown"),
            "app_dir":          s.get("app_dir",           _BASE_DIR),
        }
    except Exception:
        return None


def _gather_hw_constants() -> dict:
    ini = _read_constants_ini()
    if ini is not None:
        return ini

    hw: dict = {
        "cpu_name":         "unknown",
        "cpu_count":        os.cpu_count() or 0,
        "total_ram_gb":     0,
        "windows_version":  "unknown",
        "python_version":   "unknown",
        "webview2_version": "unknown",
        "app_dir":          _BASE_DIR,
    }

    try:
        r = subprocess.run(
            ["wmic", "cpu", "get", "Name"],
            capture_output=True, text=True, timeout=5,
            creationflags=0x08000000,
        )
        if r.returncode == 0:
            names = [
                ln.strip() for ln in r.stdout.splitlines()
                if ln.strip() and ln.strip().lower() != "name"
            ]
            if names:
                hw["cpu_name"] = names[0]
    except Exception:
        pass

    try:
        import ctypes

        class _MEMSTATUS(ctypes.Structure):
            _fields_ = [
                ("dwLength",                ctypes.c_ulong),
                ("dwMemoryLoad",            ctypes.c_ulong),
                ("ullTotalPhys",            ctypes.c_ulonglong),
                ("ullAvailPhys",            ctypes.c_ulonglong),
                ("ullTotalPageFile",        ctypes.c_ulonglong),
                ("ullAvailPageFile",        ctypes.c_ulonglong),
                ("ullTotalVirtual",         ctypes.c_ulonglong),
                ("ullAvailVirtual",         ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        ms = _MEMSTATUS()
        ms.dwLength = ctypes.sizeof(_MEMSTATUS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
        hw["total_ram_gb"] = round(ms.ullTotalPhys / (1024 ** 3))
    except Exception:
        pass

    try:
        hw["windows_version"] = platform.version()
    except Exception:
        pass

    try:
        import winreg
        WEBVIEW2_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
        reg_paths = [
            (winreg.HKEY_LOCAL_MACHINE,
             rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}"),
            (winreg.HKEY_LOCAL_MACHINE,
             rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}"),
            (winreg.HKEY_CURRENT_USER,
             rf"SOFTWARE\EdgeUpdate\Clients\{WEBVIEW2_GUID}"),
        ]
        for hive, path in reg_paths:
            try:
                key = winreg.OpenKey(hive, path)
                version, _ = winreg.QueryValueEx(key, "pv")
                winreg.CloseKey(key)
                if version and version != "0.0.0.0":
                    hw["webview2_version"] = version
                    break
            except Exception:
                pass
    except Exception:
        pass

    return hw

constants: dict = _gather_hw_constants()

# =============================================================================
# PAGE CONFIG DEFAULTS
# =============================================================================
_PERSISTENT_DEFAULTS = {
    "window_width":  884,
    "window_height": 522,
    "harmonic_multiplier": DEFAULT_HARMONIC_MULTIPLIER,
}

_VIRAL_DEFAULTS = {
    "last_freq":        432,
    "volume":           VOLUME_DEFAULT,   # 10–100
    "duration_index":   0,                # → DURATION_OPTIONS[0] = 15 min
    "play_mode":        "single",         # "single" | "subset"
}

_FUNGAL_DEFAULTS = {
    "last_freq":        464,
    "volume":           VOLUME_DEFAULT,
    "duration_index":   0,
    "play_mode":        "single",
}

_HEALING_DEFAULTS = {
    "last_freq":        396,
    "volume":           VOLUME_DEFAULT,
    "duration_index":   0,
    "play_mode":        "single",         # "single" | "subset" (by group)
}


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_json(path: str, defaults: dict) -> dict:
    _ensure_data_dir()
    if not os.path.exists(path):
        data = dict(defaults)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return data
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        changed = False
        for k, v in defaults.items():
            if k not in data:
                data[k] = v
                changed = True
        if changed:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        return data
    except Exception:
        data = dict(defaults)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return data


def _save_json(path: str, data: dict):
    _ensure_data_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def load_config():
    """Load persistent (window) config. Missing keys filled from defaults."""
    return _load_json(CONFIG_PATH, _PERSISTENT_DEFAULTS)


def save_config(data):
    _save_json(CONFIG_PATH, data)


def load_viral_config():
    return _load_json(VIRAL_CONFIG_PATH, _VIRAL_DEFAULTS)


def save_viral_config(data):
    _save_json(VIRAL_CONFIG_PATH, data)


def load_fungal_config():
    return _load_json(FUNGAL_CONFIG_PATH, _FUNGAL_DEFAULTS)


def save_fungal_config(data):
    _save_json(FUNGAL_CONFIG_PATH, data)


def load_healing_config():
    return _load_json(HEALING_CONFIG_PATH, _HEALING_DEFAULTS)


def save_healing_config(data):
    _save_json(HEALING_CONFIG_PATH, data)


def create_default_configs():
    """Create all default JSON files (used by installer)."""
    load_config()
    load_viral_config()
    load_fungal_config()
    load_healing_config()
    return True


def duration_minutes_from_index(idx: int) -> int:
    idx = max(0, min(len(DURATION_OPTIONS) - 1, int(idx)))
    return DURATION_OPTIONS[idx]


def volume_gain_from_ui(ui_vol: int | float) -> float:
    """Map 10–100 UI volume to 0.10–1.00 gain."""
    v = max(VOLUME_MIN, min(VOLUME_MAX, float(ui_vol)))
    return v / 100.0


# =============================================================================
# AUDIO DEVICE DIAGNOSTICS
# =============================================================================
def print_audio_diagnostics():
    """
    Query PortAudio / sounddevice and print device list + default output.
    Returns the default output device index (or None on failure).
    """
    try:
        import sounddevice as sd
    except ImportError:
        print("[Audio] sounddevice not available — cannot list devices.")
        return None

    print("-" * 60)
    print("[Audio] -- Device diagnostics --")
    try:
        print(f"[Audio] PortAudio: {sd.get_portaudio_version()}")
    except Exception as e:
        print(f"[Audio] PortAudio version unavailable: {e}")

    try:
        default = sd.default.device
        print(f"[Audio] sd.default.device = {default}")
    except Exception:
        default = [None, None]
        print("[Audio] sd.default.device = unknown")

    # Resolve default OUTPUT index
    out_idx = None
    if isinstance(default, (list, tuple)) and len(default) >= 2:
        out_idx = default[1]
    elif isinstance(default, int):
        out_idx = default

    devices = []
    try:
        devices = sd.query_devices()
    except Exception as e:
        print(f"[Audio] query_devices failed: {e}")
        print("[Audio] -- End diagnostics --")
        print("-" * 60)
        return None

    # Print default output summary
    if out_idx is not None and 0 <= out_idx < len(devices):
        d = devices[out_idx]
        name = d.get("name", "?")
        hostapi = d.get("hostapi", "?")
        try:
            host_name = sd.query_hostapis(hostapi).get("name", str(hostapi))
        except Exception:
            host_name = str(hostapi)
        print(f"[Audio] Default OUTPUT -> index={out_idx}  name='{name}'  hostapi={host_name}")
    else:
        print(f"[Audio] Default OUTPUT -> index={out_idx}  (unresolved)")

    # List all devices that have output channels
    out_devs = []
    for i, d in enumerate(devices):
        if d.get("max_output_channels", 0) > 0:
            out_devs.append((i, d))

    print(f"[Audio] {len(out_devs)} output device(s):")
    for i, d in out_devs:
        ch = d.get("max_output_channels", 0)
        sr = int(d.get("default_samplerate", 0) or 0)
        name = d.get("name", "?")
        mark = "  <-- DEFAULT" if i == out_idx else ""
        print(f"[Audio]   [{i}] {name}  ({ch} ch, {sr} Hz){mark}")

    print("[Audio] -- End diagnostics --")
    print("-" * 60)
    return out_idx


def get_default_output_device():
    """Return current default output device index, or None."""
    try:
        import sounddevice as sd
        default = sd.default.device
        if isinstance(default, (list, tuple)) and len(default) >= 2:
            return default[1]
        if isinstance(default, int):
            return default
    except Exception:
        pass
    return None
