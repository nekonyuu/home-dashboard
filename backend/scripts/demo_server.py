"""Serveur de DÉMONSTRATION pour travailler le front sans le cloud Atlantic.

- Base SQLite temporaire (jamais /data, jamais la base réelle).
- Fournisseur remplacé par la fixture anonymisée (tests/fixtures) : libellés, enums
  et dernières valeurs réalistes.
- 7 jours d'historique SYNTHÉTIQUE (courbes plausibles) et un trou volontaire, pour
  voir les graphiques et les zones hachurées. Ces données n'ont rien de réel.

Usage (depuis backend/) :
    uv run python scripts/demo_server.py [--port 8000]
puis, dans frontend/ : npm run dev
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

import app.main as main_module  # noqa: E402
from app.config import Settings  # noqa: E402
from app.domain.model import Gap, GapCause  # noqa: E402
from app.domain.values import EquipmentId, Instant, Measurement, MeasurementValue, MetricKey, PollOutcome  # noqa: E402
from app.main import create_app  # noqa: E402
from tests import magellan_fixture, thinq_fixture  # noqa: E402

DAY = 86400

# (équipement, métrique, base, amplitude jour/nuit, bruit, unité)
CURVES = [
    ("heat_pump", "outdoor_temperature", 9.0, 4.5, 0.4, "°C"),
    ("room_1", "room_temperature", 20.4, 0.6, 0.1, "°C"),
    ("generator", "flow_temperature", 31.0, 4.0, 0.8, "°C"),
    ("generator", "return_temperature", 28.5, 3.0, 0.6, "°C"),
    ("generator", "water_pressure", 1.36, 0.02, 0.01, "bar"),
]


def synthetic(now: int, gap: tuple[int, int]) -> list[Measurement]:
    rnd = random.Random(42)
    out: list[Measurement] = []
    start = now - 7 * DAY
    for eq, key, base, amp, noise, unit in CURVES:
        t = start
        while t < now - 3600:
            if not (gap[0] <= t < gap[1]):
                phase = math.sin((t % DAY) / DAY * 2 * math.pi - math.pi / 2)
                v = base + (-amp if key == "outdoor_temperature" else amp) * -phase + rnd.gauss(0, noise)
                out.append(_m(eq, key, t, round(v, 2), unit))
            t += rnd.randint(900, 2700)
    # ECS : chauffe nocturne (heures creuses) puis lente décroissance
    t = start
    temp = 50.0
    while t < now - 3600:
        hour = (t % DAY) / 3600
        if not (gap[0] <= t < gap[1]):
            temp = min(temp + 3.2, 55.5) if 1 <= hour < 4 else max(temp - rnd.uniform(0.15, 0.6), 41.0)
            out.append(_m("dhw", "dhw_temperature", t, round(temp, 2), "°C"))
        t += 1200
    # vanne 3 voies (1 = ECS) pendant la chauffe nocturne + compteur d'énergie ECS (Wh) qui monte pendant la chauffe
    counter = 150_000.0
    day = (start // DAY + 1) * DAY
    while day + 4 * 3600 < now - 3600:
        if not (gap[0] <= day + 3600 < gap[1]):
            out.append(_m("dhw", "dhw_status", day + 3600, 1, None))
            for k in range(1, 7):
                counter += rnd.uniform(250, 450)
                out.append(_m("heat_pump", "energy_dhw_cumulative", day + 3600 + k * 1800, round(counter), "Wh"))
            out.append(_m("dhw", "dhw_status", day + 4 * 3600, 0, None))
        day += DAY
    for eq, key, value in (("dhw", "dhw_setpoint", 55.0), ("room_1", "room_setpoint", 19.0), ("circuit_1", "flow_setpoint", 20.0)):
        out.append(_m(eq, key, start, value, "°C"))
    return out


def home_synthetic(now: int) -> list[Measurement]:
    """Historique SYNTHÉTIQUE des appareils LG : cycles de lavage (temps restant) et consignes du frigo."""
    rnd = random.Random(7)
    out: list[Measurement] = []
    start = now - 7 * DAY
    for eq, total, hours in (("washer", 90, (9, 19)), ("dishwasher", 59, (13, 21))):
        day = (start // DAY + 1) * DAY
        while day + 22 * 3600 < now - 3 * 3600:
            if rnd.random() < 0.6:
                t0 = day + rnd.randint(*hours) * 3600
                for k in range(0, total, 10):
                    out.append(_m(eq, "remaining_minutes", t0 + k * 60, float(total - k), "min"))
                out.append(_m(eq, "remaining_minutes", t0 + total * 60, 0.0, "min"))
            day += DAY
    for key, value in (("fridge_setpoint", 4.0), ("freezer_setpoint", -18.0)):
        out.append(_m("fridge", key, start, value, "°C"))
        out.append(_m("fridge", key, now - 3 * DAY, value - 1 if key == "fridge_setpoint" else value, "°C"))
    return out


def _m(eq: str, key: str, t: int, v: float, unit: str | None) -> Measurement:
    return Measurement(
        equipment_id=EquipmentId(eq),
        metric_key=MetricKey(key),
        instant=Instant(t),
        value=MeasurementValue.of_number(v, unit),
        source="demo",
        polled_at=Instant(t),
    )


async def seed(app) -> None:
    c = app.state.container
    await c.collect.run()  # un cycle sur la fixture : équipements, libellés, dernières valeurs
    await c.catch_up.run()  # consommations journalières de la fixture
    now = c.clock.now().epoch
    gap = (now - 2 * DAY - 5 * 3600, now - 2 * DAY + 2 * 3600)
    repo = c.collect._measurements  # démo uniquement
    await repo.append(synthetic(now, gap))
    await repo.append(home_synthetic(now))
    await c.collect._gaps.add(Gap(Instant(gap[0]), Instant(gap[1]), GapCause.PROVIDER_ERROR))
    await c.collect._poll_log.add(PollOutcome.success(Instant(now), 120, 0))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="pac-demo-"))
    # le client Magellan est remplacé par la fixture : aucun appel réseau
    main_module.MagellanClient = lambda *a, **k: magellan_fixture.FixtureClient()  # type: ignore[assignment]
    # LG ThinQ aussi : fixture, avec le lave-vaisselle hors ligne pour voir l'état « éteint »
    thinq = thinq_fixture.FixtureClient()
    thinq.offline.add(thinq_fixture.device_id_of("DEVICE_DISH_WASHER"))
    main_module.ThinQClient = lambda *a, **k: thinq  # type: ignore[assignment]
    settings = Settings(
        username="demo",
        password="demo",
        db_path=tmp / "demo.db",
        backup_dir=tmp / "backup",
        static_dir=tmp / "static",
        thinq_pat="demo",
        thinq_client_id="11111111-2222-4333-8444-555555555555",
    )
    app = create_app(settings, start_scheduler=False)
    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(a):
        async with original(a):
            await seed(a)
            print(f"Démo prête sur http://127.0.0.1:{args.port} (base temporaire {tmp / 'demo.db'})")
            yield

    app.router.lifespan_context = lifespan
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
