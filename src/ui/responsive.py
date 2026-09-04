"""Small helpers for predictable, clamped responsive sizing."""

from __future__ import annotations


def clamp(minimum: float, value: float, maximum: float) -> float:
    """Return *value* constrained to an inclusive range."""
    if minimum > maximum:
        raise ValueError("minimum cannot be greater than maximum")
    return max(minimum, min(value, maximum))


def responsive_scale(
    width: int,
    height: int,
    *,
    reference_width: int = 1500,
    reference_height: int = 1000,
    minimum: float = 0.76,
    maximum: float = 1.36,
) -> float:
    """Scale against both dimensions so one short edge prevents clipping."""
    if reference_width <= 0 or reference_height <= 0:
        raise ValueError("reference dimensions must be positive")
    calculated = min(
        max(0, width) / reference_width,
        max(0, height) / reference_height,
    )
    return clamp(minimum, calculated, maximum)


def scaled(
    scale: float,
    base: float,
    minimum: int,
    maximum: int,
) -> int:
    """Scale and round a base value while enforcing usable limits."""
    return int(round(clamp(minimum, base * scale, maximum)))
