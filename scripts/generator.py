"""
generator.py – Thread-safe audio generation using PortAudio via sounddevice.

Only sine waves are produced.  This is intentional: square and sawtooth
waveforms are mathematically impure composites that would introduce unintended
harmonic content and undermine the precision required for resonance-based
operation.

Two playback modes are supported:
  - Harmonic mode  (play_harmonic=True):  base sine + (base × harmonic_mult) sine,
                                          mixed at equal amplitude — Anti-Viral / Anti-Fungal.
  - Healing  mode  (play_harmonic=False): base sine only, full amplitude — Healing tab.
"""
import numpy as np
import sounddevice as sd
import math

from . import configure

TWO_PI = 2.0 * math.pi


class SoundGenerator:
    """Thread-safe, continuous audio stream using PortAudio via sounddevice.

    Phase is tracked in radians (mod 2π) to prevent float64 precision loss
    during long-running sessions.  The blocksize of 1024 frames (~23 ms at
    44 100 Hz) is comfortable for a Core 2 Duo without glitching; modern
    hardware running at AVX2 will handle even smaller blocks.
    """

    def __init__(self):
        self.active           = False
        self.stream           = None
        self.samplerate       = 44100
        self.current_freq     = 0.0
        self.current_harmonic = 11
        self.volume           = 0.5
        self.play_harmonic    = True
        self.device           = None   # None = system default
        self.phase_base       = 0.0
        self.phase_harm       = 0.0

    def _callback(self, outdata: np.ndarray, frames: int, time_info, status):
        if not self.active:
            outdata.fill(0)
            return

        omega_base  = TWO_PI * self.current_freq
        frame_idx   = np.arange(frames, dtype=np.float64)
        dt          = 1.0 / self.samplerate

        phases_base = self.phase_base + omega_base * frame_idx * dt
        wave_base   = np.sin(phases_base)
        self.phase_base = (self.phase_base + omega_base * frames * dt) % TWO_PI

        if self.play_harmonic:
            omega_harm  = omega_base * self.current_harmonic
            phases_harm = self.phase_harm + omega_harm * frame_idx * dt
            wave_harm   = np.sin(phases_harm)
            self.phase_harm = (self.phase_harm + omega_harm * frames * dt) % TWO_PI
            wave = (wave_base + wave_harm) * 0.5 * self.volume
        else:
            self.phase_harm = 0.0
            wave = wave_base * self.volume

        # Mono stream; if stereo device requested, callback still gets 1-ch buffer
        # because we open with channels=1.  Duplicate if outdata has more channels.
        ch = outdata.shape[1] if outdata.ndim > 1 else 1
        if ch == 1:
            outdata[:, 0] = wave.astype(np.float32)
        else:
            for c in range(ch):
                outdata[:, c] = wave.astype(np.float32)

    def start_stream(self, freq_base: float, harmonic_mult: int = 11,
                     volume: float = 0.5, play_harmonic: bool = True,
                     device=None):
        """Begin audio output on the (re-detected) default Windows output device.

        Args:
            freq_base:      Base frequency in Hz.
            harmonic_mult:  Harmonic multiplier (default 11).  Ignored when
                            play_harmonic is False.
            volume:         Output gain in [0.0, 1.0].
            play_harmonic:  True  → base + harmonic sine blend.
                            False → base sine only (Healing).
            device:         Optional explicit device index.  If None, the
                            current system default output is used.
        """
        if freq_base > 20000:
            print(
                f"NOTE: {freq_base:.0f} Hz is above the audible range (>20 kHz). "
                "Standard speakers will be silent. Use RF/plasma equipment."
            )

        self.current_freq     = float(freq_base)
        self.current_harmonic = int(harmonic_mult)
        self.volume           = max(0.0, min(1.0, float(volume)))
        self.play_harmonic    = bool(play_harmonic)
        self.active           = True
        self.phase_base       = 0.0
        self.phase_harm       = 0.0

        # Re-detect default output so user can switch devices between runs
        if device is None:
            device = configure.get_default_output_device()
        self.device = device

        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

        # Prefer device's default sample rate when available
        try:
            if device is not None:
                info = sd.query_devices(device)
                sr = int(info.get("default_samplerate") or 44100)
                if sr > 0:
                    self.samplerate = sr
        except Exception:
            self.samplerate = 44100

        try:
            kwargs = dict(
                samplerate=self.samplerate,
                channels=1,
                callback=self._callback,
                dtype="float32",
                blocksize=1024,
            )
            if device is not None:
                kwargs["device"] = device
            self.stream = sd.OutputStream(**kwargs)
            self.stream.start()
            dev_label = device if device is not None else "system default"
            print(f"[Audio] Stream started on device={dev_label}  "
                  f"sr={self.samplerate}  freq={freq_base:.2f} Hz")
        except Exception as exc:
            print(f"Audio Stream Error: {exc}")
            self.active = False

    def stop_stream(self):
        """Halt audio output and release the PortAudio stream."""
        self.active = False
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def update_volume(self, volume: float):
        """Thread-safe volume change — takes effect on the next callback block."""
        self.volume = max(0.0, min(1.0, float(volume)))