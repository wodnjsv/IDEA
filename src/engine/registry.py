"""Data registry (ISS-002): no hardcoded paths. IDEA_DATA_DIR env -> default repo_root/data."""
import hashlib
import json
import os
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    return Path(os.environ.get("IDEA_DATA_DIR", repo_root() / "data"))


def load_registry() -> dict:
    with open(data_dir() / "registry.json", encoding="utf-8") as f:
        return json.load(f)


def resolve(name: str, verify: bool = False) -> Path:
    """Resolve a logical dataset name to a path (optionally verifying sha256)."""
    reg = load_registry()
    if name not in reg["datasets"]:
        raise KeyError(f"unknown dataset: {name}")
    ent = reg["datasets"][name]
    p = data_dir() / ent["path"]
    if not p.exists():
        raise FileNotFoundError(f"{name}: {p} 없음 — data/raw/ 배치 여부 확인 (data_manifest.md)")
    if verify and ent.get("sha256"):
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != ent["sha256"]:
            raise ValueError(f"{name}: sha256 불일치 — 파일이 매니페스트와 다름")
    return p


def meta(name: str) -> dict:
    return load_registry()["datasets"][name]
