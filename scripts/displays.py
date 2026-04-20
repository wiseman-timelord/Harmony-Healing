"""
displays.py – GUI frontend using pywebview with Edge WebView2 backend.
All comments start with # as per Python convention.

Bridge safety note
------------------
pywebview serialises every *public* attribute of the js_api object into the
JavaScript API proxy when the window loads.  If the object carries large or
complex public attrs (lists, nested objects, SoundGenerator, etc.) pywebview
walks them recursively, which can exceed Python's recursion limit mid-init and
leave the bridge partially broken — buttons click but nothing happens.

Fix: all internal state uses _ prefix so pywebview ignores it.  Only the
explicitly defined public def methods below are exposed to JavaScript.
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
        # ALL instance data is private (_) so pywebview's bridge serialiser
        # never walks them.  Only the public def methods below are exposed.
        self._gen            = generator.SoundGenerator()
        self._config         = configure.load_config()
        self._frequencies    = configure.FREQUENCY_DATA
        self._fungus_freqs   = configure.FUNGUS_FREQUENCY_DATA
        self._healing_freqs  = configure.HEALING_FREQUENCY_DATA
        self._window         = None
        self._stop_timer     = None
        self._subset_thread  = None
        self._should_stop_subset = False
        self._stop_event     = None  # threading.Event for cancelling the auto-stop timer

    def _set_window(self, window):
        """Store reference to the pywebview window (internal — not exposed to JS)."""
        self._window = window

    # ── Config ────────────────────────────────────────────────────────────────
    def get_config(self):
        return self._config

    def get_frequencies(self):
        return self._frequencies

    def get_fungus_frequencies(self):
        return self._fungus_freqs

    def get_healing_frequencies(self):
        return self._healing_freqs

    def save_config(self, data):
        configure.save_config(data)
        self._config = data
        return {"status": "saved"}

    def save_setting(self, key, value):
        """Persist a single config key without replacing the whole config."""
        self._config[key] = value
        configure.save_config(self._config)
        return {"status": "saved"}

    # ── Window size persistence ───────────────────────────────────────────────
    def save_window_size(self, width, height):
        """Called from JS on window resize (debounced 700 ms).
        Stores dimensions in-memory; flushed to disk on shutdown().
        """
        self._config['window_width']  = max(400, int(width))
        self._config['window_height'] = max(300, int(height))
        return {"status": "ok"}

    # ── Hardware / Runtime constants (Info tab) ───────────────────────────────
    def get_constants(self):
        """Return hardware and runtime info for the Info / Debug tab."""
        hw = configure.constants
        return {
            "cpu_name":        hw.get("cpu_name",         "unknown"),
            "cpu_count":       hw.get("cpu_count",          0),
            "total_ram_gb":    hw.get("total_ram_gb",        0),
            "windows_version": hw.get("windows_version",   "unknown"),
            "python_version":  sys.version.split()[0],
            "webview_version": hw.get("webview2_version",  "unknown"),
            "app_dir":         hw.get("app_dir",            "unknown"),
        }

    # ── Harmonic Treatment ────────────────────────────────────────────────────
    def _run_subset_sequence(self, freq_list, volume, duration_per_freq_min, harmonic_mult):
        """Play each frequency in subset sequentially for duration_per_freq_min minutes.
        Always uses sine wave and harmonic blending (Harmonic tab operation).
        """
        duration_seconds = duration_per_freq_min * 60
        for idx, freq_entry in enumerate(freq_list):
            if self._should_stop_subset:
                print(f"Subset playback interrupted at step {idx + 1}/{len(freq_list)}")
                break
            freq  = float(freq_entry['base'])
            label = freq_entry.get('label', f'{freq} Hz')
            try:
                print(f"Subset step {idx + 1}/{len(freq_list)}: {label} @ {freq} Hz")
                self._gen.start_stream(freq, harmonic_mult, volume, play_harmonic=True)
                time.sleep(duration_seconds)
                self._gen.stop_stream()
            except Exception as e:
                print(f"Error playing subset freq {freq}: {e}")
                break
        self._should_stop_subset = False
        print("Subset sequence complete.")

    def start_treatment(self, params):
        """Start Harmonic-tab treatment (base + 11th harmonic sine blend).

        params = {
            'freq':             float,
            'volume':           float,
            'timelength_steps': int,     # 1-12  (15-180 min)
            'play_mode':        str,     # 'single' | 'subset'
            'subset_key':       str      # e.g. 'Cancer lymphoma' for grouping
        }
        """
        try:
            freq             = float(params.get('freq', 432))
            vol              = float(params.get('volume', 0.5))
            hm               = int(self._config.get('harmonic_multiplier', 11))
            timelength_steps = int(params.get('timelength_steps', 1))
            play_mode        = params.get('play_mode', 'single')
            subset_key       = params.get('subset_key', None)

            duration_minutes = timelength_steps * 15

            print(f"Starting Treatment: {freq} Hz | {hm}th harmonic: {freq * hm:.0f} Hz | "
                  f"Vol: {vol} | Mode: {play_mode} | Duration: {duration_minutes} min")

            self.stop_treatment()

            if play_mode == 'subset' and subset_key:
                subset_freqs = [f for f in self._frequencies   if f['label'].startswith(subset_key)]
                if not subset_freqs:
                    subset_freqs = [f for f in self._fungus_freqs if f['label'].startswith(subset_key)]

                if subset_freqs:
                    self._should_stop_subset = False
                    self._subset_thread = threading.Thread(
                        target=self._run_subset_sequence,
                        args=(subset_freqs, vol, duration_minutes, hm),
                        daemon=True
                    )
                    self._subset_thread.start()
                    return {
                        "status": "playing_subset",
                        "count": len(subset_freqs),
                        "total_duration_min": duration_minutes * len(subset_freqs)
                    }
                else:
                    print(f"Warning: No subset frequencies found for key '{subset_key}'")
                    play_mode = 'single'

            # Single mode (or fallback from empty subset)
            self._gen.start_stream(freq, hm, vol, play_harmonic=True)

            self._config['last_freq']        = freq
            self._config['volume']           = vol
            self._config['timelength_steps'] = timelength_steps
            self._config['play_mode']        = play_mode
            configure.save_config(self._config)

            # Cancel any previously running auto-stop timer so it does not race
            # against the new stream when its timeout fires.
            if self._stop_event is not None:
                self._stop_event.set()
            stop_event       = threading.Event()
            self._stop_event = stop_event

            def auto_stop(ev=stop_event, mins=duration_minutes):
                cancelled = ev.wait(timeout=mins * 60)
                if cancelled:
                    return
                if self._gen.active:
                    print(f"Auto-stopping Harmonic treatment after {mins} minutes")
                    self._gen.stop_stream()

            self._stop_timer = threading.Thread(target=auto_stop, daemon=True)
            self._stop_timer.start()

            return {"status": "playing", "freq": freq,
                    "harmonic": freq * hm, "duration_min": duration_minutes}

        except Exception as e:
            print(f"Error starting treatment: {e}")
            return {"error": str(e)}

    # ── Healing Treatment ─────────────────────────────────────────────────────
    def start_healing(self, params):
        """Start Healing-tab treatment: pure base sine, no harmonic blending.

        params = {
            'freq':             float,
            'volume':           float,
            'timelength_steps': int,     # 1-12  (15-180 min)
        }
        """
        try:
            freq             = float(params.get('freq', 396))
            vol              = float(params.get('volume', 0.5))
            timelength_steps = int(params.get('timelength_steps', 1))
            duration_minutes = timelength_steps * 15

            print(f"Starting Healing: {freq} Hz (pure sine) | "
                  f"Vol: {vol} | Duration: {duration_minutes} min")

            # Stop any running stream (Harmonic or Healing) before starting
            self.stop_treatment()

            # Pure sine — no harmonic blending
            self._gen.start_stream(freq, 11, vol, play_harmonic=False)

            self._config['heal_volume']           = vol
            self._config['heal_timelength_steps'] = timelength_steps
            configure.save_config(self._config)

            # Auto-stop timer — same event/thread pattern as start_treatment
            if self._stop_event is not None:
                self._stop_event.set()
            stop_event       = threading.Event()
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
        """Stop all audio output (works for both Harmonic and Healing sessions)."""
        print("Stopping audio.")
        if self._stop_event is not None:
            self._stop_event.set()
        self._should_stop_subset = True
        if self._subset_thread and self._subset_thread.is_alive():
            self._subset_thread.join(timeout=1.0)
        self._gen.stop_stream()
        return {"status": "stopped"}

    def update_volume(self, volume):
        """Thread-safe live volume adjustment."""
        self._gen.update_volume(float(volume))
        return {"status": "volume_updated"}

    # ── Shutdown ──────────────────────────────────────────────────────────────
    def shutdown(self):
        """Called on window [X] close — audio cleanup + config flush to disk."""
        print("Shutting down Harmonic-Healer...")
        self.stop_treatment()
        configure.save_config(self._config)
        print("Audio stream stopped. Config saved. Goodbye.")


# =============================================================================
# Main GUI Loop
# =============================================================================
def main_loop(config):
    api = Api()

    # ── Build <option> blocks for the Harmonic tab dropdowns ─────────────────
    freq_options = ""
    for item in api._frequencies:
        label     = item['label'].replace('"', '&quot;')
        base      = item['base']
        group_key = item['label'].split('\u2013')[0].split(' - ')[0].strip()
        freq_options += f'<option value="{base}" data-key="{group_key}">{label}</option>\n'

    fungus_options = ""
    for item in api._fungus_freqs:
        label     = item['label'].replace('"', '&quot;')
        base      = item['base']
        group_key = item['label'].split('\u2013')[0].split(' - ')[0].strip()
        fungus_options += f'<option value="{base}" data-key="{group_key}">{label}</option>\n'

    # ── Build <optgroup>/<option> block for the Healing tab dropdown ──────────
    healing_options = ""
    current_group   = None
    for item in api._healing_freqs:
        g = item['group']
        if g != current_group:
            if current_group is not None:
                healing_options += '</optgroup>\n'
            healing_options += f'<optgroup label="{g}">\n'
            current_group = g
        base      = item['base']
        label     = item['label']
        desc      = item.get('desc', '').replace('"', '&quot;')
        freq_disp = f"{base:.2f} Hz" if base < 10 else f"{int(base)} Hz"
        healing_options += (
            f'<option value="{base}" data-desc="{desc}">'
            f'{freq_disp} \u2013 {label}'
            f'</option>\n'
        )
    if current_group is not None:
        healing_options += '</optgroup>\n'

    # ── Restore saved window size ─────────────────────────────────────────────
    win_w = int(config.get('window_width',  884))
    win_h = int(config.get('window_height', 522))

    # ── Saved Harmonic tab controls ───────────────────────────────────────────
    saved_steps = int(config.get('timelength_steps', 1))
    saved_mode  = config.get('play_mode', 'single')

    # ── Saved Healing tab controls ────────────────────────────────────────────
    saved_heal_steps = int(config.get('heal_timelength_steps', 1))
    heal_vol         = float(config.get('heal_volume', 0.5))

    # ── HTML / CSS / JS Template ──────────────────────────────────────────────
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
            width: 100%; max-width: 820px;
        }}
        .app-title {{
            text-align: center; font-size: 13px; font-weight: 700; color: #38bdf8;
            letter-spacing: 3px; text-transform: uppercase;
            padding-bottom: 14px; margin-bottom: 0; border-bottom: 1px solid #2d4263;
        }}
        .tab-nav {{
            display: flex; gap: 3px; padding: 10px 0 0;
            margin-bottom: 14px; border-bottom: 1px solid #2d4263;
        }}
        .tab-btn {{
            padding: 7px 20px; font-size: 12px; font-weight: 700;
            letter-spacing: 0.8px; text-transform: uppercase;
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
        .tab-btn.active[data-tab="healing"] {{ color: #22c55e; }}
        hr {{ border: none; border-top: 1px solid #2d4263; margin: 12px 0; }}
        .row {{
            display: flex; align-items: center; justify-content: center;
            gap: 10px; flex-wrap: wrap; margin: 10px 0;
        }}
        .rl {{
            font-weight: 600; font-size: 13px; color: #94a3b8;
            text-align: right; white-space: nowrap; flex-shrink: 0; min-width: 110px;
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
        .freq-box.heal {{ color: #86efac; border-color: #1a4731; }}
        .freq-arrow {{ font-size: 15px; color: #38bdf8; padding-bottom: 8px; flex-shrink: 0; }}
        .vol-wrap {{
            display: flex; align-items: center; gap: 8px; padding: 5px 12px;
            border: 1px solid #2d4263; border-radius: 5px;
            background: rgba(15,23,42,0.5); flex-shrink: 0;
        }}
        .vol-lbl {{ font-size: 13px; font-weight: 600; color: #94a3b8; white-space: nowrap; }}
        input[type="range"] {{ width: 90px; cursor: pointer; accent-color: #38bdf8; }}
        input[type="range"].heal-range {{ accent-color: #22c55e; }}
        #volumeValue, #healVolumeValue {{
            font-family: 'Consolas','Courier New',monospace; font-size: 13px;
            color: #7dd3fc; min-width: 30px; text-align: right;
        }}
        #healVolumeValue {{ color: #86efac; }}
        .canvas-wrap {{
            margin: 12px 0 8px; border: 1px solid #2d4263;
            border-radius: 7px; overflow: hidden; background: #070d1a;
        }}
        #waveCanvas, #healCanvas {{ display: block; width: 100%; height: 130px; }}
        .tl-wrap {{
            display: flex; align-items: center; gap: 8px; padding: 5px 12px;
            border: 1px solid #2d4263; border-radius: 5px;
            background: rgba(15,23,42,0.5); flex-shrink: 0;
        }}
        .tl-lbl {{ font-size: 13px; font-weight: 600; color: #94a3b8; white-space: nowrap; }}
        #timelengthSlider, #healTimelengthSlider {{ width: 130px; }}
        #timelengthValue, #healTimelengthValue {{
            font-family: 'Consolas','Courier New',monospace; font-size: 13px; color: #7dd3fc;
            min-width: 66px; text-align: right; white-space: nowrap;
        }}
        #healTimelengthValue {{ color: #86efac; }}
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
            padding: 10px 32px; font-size: 14px; font-weight: 700; letter-spacing: 0.5px;
            border-radius: 6px; border: 1px solid transparent; cursor: pointer;
            transition: background 0.15s, transform 0.1s, box-shadow 0.15s;
        }}
        button:hover {{ transform: translateY(-1px); }}
        button:active {{ transform: translateY(0px); }}
        #startBtn, #healStartBtn {{
            background: #15643a; color: #d1fae5; border-color: #22c55e;
        }}
        #startBtn:hover, #healStartBtn:hover {{
            background: #16a34a; box-shadow: 0 4px 14px rgba(34,197,94,0.35);
        }}
        #startBtn:disabled, #healStartBtn:disabled {{
            background: #1c3028; color: #4d7a60; border-color: #1c3028;
            cursor: not-allowed; transform: none; box-shadow: none;
        }}
        #stopBtn, #healStopBtn {{
            background: #641515; color: #fee2e2; border-color: #ef4444;
        }}
        #stopBtn:hover, #healStopBtn:hover {{
            background: #dc2626; box-shadow: 0 4px 14px rgba(239,68,68,0.35);
        }}
        #stopBtn:disabled, #healStopBtn:disabled {{
            background: #2d1c1c; color: #7a4d4d; border-color: #2d1c1c;
            cursor: not-allowed; transform: none; box-shadow: none;
        }}
        .status-bar {{
            text-align: center; padding: 9px 14px; background: #0f172a;
            border-left: 3px solid #38bdf8; border-radius: 0 5px 5px 0;
            font-family: 'Consolas','Courier New',monospace;
            font-size: 12px; color: #7dd3fc; letter-spacing: 0.8px; margin-top: 8px;
        }}
        #healStatusBar {{ border-left-color: #22c55e; color: #86efac; }}
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
        .info-refresh-row {{ display: flex; justify-content: flex-end; margin-top: 8px; }}
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
        .info-btn:active {{ transform: none !important; }}
    </style>
</head>
<body>
    <div class="container">

        <div class="app-title">&#9877; Harmonic-Healer</div>

        <div class="tab-nav">
            <button class="tab-btn active" data-tab="harmonic">
                &#9877; Harmonic
            </button>
            <button class="tab-btn" data-tab="healing">
                &#10022; Healing
            </button>
            <button class="tab-btn" data-tab="info">
                &#9432; Info / Debug
            </button>
        </div>

        <!-- ══════════════════════════════════════════════════════════════════
             TAB: Harmonic  (base + 11th harmonic sine)
             ══════════════════════════════════════════════════════════════════ -->
        <div id="tab-harmonic" class="tab-panel">

            <div class="row">
                <div class="mode-switch">
                    <span class="ms-label active"   id="msVirus">Virus</span>
                    <label class="ms-toggle" title="Switch between Virus and Fungus frequency sets">
                        <input type="checkbox" id="modeCheck">
                        <span class="ms-knob"></span>
                    </label>
                    <span class="ms-label inactive" id="msFungus">Fungus</span>
                </div>
                <span class="rl" id="typeLabel">Virus Type:</span>
                <select id="freqSelect">
                    {freq_options}
                </select>
                <select id="fungusSelect" style="display:none;">
                    {fungus_options}
                </select>
            </div>

            <div class="row">
                <span class="rl">Playback:</span>
                <div class="mode-switch">
                    <span class="ms-label active"   id="msSingle">Single</span>
                    <label class="ms-toggle"
                           title="Single: plays the selected frequency for the set duration.&#10;Subset: plays every frequency in the same group in sequence.">
                        <input type="checkbox" id="playModeCheck" {'checked' if saved_mode == 'subset' else ''}>
                        <span class="ms-knob"></span>
                    </label>
                    <span class="ms-label inactive" id="msSubset">Subset</span>
                </div>
                <div class="tl-wrap">
                    <span class="tl-lbl">Duration:</span>
                    <input type="range" id="timelengthSlider" min="1" max="12" step="1"
                           value="{saved_steps}">
                    <span id="timelengthValue">{saved_steps * 15} min</span>
                    <span id="subsetInfo" class="subset-info"></span>
                </div>
            </div>

            <div class="row">
                <span class="rl">Frequency:</span>
                <div class="freq-pair">
                    <div class="freq-block">
                        <span class="freq-tag">Base</span>
                        <div class="freq-box" id="baseFreq">432 Hz</div>
                    </div>
                    <span class="freq-arrow">&times;11 &rarr;</span>
                    <div class="freq-block">
                        <span class="freq-tag">11th Harmonic</span>
                        <div class="freq-box" id="harmFreq">4,752 Hz</div>
                    </div>
                </div>
            </div>

            <div id="ultrasoundWarning" class="us-warn" style="display:none;">
                &#9888; Frequency &gt;20 kHz &mdash; standard speakers will be silent.
                RF / plasma equipment required.
            </div>

            <hr>

            <div class="row">
                <span class="rl">Volume:</span>
                <div class="vol-wrap">
                    <span class="vol-lbl">Volume:</span>
                    <input type="range" id="volumeSlider" min="0" max="1" step="0.01"
                           value="{config.get('volume', 0.5)}">
                    <span id="volumeValue">{config.get('volume', 0.5):.2f}</span>
                </div>
            </div>

            <div class="canvas-wrap">
                <canvas id="waveCanvas"></canvas>
            </div>

            <div style="display:flex;gap:14px;justify-content:center;margin:12px 0 10px;">
                <button id="startBtn">&#9654;&nbsp; Start Treatment</button>
                <button id="stopBtn" disabled>&#9632;&nbsp; Stop Treatment</button>
            </div>

            <div id="statusBar" class="status-bar">SYSTEM READY</div>

        </div><!-- /#tab-harmonic -->

        <!-- ══════════════════════════════════════════════════════════════════
             TAB: Healing  (pure base sine)
             ══════════════════════════════════════════════════════════════════ -->
        <div id="tab-healing" class="tab-panel" style="display:none;">

            <div class="row">
                <span class="rl">Preset:</span>
                <select id="healSelect">
                    {healing_options}
                </select>
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
                &#9888; Frequency &lt;20 Hz &mdash; below standard audible range.
                May be felt rather than heard on conventional speakers.
            </div>

            <hr>

            <div class="row">
                <div class="vol-wrap">
                    <span class="vol-lbl">Volume:</span>
                    <input type="range" class="heal-range" id="healVolumeSlider"
                           min="0" max="1" step="0.01"
                           value="{heal_vol:.2f}">
                    <span id="healVolumeValue">{heal_vol:.2f}</span>
                </div>
                <div class="tl-wrap">
                    <span class="tl-lbl">Duration:</span>
                    <input type="range" class="heal-range" id="healTimelengthSlider"
                           min="1" max="12" step="1"
                           value="{saved_heal_steps}">
                    <span id="healTimelengthValue">{saved_heal_steps * 15} min</span>
                </div>
            </div>

            <div class="canvas-wrap">
                <canvas id="healCanvas"></canvas>
            </div>

            <div style="display:flex;gap:14px;justify-content:center;margin:12px 0 10px;">
                <button id="healStartBtn">&#9654;&nbsp; Start Healing</button>
                <button id="healStopBtn" disabled>&#9632;&nbsp; Stop Healing</button>
            </div>

            <div id="healStatusBar" class="status-bar">SYSTEM READY</div>

        </div><!-- /#tab-healing -->

        <!-- ══════════════════════════════════════════════════════════════════
             TAB: Info / Debug
             ══════════════════════════════════════════════════════════════════ -->
        <div id="tab-info" class="tab-panel" style="display:none;">

            <div class="info-card">
                <div class="info-app-name">Harmonic-Healer</div>
                <div class="info-subtitle">A sound frequency therapy tool for Windows.</div>
                <div class="info-links">
                    <p>
                        By&nbsp;<a href="mailto:wiseman-timelord@mail.com">WiseMan-TimeLord</a>
                        &nbsp;at&nbsp;<a href="http://wisetime.rf.gd/" target="_blank">WiseTime.Rf.Gd</a>
                    </p>
                    <p>Projects on&nbsp;<a href="https://github.com/wiseman-timelord" target="_blank">GitHub</a></p>
                    <p>
                        Support at&nbsp;
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
                    <button class="info-btn" id="refreshBtn">Refresh</button>
                </div>
            </div>

        </div><!-- /#tab-info -->

    </div><!-- /.container -->

    <script>
        // ════════════════════════════════════════════════════════════════════
        // Global JS error logger — surfaced in the Python terminal
        // ════════════════════════════════════════════════════════════════════
        window.addEventListener('error', function(e) {{
            console.error('[HH JS Error] ' + e.message +
                          ' (line ' + e.lineno + ')');
        }});
        window.addEventListener('unhandledrejection', function(e) {{
            console.error('[HH Promise Rejection] ' + e.reason);
        }});

        // ════════════════════════════════════════════════════════════════════
        // Shared helpers
        // ════════════════════════════════════════════════════════════════════
        var TWO_PI        = Math.PI * 2;
        var HARMONIC_MULT = 11;

        // apiReady() — safe check used before every pywebview.api call.
        // Guards against partial bridge initialisation on low-RAM machines
        // where pywebview's recursion errors can leave the api object broken.
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
            var hrs  = Math.floor(minutes / 60);
            var mins = minutes % 60;
            if (mins === 0) return hrs + ' hr';
            return hrs + ' hr ' + mins + ' min';
        }}

        // ════════════════════════════════════════════════════════════════════
        // HEALING TAB — State (MUST be defined BEFORE switchTab uses it)
        // ════════════════════════════════════════════════════════════════════
        var healFreq              = 396;
        var healIsPlaying         = false;
        var healTimelength        = {saved_heal_steps * 15};
        var healTreatmentTimer    = null;
        var healCountdownInterval = null;
        var healCountdownEnd      = 0;
        var healAnimId            = null;
        var healAnimPhi           = 0.0;

        // ════════════════════════════════════════════════════════════════════
        // HEALING TAB — Canvas functions (defined EARLY for switchTab)
        // ════════════════════════════════════════════════════════════════════
        function resizeHealCanvas() {{
            var hc  = document.getElementById('healCanvas');
            if (!hc) return;
            var dpr = window.devicePixelRatio || 1;
            var w   = hc.offsetWidth;
            if (w === 0) return;
            var h = hc.offsetHeight || 130;
            hc.width = w*dpr; hc.height = h*dpr;
            var hCtx = hc.getContext('2d');
            hCtx.setTransform(1,0,0,1,0,0); hCtx.scale(dpr, dpr);
            if (!healIsPlaying) drawHealWave();
        }}

        function drawHealWave() {{
            var hc   = document.getElementById('healCanvas');
            if (!hc) return;
            var hCtx = hc.getContext('2d');
            var W = hc.offsetWidth || hc.width;
            var H = hc.offsetHeight || hc.height;
            if (W === 0 || H === 0) return;
            var mid = H*0.50, amp = H*0.38, CYCLES = 3, phi = healAnimPhi;

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
            hCtx.fillText('\u2500\u2500 pure sine', 8, H-4);
            hCtx.fillStyle = 'rgba(134,239,172,0.50)'; hCtx.textAlign = 'right';
            hCtx.fillText(formatHz(healFreq), W-8, H-4);
            hCtx.textAlign = 'left'; hCtx.textBaseline = 'alphabetic';
        }}

        function startHealAnim() {{
            if (healAnimId) cancelAnimationFrame(healAnimId);
            (function loop() {{
                healAnimPhi = (healAnimPhi + 0.042) % TWO_PI;
                drawHealWave();
                if (healIsPlaying) healAnimId = requestAnimationFrame(loop);
            }})();
        }}

        function stopHealAnim() {{
            if (healAnimId) {{ cancelAnimationFrame(healAnimId); healAnimId = null; }}
            healAnimPhi = 0.0; drawHealWave();
        }}

        // ════════════════════════════════════════════════════════════════════
        // Tab system
        // ════════════════════════════════════════════════════════════════════
        var infoLoaded = false;

        function switchTab(name) {{
            document.querySelectorAll('.tab-panel').forEach(function(p) {{
                p.style.display = 'none';
            }});
            document.querySelectorAll('.tab-btn').forEach(function(b) {{
                b.classList.remove('active');
            }});
            var tabEl = document.getElementById('tab-' + name);
            if (tabEl) tabEl.style.display = '';
            document.querySelectorAll('.tab-btn').forEach(function(b) {{
                if (b.dataset.tab === name) b.classList.add('active');
            }});
            if (name === 'info' && !infoLoaded) loadInfoTab();
            if (name === 'healing') {{
                setTimeout(function() {{
                    resizeHealCanvas();
                    if (!healIsPlaying) drawHealWave();
                }}, 20);
            }}
        }}

        // ════════════════════════════════════════════════════════════════════
        // Info tab
        // ════════════════════════════════════════════════════════════════════
        function loadInfoTab() {{
            var pre = document.getElementById('constantsDisplay');
            if (!pre) return;
            if (!apiReady()) {{
                pre.textContent =
                    '  [Running without pywebview bridge]\n'
                    + '  Launch via launcher.py to see live data.';
                infoLoaded = true;
                return;
            }}
            pre.textContent = '  Loading\u2026';
            pywebview.api.get_constants().then(function(c) {{
                var ramStr = c.total_ram_gb ? c.total_ram_gb + ' GB' : 'unknown';
                var lines  = [
                    '  CPU Name .......... ' + (c.cpu_name        || 'unknown'),
                    '  Total Threads ..... ' + (c.cpu_count       || 0)  + 'T',
                    '  Total RAM ......... ' + ramStr,
                    '  Windows Version ... ' + (c.windows_version || 'unknown'),
                    '  Python Version .... v' + (c.python_version || 'unknown'),
                    '  WebView Version ... v' + (c.webview_version|| 'unknown'),
                    '  App Directory ..... ' + (c.app_dir         || 'unknown'),
                ];
                pre.textContent = lines.join('\n');
                infoLoaded = true;
            }}).catch(function(err) {{
                pre.textContent = '  Error fetching constants: ' + err;
            }});
        }}

        function refreshConstants() {{ infoLoaded = false; loadInfoTab(); }}

        // ════════════════════════════════════════════════════════════════════
        // HARMONIC TAB — State
        // ════════════════════════════════════════════════════════════════════
        var currentFreq       = 432;
        var isPlaying         = false;
        var timelengthMinutes = {saved_steps * 15};
        var playMode          = '{saved_mode}';
        var treatmentTimer    = null;
        var countdownInterval = null;
        var countdownEnd      = 0;
        var subsetQueue       = [];
        var subsetIndex       = 0;
        var currentSubsetStep = 0;

        function activeSelect() {{
            return document.getElementById(
                document.getElementById('modeCheck').checked ? 'fungusSelect' : 'freqSelect'
            );
        }}

        function updateFrequencyDisplay() {{
            var sel = activeSelect();
            if (!sel || !sel.options[sel.selectedIndex]) return;
            currentFreq = parseFloat(sel.value);
            document.getElementById('baseFreq').textContent = formatHz(currentFreq);
            document.getElementById('harmFreq').textContent = formatHz(currentFreq * HARMONIC_MULT);
            document.getElementById('ultrasoundWarning').style.display =
                currentFreq > 20000 ? 'block' : 'none';
            if (!isPlaying) drawWaveform();
            updateSubsetInfo();
        }}

        function toggleType() {{
            var isFungus = document.getElementById('modeCheck').checked;
            document.getElementById('freqSelect').style.display   = isFungus ? 'none' : '';
            document.getElementById('fungusSelect').style.display = isFungus ? '' : 'none';
            document.getElementById('typeLabel').textContent =
                isFungus ? 'Fungus Type:' : 'Virus Type:';
            document.getElementById('msVirus').className  =
                'ms-label ' + (isFungus ? 'inactive' : 'active');
            document.getElementById('msFungus').className =
                'ms-label ' + (isFungus ? 'active' : 'inactive');
            updateFrequencyDisplay();
        }}

        function updateVolume() {{
            var vol = document.getElementById('volumeSlider').value;
            document.getElementById('volumeValue').textContent = parseFloat(vol).toFixed(2);
            if (apiReady()) pywebview.api.update_volume(vol);
        }}

        function updateTimelength() {{
            var steps = parseInt(document.getElementById('timelengthSlider').value);
            timelengthMinutes = steps * 15;
            document.getElementById('timelengthValue').textContent = formatDuration(timelengthMinutes);
            if (apiReady()) pywebview.api.save_setting('timelength_steps', steps);
            updateSubsetInfo();
        }}

        function updatePlayMode() {{
            var isSubset = document.getElementById('playModeCheck').checked;
            playMode = isSubset ? 'subset' : 'single';
            document.getElementById('msSingle').className =
                'ms-label ' + (isSubset ? 'inactive' : 'active');
            document.getElementById('msSubset').className =
                'ms-label ' + (isSubset ? 'active' : 'inactive');
            if (apiReady()) pywebview.api.save_setting('play_mode', playMode);
            updateSubsetInfo();
        }}

        function getGroupKey(label) {{
            var idx = label.indexOf(' \u2013 ');
            if (idx === -1) idx = label.indexOf(' - ');
            return idx !== -1 ? label.substring(0, idx).trim() : label.trim();
        }}

        function buildSubsetQueue() {{
            var sel = activeSelect();
            if (!sel || !sel.options[sel.selectedIndex]) return [];
            var selOption = sel.options[sel.selectedIndex];
            var groupKey  = selOption.dataset.key || getGroupKey(selOption.text);
            var queue     = [];
            for (var i = 0; i < sel.options.length; i++) {{
                var opt    = sel.options[i];
                var optKey = opt.dataset.key || getGroupKey(opt.text);
                if (optKey === groupKey)
                    queue.push({{ freq: parseFloat(opt.value), label: opt.text, key: optKey }});
            }}
            return queue;
        }}

        function updateSubsetInfo() {{
            var infoEl   = document.getElementById('subsetInfo');
            var isSubset = document.getElementById('playModeCheck').checked;
            if (!isSubset) {{ infoEl.textContent = ''; return; }}
            var queue = buildSubsetQueue();
            if (queue.length <= 1) {{
                infoEl.textContent = '(no other frequencies in subset \u2014 plays as single)';
                infoEl.style.color = '#64748b';
            }} else {{
                infoEl.textContent = '(' + formatDuration(queue.length * timelengthMinutes) + ')';
                infoEl.style.color = '#38bdf8';
            }}
        }}

        function updateStatus(msg) {{ document.getElementById('statusBar').textContent = msg; }}

        function startCountdown(durationMs) {{
            clearCountdown();
            countdownEnd = Date.now() + durationMs;
            tickCountdown();
            countdownInterval = setInterval(tickCountdown, 1000);
        }}
        function clearCountdown() {{
            if (countdownInterval) {{ clearInterval(countdownInterval); countdownInterval = null; }}
        }}
        function tickCountdown() {{
            var remaining = Math.max(0, countdownEnd - Date.now());
            var totalSecs = Math.ceil(remaining / 1000);
            var mins = Math.floor(totalSecs / 60);
            var secs = totalSecs % 60;
            var timeStr = mins + ':' + String(secs).padStart(2, '0');
            var msg;
            if (playMode === 'subset' && subsetQueue.length > 0) {{
                msg = 'SUBSET ' + currentSubsetStep + '/' + subsetQueue.length
                    + '  \u2500\u2500  ' + formatHz(currentFreq)
                    + ' + ' + formatHz(currentFreq * HARMONIC_MULT)
                    + '  \u2500\u2500  ' + timeStr;
            }} else {{
                msg = 'RESONATING  \u2500\u2500  '
                    + formatHz(currentFreq) + ' + ' + formatHz(currentFreq * HARMONIC_MULT)
                    + '  \u2500\u2500  ' + timeStr;
            }}
            updateStatus(msg);
        }}

        function clearTreatmentTimer() {{
            if (treatmentTimer) {{ clearTimeout(treatmentTimer); treatmentTimer = null; }}
        }}

        function autoStop() {{
            clearTreatmentTimer(); clearCountdown();
            var done = function() {{
                isPlaying = false; stopWaveAnim();
                var msg = (playMode === 'subset' && subsetQueue.length > 1)
                    ? 'PROGRAM COMPLETE  \u2500\u2500  AUTO OFF  ('
                      + subsetQueue.length + '/' + subsetQueue.length + ' played)'
                    : 'PROGRAM COMPLETE  \u2500\u2500  AUTO OFF';
                updateStatus(msg);
                document.getElementById('startBtn').disabled = false;
                document.getElementById('stopBtn').disabled  = true;
            }};
            if (apiReady()) pywebview.api.stop_treatment().then(done); else done();
        }}

        function playSubsetItem(vol, durationMs) {{
            if (subsetIndex >= subsetQueue.length) {{ autoStop(); return; }}
            var item          = subsetQueue[subsetIndex];
            currentSubsetStep = subsetIndex + 1;
            currentFreq       = item.freq;
            updateStatus('LOADING SUBSET ' + currentSubsetStep + '/' + subsetQueue.length + '...');

            var call = apiReady()
                ? pywebview.api.start_treatment({{
                    freq: item.freq, volume: vol,
                    timelength_steps: Math.round(timelengthMinutes / 15),
                    play_mode: 'single', subset_key: item.key
                  }})
                : Promise.resolve({{status: 'playing'}});

            call.then(function(result) {{
                if (result && result.error) {{
                    updateStatus('ERROR: ' + result.error); autoStop(); return;
                }}
                isPlaying = true; updateFrequencyDisplay();
                if (!animId) startWaveAnim();
                document.getElementById('startBtn').disabled = true;
                document.getElementById('stopBtn').disabled  = false;
                startCountdown(durationMs);
                treatmentTimer = setTimeout(function() {{
                    subsetIndex++;
                    playSubsetItem(vol, durationMs);
                }}, durationMs);
            }}).catch(function(err) {{ console.error('API error:', err); autoStop(); }});
        }}

        function startResonance() {{
            clearTreatmentTimer(); clearCountdown();
            var vol        = parseFloat(document.getElementById('volumeSlider').value);
            var durationMs = timelengthMinutes * 60 * 1000;

            if (playMode === 'subset') {{
                subsetQueue = buildSubsetQueue();
                if (subsetQueue.length === 0) {{
                    updateStatus('ERROR: No frequencies in subset'); return;
                }}
                subsetIndex = 0; currentSubsetStep = 0;
                playSubsetItem(vol, durationMs);
            }} else {{
                updateStatus('INITIALIZING AUDIO...');
                var call = apiReady()
                    ? pywebview.api.start_treatment({{
                        freq: currentFreq, volume: vol,
                        timelength_steps: Math.round(timelengthMinutes / 15),
                        play_mode: 'single', subset_key: null
                      }})
                    : Promise.resolve({{status: 'playing'}});
                call.then(function(result) {{
                    if (result && result.error) {{
                        updateStatus('ERROR: ' + result.error);
                        document.getElementById('startBtn').disabled = false;
                    }} else {{
                        isPlaying = true; startWaveAnim();
                        document.getElementById('startBtn').disabled = true;
                        document.getElementById('stopBtn').disabled  = false;
                        startCountdown(durationMs);
                        treatmentTimer = setTimeout(function() {{ autoStop(); }}, durationMs);
                    }}
                }}).catch(function(err) {{
                    console.error('API error:', err);
                    updateStatus('ERROR: ' + err);
                    document.getElementById('startBtn').disabled = false;
                }});
            }}
        }}

        function stopResonance() {{
            clearTreatmentTimer(); clearCountdown();
            updateStatus('STOPPING...');
            var done = function() {{
                isPlaying = false; stopWaveAnim(); updateStatus('SYSTEM READY');
                document.getElementById('startBtn').disabled = false;
                document.getElementById('stopBtn').disabled  = true;
            }};
            if (apiReady()) pywebview.api.stop_treatment().then(done); else done();
        }}

        // ════════════════════════════════════════════════════════════════════
        // HARMONIC TAB — Canvas
        // ════════════════════════════════════════════════════════════════════
        var canvas  = document.getElementById('waveCanvas');
        var ctx     = canvas.getContext('2d');
        var animId  = null;
        var animPhi = 0.0;

        function resizeCanvas() {{
            var dpr = window.devicePixelRatio || 1;
            var w   = canvas.offsetWidth;
            var h   = canvas.offsetHeight || 130;
            canvas.width  = w * dpr; canvas.height = h * dpr;
            ctx.setTransform(1,0,0,1,0,0); ctx.scale(dpr, dpr);
            if (!isPlaying) drawWaveform();
        }}

        function drawWaveform() {{
            var W = canvas.offsetWidth || canvas.width;
            var H = canvas.offsetHeight || canvas.height;
            if (W === 0 || H === 0) return;
            var mid = H*0.50, amp = H*0.34, CYCLES = 3, phi = animPhi;

            ctx.fillStyle = '#070d1a'; ctx.fillRect(0, 0, W, H);
            ctx.lineWidth = 1; ctx.strokeStyle = 'rgba(45,66,99,0.7)';
            [0.12,0.31,0.50,0.69,0.88].forEach(function(f) {{
                ctx.beginPath(); ctx.moveTo(0, H*f); ctx.lineTo(W, H*f); ctx.stroke();
            }});
            ctx.strokeStyle = 'rgba(45,66,99,0.4)';
            for (var gx = 1; gx < 8; gx++) {{
                ctx.beginPath(); ctx.moveTo(W*gx/8, 0); ctx.lineTo(W*gx/8, H); ctx.stroke();
            }}
            ctx.strokeStyle = 'rgba(56,189,248,0.18)';
            ctx.beginPath(); ctx.moveTo(0, mid); ctx.lineTo(W, mid); ctx.stroke();

            // 11th harmonic — amber
            ctx.beginPath(); ctx.strokeStyle = 'rgba(251,191,36,0.30)'; ctx.lineWidth = 1;
            for (var p1 = 0; p1 <= W; p1++) {{
                var t1 = (p1/W)*CYCLES*TWO_PI;
                var y1 = mid - Math.sin(t1*HARMONIC_MULT + phi*HARMONIC_MULT)*0.40*amp;
                if (p1===0) ctx.moveTo(p1,y1); else ctx.lineTo(p1,y1);
            }}
            ctx.stroke();

            // Base sine — pale
            ctx.beginPath(); ctx.strokeStyle = 'rgba(226,232,240,0.55)'; ctx.lineWidth = 1.5;
            for (var p2 = 0; p2 <= W; p2++) {{
                var t2 = (p2/W)*CYCLES*TWO_PI;
                var y2 = mid - Math.sin(t2 + phi)*amp;
                if (p2===0) ctx.moveTo(p2,y2); else ctx.lineTo(p2,y2);
            }}
            ctx.stroke();

            // Composite — cyan glow
            ctx.beginPath(); ctx.strokeStyle = '#38bdf8'; ctx.lineWidth = 2;
            ctx.shadowBlur = 7; ctx.shadowColor = 'rgba(56,189,248,0.55)';
            for (var p3 = 0; p3 <= W; p3++) {{
                var t3   = (p3/W)*CYCLES*TWO_PI;
                var bv   = Math.sin(t3 + phi);
                var hv   = Math.sin(t3*HARMONIC_MULT + phi*HARMONIC_MULT)*0.40;
                var y3   = mid - ((bv + hv)/1.40)*amp;
                if (p3===0) ctx.moveTo(p3,y3); else ctx.lineTo(p3,y3);
            }}
            ctx.stroke(); ctx.shadowBlur = 0;

            ctx.font = '10px Consolas,monospace'; ctx.textBaseline = 'bottom';
            ctx.fillStyle = 'rgba(56,189,248,0.75)';
            ctx.fillText('\u2500\u2500 composite (base + 11th harmonic)', 8, H-4);
            ctx.fillStyle = 'rgba(125,211,252,0.50)'; ctx.textAlign = 'right';
            ctx.fillText(formatHz(currentFreq)+'  +  '+formatHz(currentFreq*HARMONIC_MULT), W-8, H-4);
            ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
        }}

        function startWaveAnim() {{
            if (animId) cancelAnimationFrame(animId);
            (function loop() {{
                animPhi = (animPhi + 0.042) % TWO_PI;
                drawWaveform();
                if (isPlaying) animId = requestAnimationFrame(loop);
            }})();
        }}
        function stopWaveAnim() {{
            if (animId) {{ cancelAnimationFrame(animId); animId = null; }}
            animPhi = 0.0; drawWaveform();
        }}

        new ResizeObserver(function() {{ resizeCanvas(); }}).observe(canvas);

        // ════════════════════════════════════════════════════════════════════
        // HEALING TAB — Functions
        // ════════════════════════════════════════════════════════════════════
        function updateHealDisplay() {{
            var sel = document.getElementById('healSelect');
            if (!sel || !sel.options[sel.selectedIndex]) return;
            healFreq = parseFloat(sel.value);
            var desc = sel.options[sel.selectedIndex].getAttribute('data-desc') || '';
            document.getElementById('healFreqBox').textContent = formatHz(healFreq);
            document.getElementById('healDesc').textContent    = desc;
            document.getElementById('infrasoundWarning').style.display =
                healFreq < 20 ? 'block' : 'none';
            if (!healIsPlaying) drawHealWave();
        }}

        function updateHealVolume() {{
            var vol = parseFloat(document.getElementById('healVolumeSlider').value);
            document.getElementById('healVolumeValue').textContent = vol.toFixed(2);
            if (apiReady()) {{
                pywebview.api.update_volume(vol);
                pywebview.api.save_setting('heal_volume', vol);
            }}
        }}

        function updateHealTimelength() {{
            var steps = parseInt(document.getElementById('healTimelengthSlider').value);
            healTimelength = steps * 15;
            document.getElementById('healTimelengthValue').textContent = formatDuration(healTimelength);
            if (apiReady()) pywebview.api.save_setting('heal_timelength_steps', steps);
        }}

        function updateHealStatus(msg) {{
            document.getElementById('healStatusBar').textContent = msg;
        }}

        function startHealCountdown(durationMs) {{
            clearHealCountdown();
            healCountdownEnd = Date.now() + durationMs;
            tickHealCountdown();
            healCountdownInterval = setInterval(tickHealCountdown, 1000);
        }}
        function clearHealCountdown() {{
            if (healCountdownInterval) {{ clearInterval(healCountdownInterval); healCountdownInterval = null; }}
        }}
        function tickHealCountdown() {{
            var remaining = Math.max(0, healCountdownEnd - Date.now());
            var totalSecs = Math.ceil(remaining / 1000);
            var mins = Math.floor(totalSecs / 60);
            var secs = totalSecs % 60;
            updateHealStatus(
                'HEALING  \u2500\u2500  ' + formatHz(healFreq)
                + '  \u2500\u2500  ' + mins + ':' + String(secs).padStart(2,'0')
            );
        }}
        function clearHealTimer() {{
            if (healTreatmentTimer) {{ clearTimeout(healTreatmentTimer); healTreatmentTimer = null; }}
        }}

        function autoStopHealing() {{
            clearHealTimer(); clearHealCountdown();
            var done = function() {{
                healIsPlaying = false; stopHealAnim();
                updateHealStatus('HEALING COMPLETE  \u2500\u2500  AUTO OFF');
                document.getElementById('healStartBtn').disabled = false;
                document.getElementById('healStopBtn').disabled  = true;
            }};
            if (apiReady()) pywebview.api.stop_treatment().then(done); else done();
        }}

        function startHealing() {{
            clearHealTimer(); clearHealCountdown();
            var vol        = parseFloat(document.getElementById('healVolumeSlider').value);
            var durationMs = healTimelength * 60 * 1000;
            updateHealStatus('INITIALIZING HEALING TONE...');

            var call = apiReady()
                ? pywebview.api.start_healing({{
                    freq: healFreq, volume: vol,
                    timelength_steps: Math.round(healTimelength / 15)
                  }})
                : Promise.resolve({{status: 'playing'}});

            call.then(function(result) {{
                if (result && result.error) {{
                    updateHealStatus('ERROR: ' + result.error);
                    document.getElementById('healStartBtn').disabled = false;
                }} else {{
                    healIsPlaying = true; startHealAnim();
                    document.getElementById('healStartBtn').disabled = true;
                    document.getElementById('healStopBtn').disabled  = false;
                    startHealCountdown(durationMs);
                    healTreatmentTimer = setTimeout(function() {{ autoStopHealing(); }}, durationMs);
                }}
            }}).catch(function(err) {{
                console.error('Healing API error:', err);
                updateHealStatus('ERROR: ' + err);
                document.getElementById('healStartBtn').disabled = false;
            }});
        }}

        function stopHealing() {{
            clearHealTimer(); clearHealCountdown();
            updateHealStatus('STOPPING...');
            var done = function() {{
                healIsPlaying = false; stopHealAnim(); updateHealStatus('SYSTEM READY');
                document.getElementById('healStartBtn').disabled = false;
                document.getElementById('healStopBtn').disabled  = true;
            }};
            if (apiReady()) pywebview.api.stop_treatment().then(done); else done();
        }}

        new ResizeObserver(function() {{
            if (document.getElementById('tab-healing').style.display !== 'none')
                resizeHealCanvas();
        }}).observe(document.getElementById('healCanvas'));

        // ════════════════════════════════════════════════════════════════════
        // Window size persistence (debounced)
        // ════════════════════════════════════════════════════════════════════
        window.addEventListener('resize', (function() {{
            var t;
            return function() {{
                clearTimeout(t);
                t = setTimeout(function() {{
                    if (apiReady())
                        pywebview.api.save_window_size(
                            document.documentElement.clientWidth,
                            document.documentElement.clientHeight
                        );
                }}, 700);
            }};
        }})());

        // ════════════════════════════════════════════════════════════════════
        // Initialise on DOM ready
        // ════════════════════════════════════════════════════════════════════
        function initApp() {{
            // ── Bind all interactive controls ──
            document.querySelectorAll('.tab-btn').forEach(function(btn) {{
                btn.addEventListener('click', function() {{ switchTab(btn.dataset.tab); }});
            }});
            document.getElementById('modeCheck').addEventListener('change', toggleType);
            document.getElementById('freqSelect').addEventListener('change', updateFrequencyDisplay);
            document.getElementById('fungusSelect').addEventListener('change', updateFrequencyDisplay);
            document.getElementById('playModeCheck').addEventListener('change', updatePlayMode);
            document.getElementById('timelengthSlider').addEventListener('input', updateTimelength);
            document.getElementById('volumeSlider').addEventListener('input', updateVolume);
            document.getElementById('startBtn').addEventListener('click', startResonance);
            document.getElementById('stopBtn').addEventListener('click', stopResonance);
            document.getElementById('healSelect').addEventListener('change', updateHealDisplay);
            document.getElementById('healVolumeSlider').addEventListener('input', updateHealVolume);
            document.getElementById('healTimelengthSlider').addEventListener('input', updateHealTimelength);
            document.getElementById('healStartBtn').addEventListener('click', startHealing);
            document.getElementById('healStopBtn').addEventListener('click', stopHealing);
            var _rb = document.getElementById('refreshBtn');
            if (_rb) _rb.addEventListener('click', refreshConstants);

            resizeCanvas();
            updateFrequencyDisplay();
            document.getElementById('volumeValue').textContent =
                parseFloat(document.getElementById('volumeSlider').value).toFixed(2);
            var steps = parseInt(document.getElementById('timelengthSlider').value);
            timelengthMinutes = steps * 15;
            document.getElementById('timelengthValue').textContent = formatDuration(timelengthMinutes);
            playMode = document.getElementById('playModeCheck').checked ? 'subset' : 'single';
            updateSubsetInfo();

            document.getElementById('healVolumeValue').textContent =
                parseFloat(document.getElementById('healVolumeSlider').value).toFixed(2);
            var hs = parseInt(document.getElementById('healTimelengthSlider').value);
            healTimelength = hs * 15;
            document.getElementById('healTimelengthValue').textContent = formatDuration(healTimelength);
            updateHealDisplay();

            console.log('[HH] Application initialized successfully');
        }}

        // Use DOMContentLoaded OR run immediately if already loaded
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', initApp);
        }} else {{
            initApp();
        }}

        // Restore persisted settings once the pywebview bridge is ready
        window.addEventListener('pywebviewready', function() {{
            console.log('[HH] pywebview bridge ready');
            if (!apiReady()) {{
                console.warn('[HH] pywebview bridge not available');
                return;
            }}
            pywebview.api.get_config().then(function(cfg) {{
                if (cfg.volume !== undefined) {{
                    document.getElementById('volumeSlider').value = cfg.volume;
                    document.getElementById('volumeValue').textContent =
                        parseFloat(cfg.volume).toFixed(2);
                }}
                if (cfg.timelength_steps !== undefined) {{
                    var s = parseInt(cfg.timelength_steps);
                    document.getElementById('timelengthSlider').value = s;
                    timelengthMinutes = s * 15;
                    document.getElementById('timelengthValue').textContent =
                        formatDuration(timelengthMinutes);
                }}
                if (cfg.play_mode === 'subset') {{
                    document.getElementById('playModeCheck').checked = true;
                    playMode = 'subset'; updatePlayMode();
                }}
                updateFrequencyDisplay();

                if (cfg.heal_volume !== undefined) {{
                    document.getElementById('healVolumeSlider').value = cfg.heal_volume;
                    document.getElementById('healVolumeValue').textContent =
                        parseFloat(cfg.heal_volume).toFixed(2);
                }}
                if (cfg.heal_timelength_steps !== undefined) {{
                    var hs = parseInt(cfg.heal_timelength_steps);
                    document.getElementById('healTimelengthSlider').value = hs;
                    healTimelength = hs * 15;
                    document.getElementById('healTimelengthValue').textContent =
                        formatDuration(healTimelength);
                }}
                updateHealDisplay();
            }}).catch(function(err) {{ console.error('get_config error:', err); }});
        }});
    </script>
</body>
</html>"""

    # ── Create window ─────────────────────────────────────────────────────────
    try:
        window = webview.create_window(
            configure.APP_TITLE,
            html=html,
            js_api=api,
            width=win_w,
            height=win_h,
            resizable=True,
            text_select=True,
        )
        api._set_window(window)

        def on_window_closing():
            api.shutdown()
            return True

        window.events.closing += on_window_closing

        # Explicitly request the Edge WebView2 (edgechromium) backend.
        # Without this, pywebview may fall back to MSHTML and produce
        # recursive COM E_NOINTERFACE errors from the accessibility tree.
        webview.start(gui='edgechromium', debug=False)

    except TypeError as te:
        if "unexpected keyword argument" in str(te):
            print(f"[WARN] pywebview version compatibility issue: {te}")
            print("[WARN] Trying minimal window creation parameters...")
            try:
                window = webview.create_window(
                    configure.APP_TITLE,
                    html=html,
                    js_api=api,
                    width=win_w,
                    height=win_h,
                )
                api._set_window(window)
                window.events.closing += lambda: api.shutdown() or True
                webview.start(gui='edgechromium')
            except Exception as e2:
                print(f"[ERROR] Fallback window creation failed: {e2}")
                api.shutdown()
                return
        else:
            raise
    except Exception as e:
        print(f"[ERROR] Failed to initialize GUI: {e}")
        print("Falling back to console-only mode with audio generation...")
        api.shutdown()
        return

    print("GUI closed. Shutdown complete.")
