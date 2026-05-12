from __future__ import annotations

import argparse
from pathlib import Path
from typing import Tuple

import matplotlib.pyplot as plt
import numpy as np


def _read_surface(path: Path) -> np.ndarray:
    data = np.loadtxt(path, skiprows=1)
    if data.ndim == 1:
        data = data.reshape(1, -1)
    if data.shape[1] < 2:
        raise ValueError(f"{path} does not contain two columns")
    return data[:, :2]


def _resolve_paths(args: argparse.Namespace) -> Tuple[Path, Path]:
    if args.case_dir:
        case_dir = Path(args.case_dir)
        upper = case_dir / "upper_surface.txt"
        lower = case_dir / "lower_surface.txt"
    else:
        if not args.upper or not args.lower:
            raise ValueError("Provide --case-dir or both --upper and --lower")
        upper = Path(args.upper)
        lower = Path(args.lower)
    if not upper.exists():
        raise FileNotFoundError(f"Upper surface file not found: {upper}")
    if not lower.exists():
        raise FileNotFoundError(f"Lower surface file not found: {lower}")
    return upper, lower


def main() -> None:
    parser = argparse.ArgumentParser(description="可视化上下表面坐标")
    parser.add_argument("--case-dir", help="工况目录，例如 cases/case_001")
    parser.add_argument("--upper", help="upper_surface.txt 路径")
    parser.add_argument("--lower", help="lower_surface.txt 路径")
    parser.add_argument("--out", help="保存图片路径，例如 figures/surfaces.png")
    parser.add_argument("--title", default="Airfoil Surfaces", help="图标题")
    args = parser.parse_args()

    upper_path, lower_path = _resolve_paths(args)
    upper = _read_surface(upper_path)
    lower = _read_surface(lower_path)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(upper[:, 0], upper[:, 1], label="upper")
    ax.plot(lower[:, 0], lower[:, 1], label="lower")
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x_mm")
    ax.set_ylabel("y_mm")
    ax.set_title(args.title)
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)
    ax.legend()

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, dpi=200, bbox_inches="tight")
    else:
        plt.show()


if __name__ == "__main__":
    main()
