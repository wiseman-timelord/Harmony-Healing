"""
utilities.py – General-purpose helpers for Harmonic-Healer.
No global state lives here; see configure.py for all globals/lists/maps.
"""


def format_hz(freq: float) -> str:
    """
    Return a human-readable frequency string.
    ≥ 1 MHz → '1.00 MHz'
    ≥ 1 kHz → '1.00 kHz'
    < 1 kHz → '440 Hz'
    """
    if freq >= 1_000_000:
        return f"{freq / 1_000_000:.2f} MHz"
    elif freq >= 1_000:
        return f"{freq / 1_000:.2f} kHz"
    else:
        return f"{int(freq)} Hz"


def format_hz_pair(base: float, multiplier: int) -> str:
    """Return a formatted string showing both base and harmonic frequency."""
    harmonic = base * multiplier
    return f"{format_hz(base)} + {format_hz(harmonic)} ({multiplier}th harmonic)"


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value to [lo, hi]."""
    return max(lo, min(hi, float(value)))


def separator(char: str = "=", length: int = 80) -> str:
    """Return a text separator of the given character and length."""
    return char * length