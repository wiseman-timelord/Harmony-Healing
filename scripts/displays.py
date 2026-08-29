"""
displays.py – GUI frontend using pywebview with Edge WebView2 backend.
Harmony-Healing

Tabs: Anti-Viral | Anti-Fungal | Healing | Info / Debug

Bridge safety note
------------------
pywebview serialises every *public* attribute of the js_api object into the
JavaScript API proxy when the window loads.  All internal state uses _ prefix
so pywebview ignores it.  Only explicitly defined public def methods are exposed.
"""
import sys
import webview
import threading
import time
from . import configure
from . import generator


# =============================================================================
# JS/Python Bridge API
# =============================================================================
class Api:
    def __init__(self):
        self._gen            = generator.SoundGenerator()
        self._viral_cfg      = configure.load_viral_config()
        self._fungal_cfg     = configure.load_fungal_config()
        self._healing_cfg    = configure.load_healing_config()
        self._frequencies    = configure.FREQUENCY_DATA
        self._fungus_freqs   = configure.FUNGUS_FREQUENCY_DATA
        self._healing_freqs  = configure.HEALING_FREQUENCY_DATA
        self._window         = None
        self._stop_timer     = None
        self._subset_thread  = None
        self._should_stop_subset = False
        self._stop_event     = None

    def _set_window(self, window):
        self._window = window

    # ── Config ────────────────────────────────────────────────────────────────
    def get_viral_config(self):
        return self._viral_cfg

    def get_fungal_config(self):
        return self._fungal_cfg

    def get_healing_config(self):
        return self._healing_cfg

    def get_frequencies(self):
        return self._frequencies

    def get_fungus_frequencies(self):
        return self._fungus_freqs

    def get_healing_frequencies(self):
        return self._healing_freqs

    def get_duration_options(self):
        return list(configure.DURATION_OPTIONS)

    def get_constants(self):
        hw = configure.constants
        return {
            "cpu_name":         hw.get("cpu_name",         "unknown"),
            "cpu_count":        hw.get("cpu_count",          0),
            "total_ram_gb":     hw.get("total_ram_gb",        0),
            "windows_version":  hw.get("windows_version",   "unknown"),
            "python_version":   sys.version.split()[0],
            "webview_version":  hw.get("webview2_version",  "unknown"),
            "app_dir":          hw.get("app_dir",            "unknown"),
        }

    def diagnose_audio(self):
        """Re-run device diagnostics (called from Info tab or on Start)."""
        idx = configure.print_audio_diagnostics()
        return {"default_output": idx}

    # ── Shared treatment helpers ──────────────────────────────────────────────
    def _run_subset_sequence(self, freq_list, volume_gain, duration_per_freq_min,
                             harmonic_mult, play_harmonic=True):
        """Play each entry in freq_list for duration_per_freq_min minutes."""
        duration_seconds = duration_per_freq_min * 60
        mode = "harmonic" if play_harmonic else "pure sine"
        for idx, freq_entry in enumerate(freq_list):
            if self._should_stop_subset:
                print(f"Subset playback interrupted at step {idx + 1}/{len(freq_list)}")
                break
            freq  = float(freq_entry["base"])
            label = freq_entry.get("label", f"{freq} Hz")
            try:
                print(f"Subset step {idx + 1}/{len(freq_list)}: {label} @ {freq} Hz ({mode})")
                self._gen.start_stream(freq, harmonic_mult, volume_gain,
                                       play_harmonic=play_harmonic)
                time.sleep(duration_seconds)
                self._gen.stop_stream()
            except Exception as e:
                print(f"Error playing subset freq {freq}: {e}")
                break
        self._should_stop_subset = False
        print("Subset sequence complete.")

    def _start_harmonic_page(self, params, page: str):
        """Shared start for Anti-Viral / Anti-Fungal (harmonic blend)."""
        try:
            # Re-detect devices every start so user can change default output
            configure.print_audio_diagnostics()

            freq             = float(params.get("freq", 432))
            ui_vol           = int(params.get("volume", configure.VOLUME_DEFAULT))
            volume_gain      = configure.volume_gain_from_ui(ui_vol)
            duration_index   = int(params.get("duration_index", 0))
            duration_minutes = configure.duration_minutes_from_index(duration_index)
            play_mode        = params.get("play_mode", "single")
            subset_key       = params.get("subset_key", None)
            hm               = int(configure.DEFAULT_HARMONIC_MULTIPLIER)

            print(
                f"Starting {page}: {freq} Hz | {hm}th harmonic: {freq * hm:.0f} Hz | "
                f"Vol: {ui_vol}/100 ({volume_gain:.2f}) | Mode: {play_mode} | "
                f"Duration: {duration_minutes} min"
            )

            self.stop_treatment()

            # Persist page settings
            page_cfg = {
                "last_freq":      freq,
                "volume":         ui_vol,
                "duration_index": duration_index,
                "play_mode":      play_mode,
            }
            if page == "viral":
                self._viral_cfg = page_cfg
                configure.save_viral_config(page_cfg)
            else:
                self._fungal_cfg = page_cfg
                configure.save_fungal_config(page_cfg)

            freq_source = self._frequencies if page == "viral" else self._fungus_freqs

            if play_mode == "subset" and subset_key:
                subset_freqs = [f for f in freq_source if f["label"].startswith(subset_key)]
                if subset_freqs:
                    self._should_stop_subset = False
                    self._subset_thread = threading.Thread(
                        target=self._run_subset_sequence,
                        args=(subset_freqs, volume_gain, duration_minutes, hm),
                        daemon=True,
                    )
                    self._subset_thread.start()
                    return {
                        "status": "playing_subset",
                        "count": len(subset_freqs),
                        "total_duration_min": duration_minutes * len(subset_freqs),
                    }
                else:
                    print(f"Warning: No subset frequencies for key '{subset_key}'")
                    play_mode = "single"

            self._gen.start_stream(freq, hm, volume_gain, play_harmonic=True)

            if self._stop_event is not None:
                self._stop_event.set()
            stop_event = threading.Event()
            self._stop_event = stop_event

            def auto_stop(ev=stop_event, mins=duration_minutes):
                cancelled = ev.wait(timeout=mins * 60)
                if cancelled:
                    return
                if self._gen.active:
                    print(f"Auto-stopping {page} treatment after {mins} minutes")
                    self._gen.stop_stream()

            self._stop_timer = threading.Thread(target=auto_stop, daemon=True)
            self._stop_timer.start()

            return {
                "status": "playing",
                "freq": freq,
                "harmonic": freq * hm,
                "duration_min": duration_minutes,
            }
        except Exception as e:
            print(f"Error starting {page}: {e}")
            return {"error": str(e)}

    def start_viral(self, params):
        return self._start_harmonic_page(params, "viral")

    def start_fungal(self, params):
        return self._start_harmonic_page(params, "fungal")

    def start_healing(self, params):
        try:
            configure.print_audio_diagnostics()

            freq             = float(params.get("freq", 396))
            ui_vol           = int(params.get("volume", configure.VOLUME_DEFAULT))
            volume_gain      = configure.volume_gain_from_ui(ui_vol)
            duration_index   = int(params.get("duration_index", 0))
            duration_minutes = configure.duration_minutes_from_index(duration_index)
            play_mode        = params.get("play_mode", "single")
            subset_key       = params.get("subset_key", None)  # group name e.g. "Angel Numbers"

            print(
                f"Starting Healing: {freq} Hz (pure sine) | "
                f"Vol: {ui_vol}/100 ({volume_gain:.2f}) | Mode: {play_mode} | "
                f"Duration: {duration_minutes} min"
            )

            self.stop_treatment()

            page_cfg = {
                "last_freq":      freq,
                "volume":         ui_vol,
                "duration_index": duration_index,
                "play_mode":      play_mode,
            }
            self._healing_cfg = page_cfg
            configure.save_healing_config(page_cfg)

            if play_mode == "subset" and subset_key:
                subset_freqs = [
                    f for f in self._healing_freqs
                    if f.get("group") == subset_key
                ]
                if subset_freqs:
                    self._should_stop_subset = False
                    self._subset_thread = threading.Thread(
                        target=self._run_subset_sequence,
                        args=(subset_freqs, volume_gain, duration_minutes, 11, False),
                        daemon=True,
                    )
                    self._subset_thread.start()
                    return {
                        "status": "playing_subset",
                        "count": len(subset_freqs),
                        "total_duration_min": duration_minutes * len(subset_freqs),
                    }
                else:
                    print(f"Warning: No healing subset for group '{subset_key}'")
                    play_mode = "single"

            self._gen.start_stream(freq, 11, volume_gain, play_harmonic=False)

            if self._stop_event is not None:
                self._stop_event.set()
            stop_event = threading.Event()
            self._stop_event = stop_event

            def auto_stop(ev=stop_event, mins=duration_minutes):
                cancelled = ev.wait(timeout=mins * 60)
                if cancelled:
                    return
                if self._gen.active:
                    print(f"Auto-stopping Healing tone after {mins} minutes")
                    self._gen.stop_stream()

            self._stop_timer = threading.Thread(target=auto_stop, daemon=True)
            self._stop_timer.start()

            return {"status": "playing", "freq": freq, "duration_min": duration_minutes}
        except Exception as e:
            print(f"Error starting healing: {e}")
            return {"error": str(e)}

    def stop_treatment(self):
        print("Stopping audio.")
        if self._stop_event is not None:
            self._stop_event.set()
        self._should_stop_subset = True
        if self._subset_thread and self._subset_thread.is_alive():
            self._subset_thread.join(timeout=1.0)
        self._gen.stop_stream()
        return {"status": "stopped"}

    def update_volume(self, volume):
        """volume may be UI 10–100 or gain 0–1; normalise to gain."""
        v = float(volume)
        if v > 1.0:
            v = configure.volume_gain_from_ui(v)
        self._gen.update_volume(v)
        return {"status": "volume_updated"}

    def shutdown(self):
        print("Shutting down Harmony-Healing...")
        self.stop_treatment()
        print("Audio stream stopped. Goodbye.")


