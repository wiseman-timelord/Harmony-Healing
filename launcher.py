"""
launcher.py – Main entry point for Harmony-Healing.
Handles startup, dependency checks, audio diagnostics, initialization, and graceful shutdown.
"""
print("Starting Imports...")
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def startup():
    # Raise recursion limit BEFORE pywebview starts.
    # pywebview's JS-bridge property-walker traverses the WebView2 COM object
    # tree, which contains circular back-references.  Python's default 1000-frame
    # limit is too low — it triggers a RecursionError that corrupts bridge setup.
    sys.setrecursionlimit(5000)

    print("Initializing Harmony-Healing...")
    missing = []
    for lib in ("webview", "numpy", "sounddevice"):
        try:
            __import__(lib)
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

    # Ensure all page JSONs exist and load persistent config
    configure.create_default_configs()
    config = configure.load_config()
    print("Configuration loaded successfully.")

    # Device diagnostics at startup (default Windows output selected)
    configure.print_audio_diagnostics()

    print("Starting GUI...\n")
    print("-" * 60)

    displays.main_loop(config)

    print("-" * 60)
    print("\n✓ Harmony-Healing shutdown complete.")
    print("  Audio stream: STOPPED")
    print("  Configuration: SAVED")
    print("  Thank you for using Harmony-Healing.\n")


if __name__ == "__main__":
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