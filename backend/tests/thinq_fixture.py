"""Accès à la fixture anonymisée de la sonde ThinQ (``fixtures/thinq_anonymized.json``)."""

from __future__ import annotations

import copy
import json
from functools import cache
from pathlib import Path
from typing import Any

from app.adapters.outbound.thinq.client import DeviceOffline

FIXTURE = Path(__file__).with_name("fixtures") / "thinq_anonymized.json"


@cache
def _load() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def fixture() -> dict[str, Any]:
    return copy.deepcopy(_load())


def devices() -> list[dict[str, Any]]:
    return fixture()["devices"]["response"]


def state_of(device_id: str) -> Any:
    return fixture()["per_device"][device_id]["state"]["response"]


def device_id_of(device_type: str) -> str:
    return next(d["deviceId"] for d in devices() if d["deviceInfo"]["deviceType"] == device_type)


class FixtureClient:
    """Remplace ``ThinQClient`` : sert la fixture, compte les appels."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_with: Exception | None = None
        self.offline: set[str] = set()
        self.states: dict[str, Any] = {}

    async def devices(self) -> list[dict[str, Any]]:
        self.calls.append("devices")
        if self.fail_with is not None:
            raise self.fail_with
        return devices()

    async def state(self, device_id: str) -> Any:
        self.calls.append("state")
        if self.fail_with is not None:
            raise self.fail_with
        if device_id in self.offline:
            raise DeviceOffline("state")
        return self.states.get(device_id, state_of(device_id))
