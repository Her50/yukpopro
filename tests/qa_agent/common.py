"""Shared utilities: config, logging, run context, artifact paths."""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent


def load_config(env: str = "prod") -> dict[str, Any]:
    cfg_path = ROOT / "config.yaml"
    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    base = cfg.pop(env)
    cfg["env"] = env
    cfg["web_url"] = base["web_url"]
    cfg["api_url"] = base["api_url"]
    cfg["health_url"] = base.get("health_url", base["api_url"] + "/health")
    return cfg


@dataclass
class RunContext:
    cfg: dict[str, Any]
    started_at: datetime = field(default_factory=datetime.utcnow)
    artifacts_dir: Path = field(init=False)
    screenshots_dir: Path = field(init=False)
    downloads_dir: Path = field(init=False)
    results: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        stamp = self.started_at.strftime("%Y-%m-%d_%H%M")
        self.artifacts_dir = REPO_ROOT / self.cfg["artifacts_root"] / stamp
        self.screenshots_dir = self.artifacts_dir / "screenshots"
        self.downloads_dir = self.artifacts_dir / "downloads"
        for d in (self.screenshots_dir, self.downloads_dir):
            d.mkdir(parents=True, exist_ok=True)

    def record(self, feature: str, status: str, score: int | None,
               details: dict[str, Any]) -> None:
        self.results.append({
            "feature": feature,
            "status": status,
            "score": score,
            "details": details,
            "timestamp": datetime.utcnow().isoformat(),
        })


def setup_logging(level: str = "INFO") -> logging.Logger:
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stdout)
    return logging.getLogger("qa_agent")


def fixtures_dir() -> Path:
    return REPO_ROOT / "tests" / "qa_agent" / "fixtures"


def safe_filename(name: str) -> str:
    keep = "-_.()[] "
    return "".join(c for c in name if c.isalnum() or c in keep).strip().replace(" ", "_")
