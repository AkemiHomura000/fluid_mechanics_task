from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np

try:
    from .utils import ensure_dir
except ImportError:
    from utils import ensure_dir


def read_airfoil_dat(path: str | Path) -> np.ndarray:
    coords = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            parts = text.replace(",", " ").split()
            if len(parts) < 2:
                continue
            try:
                x = float(parts[0])
                y = float(parts[1])
            except ValueError:
                continue
            coords.append((x, y))
    if len(coords) < 2:
        raise ValueError(f"No valid coordinates found in {path}")
    return np.array(coords, dtype=float)


def split_upper_lower(coords: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    coords = np.asarray(coords, dtype=float)
    idx = int(np.argmin(coords[:, 0]))
    upper = coords[: idx + 1]
    lower = coords[idx:]
    if upper[0, 0] > upper[-1, 0]:
        upper = upper[::-1]
    if lower[0, 0] > lower[-1, 0]:
        lower = lower[::-1]
    return upper, lower


def _sort_by_x(surface: np.ndarray) -> np.ndarray:
    order = np.argsort(surface[:, 0])
    return surface[order]


def resample_surfaces(
    upper: np.ndarray, lower: np.ndarray, n_points: int = 200
) -> Tuple[np.ndarray, np.ndarray]:
    upper = _sort_by_x(upper)
    lower = _sort_by_x(lower)
    x_min = max(float(upper[:, 0].min()), float(lower[:, 0].min()))
    x_max = min(float(upper[:, 0].max()), float(lower[:, 0].max()))
    if x_max <= x_min:
        raise ValueError("Upper and lower surfaces have no overlapping x range")
    x = np.linspace(x_min, x_max, n_points)
    y_upper = np.interp(x, upper[:, 0], upper[:, 1])
    y_lower = np.interp(x, lower[:, 0], lower[:, 1])
    return np.column_stack([x, y_upper]), np.column_stack([x, y_lower])


def modify_thickness(
    upper: np.ndarray, lower: np.ndarray, t_new: float, t_base: float = 0.12
) -> Tuple[np.ndarray, np.ndarray]:
    if not np.allclose(upper[:, 0], lower[:, 0]):
        raise ValueError("Upper and lower surfaces must share the same x grid")
    scale_t = float(t_new) / float(t_base)
    yc = 0.5 * (upper[:, 1] + lower[:, 1])
    yt = 0.5 * (upper[:, 1] - lower[:, 1])
    yt_new = yt * scale_t
    upper_new = np.column_stack([upper[:, 0], yc + yt_new])
    lower_new = np.column_stack([lower[:, 0], yc - yt_new])
    return upper_new, lower_new


def invert_airfoil_y(
    upper: np.ndarray, lower: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    upper_new = upper.copy()
    lower_new = lower.copy()
    upper_new[:, 1] *= -1.0
    lower_new[:, 1] *= -1.0
    return upper_new, lower_new


def scale_to_chord(
    upper: np.ndarray, lower: np.ndarray, chord_mm: float = 300
) -> Tuple[np.ndarray, np.ndarray]:
    upper_new = upper.copy() * float(chord_mm)
    lower_new = lower.copy() * float(chord_mm)
    return upper_new, lower_new


def rotate_airfoil(
    upper: np.ndarray,
    lower: np.ndarray,
    alpha_deg: float,
    chord_mm: float = 300,
    rotation_sign: float = -1,
) -> Tuple[np.ndarray, np.ndarray]:
    theta = float(rotation_sign) * float(alpha_deg) * math.pi / 180.0
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    x0 = 0.25 * float(chord_mm)
    y0 = 0.0

    def _rotate(surface: np.ndarray) -> np.ndarray:
        xr = surface[:, 0] - x0
        yr = surface[:, 1] - y0
        x_new = x0 + xr * cos_t - yr * sin_t
        y_new = y0 + xr * sin_t + yr * cos_t
        return np.column_stack([x_new, y_new])

    return _rotate(upper), _rotate(lower)


def align_leading_edge(
    upper: np.ndarray, lower: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    upper_new = np.asarray(upper, dtype=float).copy()
    lower_new = np.asarray(lower, dtype=float).copy()
    all_points = np.vstack([upper_new, lower_new])
    le_point = all_points[int(np.argmin(all_points[:, 0]))]
    upper_new -= le_point
    lower_new -= le_point
    return upper_new, lower_new


def sort_surfaces_by_x(
    upper: np.ndarray, lower: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    return _sort_by_x(upper), _sort_by_x(lower)


def resample_surfaces_by_x(
    upper: np.ndarray, lower: np.ndarray, n_points: int
) -> Tuple[np.ndarray, np.ndarray]:
    def _unique_xy(surface: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        surface = np.asarray(surface, dtype=float)
        order = np.argsort(surface[:, 0])
        x_sorted = surface[order, 0]
        y_sorted = surface[order, 1]
        unique_x, inverse = np.unique(x_sorted, return_inverse=True)
        y_sum = np.zeros_like(unique_x, dtype=float)
        counts = np.zeros_like(unique_x, dtype=int)
        for idx, y_val in zip(inverse, y_sorted):
            y_sum[idx] += y_val
            counts[idx] += 1
        y_mean = y_sum / counts
        return unique_x, y_mean

    def _ensure_le(x_vals: np.ndarray, y_vals: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        x_vals = np.asarray(x_vals, dtype=float)
        y_vals = np.asarray(y_vals, dtype=float)
        idx = int(np.argmin(np.abs(x_vals)))
        if np.isclose(x_vals[idx], 0.0, atol=1e-9):
            y_vals[idx] = 0.0
        else:
            x_vals = np.insert(x_vals, 0, 0.0)
            y_vals = np.insert(y_vals, 0, 0.0)
        return x_vals, y_vals

    x_u, y_u = _unique_xy(upper)
    x_l, y_l = _unique_xy(lower)
    x_u, y_u = _ensure_le(x_u, y_u)
    x_l, y_l = _ensure_le(x_l, y_l)

    x_min = 0.0
    x_max = min(float(x_u.max()), float(x_l.max()))
    if x_max <= x_min:
        raise ValueError("Upper and lower surfaces have no overlapping x range")

    x_grid = np.linspace(x_min, x_max, int(n_points))
    y_upper = np.interp(x_grid, x_u, y_u)
    y_lower = np.interp(x_grid, x_l, y_l)

    swap_mask = y_upper < y_lower
    if np.any(swap_mask):
        y_upper[swap_mask], y_lower[swap_mask] = (
            y_lower[swap_mask],
            y_upper[swap_mask],
        )

    upper_new = np.column_stack([x_grid, y_upper])
    lower_new = np.column_stack([x_grid, y_lower])
    return upper_new, lower_new


def write_surface_txt(surface: np.ndarray, path: str | Path) -> None:
    path = Path(path)
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as f:
        f.write("x_mm y_mm\n")
        for x, y in surface:
            f.write(f"{x:.6f} {y:.6f}\n")


def write_airfoil_txt(upper: np.ndarray, lower: np.ndarray, path: str | Path) -> None:
    upper = np.asarray(upper, dtype=float)
    lower = np.asarray(lower, dtype=float)
    lower_rev = lower[::-1]
    if lower_rev.shape[0] > 0 and np.allclose(lower_rev[-1], upper[0], atol=1e-9):
        lower_rev = lower_rev[:-1]
    coords = np.vstack([upper, lower_rev])

    path = Path(path)
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as f:
        f.write("x_mm y_mm\n")
        for x, y in coords:
            f.write(f"{x:.6f} {y:.6f}\n")


def _warn_te_thickness(
    upper: np.ndarray, lower: np.ndarray, chord_mm: float, min_ratio: float
) -> None:
    min_thickness = float(min_ratio) * float(chord_mm)
    te_thickness = abs(float(upper[-1, 1] - lower[-1, 1]))
    if te_thickness < min_thickness:
        msg = (
            "警告：尾缘厚度 "
            f"{te_thickness:.4f} mm 低于 {min_thickness:.4f} mm"
        )
        print(msg, file=sys.stderr)


def generate_case_geometry(
    case_id: int, alpha_deg: float, t_over_c: float, config: Dict[str, Any]
) -> Path:
    geometry = config.get("geometry", {})
    paths = config.get("paths", {})

    base_path = Path(paths.get("base_airfoil_path", ""))
    if not base_path.exists():
        raise FileNotFoundError(
            "Base airfoil file not found. Update config.yaml or add the file."
        )

    coords = read_airfoil_dat(base_path)
    upper, lower = split_upper_lower(coords)
    upper, lower = resample_surfaces(
        upper, lower, n_points=int(geometry.get("n_points_per_surface", 200))
    )
    upper, lower = modify_thickness(
        upper,
        lower,
        t_new=float(t_over_c),
        t_base=float(geometry.get("base_t_over_c", 0.12)),
    )

    if bool(geometry.get("invert_y", True)):
        upper, lower = invert_airfoil_y(upper, lower)

    chord_mm = float(geometry.get("chord_mm", 300))
    upper, lower = scale_to_chord(upper, lower, chord_mm=chord_mm)
    upper, lower = rotate_airfoil(
        upper,
        lower,
        alpha_deg=float(alpha_deg),
        chord_mm=chord_mm,
        rotation_sign=float(geometry.get("rotation_sign", -1)),
    )
    upper, lower = align_leading_edge(upper, lower)
    upper, lower = resample_surfaces_by_x(
        upper,
        lower,
        n_points=int(geometry.get("n_points_per_surface", 200)),
    )

    _warn_te_thickness(
        upper,
        lower,
        chord_mm=chord_mm,
        min_ratio=float(geometry.get("min_te_thickness_ratio", 0.002)),
    )

    case_dir = Path(paths.get("cases_dir", "cases")) / f"case_{case_id:03d}"
    ensure_dir(case_dir)
    write_airfoil_txt(upper, lower, case_dir / "Airfoil.txt")
    write_surface_txt(upper, case_dir / "upper_surface.txt")
    write_surface_txt(lower, case_dir / "lower_surface.txt")
    return case_dir
