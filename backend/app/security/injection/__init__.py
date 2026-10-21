"""Prompt-injection defence (SR-3). Layers: 1 wrap, 2 detector, 3 capability control (money safety,
lives in the risk engine and `events`), 4 tool gating, 5 output guard; 6 is the evaluation toggle
in `switch`. This package root keeps the original import surface of `app.security.injection`."""

from app.security.injection.legacy import Finding, detect_instructions, normalize

__all__ = ["Finding", "detect_instructions", "normalize"]
