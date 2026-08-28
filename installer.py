import subprocess
import sys
import os
import shutil
import platform
import time
import json
import configparser  # stdlib only — no project imports in this file

def print_header(text):
    print("=" * 80)
    print(f"    Harmony-Healing : {text}")
    print("=" * 80)

def menu():
    print_header("Installation")
    print("    1. Purge Install  (remove venv, reinstall everything)")
    print("    2. Check / Install  (fix broken or missing packages)")
    print("    3. Replace JSON  (reset persistent + viral/fungal/healing defaults)")
    print("=" * 80)
    choice = input("Selection; Menu Options = 1-3, Abandon Install = A: ")
    return choice.strip().upper()

# ---------------------------------------------------------------------------
# CPU Feature Detection (Windows-focused)
# ---------------------------------------------------------------------------
def detect_cpu_features() -> dict:
    """Detect CPU instruction set support on Windows."""
    features = {
        'sse3': False, 'ssse3': False, 'sse41': False, 'sse42': False,
        'popcnt': False, 'avx': False, 'avx2': False, 'x86_64_v2': False
    }
    if platform.system() != "Windows":
        # Non-Windows: assume modern enough for x86_64-v2
        features.update({'sse3': True, 'ssse3': True, 'x86_64_v2': True})
        return features
    try:
        result = subprocess.run(
            ["wmic", "cpu", "get", "Name"],
            capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        cpu_name = result.stdout.lower() if result.returncode == 0 else " "

        if "core2" in cpu_name or "core 2" in cpu_name or "x3900" in cpu_name:
            # Core 2 / Athlon X2-era: SSE3 + SSSE3 only, no AVX
            features.update({'sse3': True, 'ssse3': True})
        elif any(x in cpu_name for x in ["i3-", "i5-", "i7-", "i9-"]):
            if "2000" in cpu_name or "3000" in cpu_name:
                # Sandy Bridge / Ivy Bridge: SSE4.2 + POPCNT, no AVX2
                features.update({'sse3': True, 'ssse3': True,
                                  'sse41': True, 'sse42': True, 'popcnt': True})
            elif "4000" in cpu_name or "5000" in cpu_name:
                # Haswell / Broadwell: AVX2 available
                features.update({'sse3': True, 'ssse3': True,
                                  'sse41': True, 'sse42': True,
                                  'popcnt': True, 'avx': True, 'avx2': True})
            else:
                # Skylake+: full x86_64-v2 and AVX2
                features.update({'sse3': True, 'ssse3': True,
                                  'sse41': True, 'sse42': True,
                                  'popcnt': True, 'avx': True, 'avx2': True,
                                  'x86_64_v2': True})
        elif "amd" in cpu_name:
            if "athlon" in cpu_name or "phenom" in cpu_name:
                # Pre-Bulldozer AMD: SSE3/SSSE3 only
                features.update({'sse3': True, 'ssse3': True})
            else:
                # Ryzen and Zen-series: full support
                features.update({'sse3': True, 'ssse3': True,
                                  'sse41': True, 'sse42': True,
                                  'popcnt': True, 'avx': True, 'avx2': True,
                                  'x86_64_v2': True})
        else:
            # Unknown/generic: safe minimum
            features.update({'sse3': True, 'ssse3': True})

    except Exception:
        features.update({'sse3': True, 'ssse3': True})

    # Derive x86_64-v2 composite flag
    if all([features['sse3'], features['ssse3'],
            features['sse41'], features['sse42'], features['popcnt']]):
        features['x86_64_v2'] = True

    return features

def detect_webview2_version() -> str:
    """
    Read the installed Edge WebView2 runtime version from the Windows registry.
    Checks HKLM (system-wide) and HKCU (per-user) in both 32- and 64-bit views.
    Returns the version string, or 'not_installed' if the runtime is absent.
    """
    try:
        import winreg
    except ImportError:
        return "unavailable"

    # GUID for the WebView2 Evergreen runtime
    WEBVIEW2_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    reg_paths = [
        (winreg.HKEY_LOCAL_MACHINE,
         rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}"),
        (winreg.HKEY_LOCAL_MACHINE,
         rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}"),
        (winreg.HKEY_CURRENT_USER,
         rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}"),
    ]
    for hive, path in reg_paths:
        try:
            key = winreg.OpenKey(hive, path)
            version, _ = winreg.QueryValueEx(key, "pv")
            winreg.CloseKey(key)
            if version and version != "0.0.0.0":
                return version
        except Exception:
            pass
    return "not_installed"


def create_constants_ini():
    """
    Detect system info at install time and write to data/constants.ini.
    The main program reads this file at startup so it does not need to
    re-detect hardware on every launch.
    """
    # ── CPU name ─────────────────────────────────────────────────────────────
    cpu_name = "unknown"
    try:
        r = subprocess.run(
            ["wmic", "cpu", "get", "Name"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if r.returncode == 0:
            names = [ln.strip() for ln in r.stdout.splitlines()
                     if ln.strip() and ln.strip().lower() != "name"]
            if names:
                cpu_name = names[0]
    except Exception:
        pass

    # ── Thread count ─────────────────────────────────────────────────────────
    cpu_count = os.cpu_count() or 0

    # ── Physical RAM (via ctypes GlobalMemoryStatusEx) ────────────────────────
    total_ram_gb = 0
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
        total_ram_gb = round(ms.ullTotalPhys / (1024 ** 3))
    except Exception:
        pass

    windows_version  = platform.version()
    python_version   = sys.version.split()[0]
    webview2_version = detect_webview2_version()
    app_dir          = os.path.abspath(".")

    cfg = configparser.ConfigParser()
    cfg["system"] = {
        "cpu_name":        cpu_name,
        "cpu_count":       str(cpu_count),
        "total_ram_gb":    str(total_ram_gb),
        "windows_version": windows_version,
        "python_version":  python_version,
        "webview2_version":webview2_version,
        "app_dir":         app_dir,
    }

    os.makedirs("data", exist_ok=True)
    ini_path = os.path.join("data", "constants.ini")
    with open(ini_path, "w", encoding="utf-8") as f:
        cfg.write(f)

    print(f"✓ constants.ini written: {ini_path}")
    print(f"  CPU Name:    {cpu_name}")
    print(f"  Threads:     {cpu_count}")
    print(f"  RAM:         {total_ram_gb} GB")
    print(f"  Windows:     {windows_version}")
    print(f"  Python:      {python_version}")
    print(f"  WebView2:    {webview2_version}")
    print(f"  App Dir:     {app_dir}")


def get_numpy_spec(cpu_features: dict) -> str:
    return "numpy>=2.0" if cpu_features.get('x86_64_v2') else "numpy==1.26.4"

# ---------------------------------------------------------------------------
# Virtual environment helpers
# ---------------------------------------------------------------------------
def _venv_python() -> str:
    """Return path to Python interpreter inside the virtual environment."""
    if os.name == "nt":
        return os.path.join(".venv", "Scripts", "python.exe")
    return os.path.join(".venv", "bin", "python")

def _venv_path() -> str:
    """Return path to virtual environment directory."""
    return ".venv"

def purge_venv() -> bool:
    """Remove existing virtual environment if present, with retry logic."""
    venv_path = _venv_path()
    if os.path.exists(venv_path):
        print("Removing old virtual environment...")
        print(f"  Path: {os.path.abspath(venv_path)}")
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                shutil.rmtree(venv_path)
                print("  Purge complete.")
                return True
            except PermissionError as e:
                if attempt < max_retries:
                    print(f"  Attempt {attempt} failed - files may be in use. Retrying in 2 seconds...")
                    time.sleep(2)
                else:
                    print("  ERROR: Could not remove .venv after 3 attempts.")
                    print(f"  Debug: {e}")
                    return False
            except Exception as e:
                print(f"  ERROR: Unexpected error during purge: {e}")
                return False
    else:
        print("No virtual environment found to purge.")
        return True

def create_venv() -> bool:
    """Create a new virtual environment."""
    print("Creating virtual environment...")
    try:
        subprocess.check_call([sys.executable, "-m", "venv", ".venv"])
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to create virtual environment: {e}")
        return False
    except FileNotFoundError:
        print("ERROR: Python executable not found.")
        return False
    venv_py = _venv_python()
    print("Upgrading pip...")
    try:
        subprocess.check_call([venv_py, "-m", "pip", "install", "--upgrade", "pip"])
    except subprocess.CalledProcessError:
        print("Warning: pip upgrade failed — continuing.")
    return True

def install_packages(cpu_features: dict):
    """Install required packages into the virtual environment, CPU-aware."""
    print("Installing required packages...")
    venv_py = _venv_python()
    numpy_spec = get_numpy_spec(cpu_features)
    packages = [
        ("pywebview>=4.4,<5.0", "Edge WebView2 desktop wrapper"),
        (numpy_spec,          "Numerical computing"),
        ("sounddevice",       "PortAudio bindings"),
    ]
    all_ok = True
    for pkg_spec, description in packages:
        print(f"  Installing {pkg_spec}... ({description})")
        try:
            subprocess.check_call([venv_py, "-m", "pip", "install", pkg_spec])
        except subprocess.CalledProcessError as e:
            print(f"  Warning: Failed to install {pkg_spec}. Debug: {e}")
            all_ok = False
    return all_ok

def ensure_package_init():
    """Create __init__.py in scripts/ directory if absent."""
    init_path = os.path.join("scripts", "__init__.py")
    if not os.path.exists(init_path):
        os.makedirs("scripts", exist_ok=True)
        with open(init_path, "w", encoding="utf-8") as f:
            f.write("# Harmony-Healing scripts package\n")

# ---------------------------------------------------------------------------
# JSON config helper — STANDALONE, no project-module imports.
# Creates persistent.json (window) + viral.json + fungal.json + healing.json
# ---------------------------------------------------------------------------
def create_json() -> bool:
    """
    Regenerate data/*.json defaults.
    Standalone — does NOT import from scripts.configure.
    """
    persistent = {
        "window_width": 884,
        "window_height": 522,
        "harmonic_multiplier": 11,
    }
    viral = {
        "last_freq": 432,
        "volume": 50,           # UI 10–100
        "duration_index": 0,    # → 15 min
        "play_mode": "single",
    }
    fungal = {
        "last_freq": 464,
        "volume": 50,
        "duration_index": 0,
        "play_mode": "single",
    }
    healing = {
        "last_freq": 396,
        "volume": 50,
        "duration_index": 0,
        "play_mode": "single",
    }

    try:
        os.makedirs("data", exist_ok=True)
        files = {
            "persistent.json": persistent,
            "viral.json": viral,
            "fungal.json": fungal,
            "healing.json": healing,
        }
        for name, data in files.items():
            path = os.path.join("data", name)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            print(f"✓ JSON created: data/{name}")
        print(f"  window: {persistent['window_width']}×{persistent['window_height']}")
        print(f"  volume default: 50 (0.50 gain)  duration default: 15 min")
        return True
    except Exception as exc:
        print(f"ERROR: Could not create JSON config: {exc}")
        return False

def create_runtime_env_file(cpu_features: dict):
    """
    Create data/.env to disable unsupported NumPy SIMD flags at runtime.
    Only written for legacy CPUs that lack x86_64-v2 support.
    """
    if not cpu_features.get('x86_64_v2'):
        env_content = (
            "# Harmony-Healing Runtime Environment (Legacy CPU Mode)\n"
            "NPY_DISABLE_CPU_FEATURES=AVX,AVX2,AVX512F,AVX512_CD,"
            "AVX512_KNL,AVX512_KNM,AVX512_SKX,AVX512_CLX,"
            "AVX512_CNL,AVX512_ICL\n"
        )
        env_path = os.path.join("data", ".env")
        os.makedirs("data", exist_ok=True)
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(env_content)
        print(f"✓ Legacy CPU env file written: {env_path}")

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print_header("Installer Started")
    print(f"Python:            {sys.version}")
    print(f"Platform:          {sys.platform}")
    print(f"Working directory: {os.getcwd()}")
    print("\nDetecting CPU capabilities...")
    cpu_features = detect_cpu_features()
    active = [k for k, v in cpu_features.items() if v]
    print(f"CPU feature flags: {active}")
    print()

    choice = menu()

    if choice == "1":
        print("\n[Mode: Purge Install]")
        if purge_venv():
            if create_venv():
                install_packages(cpu_features)
                ensure_package_init()
                create_json()
                create_constants_ini()
                create_runtime_env_file(cpu_features)
        else:
            print("Purge failed. Aborting installation.")

    elif choice == "2":
        print("\n[Mode: Check / Install]")
        if not os.path.exists(".venv"):
            print("Virtual environment not found. Creating one...")
            if not create_venv():
                input("Press Enter to continue...")
                sys.exit(1)
        install_packages(cpu_features)
        ensure_package_init()
        create_constants_ini()
        create_runtime_env_file(cpu_features)

    elif choice == "3":
        print("\n[Mode: Replace JSON]")
        create_json()

    elif choice == "A":
        print("Installation abandoned by user.")

    else:
        print(f"Invalid selection: '{choice}'. Please choose 1, 2, 3, or A.")

    print("\n" + "=" * 80)
    input("Press Enter to exit...")
