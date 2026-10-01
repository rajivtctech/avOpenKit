"""Named presets per task (spec F10), kept in QSettings as one JSON object per task."""

from __future__ import annotations

import json
import re

from PyQt6.QtCore import QSettings

MAX_NAME = 60

# Shipped presets. They are copied into the user's settings once and are then ordinary presets:
# they can be changed, deleted, or brought back with restore_builtins().
# Shrink has sizes only. Presets named after services (an e-mail or messaging limit) are added
# at release from each service's published figure, with source and date - spec D7.
BUILTIN: dict[str, dict[str, dict]] = {
    "shrink": {
        "10 MB": {"size": 10.0},
        "25 MB": {"size": 25.0},
        "50 MB": {"size": 50.0},
        "100 MB": {"size": 100.0},
    },
}


def natural(name: str):
    """Sort key that puts '25 MB' before '100 MB'."""
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", name)]


def clean_name(name: str) -> str:
    return " ".join(name.split())[:MAX_NAME]


class PresetStore:
    def __init__(self, settings: QSettings) -> None:
        self._settings = settings

    def _read(self, task: str) -> dict[str, dict]:
        if not self._settings.value(f"presets_seeded/{task}", False, type=bool):
            self._settings.setValue(f"presets_seeded/{task}", True)
            if task in BUILTIN:
                self._write(task, dict(BUILTIN[task]))
        try:
            data = json.loads(self._settings.value(f"presets/{task}", "{}", type=str))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, task: str, data: dict[str, dict]) -> None:
        self._settings.setValue(f"presets/{task}", json.dumps(data, ensure_ascii=False))

    def names(self, task: str) -> list[str]:
        return sorted(self._read(task), key=natural)

    def get(self, task: str, name: str) -> dict | None:
        return self._read(task).get(name)

    def save(self, task: str, name: str, state: dict) -> str:
        """Store a preset, replacing one of the same name. Returns the name as stored."""
        name = clean_name(name)
        if not name:
            raise ValueError("a preset needs a name")
        data = self._read(task)
        data[name] = state
        self._write(task, data)
        return name

    def delete(self, task: str, name: str) -> None:
        data = self._read(task)
        if data.pop(name, None) is not None:
            self._write(task, data)

    def restore_builtins(self, task: str) -> None:
        data = self._read(task)
        data.update(BUILTIN.get(task, {}))
        self._write(task, data)
