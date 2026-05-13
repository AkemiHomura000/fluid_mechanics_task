from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import List, Tuple

import matplotlib.pyplot as plt
import numpy as np

CASE_DIR_RE = re.compile(r"^case_(\d+)$")


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


def _collect_case_dirs(cases_dir: Path) -> List[Path]:
    if not cases_dir.exists():
        return []
    case_dirs = []
    for child in cases_dir.iterdir():
        if not child.is_dir():
            continue
        match = CASE_DIR_RE.match(child.name)
        if not match:
            continue
        case_dirs.append((int(match.group(1)), child))
    return [item[1] for item in sorted(case_dirs, key=lambda x: x[0])]


def _build_plot(upper: np.ndarray, lower: np.ndarray, title: str) -> Tuple[plt.Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(upper[:, 0], upper[:, 1], label="upper")
    ax.plot(lower[:, 0], lower[:, 1], label="lower")
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x_mm")
    ax.set_ylabel("y_mm")
    ax.set_title(title)
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)
    ax.legend()
    return fig, ax


def _save_plot(upper_path: Path, lower_path: Path, title: str, out_path: Path) -> None:
    upper = _read_surface(upper_path)
    lower = _read_surface(lower_path)
    fig, _ = _build_plot(upper, lower, title)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="可视化上下表面坐标")
    parser.add_argument("--case-dir", help="工况目录，例如 cases/case_001")
    parser.add_argument("--cases-dir", default="cases", help="批量模式下的 cases 目录")
    parser.add_argument(
        "--all-cases",
        action="store_true",
        help="批量生成 cases 目录下所有工况图片",
    )
    parser.add_argument("--upper", help="upper_surface.txt 路径")
    parser.add_argument("--lower", help="lower_surface.txt 路径")
    parser.add_argument("--out", help="保存图片路径，例如 figures/surfaces.png")
    parser.add_argument(
        "--out-dir",
        default="figures",
        help="批量模式下的输出目录，例如 figures",
    )
    parser.add_argument("--title", default="Airfoil Surfaces", help="图标题")
    args = parser.parse_args()

    if args.all_cases:
        if args.case_dir or args.upper or args.lower:
            raise ValueError("批量模式请仅使用 --cases-dir 指定目录")
        if args.out:
            raise ValueError("批量模式请使用 --out-dir，而不是 --out")

        cases_dir = Path(args.cases_dir)
        case_dirs = _collect_case_dirs(cases_dir)
        if not case_dirs:
            print(f"未找到工况目录：{cases_dir}")
            return

        out_dir = Path(args.out_dir)
        saved = 0
        skipped = 0
        for case_dir in case_dirs:
            upper_path = case_dir / "upper_surface.txt"
            lower_path = case_dir / "lower_surface.txt"
            if not upper_path.exists() or not lower_path.exists():
                print(f"跳过 {case_dir.name}：未找到上下表面坐标")
                skipped += 1
                continue
            title = f"{args.title} - {case_dir.name}"
            out_path = out_dir / f"surfaces_{case_dir.name}.png"
            try:
                _save_plot(upper_path, lower_path, title, out_path)
                saved += 1
            except Exception as exc:
                print(f"跳过 {case_dir.name}：{exc}")
                skipped += 1
        print(f"批量生成完成：{saved} 张，跳过 {skipped} 张，输出目录：{out_dir}")
        return

    upper_path, lower_path = _resolve_paths(args)
    upper = _read_surface(upper_path)
    lower = _read_surface(lower_path)
    fig, _ = _build_plot(upper, lower, args.title)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, dpi=200, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()


if __name__ == "__main__":
    main()
