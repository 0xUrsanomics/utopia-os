# lib_telemetry.py — graceful no-op metric layer (counters/histograms) with optional OTEL backend.
# Part of Utopia OS, an open framework for personal-AI-operations. MIT.
"""
lib_telemetry.py — graceful no-op metric layer.

Pattern from rohitg00/agentmemory `src/telemetry/setup.ts` (Apache-2.0).

Why this shape: scripts can record counters and histograms without caring
whether OTEL or any other observability backend is wired. Default impls
are no-ops, so calling code is identical with or without a meter.

Usage:
    from lib_telemetry import get_meter

    meter = get_meter("auto_compound_counter")
    bump  = meter.counter("ops_per_user_msg", unit="ops")
    bump.add(1, attrs={"domain": "install"})

    latency = meter.histogram("recall_ms", unit="ms")
    latency.record(42.7, attrs={"mode": "vector"})

To later wire OTEL: install opentelemetry-api + opentelemetry-sdk, then
set `TELEMETRY_BACKEND=otel` in the env. The existing call sites do not change.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping, Protocol, runtime_checkable


@runtime_checkable
class Counter(Protocol):
    def add(self, value: float = 1, attrs: Mapping[str, str] | None = None) -> None: ...


@runtime_checkable
class Histogram(Protocol):
    def record(self, value: float, attrs: Mapping[str, str] | None = None) -> None: ...


@dataclass
class NoopCounter:
    name: str
    unit: str = ""
    description: str = ""

    def add(self, value: float = 1, attrs: Mapping[str, str] | None = None) -> None:
        return None


@dataclass
class NoopHistogram:
    name: str
    unit: str = ""
    description: str = ""

    def record(self, value: float, attrs: Mapping[str, str] | None = None) -> None:
        return None


@dataclass
class Meter:
    name: str
    _counters: dict[str, Counter] = field(default_factory=dict)
    _histograms: dict[str, Histogram] = field(default_factory=dict)

    def counter(self, name: str, unit: str = "", description: str = "") -> Counter:
        if name not in self._counters:
            self._counters[name] = _make_counter(name, unit, description)
        return self._counters[name]

    def histogram(self, name: str, unit: str = "", description: str = "") -> Histogram:
        if name not in self._histograms:
            self._histograms[name] = _make_histogram(name, unit, description)
        return self._histograms[name]


_BACKEND = os.environ.get("TELEMETRY_BACKEND", "noop").lower()
_METERS: dict[str, Meter] = {}


def _make_counter(name: str, unit: str, description: str) -> Counter:
    if _BACKEND == "noop":
        return NoopCounter(name=name, unit=unit, description=description)
    if _BACKEND == "otel":
        return _otel_counter(name, unit, description)
    return NoopCounter(name=name, unit=unit, description=description)


def _make_histogram(name: str, unit: str, description: str) -> Histogram:
    if _BACKEND == "noop":
        return NoopHistogram(name=name, unit=unit, description=description)
    if _BACKEND == "otel":
        return _otel_histogram(name, unit, description)
    return NoopHistogram(name=name, unit=unit, description=description)


def _otel_counter(name: str, unit: str, description: str) -> Counter:
    try:
        from opentelemetry import metrics
    except ImportError:
        return NoopCounter(name=name, unit=unit, description=description)
    meter = metrics.get_meter("agent")
    instrument = meter.create_counter(name, unit=unit, description=description)

    @dataclass
    class _OTelCounter:
        _inst: object
        def add(self, value: float = 1, attrs: Mapping[str, str] | None = None) -> None:
            self._inst.add(value, attributes=dict(attrs or {}))
    return _OTelCounter(_inst=instrument)


def _otel_histogram(name: str, unit: str, description: str) -> Histogram:
    try:
        from opentelemetry import metrics
    except ImportError:
        return NoopHistogram(name=name, unit=unit, description=description)
    meter = metrics.get_meter("agent")
    instrument = meter.create_histogram(name, unit=unit, description=description)

    @dataclass
    class _OTelHistogram:
        _inst: object
        def record(self, value: float, attrs: Mapping[str, str] | None = None) -> None:
            self._inst.record(value, attributes=dict(attrs or {}))
    return _OTelHistogram(_inst=instrument)


def get_meter(name: str) -> Meter:
    if name not in _METERS:
        _METERS[name] = Meter(name=name)
    return _METERS[name]


if __name__ == "__main__":
    m = get_meter("smoke")
    c = m.counter("test_ops", unit="ops", description="smoke test counter")
    h = m.histogram("test_latency", unit="ms")
    c.add(1, attrs={"k": "v"})
    h.record(12.3)
    print(f"backend={_BACKEND} counter={c.__class__.__name__} histogram={h.__class__.__name__}")
    print("ok")
