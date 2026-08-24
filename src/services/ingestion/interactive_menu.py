"""Small terminal menu helpers for interactive CLI selectors."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import import_module
from typing import TextIO

from src.services.ingestion.dataset_catalog import DATASET_CATALOG, PackageReadiness
from src.services.ingestion.dataset_selector import SCENARIO_PROFILES, DatasetType

KEY_UP = "\x1b[A"
KEY_DOWN = "\x1b[B"
KEY_ENTER = "\r"
KEY_NEWLINE = "\n"


@dataclass(frozen=True)
class MenuOption:
    value: str
    label: str
    description: str


def dataset_menu_options() -> tuple[MenuOption, ...]:
    """Return the dataset choices shown by the CLI selector."""
    return (
        MenuOption(
            value=DatasetType.KITTI.value,
            label="KITTI Dataset",
            description="Flat frame-by-frame directory: image_2, velodyne, calib, label_2.",
        ),
        MenuOption(
            value=DatasetType.NUSCENES.value,
            label="nuScenes Dataset",
            description="Relational JSON token graph: scene, sample, sample_data, annotations, calibration.",
        ),
    )


def scenario_menu_options() -> tuple[MenuOption, ...]:
    """Return context-aware scenario choices mapped to their canonical datasets."""
    return tuple(
        MenuOption(
            value=profile.scenario.value,
            label=f"{profile.label} ({profile.dataset_type})",
            description=f"{profile.description} Tags: {', '.join(profile.tags)}.",
        )
        for profile in SCENARIO_PROFILES.values()
    )


def source_menu_options() -> tuple[MenuOption, ...]:
    """Return local/official source choices."""
    return (
        MenuOption(
            value="local",
            label="Local dataset",
            description="Use an existing dataset directory on this machine or mounted volume.",
        ),
        MenuOption(
            value="official",
            label="Official platform",
            description="Download from the official KITTI/nuScenes platform before ingestion.",
        ),
    )


def adapter_menu_options() -> tuple[MenuOption, ...]:
    """Show only adapters that can currently ingest and normalize data."""
    return tuple(
        MenuOption(package.package_id, package.package_id.replace("-", " ").title(), package.description)
        for package in DATASET_CATALOG
        if package.readiness == PackageReadiness.READY
    )


def package_count_menu_options(maximum: int = 2) -> tuple[MenuOption, ...]:
    """Return complete-package counts currently supported by the ready catalog."""
    if maximum < 1:
        raise ValueError("maximum must be at least 1")
    options = (
        MenuOption("1", "One complete package", "Ingest one matching ready package."),
        MenuOption(
            "2",
            "Two complete packages",
            "Ingest KITTI Object Detection and nuScenes mini; packages already marked complete are skipped.",
        ),
    )
    return options[:maximum]


def topic_menu_options(topics: frozenset[str] | None = None) -> tuple[MenuOption, ...]:
    """Return data topic choices."""
    options = (
        MenuOption(
            value="2d",
            label="2D Detection",
            description="Camera images and 2D bounding boxes.",
        ),
        MenuOption(
            value="3d",
            label="3D Detection / Projection",
            description="LiDAR/cuboids plus calibration for 3D-to-2D projection.",
        ),
    )
    return tuple(option for option in options if topics is None or option.value in topics)


def city_menu_options(dataset_type: str) -> tuple[MenuOption, ...]:
    """Return city/location filters relevant to the selected dataset."""
    if dataset_type == DatasetType.NUSCENES.value:
        return (
            MenuOption("multi_region", "Multi-region", "Boston and Singapore challenging scenes."),
            MenuOption("boston-seaport", "Boston Seaport", "nuScenes Boston driving scenes."),
            MenuOption("singapore-onenorth", "Singapore One North", "nuScenes One North scenes."),
            MenuOption("singapore-hollandvillage", "Singapore Holland Village", "nuScenes Holland Village scenes."),
            MenuOption("singapore-queenstown", "Singapore Queenstown", "nuScenes Queenstown scenes."),
        )
    return (
        MenuOption("karlsruhe_urban", "Karlsruhe urban", "KITTI baseline city driving in Karlsruhe, Germany."),
        MenuOption("residential", "Residential", "KITTI raw residential recordings where available."),
        MenuOption("road", "Road", "KITTI raw road recordings where available."),
        MenuOption("campus", "Campus", "KITTI raw campus recordings where available."),
    )


def time_menu_options() -> tuple[MenuOption, ...]:
    """Return time-of-day filters."""
    return (
        MenuOption("any", "Any time", "Do not restrict by time of day."),
        MenuOption("day", "Day", "Prefer daytime captures when metadata is available."),
        MenuOption("night", "Night", "Prefer night captures when metadata is available."),
    )


def move_selection(current_index: int, option_count: int, key: str) -> int:
    """Move the highlighted menu row for an arrow-key press."""
    if option_count <= 0:
        raise ValueError("option_count must be positive")
    if key == KEY_UP:
        return (current_index - 1) % option_count
    if key == KEY_DOWN:
        return (current_index + 1) % option_count
    return current_index


def render_menu(options: Sequence[MenuOption], selected_index: int, *, title: str = "Select an option") -> str:
    """Render a compact interactive selector menu."""
    lines = [f"{title} with ↑/↓, press Enter to confirm:", ""]
    for index, option in enumerate(options):
        marker = ">" if index == selected_index else " "
        lines.append(f"{marker} {option.label}")
        lines.append(f"  {option.description}")
    return "\n".join(lines)


@contextmanager
def _raw_terminal(input_stream: TextIO) -> Iterator[None]:
    if sys.platform == "win32":
        yield
        return
    termios = import_module("termios")
    tty = import_module("tty")
    file_descriptor = input_stream.fileno()
    old_settings = termios.tcgetattr(file_descriptor)
    try:
        tty.setcbreak(file_descriptor)
        yield
    finally:
        termios.tcsetattr(file_descriptor, termios.TCSADRAIN, old_settings)


def _read_key(input_stream: TextIO) -> str:
    char = input_stream.read(1)
    if char == "\x1b":
        return char + input_stream.read(2)
    return char


def choose_from_menu(
    options: Sequence[MenuOption],
    *,
    title: str = "Select an option",
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
    key_reader: Callable[[TextIO], str] = _read_key,
) -> MenuOption:
    """Display an arrow-key menu and return the chosen option."""
    if not options:
        raise ValueError("options must not be empty")
    if not input_stream.isatty() or not output_stream.isatty():
        raise RuntimeError("interactive selector requires a TTY")
    selected_index = 0
    output_stream.write("\033[?25l")
    output_stream.flush()
    rendered_line_count = 0
    try:
        with _raw_terminal(input_stream):
            while True:
                if rendered_line_count:
                    output_stream.write(f"\033[{rendered_line_count}F\033[J")
                rendered = render_menu(options, selected_index, title=title)
                rendered_line_count = len(rendered.splitlines())
                output_stream.write(rendered)
                output_stream.write("\n")
                output_stream.flush()
                key = key_reader(input_stream)
                if key in {KEY_ENTER, KEY_NEWLINE}:
                    return options[selected_index]
                if key in {"q", "Q", "\x03"}:
                    raise KeyboardInterrupt
                selected_index = move_selection(selected_index, len(options), key)
    finally:
        output_stream.write("\033[?25h")
        output_stream.flush()
