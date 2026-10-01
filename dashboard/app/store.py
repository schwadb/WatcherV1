"""Tiny JSON file store for the to-do list, notes and tokens (data/*.json)."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any


class JsonStore:
    def __init__(self, path: Path, default: Any):
        self.path = path
        self.default = default
        self._lock = asyncio.Lock()

    def read(self) -> Any:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return json.loads(json.dumps(self.default))

    def write(self, data: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    async def update(self, fn) -> Any:
        """Read-modify-write under a lock. fn(data) returns the new data."""
        async with self._lock:
            data = fn(self.read())
            self.write(data)
            return data