# =============================================================================
# Main GUI Loop
# =============================================================================
def main_loop():
    api = Api()

    # ── Build option lists ────────────────────────────────────────────────────
    freq_options = ""
    for item in api._frequencies:
        label     = item["label"].replace('"', "&quot;")
        base      = item["base"]
        group_key = item["label"].split("\u2013")[0].split(" - ")[0].strip()
        freq_options += f'<option value="{base}" data-key="{group_key}">{label}</option>\n'

    fungus_options = ""
    for item in api._fungus_freqs:
        label     = item["label"].replace('"', "&quot;")
        base      = item["base"]
        group_key = item["label"].split("\u2013")[0].split(" - ")[0].strip()
        fungus_options += f'<option value="{base}" data-key="{group_key}">{label}</option>\n'

    healing_options = ""
    current_group = None
    for item in api._healing_freqs:
        g = item["group"]
        if g != current_group:
            if current_group is not None:
                healing_options += "</optgroup>\n"
            healing_options += f'<optgroup label="{g}">\n'
            current_group = g
        base      = item["base"]
        label     = item["label"]
        desc      = item.get("desc", "").replace('"', "&quot;")
        freq_disp = f"{base:.2f} Hz" if base < 10 else f"{int(base)} Hz"
        healing_options += (
            f'<option value="{base}" data-desc="{desc}" data-group="{g}">'
            f"{freq_disp} \u2013 {label}"
            f"</option>\n"
        )
    if current_group is not None:
        healing_options += "</optgroup>\n"

    win_w = configure.WINDOW_WIDTH_DEFAULT
    win_h = configure.WINDOW_HEIGHT_DEFAULT

    # Page configs
    viral_cfg   = api._viral_cfg
    fungal_cfg  = api._fungal_cfg
    healing_cfg = api._healing_cfg

    v_steps = int(viral_cfg.get("duration_index", 0))
    v_vol   = int(viral_cfg.get("volume", configure.VOLUME_DEFAULT))
    v_mode  = viral_cfg.get("play_mode", "single")
    v_mins  = configure.duration_minutes_from_index(v_steps)

    f_steps = int(fungal_cfg.get("duration_index", 0))
    f_vol   = int(fungal_cfg.get("volume", configure.VOLUME_DEFAULT))
    f_mode  = fungal_cfg.get("play_mode", "single")
    f_mins  = configure.duration_minutes_from_index(f_steps)

    h_steps = int(healing_cfg.get("duration_index", 0))
    h_vol   = int(healing_cfg.get("volume", configure.VOLUME_DEFAULT))
    h_mode  = healing_cfg.get("play_mode", "single")
    h_mins  = configure.duration_minutes_from_index(h_steps)

    duration_js = ",".join(str(x) for x in configure.DURATION_OPTIONS)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{configure.APP_TITLE}</title>
    <style>
        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: #111827; color: #e2e8f0;
            display: flex; justify-content: center; align-items: flex-start;
            padding: 18px 14px 24px; min-height: 100vh;
        }}
        .container {{
            background: #1e293b; border: 1px solid #2d4263; border-radius: 10px;
            box-shadow: 0 6px 28px rgba(0,0,0,0.5); padding: 20px 24px 22px;
            width: 100%; max-width: 860px;
        }}
        .app-title {{
            text-align: center; font-size: 13px; font-weight: 700; color: #38bdf8;
            letter-spacing: 2px; text-transform: uppercase;
            padding-bottom: 14px; margin-bottom: 0; border-bottom: 1px solid #2d4263;
        }}
        .tab-nav {{
            display: flex; gap: 2px; padding: 10px 0 0;
            margin-bottom: 14px; border-bottom: 1px solid #2d4263; flex-wrap: wrap;
        }}
        .tab-btn {{
            padding: 7px 14px; font-size: 11px; font-weight: 700;
            letter-spacing: 0.6px; text-transform: uppercase;
            background: transparent; color: #4a6080;
            border: 1px solid transparent; border-bottom: none;
            border-radius: 6px 6px 0 0; cursor: pointer;
            transition: color 0.15s, background 0.15s, border-color 0.15s;
            transform: none !important; box-shadow: none !important;
        }}
        .tab-btn:hover {{
            color: #94a3b8; background: rgba(45,66,99,0.25); transform: none !important;
        }}
        .tab-btn:active {{ transform: none !important; }}
        .tab-btn.active {{
            color: #38bdf8; background: #1e293b;
            border-color: #2d4263; border-bottom-color: #1e293b; margin-bottom: -1px;
        }}
        .tab-btn.active[data-tab="fungal"]  {{ color: #f59e0b; }}
        .tab-btn.active[data-tab="healing"] {{ color: #22c55e; }}
        .tab-btn.active[data-tab="info"]    {{ color: #a78bfa; }}
        hr {{ border: none; border-top: 1px solid #2d4263; margin: 12px 0; }}
        .row {{
            display: flex; align-items: center; justify-content: center;
            gap: 10px; flex-wrap: wrap; margin: 10px 0;
        }}
        .rl {{
            font-weight: 600; font-size: 13px; color: #94a3b8;
            text-align: right; white-space: nowrap; flex-shrink: 0; min-width: 100px;
        }}
        select {{
            flex: 1; min-width: 220px; max-width: 530px; padding: 7px 10px;
            border: 1px solid #2d4263; border-radius: 5px;
            background: #0f172a; color: #e2e8f0; font-size: 13px;
            cursor: pointer; outline: none; transition: border-color 0.15s;
        }}
        select:focus {{ border-color: #38bdf8; }}
        select option, select optgroup {{ background: #1e293b; color: #e2e8f0; }}
        .mode-switch {{
            display: flex; align-items: center; gap: 7px; flex-shrink: 0;
            padding: 4px 10px; border: 1px solid #2d4263; border-radius: 20px;
            background: rgba(15,23,42,0.55);
        }}
        .ms-label {{
            font-size: 12px; font-weight: 700; letter-spacing: 0.6px;
            text-transform: uppercase; user-select: none; transition: color 0.2s; cursor: pointer;
        }}
        .ms-label.active   {{ color: #38bdf8; }}
        .ms-label.inactive {{ color: #3d5066; }}
        .ms-toggle {{
            position: relative; display: inline-block;
            width: 36px; height: 18px; cursor: pointer; flex-shrink: 0;
        }}
        .ms-toggle input {{ opacity: 0; width: 0; height: 0; position: absolute; }}
        .ms-knob {{
            position: absolute; top: 0; left: 0; right: 0; bottom: 0;
            background: #0f172a; border: 1px solid #2d4263; border-radius: 18px;
            transition: background 0.2s, border-color 0.2s;
        }}
        .ms-knob::before {{
            content: ''; position: absolute; width: 12px; height: 12px;
            left: 2px; top: 2px; background: #38bdf8; border-radius: 50%;
            transition: transform 0.2s, background 0.2s;
            box-shadow: 0 0 5px rgba(56,189,248,0.5);
        }}
        .ms-toggle input:checked + .ms-knob {{ background: #0f172a; border-color: #38bdf8; }}
        .ms-toggle input:checked + .ms-knob::before {{ transform: translateX(18px); background: #38bdf8; }}
        .freq-pair {{
            display: flex; align-items: flex-end; gap: 10px;
            flex-wrap: wrap; justify-content: center;
        }}
        .freq-block {{ display: flex; flex-direction: column; align-items: center; gap: 3px; }}
        .freq-tag {{ font-size: 10px; color: #64748b; letter-spacing: 1.2px; text-transform: uppercase; }}
        .freq-box {{
            background: #0f172a; border: 1px solid #2d4263; border-radius: 5px;
            font-family: 'Consolas','Courier New',monospace; font-size: 15px; color: #7dd3fc;
            padding: 7px 18px; text-align: center; min-width: 140px;
        }}
        .freq-box.fungal {{ color: #fbbf24; border-color: #78350f; }}
        .freq-box.heal {{ color: #86efac; border-color: #1a4731; }}
        .freq-arrow {{ font-size: 15px; color: #38bdf8; padding-bottom: 8px; flex-shrink: 0; }}
        .vol-wrap, .tl-wrap {{
            display: flex; align-items: center; gap: 8px; padding: 5px 12px;
            border: 1px solid #2d4263; border-radius: 5px;
            background: rgba(15,23,42,0.5); flex-shrink: 0;
        }}
        .vol-lbl, .tl-lbl {{ font-size: 13px; font-weight: 600; color: #94a3b8; white-space: nowrap; }}
        input[type="range"] {{ width: 100px; cursor: pointer; accent-color: #38bdf8; }}
        input[type="range"].fungal-range {{ accent-color: #f59e0b; }}
        input[type="range"].heal-range {{ accent-color: #22c55e; }}
        .val-readout {{
            font-family: 'Consolas','Courier New',monospace; font-size: 13px;
            color: #7dd3fc; min-width: 42px; text-align: right; white-space: nowrap;
        }}
        .val-readout.fungal {{ color: #fbbf24; }}
        .val-readout.heal {{ color: #86efac; }}
        .canvas-wrap {{
            margin: 12px 0 8px; border: 1px solid #2d4263;
            border-radius: 7px; overflow: hidden; background: #070d1a;
        }}
        canvas {{ display: block; width: 100%; height: 130px; }}
        .subset-info {{
            font-size: 11px; color: #64748b; white-space: nowrap; flex-shrink: 0;
            font-family: 'Consolas','Courier New',monospace;
            letter-spacing: 0.4px; padding: 3px 0; transition: color 0.2s;
        }}
        .heal-desc {{
            text-align: center; font-size: 12px; color: #94a3b8; font-style: italic;
            padding: 4px 14px 2px; min-height: 20px; letter-spacing: 0.3px;
        }}
        button {{
            padding: 10px 28px; font-size: 14px; font-weight: 700; letter-spacing: 0.5px;
            border-radius: 6px; border: 1px solid transparent; cursor: pointer;
            transition: background 0.15s, transform 0.1s, box-shadow 0.15s;
        }}
        button:hover {{ transform: translateY(-1px); }}
        button:active {{ transform: translateY(0px); }}
        .btn-start {{ background: #15643a; color: #d1fae5; border-color: #22c55e; }}
        .btn-start:hover {{ background: #16a34a; box-shadow: 0 4px 14px rgba(34,197,94,0.35); }}
        .btn-start:disabled {{
            background: #1c3028; color: #4d7a60; border-color: #1c3028;
            cursor: not-allowed; transform: none; box-shadow: none;
        }}
        .btn-stop {{ background: #641515; color: #fee2e2; border-color: #ef4444; }}
        .btn-stop:hover {{ background: #dc2626; box-shadow: 0 4px 14px rgba(239,68,68,0.35); }}
        .btn-stop:disabled {{
            background: #2d1c1c; color: #7a4d4d; border-color: #2d1c1c;
            cursor: not-allowed; transform: none; box-shadow: none;
        }}
        .status-bar {{
            text-align: center; padding: 9px 14px; background: #0f172a;
            border-left: 3px solid #38bdf8; border-radius: 0 5px 5px 0;
            font-family: 'Consolas','Courier New',monospace;
            font-size: 12px; color: #7dd3fc; letter-spacing: 0.8px; margin-top: 8px;
        }}
        .status-bar.fungal {{ border-left-color: #f59e0b; color: #fbbf24; }}
        .status-bar.heal {{ border-left-color: #22c55e; color: #86efac; }}
        .us-warn {{
            text-align: center; font-size: 12px; color: #fbbf24;
            background: rgba(251,191,36,0.08); border: 1px solid rgba(251,191,36,0.3);
            border-radius: 5px; padding: 6px 14px; margin: 4px 0;
        }}
        .info-card {{
            background: #0f172a; border: 1px solid #2d4263;
            border-radius: 7px; padding: 18px 22px; margin-bottom: 14px;
        }}
        .info-app-name {{
            font-size: 20px; font-weight: 700; color: #38bdf8;
            text-align: center; letter-spacing: 1px; margin-bottom: 5px;
        }}
        .info-subtitle {{ font-size: 13px; color: #94a3b8; text-align: center; margin-bottom: 14px; }}
        .info-links {{ text-align: center; font-size: 13px; color: #94a3b8; line-height: 2.0; }}
        .info-links p {{ margin: 0; }}
        .info-links a {{ color: #7799dd; text-decoration: none; }}
        .info-links a:hover {{ text-decoration: underline; color: #93b8f0; }}
        .info-sep {{ color: #3d5066; margin: 0 6px; }}
        .info-card-title {{
            font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 1.5px;
            text-transform: uppercase; margin-bottom: 10px;
            padding-bottom: 6px; border-bottom: 1px solid #1e3a5f;
        }}
        .constants-pre {{
            font-family: 'Consolas','Courier New',monospace; font-size: 12px; color: #7dd3fc;
            background: #070d1a; border: 1px solid #1e3a5f; border-radius: 4px;
            padding: 12px 14px; white-space: pre; min-height: 136px;
            line-height: 1.75; overflow-x: auto;
        }}
        .info-refresh-row {{ display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }}
        .info-btn {{
            padding: 5px 16px !important; font-size: 12px !important;
            font-weight: 600 !important; background: #1e293b !important;
            color: #94a3b8 !important; border: 1px solid #2d4263 !important;
            border-radius: 5px !important; letter-spacing: 0.4px !important;
            transform: none !important; box-shadow: none !important;
        }}
        .info-btn:hover {{
            background: #2d4263 !important; color: #e2e8f0 !important;
            transform: none !important; box-shadow: none !important;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="app-title">&#9877; Harmony-Healing</div>

        <div class="tab-nav">
            <button class="tab-btn active" data-tab="viral">Anti-Viral</button>
            <button class="tab-btn" data-tab="fungal">Anti-Fungal</button>
            <button class="tab-btn" data-tab="healing">&#10022; Healing</button>
            <button class="tab-btn" data-tab="info">&#9432; Info / Debug</button>
        </div>

        <!-- ═══ Anti-Viral ═══ -->
        <div id="tab-viral" class="tab-panel">
            <div class="row">
                <span class="rl">Virus Type:</span>
                <select id="viralSelect">{freq_options}</select>
                <span class="rl">Playback:</span>
                <div class="mode-switch">
                    <span class="ms-label active" id="vMsSingle">Single</span>
                    <label class="ms-toggle" title="Single: one frequency. Subset: all in the same group sequentially.">
                        <input type="checkbox" id="viralPlayMode" {'checked' if v_mode == 'subset' else ''}>
                        <span class="ms-knob"></span>
                    </label>
                    <span class="ms-label inactive" id="vMsSubset">Subset</span>
                </div>
            </div>
            <div class="row">
                <div class="tl-wrap">
                    <span class="tl-lbl">Duration:</span>
                    <input type="range" id="viralDuration" min="0" max="5" step="1" value="{v_steps}">
                    <span class="val-readout" id="viralDurationVal">{v_mins} min</span>
                    <span id="viralSubsetInfo" class="subset-info"></span>
                </div>
                <div class="vol-wrap">
                    <span class="vol-lbl">Volume:</span>
                    <input type="range" id="viralVolume" min="10" max="100" step="10" value="{v_vol}">
                    <span class="val-readout" id="viralVolumeVal">{v_vol / 100:.2f}</span>
                </div>
            </div>
            <div class="row">
                <span class="rl">Frequency:</span>
                <div class="freq-pair">
                    <div class="freq-block">
                        <span class="freq-tag">Base</span>
                        <div class="freq-box" id="viralBase">432 Hz</div>
                    </div>
                    <span class="freq-arrow">&times;11 &rarr;</span>
                    <div class="freq-block">
                        <span class="freq-tag">11th Harmonic</span>
                        <div class="freq-box" id="viralHarm">4,752 Hz</div>
                    </div>
                </div>
            </div>
            <div id="viralUsWarn" class="us-warn" style="display:none;">
                &#9888; Frequency &gt;20 kHz — standard speakers silent. RF / plasma required.
            </div>
            <hr>
            <div class="canvas-wrap"><canvas id="viralCanvas"></canvas></div>
            <div style="display:flex;gap:14px;justify-content:center;margin:12px 0 10px;">
                <button class="btn-start" id="viralStart">&#9654;&nbsp; Start Treatment</button>
                <button class="btn-stop" id="viralStop" disabled>&#9632;&nbsp; Stop</button>
            </div>
            <div id="viralStatus" class="status-bar">SYSTEM READY</div>
        </div>

        <!-- ═══ Anti-Fungal ═══ -->
        <div id="tab-fungal" class="tab-panel" style="display:none;">
            <div class="row">
                <span class="rl">Fungus Type:</span>
                <select id="fungalSelect">{fungus_options}</select>
                <span class="rl">Playback:</span>
                <div class="mode-switch">
                    <span class="ms-label active" id="fMsSingle">Single</span>
                    <label class="ms-toggle" title="Single: one frequency. Subset: all in the same group sequentially.">
                        <input type="checkbox" id="fungalPlayMode" {'checked' if f_mode == 'subset' else ''}>
                        <span class="ms-knob"></span>
                    </label>
                    <span class="ms-label inactive" id="fMsSubset">Subset</span>
                </div>
            </div>
            <div class="row">
                <div class="tl-wrap">
                    <span class="tl-lbl">Duration:</span>
                    <input type="range" class="fungal-range" id="fungalDuration" min="0" max="5" step="1" value="{f_steps}">
                    <span class="val-readout fungal" id="fungalDurationVal">{f_mins} min</span>
                    <span id="fungalSubsetInfo" class="subset-info"></span>
                </div>
                <div class="vol-wrap">
                    <span class="vol-lbl">Volume:</span>
                    <input type="range" class="fungal-range" id="fungalVolume" min="10" max="100" step="10" value="{f_vol}">
                    <span class="val-readout fungal" id="fungalVolumeVal">{f_vol / 100:.2f}</span>
                </div>
            </div>
            <div class="row">
                <span class="rl">Frequency:</span>
                <div class="freq-pair">
                    <div class="freq-block">
                        <span class="freq-tag">Base</span>
                        <div class="freq-box fungal" id="fungalBase">464 Hz</div>
                    </div>
                    <span class="freq-arrow" style="color:#f59e0b;">&times;11 &rarr;</span>
                    <div class="freq-block">
                        <span class="freq-tag">11th Harmonic</span>
                        <div class="freq-box fungal" id="fungalHarm">5,104 Hz</div>
                    </div>
                </div>
            </div>
            <div id="fungalUsWarn" class="us-warn" style="display:none;">
                &#9888; Frequency &gt;20 kHz — standard speakers silent. RF / plasma required.
            </div>
            <hr>
            <div class="canvas-wrap"><canvas id="fungalCanvas"></canvas></div>
            <div style="display:flex;gap:14px;justify-content:center;margin:12px 0 10px;">
                <button class="btn-start" id="fungalStart">&#9654;&nbsp; Start Treatment</button>
                <button class="btn-stop" id="fungalStop" disabled>&#9632;&nbsp; Stop</button>
            </div>
            <div id="fungalStatus" class="status-bar fungal">SYSTEM READY</div>
        </div>

        <!-- ═══ Healing ═══ -->
        <div id="tab-healing" class="tab-panel" style="display:none;">
            <div class="row">
                <span class="rl">Preset:</span>
                <select id="healSelect">{healing_options}</select>
                <span class="rl">Playback:</span>
                <div class="mode-switch">
                    <span class="ms-label active" id="hMsSingle">Single</span>
                    <label class="ms-toggle"
                           title="Single: plays the selected frequency for the set duration.&#10;Subset: plays every frequency in the same group (e.g. Angel Numbers, Solfeggio) in sequence.">
                        <input type="checkbox" id="healPlayMode" {'checked' if h_mode == 'subset' else ''}>
                        <span class="ms-knob"></span>
                    </label>
                    <span class="ms-label inactive" id="hMsSubset">Subset</span>
                </div>
            </div>
            <div class="row">
                <div class="tl-wrap">
                    <span class="tl-lbl">Duration:</span>
                    <input type="range" class="heal-range" id="healDuration" min="0" max="5" step="1" value="{h_steps}">
                    <span class="val-readout heal" id="healDurationVal">{h_mins} min</span>
                    <span id="healSubsetInfo" class="subset-info"></span>
                </div>
                <div class="vol-wrap">
                    <span class="vol-lbl">Volume:</span>
                    <input type="range" class="heal-range" id="healVolume" min="10" max="100" step="10" value="{h_vol}">
                    <span class="val-readout heal" id="healVolumeVal">{h_vol / 100:.2f}</span>
                </div>
            </div>
            <div class="heal-desc" id="healDesc"></div>
            <div class="row">
                <span class="rl">Frequency:</span>
                <div class="freq-block">
                    <span class="freq-tag">Healing Tone</span>
                    <div class="freq-box heal" id="healFreqBox">396 Hz</div>
                </div>
            </div>
            <div id="infrasoundWarning" class="us-warn" style="display:none;">
                &#9888; Frequency &lt;20 Hz — below standard audible range.
            </div>
            <hr>
            <div class="canvas-wrap"><canvas id="healCanvas"></canvas></div>
            <div style="display:flex;gap:14px;justify-content:center;margin:12px 0 10px;">
                <button class="btn-start" id="healStart">&#9654;&nbsp; Start Healing</button>
                <button class="btn-stop" id="healStop" disabled>&#9632;&nbsp; Stop</button>
            </div>
            <div id="healStatus" class="status-bar heal">SYSTEM READY</div>
        </div>

        <!-- ═══ Info / Debug ═══ -->
        <div id="tab-info" class="tab-panel" style="display:none;">
            <div class="info-card">
                <div class="info-app-name">Harmony-Healing</div>
                <div class="info-subtitle">Sound frequency therapy tool for Windows 10 (Edge WebView2).</div>
                <div class="info-links">
                    <p>By&nbsp;<a href="mailto:wiseman-timelord@mail.com">WiseMan-TimeLord</a>
                       &nbsp;at&nbsp;<a href="http://wisetime.rf.gd/" target="_blank">WiseTime.Rf.Gd</a></p>
                    <p>Projects on&nbsp;<a href="https://github.com/wiseman-timelord" target="_blank">GitHub</a></p>
                    <p>Support at&nbsp;
                        <a href="https://patreon.com/WiseManTimeLord" target="_blank">Patreon</a>
                        <span class="info-sep">&middot;</span>
                        <a href="https://ko-fi.com/WiseManTimeLord" target="_blank">Ko-Fi</a>
                    </p>
                </div>
            </div>
            <div class="info-card">
                <div class="info-card-title">Runtime Constants</div>
                <pre id="constantsDisplay" class="constants-pre">  Loading&#8230;</pre>
                <div class="info-refresh-row">
                    <button class="info-btn" id="audioDiagBtn">Audio Devices</button>
                    <button class="info-btn" id="refreshBtn">Refresh</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        var TWO_PI = Math.PI * 2;
        var HARMONIC_MULT = 11;
        var DURATION_OPTS = [{duration_js}];

        function apiReady() {{
            return typeof pywebview !== 'undefined' && !!pywebview.api;
        }}
        function formatHz(hz) {{
            if (hz >= 1e6) return (hz/1e6).toFixed(3) + ' MHz';
            if (hz >= 1e3) return (hz/1e3).toFixed(2) + ' kHz';
            return hz.toLocaleString() + ' Hz';
        }}
        function formatDuration(minutes) {{
            if (minutes < 60) return minutes + ' min';
            var hrs = Math.floor(minutes / 60);
            var mins = minutes % 60;
            if (mins === 0) return hrs + ' hr';
            return hrs + ' hr ' + mins + ' min';
        }}
        function durationFromSlider(el) {{
            var idx = parseInt(el.value, 10);
            if (isNaN(idx) || idx < 0) idx = 0;
            if (idx >= DURATION_OPTS.length) idx = DURATION_OPTS.length - 1;
            return DURATION_OPTS[idx];
        }}

        // ── Tab system ───────────────────────────────────────────────────────
        var infoLoaded = false;
        function switchTab(name) {{
            document.querySelectorAll('.tab-panel').forEach(function(p) {{ p.style.display = 'none'; }});
            document.querySelectorAll('.tab-btn').forEach(function(b) {{ b.classList.remove('active'); }});
            var tabEl = document.getElementById('tab-' + name);
            if (tabEl) tabEl.style.display = '';
            document.querySelectorAll('.tab-btn').forEach(function(b) {{
                if (b.dataset.tab === name) b.classList.add('active');
            }});
            if (name === 'info' && !infoLoaded) loadInfoTab();
            if (name === 'viral') setTimeout(function(){{ resizePageCanvas('viral'); }}, 20);
            if (name === 'fungal') setTimeout(function(){{ resizePageCanvas('fungal'); }}, 20);
            if (name === 'healing') setTimeout(function(){{ resizePageCanvas('heal'); }}, 20);
        }}

        function loadInfoTab() {{
            var pre = document.getElementById('constantsDisplay');
            if (!pre) return;
            if (!apiReady()) {{
                pre.textContent = '  [Running without pywebview bridge]\\n  Launch via launcher.py to see live data.';
                infoLoaded = true;
                return;
            }}
            pre.textContent = '  Loading\\u2026';
            pywebview.api.get_constants().then(function(c) {{
                var ramStr = c.total_ram_gb ? c.total_ram_gb + ' GB' : 'unknown';
                var lines = [
                    '  CPU Name .......... ' + (c.cpu_name || 'unknown'),
                    '  Total Threads ..... ' + (c.cpu_count || 0) + 'T',
                    '  Total RAM ......... ' + ramStr,
                    '  Windows Version ... ' + (c.windows_version || 'unknown'),
                    '  Python Version .... v' + (c.python_version || 'unknown'),
                    '  WebView Version ... v' + (c.webview_version || 'unknown'),
                    '  App Directory ..... ' + (c.app_dir || 'unknown'),
                ];
                pre.textContent = lines.join('\\n');
                infoLoaded = true;
            }}).catch(function(err) {{
                pre.textContent = '  Error: ' + err;
            }});
        }}
        function refreshConstants() {{ infoLoaded = false; loadInfoTab(); }}
        function runAudioDiag() {{
            if (!apiReady()) return;
            pywebview.api.diagnose_audio().then(function() {{
                /* output goes to Python console */
            }});
        }}

        // ── Generic page controller factory ──────────────────────────────────
        function makeHarmonicPage(prefix, startApiName) {{
            var st = {{
                freq: 432,
                isPlaying: false,
                minutes: 15,
                playMode: 'single',
                timer: null,
                countdown: null,
                countdownEnd: 0,
                subsetQueue: [],
                subsetIndex: 0,
                subsetStep: 0,
                animId: null,
                animPhi: 0
            }};

            function selectEl() {{ return document.getElementById(prefix + 'Select'); }}
            function statusEl() {{ return document.getElementById(prefix + 'Status'); }}
            function updateStatus(msg) {{ statusEl().textContent = msg; }}

            function updateFreqDisplay() {{
                var sel = selectEl();
                if (!sel || !sel.options[sel.selectedIndex]) return;
                st.freq = parseFloat(sel.value);
                document.getElementById(prefix + 'Base').textContent = formatHz(st.freq);
                document.getElementById(prefix + 'Harm').textContent = formatHz(st.freq * HARMONIC_MULT);
                var warn = document.getElementById(prefix + 'UsWarn');
                if (warn) warn.style.display = st.freq > 20000 ? 'block' : 'none';
                if (!st.isPlaying) drawWave();
                updateSubsetInfo();
            }}

            function updateDuration() {{
                var el = document.getElementById(prefix + 'Duration');
                st.minutes = durationFromSlider(el);
                document.getElementById(prefix + 'DurationVal').textContent = formatDuration(st.minutes);
                updateSubsetInfo();
            }}

            function updateVolume() {{
                var el = document.getElementById(prefix + 'Volume');
                var ui = parseInt(el.value, 10);
                document.getElementById(prefix + 'VolumeVal').textContent = (ui / 100).toFixed(2);
                if (apiReady() && st.isPlaying) pywebview.api.update_volume(ui);
            }}

            function updatePlayMode() {{
                var isSub = document.getElementById(prefix + 'PlayMode').checked;
                st.playMode = isSub ? 'subset' : 'single';
                var singleL = document.getElementById(prefix === 'viral' ? 'vMsSingle' : 'fMsSingle');
                var subL = document.getElementById(prefix === 'viral' ? 'vMsSubset' : 'fMsSubset');
                if (singleL) singleL.className = 'ms-label ' + (isSub ? 'inactive' : 'active');
                if (subL) subL.className = 'ms-label ' + (isSub ? 'active' : 'inactive');
                updateSubsetInfo();
            }}

            function getGroupKey(label) {{
                var idx = label.indexOf(' \\u2013 ');
                if (idx === -1) idx = label.indexOf(' - ');
                return idx !== -1 ? label.substring(0, idx).trim() : label.trim();
            }}

            function buildSubsetQueue() {{
                var sel = selectEl();
                if (!sel || !sel.options[sel.selectedIndex]) return [];
                var opt = sel.options[sel.selectedIndex];
                var key = opt.dataset.key || getGroupKey(opt.text);
                var queue = [];
                for (var i = 0; i < sel.options.length; i++) {{
                    var o = sel.options[i];
                    var k = o.dataset.key || getGroupKey(o.text);
                    if (k === key) queue.push({{ freq: parseFloat(o.value), label: o.text, key: k }});
                }}
                return queue;
            }}

            function updateSubsetInfo() {{
                var infoEl = document.getElementById(prefix + 'SubsetInfo');
                if (!infoEl) return;
                var isSub = document.getElementById(prefix + 'PlayMode').checked;
                if (!isSub) {{ infoEl.textContent = ''; return; }}
                var queue = buildSubsetQueue();
                if (queue.length <= 1) {{
                    infoEl.textContent = '(no other frequencies in subset)';
                    infoEl.style.color = '#64748b';
                }} else {{
                    infoEl.textContent = '(' + formatDuration(queue.length * st.minutes) + ')';
                    infoEl.style.color = prefix === 'fungal' ? '#f59e0b' : '#38bdf8';
                }}
            }}

            function clearCountdown() {{
                if (st.countdown) {{ clearInterval(st.countdown); st.countdown = null; }}
            }}
            function clearTimer() {{
                if (st.timer) {{ clearTimeout(st.timer); st.timer = null; }}
            }}
            function tickCountdown() {{
                var remaining = Math.max(0, st.countdownEnd - Date.now());
                var totalSecs = Math.ceil(remaining / 1000);
                var mins = Math.floor(totalSecs / 60);
                var secs = totalSecs % 60;
                var timeStr = mins + ':' + String(secs).padStart(2, '0');
                var msg;
                if (st.playMode === 'subset' && st.subsetQueue.length > 0) {{
                    msg = 'SUBSET ' + st.subsetStep + '/' + st.subsetQueue.length
                        + '  \\u2500\\u2500  ' + formatHz(st.freq)
                        + ' + ' + formatHz(st.freq * HARMONIC_MULT)
                        + '  \\u2500\\u2500  ' + timeStr;
                }} else {{
                    msg = 'RESONATING  \\u2500\\u2500  '
                        + formatHz(st.freq) + ' + ' + formatHz(st.freq * HARMONIC_MULT)
                        + '  \\u2500\\u2500  ' + timeStr;
                }}
                updateStatus(msg);
            }}
            function startCountdown(ms) {{
                clearCountdown();
                st.countdownEnd = Date.now() + ms;
                tickCountdown();
                st.countdown = setInterval(tickCountdown, 1000);
            }}

            function autoStop() {{
                clearTimer(); clearCountdown();
                var done = function() {{
                    st.isPlaying = false; stopAnim();
                    var msg = (st.playMode === 'subset' && st.subsetQueue.length > 1)
                        ? 'PROGRAM COMPLETE  \\u2500\\u2500  AUTO OFF  (' + st.subsetQueue.length + '/' + st.subsetQueue.length + ')'
                        : 'PROGRAM COMPLETE  \\u2500\\u2500  AUTO OFF';
                    updateStatus(msg);
                    document.getElementById(prefix + 'Start').disabled = false;
                    document.getElementById(prefix + 'Stop').disabled = true;
                }};
                if (apiReady()) pywebview.api.stop_treatment().then(done); else done();
            }}

            function playSubsetItem(uiVol, durationMs) {{
                if (st.subsetIndex >= st.subsetQueue.length) {{ autoStop(); return; }}
                var item = st.subsetQueue[st.subsetIndex];
                st.subsetStep = st.subsetIndex + 1;
                st.freq = item.freq;
                updateStatus('LOADING SUBSET ' + st.subsetStep + '/' + st.subsetQueue.length + '...');
                var call = apiReady()
                    ? pywebview.api[startApiName]({{
                        freq: item.freq, volume: uiVol,
                        duration_index: parseInt(document.getElementById(prefix + 'Duration').value, 10),
                        play_mode: 'single', subset_key: item.key
                      }})
                    : Promise.resolve({{status: 'playing'}});
                call.then(function(result) {{
                    if (result && result.error) {{ updateStatus('ERROR: ' + result.error); autoStop(); return; }}
                    st.isPlaying = true; updateFreqDisplay();
                    if (!st.animId) startAnim();
                    document.getElementById(prefix + 'Start').disabled = true;
                    document.getElementById(prefix + 'Stop').disabled = false;
                    startCountdown(durationMs);
                    st.timer = setTimeout(function() {{
                        st.subsetIndex++;
                        playSubsetItem(uiVol, durationMs);
                    }}, durationMs);
                }}).catch(function(err) {{ console.error(err); autoStop(); }});
            }}

            function startTreatment() {{
                clearTimer(); clearCountdown();
                var uiVol = parseInt(document.getElementById(prefix + 'Volume').value, 10);
                var durationMs = st.minutes * 60 * 1000;
                if (st.playMode === 'subset') {{
                    st.subsetQueue = buildSubsetQueue();
                    if (st.subsetQueue.length === 0) {{ updateStatus('ERROR: No frequencies'); return; }}
                    st.subsetIndex = 0; st.subsetStep = 0;
                    playSubsetItem(uiVol, durationMs);
                }} else {{
                    updateStatus('INITIALIZING AUDIO...');
                    var call = apiReady()
                        ? pywebview.api[startApiName]({{
                            freq: st.freq, volume: uiVol,
                            duration_index: parseInt(document.getElementById(prefix + 'Duration').value, 10),
                            play_mode: 'single', subset_key: null
                          }})
                        : Promise.resolve({{status: 'playing'}});
                    call.then(function(result) {{
                        if (result && result.error) {{
                            updateStatus('ERROR: ' + result.error);
                            document.getElementById(prefix + 'Start').disabled = false;
                        }} else {{
                            st.isPlaying = true; startAnim();
                            document.getElementById(prefix + 'Start').disabled = true;
                            document.getElementById(prefix + 'Stop').disabled = false;
                            startCountdown(durationMs);
                            st.timer = setTimeout(function() {{ autoStop(); }}, durationMs);
                        }}
                    }}).catch(function(err) {{
                        updateStatus('ERROR: ' + err);
                        document.getElementById(prefix + 'Start').disabled = false;
                    }});
                }}
            }}

            function stopTreatment() {{
                clearTimer(); clearCountdown();
                updateStatus('STOPPING...');
                var done = function() {{
                    st.isPlaying = false; stopAnim(); updateStatus('SYSTEM READY');
                    document.getElementById(prefix + 'Start').disabled = false;
                    document.getElementById(prefix + 'Stop').disabled = true;
                }};
                if (apiReady()) pywebview.api.stop_treatment().then(done); else done();
            }}

            // Canvas
            function canvasEl() {{ return document.getElementById(prefix + 'Canvas'); }}
            function drawWave() {{
                var canvas = canvasEl();
                if (!canvas) return;
                var ctx = canvas.getContext('2d');
                var W = canvas.offsetWidth || canvas.width;
                var H = canvas.offsetHeight || canvas.height;
                if (W === 0 || H === 0) return;
                var mid = H * 0.50, amp = H * 0.34, CYCLES = 3, phi = st.animPhi;
                var accent = prefix === 'fungal' ? '#f59e0b' : '#38bdf8';
                var accentSoft = prefix === 'fungal' ? 'rgba(245,158,11,0.55)' : 'rgba(56,189,248,0.55)';
                ctx.fillStyle = '#070d1a'; ctx.fillRect(0, 0, W, H);
                ctx.lineWidth = 1; ctx.strokeStyle = 'rgba(45,66,99,0.7)';
                [0.12,0.31,0.50,0.69,0.88].forEach(function(f) {{
                    ctx.beginPath(); ctx.moveTo(0, H*f); ctx.lineTo(W, H*f); ctx.stroke();
                }});
                ctx.strokeStyle = 'rgba(45,66,99,0.4)';
                for (var gx = 1; gx < 8; gx++) {{
                    ctx.beginPath(); ctx.moveTo(W*gx/8, 0); ctx.lineTo(W*gx/8, H); ctx.stroke();
                }}
                ctx.strokeStyle = accent.replace(')', ',0.18)').replace('rgb', 'rgba').replace('#38bdf8', 'rgba(56,189,248,0.18)').replace('#f59e0b', 'rgba(245,158,11,0.18)');
                ctx.beginPath(); ctx.moveTo(0, mid); ctx.lineTo(W, mid); ctx.stroke();
                ctx.beginPath(); ctx.strokeStyle = 'rgba(251,191,36,0.30)'; ctx.lineWidth = 1;
                for (var p1 = 0; p1 <= W; p1++) {{
                    var t1 = (p1/W)*CYCLES*TWO_PI;
                    var y1 = mid - Math.sin(t1*HARMONIC_MULT + phi*HARMONIC_MULT)*0.40*amp;
                    if (p1===0) ctx.moveTo(p1,y1); else ctx.lineTo(p1,y1);
                }}
                ctx.stroke();
                ctx.beginPath(); ctx.strokeStyle = 'rgba(226,232,240,0.55)'; ctx.lineWidth = 1.5;
                for (var p2 = 0; p2 <= W; p2++) {{
                    var t2 = (p2/W)*CYCLES*TWO_PI;
                    var y2 = mid - Math.sin(t2 + phi)*amp;
                    if (p2===0) ctx.moveTo(p2,y2); else ctx.lineTo(p2,y2);
                }}
                ctx.stroke();
                ctx.beginPath(); ctx.strokeStyle = accent; ctx.lineWidth = 2;
                ctx.shadowBlur = 7; ctx.shadowColor = accentSoft;
                for (var p3 = 0; p3 <= W; p3++) {{
                    var t3 = (p3/W)*CYCLES*TWO_PI;
                    var bv = Math.sin(t3 + phi);
                    var hv = Math.sin(t3*HARMONIC_MULT + phi*HARMONIC_MULT)*0.40;
                    var y3 = mid - ((bv + hv)/1.40)*amp;
                    if (p3===0) ctx.moveTo(p3,y3); else ctx.lineTo(p3,y3);
                }}
                ctx.stroke(); ctx.shadowBlur = 0;
                ctx.font = '10px Consolas,monospace'; ctx.textBaseline = 'bottom';
                ctx.fillStyle = accentSoft;
                ctx.fillText('\\u2500\\u2500 composite (base + 11th harmonic)', 8, H-4);
                ctx.fillStyle = 'rgba(125,211,252,0.50)'; ctx.textAlign = 'right';
                ctx.fillText(formatHz(st.freq)+'  +  '+formatHz(st.freq*HARMONIC_MULT), W-8, H-4);
                ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
            }}
            function startAnim() {{
                if (st.animId) cancelAnimationFrame(st.animId);
                (function loop() {{
                    st.animPhi = (st.animPhi + 0.042) % TWO_PI;
                    drawWave();
                    if (st.isPlaying) st.animId = requestAnimationFrame(loop);
                }})();
            }}
            function stopAnim() {{
                if (st.animId) {{ cancelAnimationFrame(st.animId); st.animId = null; }}
                st.animPhi = 0; drawWave();
            }}
            function resize() {{
                var canvas = canvasEl();
                if (!canvas) return;
                var dpr = window.devicePixelRatio || 1;
                var w = canvas.offsetWidth;
                var h = canvas.offsetHeight || 130;
                canvas.width = w * dpr; canvas.height = h * dpr;
                var ctx = canvas.getContext('2d');
                ctx.setTransform(1,0,0,1,0,0); ctx.scale(dpr, dpr);
                if (!st.isPlaying) drawWave();
            }}

            return {{
                st: st,
                updateFreqDisplay: updateFreqDisplay,
                updateDuration: updateDuration,
                updateVolume: updateVolume,
                updatePlayMode: updatePlayMode,
                startTreatment: startTreatment,
                stopTreatment: stopTreatment,
                resize: resize,
                drawWave: drawWave,
                updateSubsetInfo: updateSubsetInfo
            }};
        }}

        var viralPage  = makeHarmonicPage('viral', 'start_viral');
        var fungalPage = makeHarmonicPage('fungal', 'start_fungal');

        // ── Healing page ─────────────────────────────────────────────────────
        var heal = {{
            freq: 396, isPlaying: false, minutes: 15, playMode: 'single',
            timer: null, countdown: null, countdownEnd: 0,
            subsetQueue: [], subsetIndex: 0, subsetStep: 0,
            animId: null, animPhi: 0
        }};
        function updateHealDisplay() {{
            var sel = document.getElementById('healSelect');
            if (!sel || !sel.options[sel.selectedIndex]) return;
            heal.freq = parseFloat(sel.value);
            var desc = sel.options[sel.selectedIndex].getAttribute('data-desc') || '';
            document.getElementById('healFreqBox').textContent = formatHz(heal.freq);
            document.getElementById('healDesc').textContent = desc;
            document.getElementById('infrasoundWarning').style.display =
                heal.freq < 20 ? 'block' : 'none';
            if (!heal.isPlaying) drawHealWave();
            updateHealSubsetInfo();
        }}
        function updateHealVolume() {{
            var ui = parseInt(document.getElementById('healVolume').value, 10);
            document.getElementById('healVolumeVal').textContent = (ui / 100).toFixed(2);
            if (apiReady() && heal.isPlaying) pywebview.api.update_volume(ui);
        }}
        function updateHealDuration() {{
            heal.minutes = durationFromSlider(document.getElementById('healDuration'));
            document.getElementById('healDurationVal').textContent = formatDuration(heal.minutes);
            updateHealSubsetInfo();
        }}
        function updateHealPlayMode() {{
            var isSub = document.getElementById('healPlayMode').checked;
            heal.playMode = isSub ? 'subset' : 'single';
            document.getElementById('hMsSingle').className =
                'ms-label ' + (isSub ? 'inactive' : 'active');
            document.getElementById('hMsSubset').className =
                'ms-label ' + (isSub ? 'active' : 'inactive');
            updateHealSubsetInfo();
        }}
        function buildHealSubsetQueue() {{
            var sel = document.getElementById('healSelect');
            if (!sel || !sel.options[sel.selectedIndex]) return [];
            var opt = sel.options[sel.selectedIndex];
            var group = opt.getAttribute('data-group') || '';
            if (!group) return [];
            var queue = [];
            for (var i = 0; i < sel.options.length; i++) {{
                var o = sel.options[i];
                if (o.getAttribute('data-group') === group)
                    queue.push({{
                        freq: parseFloat(o.value),
                        label: o.text,
                        key: group,
                        desc: o.getAttribute('data-desc') || ''
                    }});
            }}
            return queue;
        }}
        function updateHealSubsetInfo() {{
            var infoEl = document.getElementById('healSubsetInfo');
            if (!infoEl) return;
            var isSub = document.getElementById('healPlayMode').checked;
            if (!isSub) {{ infoEl.textContent = ''; return; }}
            var queue = buildHealSubsetQueue();
            if (queue.length <= 1) {{
                infoEl.textContent = '(no other frequencies in group)';
                infoEl.style.color = '#64748b';
            }} else {{
                infoEl.textContent = '(' + formatDuration(queue.length * heal.minutes) + ')';
                infoEl.style.color = '#22c55e';
            }}
        }}
        function updateHealStatus(msg) {{
            document.getElementById('healStatus').textContent = msg;
        }}
        function clearHealCountdown() {{
            if (heal.countdown) {{ clearInterval(heal.countdown); heal.countdown = null; }}
        }}
        function clearHealTimer() {{
            if (heal.timer) {{ clearTimeout(heal.timer); heal.timer = null; }}
        }}
        function tickHealCountdown() {{
            var remaining = Math.max(0, heal.countdownEnd - Date.now());
            var totalSecs = Math.ceil(remaining / 1000);
            var mins = Math.floor(totalSecs / 60);
            var secs = totalSecs % 60;
            var timeStr = mins + ':' + String(secs).padStart(2, '0');
            var msg;
            if (heal.playMode === 'subset' && heal.subsetQueue.length > 0) {{
                msg = 'SUBSET ' + heal.subsetStep + '/' + heal.subsetQueue.length
                    + '  \\u2500\\u2500  ' + formatHz(heal.freq)
                    + '  \\u2500\\u2500  ' + timeStr;
            }} else {{
                msg = 'HEALING  \\u2500\\u2500  ' + formatHz(heal.freq)
                    + '  \\u2500\\u2500  ' + timeStr;
            }}
            updateHealStatus(msg);
        }}
        function startHealCountdown(ms) {{
            clearHealCountdown();
            heal.countdownEnd = Date.now() + ms;
            tickHealCountdown();
            heal.countdown = setInterval(tickHealCountdown, 1000);
        }}
        function autoStopHealing() {{
            clearHealTimer(); clearHealCountdown();
            var done = function() {{
                heal.isPlaying = false; stopHealAnim();
                var msg = (heal.playMode === 'subset' && heal.subsetQueue.length > 1)
                    ? 'HEALING COMPLETE  \\u2500\\u2500  AUTO OFF  ('
                      + heal.subsetQueue.length + '/' + heal.subsetQueue.length + ')'
                    : 'HEALING COMPLETE  \\u2500\\u2500  AUTO OFF';
                updateHealStatus(msg);
                document.getElementById('healStart').disabled = false;
                document.getElementById('healStop').disabled = true;
            }};
            if (apiReady()) pywebview.api.stop_treatment().then(done); else done();
        }}
        function playHealSubsetItem(uiVol, durationMs) {{
            if (heal.subsetIndex >= heal.subsetQueue.length) {{ autoStopHealing(); return; }}
            var item = heal.subsetQueue[heal.subsetIndex];
            heal.subsetStep = heal.subsetIndex + 1;
            heal.freq = item.freq;
            document.getElementById('healFreqBox').textContent = formatHz(heal.freq);
            document.getElementById('healDesc').textContent = item.desc || '';
            updateHealStatus('LOADING SUBSET ' + heal.subsetStep + '/' + heal.subsetQueue.length + '...');
            var call = apiReady()
                ? pywebview.api.start_healing({{
                    freq: item.freq, volume: uiVol,
                    duration_index: parseInt(document.getElementById('healDuration').value, 10),
                    play_mode: 'single', subset_key: item.key
                  }})
                : Promise.resolve({{status: 'playing'}});
            call.then(function(result) {{
                if (result && result.error) {{
                    updateHealStatus('ERROR: ' + result.error); autoStopHealing(); return;
                }}
                heal.isPlaying = true;
                if (!heal.animId) startHealAnim();
                document.getElementById('healStart').disabled = true;
                document.getElementById('healStop').disabled = false;
                startHealCountdown(durationMs);
                heal.timer = setTimeout(function() {{
                    heal.subsetIndex++;
                    playHealSubsetItem(uiVol, durationMs);
                }}, durationMs);
            }}).catch(function(err) {{ console.error(err); autoStopHealing(); }});
        }}
        function startHealing() {{
            clearHealTimer(); clearHealCountdown();
            var uiVol = parseInt(document.getElementById('healVolume').value, 10);
            var durationMs = heal.minutes * 60 * 1000;

            if (heal.playMode === 'subset') {{
                heal.subsetQueue = buildHealSubsetQueue();
                if (heal.subsetQueue.length === 0) {{
                    updateHealStatus('ERROR: No frequencies in group'); return;
                }}
                heal.subsetIndex = 0; heal.subsetStep = 0;
                playHealSubsetItem(uiVol, durationMs);
                return;
            }}

            updateHealStatus('INITIALIZING HEALING TONE...');
            var call = apiReady()
                ? pywebview.api.start_healing({{
                    freq: heal.freq, volume: uiVol,
                    duration_index: parseInt(document.getElementById('healDuration').value, 10),
                    play_mode: 'single', subset_key: null
                  }})
                : Promise.resolve({{status: 'playing'}});
            call.then(function(result) {{
                if (result && result.error) {{
                    updateHealStatus('ERROR: ' + result.error);
                    document.getElementById('healStart').disabled = false;
                }} else {{
                    heal.isPlaying = true; startHealAnim();
                    document.getElementById('healStart').disabled = true;
                    document.getElementById('healStop').disabled = false;
                    startHealCountdown(durationMs);
                    heal.timer = setTimeout(function() {{ autoStopHealing(); }}, durationMs);
                }}
            }}).catch(function(err) {{
                updateHealStatus('ERROR: ' + err);
                document.getElementById('healStart').disabled = false;
            }});
        }}
        function stopHealing() {{
            clearHealTimer(); clearHealCountdown();
            updateHealStatus('STOPPING...');
            var done = function() {{
                heal.isPlaying = false; stopHealAnim(); updateHealStatus('SYSTEM READY');
                document.getElementById('healStart').disabled = false;
                document.getElementById('healStop').disabled = true;
            }};
            if (apiReady()) pywebview.api.stop_treatment().then(done); else done();
        }}
        function drawHealWave() {{
            var hc = document.getElementById('healCanvas');
            if (!hc) return;
            var hCtx = hc.getContext('2d');
            var W = hc.offsetWidth || hc.width;
            var H = hc.offsetHeight || hc.height;
            if (W === 0 || H === 0) return;
            var mid = H*0.50, amp = H*0.38, CYCLES = 3, phi = heal.animPhi;
            hCtx.fillStyle = '#070d1a'; hCtx.fillRect(0, 0, W, H);
            hCtx.lineWidth = 1; hCtx.strokeStyle = 'rgba(45,66,99,0.7)';
            [0.12,0.31,0.50,0.69,0.88].forEach(function(f) {{
                hCtx.beginPath(); hCtx.moveTo(0, H*f); hCtx.lineTo(W, H*f); hCtx.stroke();
            }});
            hCtx.strokeStyle = 'rgba(45,66,99,0.4)';
            for (var gx = 1; gx < 8; gx++) {{
                hCtx.beginPath(); hCtx.moveTo(W*gx/8, 0); hCtx.lineTo(W*gx/8, H); hCtx.stroke();
            }}
            hCtx.strokeStyle = 'rgba(34,197,94,0.18)';
            hCtx.beginPath(); hCtx.moveTo(0, mid); hCtx.lineTo(W, mid); hCtx.stroke();
            hCtx.beginPath(); hCtx.strokeStyle = '#22c55e'; hCtx.lineWidth = 2;
            hCtx.shadowBlur = 7; hCtx.shadowColor = 'rgba(34,197,94,0.55)';
            for (var hp = 0; hp <= W; hp++) {{
                var ht = (hp/W)*CYCLES*TWO_PI;
                var hy = mid - Math.sin(ht + phi)*amp;
                if (hp===0) hCtx.moveTo(hp,hy); else hCtx.lineTo(hp,hy);
            }}
            hCtx.stroke(); hCtx.shadowBlur = 0;
            hCtx.font = '10px Consolas,monospace'; hCtx.textBaseline = 'bottom';
            hCtx.fillStyle = 'rgba(34,197,94,0.75)';
            hCtx.fillText('\\u2500\\u2500 pure sine', 8, H-4);
            hCtx.fillStyle = 'rgba(134,239,172,0.50)'; hCtx.textAlign = 'right';
            hCtx.fillText(formatHz(heal.freq), W-8, H-4);
            hCtx.textAlign = 'left'; hCtx.textBaseline = 'alphabetic';
        }}
        function startHealAnim() {{
            if (heal.animId) cancelAnimationFrame(heal.animId);
            (function loop() {{
                heal.animPhi = (heal.animPhi + 0.042) % TWO_PI;
                drawHealWave();
                if (heal.isPlaying) heal.animId = requestAnimationFrame(loop);
            }})();
        }}
        function stopHealAnim() {{
            if (heal.animId) {{ cancelAnimationFrame(heal.animId); heal.animId = null; }}
            heal.animPhi = 0; drawHealWave();
        }}
        function resizeHealCanvas() {{
            var hc = document.getElementById('healCanvas');
            if (!hc) return;
            var dpr = window.devicePixelRatio || 1;
            var w = hc.offsetWidth;
            if (w === 0) return;
            var h = hc.offsetHeight || 130;
            hc.width = w*dpr; hc.height = h*dpr;
            var hCtx = hc.getContext('2d');
            hCtx.setTransform(1,0,0,1,0,0); hCtx.scale(dpr, dpr);
            if (!heal.isPlaying) drawHealWave();
        }}
        function resizePageCanvas(which) {{
            if (which === 'viral') viralPage.resize();
            else if (which === 'fungal') fungalPage.resize();
            else if (which === 'heal') resizeHealCanvas();
        }}

        // ── Init ─────────────────────────────────────────────────────────────
        function initApp() {{
            document.querySelectorAll('.tab-btn').forEach(function(btn) {{
                btn.addEventListener('click', function() {{ switchTab(btn.dataset.tab); }});
            }});

            // Viral
            document.getElementById('viralSelect').addEventListener('change', viralPage.updateFreqDisplay);
            document.getElementById('viralPlayMode').addEventListener('change', viralPage.updatePlayMode);
            document.getElementById('viralDuration').addEventListener('input', viralPage.updateDuration);
            document.getElementById('viralVolume').addEventListener('input', viralPage.updateVolume);
            document.getElementById('viralStart').addEventListener('click', viralPage.startTreatment);
            document.getElementById('viralStop').addEventListener('click', viralPage.stopTreatment);

            // Fungal
            document.getElementById('fungalSelect').addEventListener('change', fungalPage.updateFreqDisplay);
            document.getElementById('fungalPlayMode').addEventListener('change', fungalPage.updatePlayMode);
            document.getElementById('fungalDuration').addEventListener('input', fungalPage.updateDuration);
            document.getElementById('fungalVolume').addEventListener('input', fungalPage.updateVolume);
            document.getElementById('fungalStart').addEventListener('click', fungalPage.startTreatment);
            document.getElementById('fungalStop').addEventListener('click', fungalPage.stopTreatment);

            // Healing
            document.getElementById('healSelect').addEventListener('change', updateHealDisplay);
            document.getElementById('healPlayMode').addEventListener('change', updateHealPlayMode);
            document.getElementById('healVolume').addEventListener('input', updateHealVolume);
            document.getElementById('healDuration').addEventListener('input', updateHealDuration);
            document.getElementById('healStart').addEventListener('click', startHealing);
            document.getElementById('healStop').addEventListener('click', stopHealing);

            var rb = document.getElementById('refreshBtn');
            if (rb) rb.addEventListener('click', refreshConstants);
            var ab = document.getElementById('audioDiagBtn');
            if (ab) ab.addEventListener('click', runAudioDiag);

            viralPage.resize();
            viralPage.updateFreqDisplay();
            viralPage.updateDuration();
            viralPage.updateVolume();
            viralPage.updatePlayMode();

            fungalPage.updateFreqDisplay();
            fungalPage.updateDuration();
            fungalPage.updateVolume();
            fungalPage.updatePlayMode();

            updateHealDisplay();
            updateHealDuration();
            updateHealVolume();
            updateHealPlayMode();

            console.log('[HH] Application initialized successfully');
        }}

        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', initApp);
        }} else {{
            initApp();
        }}

        window.addEventListener('pywebviewready', function() {{
            console.log('[HH] pywebview bridge ready');
            if (!apiReady()) return;
            // Page configs already baked into HTML from Python load;
            // optionally re-sync from API:
            pywebview.api.get_viral_config().then(function(cfg) {{
                if (cfg.volume !== undefined) {{
                    document.getElementById('viralVolume').value = cfg.volume;
                    viralPage.updateVolume();
                }}
                if (cfg.duration_index !== undefined) {{
                    document.getElementById('viralDuration').value = cfg.duration_index;
                    viralPage.updateDuration();
                }}
                if (cfg.play_mode === 'subset') {{
                    document.getElementById('viralPlayMode').checked = true;
                    viralPage.updatePlayMode();
                }}
                viralPage.updateFreqDisplay();
            }}).catch(function(){{}});
            pywebview.api.get_fungal_config().then(function(cfg) {{
                if (cfg.volume !== undefined) {{
                    document.getElementById('fungalVolume').value = cfg.volume;
                    fungalPage.updateVolume();
                }}
                if (cfg.duration_index !== undefined) {{
                    document.getElementById('fungalDuration').value = cfg.duration_index;
                    fungalPage.updateDuration();
                }}
                if (cfg.play_mode === 'subset') {{
                    document.getElementById('fungalPlayMode').checked = true;
                    fungalPage.updatePlayMode();
                }}
                fungalPage.updateFreqDisplay();
            }}).catch(function(){{}});
            pywebview.api.get_healing_config().then(function(cfg) {{
                if (cfg.volume !== undefined) {{
                    document.getElementById('healVolume').value = cfg.volume;
                    updateHealVolume();
                }}
                if (cfg.duration_index !== undefined) {{
                    document.getElementById('healDuration').value = cfg.duration_index;
                    updateHealDuration();
                }}
                if (cfg.play_mode === 'subset') {{
                    document.getElementById('healPlayMode').checked = true;
                    updateHealPlayMode();
                }}
                updateHealDisplay();
            }}).catch(function(){{}});
        }});

    </script>
</body>
</html>"""

    try:
        window = webview.create_window(
            configure.APP_TITLE,
            html=html,
            js_api=api,
            width=win_w,
            height=win_h,
            resizable=True,
            text_select=True,
            min_size=(configure.WINDOW_MIN_WIDTH, configure.WINDOW_MIN_HEIGHT),
        )
        api._set_window(window)

        def on_window_closing():
            api.shutdown()
            return True

        window.events.closing += on_window_closing
        webview.start(gui="edgechromium", debug=False)

    except TypeError as te:
        if "unexpected keyword argument" in str(te):
            print(f"[WARN] pywebview version compatibility issue: {te}")
            try:
                window = webview.create_window(
                    configure.APP_TITLE,
                    html=html,
                    js_api=api,
                    width=win_w,
                    height=win_h,
                    min_size=(configure.WINDOW_MIN_WIDTH, configure.WINDOW_MIN_HEIGHT),
                )
                api._set_window(window)
                window.events.closing += lambda: api.shutdown() or True
                webview.start(gui="edgechromium")
            except Exception as e2:
                print(f"[ERROR] Fallback window creation failed: {e2}")
                api.shutdown()
                return
        else:
            raise
    except Exception as e:
        print(f"[ERROR] Failed to initialize GUI: {e}")
        api.shutdown()
        return

    print("GUI closed. Shutdown complete.")