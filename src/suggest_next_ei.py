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


def _normalize(X: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
    span = upper - lower
    span[span == 0.0] = 1.0
    return (X - lower) / span


def _passes_min_dim(
    cand: np.ndarray, points: np.ndarray, min_dim: np.ndarray | None
) -> bool:
    if min_dim is None or points.size == 0:
        return True
    if min_dim[0] > 0:
        if np.any(np.abs(points[:, 0] - cand[0]) < min_dim[0]):
            return False
    if min_dim[1] > 0:
        if np.any(np.abs(points[:, 1] - cand[1]) < min_dim[1]):
            return False
    return True


def _select_batch_indices(
    ei: np.ndarray,
    candidates_norm: np.ndarray,
    existing_norm: np.ndarray,
    batch_size: int,
    min_distance: float,
    min_distance_dim: np.ndarray | None,
) -> List[int]:
    sorted_idx = np.argsort(-ei)
    selected: List[int] = []
    selected_norm: List[np.ndarray] = []

    for idx in sorted_idx:
        if len(selected) >= batch_size:
            break
        if min_distance > 0:
            cand = candidates_norm[idx]
            if existing_norm.size > 0:
                dist = np.linalg.norm(existing_norm - cand, axis=1)
                if float(dist.min()) < min_distance:
                    continue
            if selected_norm:
                dist = np.linalg.norm(np.vstack(selected_norm) - cand, axis=1)
                if float(dist.min()) < min_distance:
                    continue
        if min_distance_dim is not None:
            cand = candidates_norm[idx]
            if not _passes_min_dim(cand, existing_norm, min_distance_dim):
                continue
            if selected_norm:
                selected_stack = np.vstack(selected_norm)
                if not _passes_min_dim(cand, selected_stack, min_distance_dim):
                    continue
        selected.append(int(idx))
        selected_norm.append(candidates_norm[idx])

    if len(selected) < batch_size:
        for idx in sorted_idx:
            if len(selected) >= batch_size:
                break
            if int(idx) in selected:
                continue
            selected.append(int(idx))

    return selected


def suggest_next_cases(
    config: Dict[str, Any],
    n_candidates: int,
    batch_size: int,
    min_distance: float,
    min_distance_alpha: float,
    min_distance_t: float,
) -> None:
    paths = config.get("paths", {})
    samples_csv = Path(paths.get("samples_csv", "data/samples.csv"))
    next_case_csv = Path(paths.get("next_case_csv", "data/next_case.csv"))

    rows = read_samples(samples_csv)
    x_train, y_train = _collect_training_data(rows)
    if x_train.shape[0] < 4:
        raise ValueError("有效样本不足，至少需要 4 个成功工况")

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

    lower = np.array([alpha_min, t_min], dtype=float)
    upper = np.array([alpha_max, t_max], dtype=float)
    candidates_norm = _normalize(candidates, lower, upper)
    existing_norm = _normalize(x_train, lower, upper)

    min_distance_dim = None
    if min_distance_alpha > 0 or min_distance_t > 0:
        alpha_span = max(alpha_range, 1e-12)
        t_span = max(t_range, 1e-12)
        min_distance_dim = np.array(
            [min_distance_alpha / alpha_span, min_distance_t / t_span], dtype=float
        )

    selected_idx = _select_batch_indices(
        ei,
        candidates_norm,
        existing_norm,
        batch_size,
        min_distance,
        min_distance_dim,
    )
    selected = candidates[selected_idx]

    start_id = next_case_id(samples_csv)
    rows_to_add: List[Dict[str, str]] = []

    for i, (alpha_deg, t_over_c) in enumerate(selected, start=0):
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

        rows_to_add.append(
            {
                "case_id": case_id,
                "source": "EI",
                "alpha_deg": _format_float(alpha_deg),
                "t_over_c": _format_float(t_over_c),
                "CL": "",
                "CD": "",
                "target": "",
                "converged": "",
                "status": "pending",
                "note": "",
            }
        )

    if len(rows_to_add) < batch_size:
        print(
            f"警告：距离约束过强，仅选出 {len(rows_to_add)} 个点。"
        )

    write_samples_rows(next_case_csv, rows_to_add)
    append_samples_rows(samples_csv, rows_to_add)

    case_range = f"{start_id}-{start_id + len(rows_to_add) - 1}"
    print(f"EI 批量推荐完成，工况编号：{case_range}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Kriging + EI 批量推荐下一组工况")
    parser.add_argument("--config", default="config.yaml", help="config.yaml 路径")
    parser.add_argument(
        "--n-candidates",
        type=int,
        default=None,
        help="EI 候选点数量（随机搜索）",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="批量推荐数量",
    )
    parser.add_argument(
        "--min-distance",
        type=float,
        default=None,
        help="最小距离约束（归一化后距离）",
    )
    parser.add_argument(
        "--min-distance-alpha",
        type=float,
        default=None,
        help="攻角最小间距（单位：度）",
    )
    parser.add_argument(
        "--min-distance-t",
        type=float,
        default=None,
        help="厚度比最小间距（单位：t/c）",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    opt = config.get("optimization", {})
    n_candidates = int(opt.get("ei_n_candidates", 10000))
    batch_size = int(opt.get("ei_batch_size", 3))
    min_distance = float(opt.get("ei_min_distance", 0.10))
    min_distance_alpha = float(opt.get("ei_min_distance_alpha", 0.0))
    min_distance_t = float(opt.get("ei_min_distance_t", 0.0))

    if args.n_candidates is not None:
        n_candidates = int(args.n_candidates)
    if args.batch_size is not None:
        batch_size = int(args.batch_size)
    if args.min_distance is not None:
        min_distance = float(args.min_distance)
    if args.min_distance_alpha is not None:
        min_distance_alpha = float(args.min_distance_alpha)
    if args.min_distance_t is not None:
        min_distance_t = float(args.min_distance_t)

    if n_candidates <= 0:
        raise ValueError("n_candidates 必须为正数")
    if batch_size <= 0:
        raise ValueError("batch_size 必须为正数")
    if min_distance < 0:
        raise ValueError("min_distance 不能为负数")
    if min_distance_alpha < 0:
        raise ValueError("min_distance_alpha 不能为负数")
    if min_distance_t < 0:
        raise ValueError("min_distance_t 不能为负数")

    suggest_next_cases(
        config,
        n_candidates=n_candidates,
        batch_size=batch_size,
        min_distance=min_distance,
        min_distance_alpha=min_distance_alpha,
        min_distance_t=min_distance_t,
    )


if __name__ == "__main__":
    main()
