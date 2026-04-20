"""
launcher.py – Main entry point for Harmonic-Healer.
Handles startup, dependency checks, initialization, and graceful shutdown.
"""
print("Starting Imports...")
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # FIXED: was 'file'
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def startup():
    # Raise recursion limit BEFORE pywebview starts.
    # pywebview's JS-bridge property-walker traverses the WebView2 COM object
    # tree, which contains circular back-references.  Python's default 1000-frame
    # limit is too low — it triggers a RecursionError that corrupts bridge setup,
    # producing the "[pywebview] maximum recursion depth exceeded" log spam and
    # leaving pywebview.api in a state where API methods are unreachable from JS.
    sys.setrecursionlimit(5000)

    print("Initializing Harmonic-Healer...")
    missing = []
    for lib in ("webview", "numpy", "sounddevice"):
        try:
            __import__(lib)  # FIXED: was import(lib)
        except ImportError:
            missing.append(lib)

    if missing:
        print(f"\n[CRITICAL ERROR] Missing libraries: {', '.join(missing)}")
        print("Please run the Batch Menu — Option 2 (Install Requirements).")
        input("\nPress Enter to exit...")
        sys.exit(1)

    from scripts import configure, displays

    data_dir = os.path.join(BASE_DIR, "data")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    config = configure.load_config()
    print("Configuration loaded successfully.")
    print("Starting GUI...\n")
    print("-" * 60)

    displays.main_loop(config)

    print("-" * 60)
    print("\n✓ Harmonic-Healer shutdown complete.")
    print("  Audio stream: STOPPED")
    print("  Configuration: SAVED")
    print("  Thank you for using Harmonic-Healer.\n")


if __name__ == "__main__":  # FIXED: was 'if name == " main ":'
    print("Starting main function...")
    try:
        startup()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user (Ctrl+C).")
        print("Running emergency shutdown...")
        try:
            from scripts import generator
            gen = generator.SoundGenerator()
            gen.stop_stream()
        except Exception:
            pass
        print("Shutdown complete. Goodbye.\n")
    except Exception as exc:
        print(f"\n[UNEXPECTED ERROR] {exc}")
        print("Running emergency shutdown...")
        try:
            from scripts import generator
            gen = generator.SoundGenerator()
            gen.stop_stream()
        except Exception:
            pass
        input("\nPress Enter to exit...")
