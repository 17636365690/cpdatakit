"""Headless-safe scientific plotting helpers."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import rcParams
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from .exceptions import CPDataKitError, OutputExistsError
from .model import Dataset
from .schema import ProfileSchema, load_schema

_BLUE = "#3B6FB6"
_INK = "#263238"
rcParams["svg.hashsalt"] = "cpdatakit-0.1"


def _unit(schema: ProfileSchema, field: str) -> str:
    spec = schema.field_map().get(field)
    return spec.unit if spec and spec.unit else "unit not declared"


def _finish(fig: Figure, ax: Axes) -> tuple[Figure, Axes]:
    ax.tick_params(colors=_INK)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="y", color="#D9DEE3", linewidth=0.7, alpha=0.7)
    fig.tight_layout()
    return fig, ax


def plot_stress_strain(dataset: Dataset, schema: str | ProfileSchema) -> tuple[Figure, Axes]:
    """Plot an explicitly declared scalar stress-strain curve."""
    contract = load_schema(schema)
    if "strain" not in dataset.data or "stress" not in dataset.data:
        raise CPDataKitError("stress-strain plot requires declared 'strain' and 'stress' fields")
    fig, ax = plt.subplots(figsize=(7.2, 4.5))
    ax.plot(dataset.data["strain"], dataset.data["stress"], color=_BLUE, label="Synthetic curve")
    ax.set(
        title="Stress-strain curve",
        xlabel=f"Strain [{_unit(contract, 'strain')}]",
        ylabel=f"Stress [{_unit(contract, 'stress')}]",
    )
    ax.legend(frameon=False)
    return _finish(fig, ax)


def plot_histogram(
    dataset: Dataset, schema: str | ProfileSchema, field: str
) -> tuple[Figure, Axes]:
    """Plot a finite-value histogram for a declared numeric field."""
    contract = load_schema(schema)
    if field not in dataset.data or field not in contract.field_map():
        raise CPDataKitError(f"Histogram field is absent or undeclared: {field}")
    spec = contract.field_map()[field]
    if spec.dtype not in {"float", "integer"} or spec.shape:
        raise CPDataKitError(f"Histogram field must be a declared scalar numeric field: {field}")
    try:
        values = np.asarray(dataset.data[field], dtype=float)
    except (TypeError, ValueError) as exc:
        raise CPDataKitError(f"Histogram field is not numeric: {field}") from exc
    values = values[np.isfinite(values)]
    if not len(values):
        raise CPDataKitError(f"Histogram field has no finite data: {field}")
    fig, ax = plt.subplots(figsize=(7.2, 4.5))
    ax.hist(values, bins="auto", color=_BLUE, edgecolor="white", label=field)
    ax.set(
        title=f"Distribution of {field}",
        xlabel=f"{field} [{_unit(contract, field)}]",
        ylabel="Count [records]",
    )
    ax.legend(frameon=False)
    return _finish(fig, ax)


def plot_counts(dataset: Dataset, schema: str | ProfileSchema, field: str) -> tuple[Figure, Axes]:
    """Plot record counts for grain_id or phase_id."""
    load_schema(schema)
    if field not in {"grain_id", "phase_id"} or field not in dataset.data:
        raise CPDataKitError("Count plot field must be present grain_id or phase_id")
    counts = dataset.data[field].value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(7.2, 4.5))
    ax.bar(counts.index.astype(str), counts.values, color=_BLUE, label="Record count")
    ax.set(title=f"Records by {field}", xlabel=f"{field} [identifier]", ylabel="Count [records]")
    ax.legend(frameon=False)
    return _finish(fig, ax)


def plot_field2d(dataset: Dataset, schema: str | ProfileSchema) -> tuple[Figure, Axes]:
    """Plot a 2D scalar field using its declared sample coordinates."""
    contract = load_schema(schema)
    needed = {"x", "y", "value"}
    if not needed.issubset(dataset.data):
        raise CPDataKitError("field2d plot requires x, y, and value")
    fig, ax = plt.subplots(figsize=(6.2, 5.2))
    points = ax.scatter(
        dataset.data["x"],
        dataset.data["y"],
        c=dataset.data["value"],
        cmap="viridis",
        s=35,
        label="Samples",
    )
    colorbar = fig.colorbar(points, ax=ax)
    colorbar.set_label(f"Value [{_unit(contract, 'value')}]")
    ax.set(
        title="Two-dimensional scalar field",
        xlabel=f"x [{_unit(contract, 'x')}]",
        ylabel=f"y [{_unit(contract, 'y')}]",
    )
    ax.legend(frameon=False)
    return _finish(fig, ax)


def save_figure(fig: Figure, output: str | Path, *, force: bool = False) -> Path:
    """Save a PNG or SVG and preserve existing files unless replacement is requested."""
    target = Path(output)
    if target.suffix.lower() not in {".png", ".svg"}:
        raise CPDataKitError("Plot output extension must be .png or .svg")
    if target.exists() and not force:
        raise OutputExistsError(f"Output already exists: {target}; pass force=True to replace it")
    target.parent.mkdir(parents=True, exist_ok=True)
    metadata = {"Date": None} if target.suffix.lower() == ".svg" else {"Software": "CPDataKit"}
    fig.savefig(target, dpi=180, bbox_inches="tight", metadata=metadata)
    return target
