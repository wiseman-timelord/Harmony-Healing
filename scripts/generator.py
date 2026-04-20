"""
generator.py – Thread-safe audio generation using PortAudio via sounddevice.

Only sine waves are produced.  This is intentional: square and sawtooth
waveforms are mathematically impure composites that would introduce unintended
harmonic content and undermine the precision required for resonance-based
operation.

Two playback modes are supported:
  - Harmonic mode  (play_harmonic=True):  base sine + (base × harmonic_mult) sine,
                                          mixed at equal amplitude — the Harmonic tab.
  - Healing  mode  (play_harmonic=False): base sine only, full amplitude — the
                                          Healing tab.
"""
import numpy as np
import sounddevice as sd
import math

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
        self.samplerate       = 44100       # Standard CD quality
        self.current_freq     = 0.0
        self.current_harmonic = 11
        self.volume           = 0.5
        self.play_harmonic    = True        # False = healing / pure-tone mode
        # Phase accumulators in RADIANS (mod 2π) — prevents unbounded growth
        self.phase_base       = 0.0
        self.phase_harm       = 0.0

    # ──────────────────────────────────────────────────────────────────────────
    #   PortAudio real-time callback
    # ──────────────────────────────────────────────────────────────────────────
    def _callback(self, outdata: np.ndarray, frames: int, time_info, status):
        if not self.active:
            outdata.fill(0)
            return

        omega_base  = TWO_PI * self.current_freq
        frame_idx   = np.arange(frames, dtype=np.float64)
        dt          = 1.0 / self.samplerate

        # Base sine wave
        phases_base = self.phase_base + omega_base * frame_idx * dt
        wave_base   = np.sin(phases_base)
        self.phase_base = (self.phase_base + omega_base * frames * dt) % TWO_PI

        if self.play_harmonic:
            # Blend base + Nth harmonic at equal weight — Harmonic tab mode
            omega_harm  = omega_base * self.current_harmonic
            phases_harm = self.phase_harm + omega_harm * frame_idx * dt
            wave_harm   = np.sin(phases_harm)
            self.phase_harm = (self.phase_harm + omega_harm * frames * dt) % TWO_PI
            wave = (wave_base + wave_harm) * 0.5 * self.volume
        else:
            # Pure base sine only — Healing tab mode
            self.phase_harm = 0.0
            wave = wave_base * self.volume

        outdata[:, 0] = wave.astype(np.float32)

    # ──────────────────────────────────────────────────────────────────────────
    #   Public interface
    # ──────────────────────────────────────────────────────────────────────────
    def start_stream(self, freq_base: float, harmonic_mult: int = 11,
                     volume: float = 0.5, play_harmonic: bool = True):
        """Begin audio output.

        Args:
            freq_base:      Base frequency in Hz.
            harmonic_mult:  Harmonic multiplier (default 11).  Ignored when
                            play_harmonic is False.
            volume:         Output gain in [0.0, 1.0].
            play_harmonic:  True  → base + harmonic sine blend (Harmonic tab).
                            False → base sine only (Healing tab).

        Note:
            Frequencies above 20 kHz are ultrasound; standard speakers will be
            silent.  Use RF/plasma equipment for those ranges.
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

        # Close any existing stream cleanly before opening a new one
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

        try:
            self.stream = sd.OutputStream(
                samplerate=self.samplerate,
                channels=1,
                callback=self._callback,
                dtype="float32",
                blocksize=1024,
            )
            self.stream.start()
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
