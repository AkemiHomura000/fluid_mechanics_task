from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, RBF

try:
    from .airfoil_geometry import generate_case_geometry
    from .utils import (
        SAMPLES_HEADER,
        append_samples_rows,
        load_config,
        next_case_id,
        read_samples,
        write_json,
        write_samples_rows,
    )
except ImportError:
    from airfoil_geometry import generate_case_geometry
    from utils import (
        SAMPLES_HEADER,
        append_samples_rows,
        load_config,
        next_case_id,
        read_samples,
        write_json,
        write_samples_rows,
    )


def _format_float(value: float, decimals: int = 6) -> str:
    text = f"{value:.{decimals}f}"
    text = text.rstrip("0").rstrip(".")
    return text if text else "0"


def _parse_float(value: str) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _is_success(row: Dict[str, str]) -> bool:
    status = str(row.get("status", "")).strip().lower()
    converged = str(row.get("converged", "")).strip().lower()
    return status == "success" and converged == "yes"


def _collect_training_data(rows: List[Dict[str, str]]) -> Tuple[np.ndarray, np.ndarray]:
    x_vals: List[Tuple[float, float]] = []
    y_vals: List[float] = []
    for row in rows:
        if not _is_success(row):
            continue
        alpha = _parse_float(row.get("alpha_deg", ""))
        t_over_c = _parse_float(row.get("t_over_c", ""))
        cl = _parse_float(row.get("CL", ""))
        if alpha is None or t_over_c is None or cl is None:
            continue
        x_vals.append((alpha, t_over_c))
        y_vals.append(-cl)
    if not x_vals:
        return np.empty((0, 2), dtype=float), np.empty((0,), dtype=float)
    return np.array(x_vals, dtype=float), np.array(y_vals, dtype=float)


def _normal_pdf(z: np.ndarray) -> np.ndarray:
    return np.exp(-0.5 * z**2) / math.sqrt(2.0 * math.pi)


def _normal_cdf(z: np.ndarray) -> np.ndarray:
    erf_vec = np.vectorize(math.erf)
    return 0.5 * (1.0 + erf_vec(z / math.sqrt(2.0)))


def _expected_improvement(mu: np.ndarray, sigma: np.ndarray, y_best: float) -> np.ndarray:
    sigma = np.asarray(sigma, dtype=float)
    mu = np.asarray(mu, dtype=float)
    tiny = 1e-9
    safe_sigma = np.where(sigma < tiny, tiny, sigma)
    improvement = mu - float(y_best)
    z = improvement / safe_sigma
    ei = improvement * _normal_cdf(z) + safe_sigma * _normal_pdf(z)
    ei = np.where(sigma < tiny, 0.0, ei)
    return ei


def _build_kernel(alpha_range: float, t_range: float) -> ConstantKernel:
    alpha_scale = max(alpha_range * 0.2, 1e-3)
    t_scale = max(t_range * 0.2, 1e-4)
    return ConstantKernel(1.0, (1e-2, 1e3)) * RBF(
        length_scale=[alpha_scale, t_scale], length_scale_bounds=(1e-3, 1e3)
    )


def suggest_next_case(
    config: Dict[str, Any],
    n_candidates: int,
) -> None:
    paths = config.get("paths", {})
    samples_csv = Path(paths.get("samples_csv", "data/samples.csv"))
    next_case_csv = Path(paths.get("next_case_csv", "data/next_case.csv"))

    rows = read_samples(samples_csv)
    x_train, y_train = _collect_training_data(rows)
    if x_train.shape[0] < 4:
        raise ValueError("Not enough successful samples for Kriging (need >= 4)")

    dv = config.get("design_variables", {})
    alpha_min = float(dv.get("alpha_deg", {}).get("min", 0.0))
    alpha_max = float(dv.get("alpha_deg", {}).get("max", 20.0))
    t_min = float(dv.get("t_over_c", {}).get("min", 0.10))
    t_max = float(dv.get("t_over_c", {}).get("max", 0.16))

    alpha_range = alpha_max - alpha_min
    t_range = t_max - t_min

    seed = config.get("optimization", {}).get("random_seed", None)
    rng = np.random.default_rng(seed)

    kernel = _build_kernel(alpha_range, t_range)
    model = GaussianProcessRegressor(
        kernel=kernel,
        normalize_y=True,
        n_restarts_optimizer=8,
        random_state=seed,
    )
    model.fit(x_train, y_train)

    candidates = rng.uniform(
        low=np.array([alpha_min, t_min], dtype=float),
        high=np.array([alpha_max, t_max], dtype=float),
        size=(int(n_candidates), 2),
    )
    mu, sigma = model.predict(candidates, return_std=True)
    y_best = float(np.max(y_train))
    ei = _expected_improvement(mu, sigma, y_best)
    best_idx = int(np.argmax(ei))
    best_alpha = float(candidates[best_idx, 0])
    best_t = float(candidates[best_idx, 1])

    case_id = next_case_id(samples_csv)
    case_dir = generate_case_geometry(case_id, best_alpha, best_t, config)
    params = {
        "case_id": case_id,
        "airfoil": config.get("project", {}).get("airfoil", "NACA23012"),
        "chord_mm": config.get("geometry", {}).get("chord_mm", 300),
        "alpha_deg": best_alpha,
        "t_over_c": best_t,
        "h_mm": config.get("geometry", {}).get("h_mm", 1000),
        "rotation_center": config.get("geometry", {}).get(
            "rotation_center", "quarter_chord"
        ),
        "rotation_sign": config.get("geometry", {}).get("rotation_sign", -1),
    }
    write_json(case_dir / "input_params.json", params)

    row = {
        "case_id": case_id,
        "source": "EI",
        "alpha_deg": _format_float(best_alpha),
        "t_over_c": _format_float(best_t),
        "CL": "",
        "CD": "",
        "target": "",
        "converged": "",
        "status": "pending",
        "note": "",
    }

    write_samples_rows(next_case_csv, [row])

    append_samples_rows(samples_csv, [row])

    print("EI 推荐下一工况：")
    print(f"case_id = {case_id}")
    print(f"alpha_deg = {best_alpha:.6f}")
    print(f"t_over_c = {best_t:.6f}")
    print(f"case_dir = {case_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Kriging + EI 推荐下一工况")
    parser.add_argument("--config", default="config.yaml", help="config.yaml 路径")
    parser.add_argument(
        "--n-candidates",
        type=int,
        default=10000,
        help="EI 候选点数量（随机搜索）",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    if args.n_candidates <= 0:
        raise ValueError("n_candidates must be positive")

    suggest_next_case(
        config,
        n_candidates=args.n_candidates,
    )


if __name__ == "__main__":
    main()
