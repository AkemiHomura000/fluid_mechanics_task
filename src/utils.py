from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml

SAMPLES_HEADER = [
    "case_id",
    "source",
    "alpha_deg",
    "t_over_c",
    "CL",
    "CD",
    "target",
    "converged",
    "status",
    "note",
]


def load_config(path: str | Path) -> Dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_json(path: str | Path, data: Dict[str, Any]) -> None:
    path = Path(path)
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def read_samples(path: str | Path) -> List[Dict[str, str]]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row for row in reader]


def next_case_id(path: str | Path) -> int:
    rows = read_samples(path)
    max_id = 0
    for row in rows:
        value = row.get("case_id", "")
        try:
            max_id = max(max_id, int(value))
        except (ValueError, TypeError):
            continue
    return max_id + 1


def write_samples_rows(path: str | Path, rows: Iterable[Dict[str, Any]]) -> None:
    path = Path(path)
    ensure_dir(path.parent)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SAMPLES_HEADER)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def append_samples_rows(path: str | Path, rows: Iterable[Dict[str, Any]]) -> None:
    path = Path(path)
    ensure_dir(path.parent)
    file_exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SAMPLES_HEADER)
        if not file_exists or path.stat().st_size == 0:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)
