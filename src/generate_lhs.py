from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

try:
    from .airfoil_geometry import generate_case_geometry
    from .utils import append_samples_rows, load_config, next_case_id, write_json, write_samples_rows
except ImportError:
    from airfoil_geometry import generate_case_geometry
    from utils import append_samples_rows, load_config, next_case_id, write_json, write_samples_rows


def _lhs_unit(n_samples: int, n_dims: int, rng: np.random.Generator) -> np.ndarray:
    samples = rng.random((n_samples, n_dims))
    for j in range(n_dims):
        perm = rng.permutation(n_samples)
        samples[:, j] = (perm + samples[:, j]) / n_samples
    return samples


def _scale_samples(samples: np.ndarray, bounds: List[Tuple[float, float]]) -> np.ndarray:
    lower = np.array([b[0] for b in bounds], dtype=float)
    upper = np.array([b[1] for b in bounds], dtype=float)
    return lower + samples * (upper - lower)


def _format_float(value: float, decimals: int = 6) -> str:
    text = f"{value:.{decimals}f}"
    text = text.rstrip("0").rstrip(".")
    return text if text else "0"


def generate_lhs_samples(config: Dict[str, Any], n_samples: int, overwrite: bool) -> None:
    paths = config.get("paths", {})
    samples_csv = Path(paths.get("samples_csv", "data/samples.csv"))
    cases_dir = Path(paths.get("cases_dir", "cases"))
    cases_dir.mkdir(parents=True, exist_ok=True)

    seed = config.get("optimization", {}).get("random_seed", None)
    rng = np.random.default_rng(seed)

    dv = config.get("design_variables", {})
    alpha_min = float(dv.get("alpha_deg", {}).get("min", 0.0))
    alpha_max = float(dv.get("alpha_deg", {}).get("max", 20.0))
    t_min = float(dv.get("t_over_c", {}).get("min", 0.10))
    t_max = float(dv.get("t_over_c", {}).get("max", 0.16))

    bounds = [(alpha_min, alpha_max), (t_min, t_max)]
    unit_samples = _lhs_unit(n_samples, len(bounds), rng)
    scaled = _scale_samples(unit_samples, bounds)

    if overwrite:
        start_id = 1
        rows: List[Dict[str, Any]] = []
    else:
        start_id = next_case_id(samples_csv)
        rows = []

    for i, (alpha_deg, t_over_c) in enumerate(scaled, start=0):
        case_id = start_id + i
        case_dir = generate_case_geometry(case_id, alpha_deg, t_over_c, config)

        params = {
            "case_id": case_id,
            "airfoil": config.get("project", {}).get("airfoil", "NACA23012"),
            "chord_mm": config.get("geometry", {}).get("chord_mm", 300),
            "alpha_deg": float(alpha_deg),
            "t_over_c": float(t_over_c),
            "h_mm": config.get("geometry", {}).get("h_mm", 1000),
            "rotation_center": config.get("geometry", {}).get(
                "rotation_center", "quarter_chord"
            ),
            "rotation_sign": config.get("geometry", {}).get("rotation_sign", -1),
        }
        write_json(case_dir / "input_params.json", params)

        row = {
            "case_id": case_id,
            "source": "LHS",
            "alpha_deg": _format_float(alpha_deg),
            "t_over_c": _format_float(t_over_c),
            "CL": "",
            "CD": "",
            "target": "",
            "converged": "",
            "status": "pending",
            "note": "",
        }
        rows.append(row)

    if overwrite:
        write_samples_rows(samples_csv, rows)
    else:
        append_samples_rows(samples_csv, rows)

    print(f"已生成 {n_samples} 个 LHS 样本，工况编号：{start_id}-{start_id + n_samples - 1}")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成初始 LHS 采样")
    parser.add_argument("--config", default="config.yaml", help="config.yaml 路径")
    parser.add_argument(
        "--n-samples",
        type=int,
        default=None,
        help="覆盖 optimization.n_initial_lhs",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="覆盖 samples.csv（不追加）",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    n_samples = args.n_samples or int(
        config.get("optimization", {}).get("n_initial_lhs", 10)
    )
    if n_samples <= 0:
        raise ValueError("n_samples must be positive")

    generate_lhs_samples(config, n_samples=n_samples, overwrite=args.overwrite)


if __name__ == "__main__":
    main()
