"""Distanzwert des Shelly BLU Distance direkt vom Shelly-Gateway holen und in SQLite speichern.

Der BLU Distance ist im Shelly (Gen2+) als BTHome-Gerät angelegt. Der Shelly stellt
seine Messwerte als Komponenten `bthomesensor:<id>` bereit. Den Distanzsensor erkennen
wir am BTHome-Objekttyp (0x40 = Distanz in mm, 0x41 = Distanz in 0,1 m).
"""

from __future__ import annotations

import json
import os
import sqlite3
import statistics
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ZEITZONE = ZoneInfo(os.environ.get("TZ") or "Europe/Berlin")
OBJ_DISTANZ = {64: 0.1, 65: 10.0}  # BTHome-Objekt-ID -> Faktor nach cm


def oeffne(db: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE IF NOT EXISTS messwerte (zeit TEXT PRIMARY KEY, abstand_cm REAL NOT NULL)")
    return con


def _rpc(host: str, methode: str, passwort: str = "", **params):
    url = f"http://{host}/rpc/{methode}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    oeffner = urllib.request.build_opener()
    if passwort:
        pm = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        pm.add_password(None, f"http://{host}/", "admin", passwort)
        oeffner = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(pm))
    with oeffner.open(url, timeout=20) as r:
        return json.load(r)


def finde_distanzsensor(host: str, passwort: str = "") -> tuple[int, float]:
    """Sucht die bthomesensor-Komponente mit Distanz. Gibt (id, Faktor nach cm) zurück."""
    offset, komponenten = 0, []
    while True:
        antwort = _rpc(host, "Shelly.GetComponents", passwort, dynamic_only="true", offset=offset)
        komponenten += antwort.get("components", [])
        offset = len(komponenten)
        if offset >= antwort.get("total", offset):
            break
    for k in komponenten:
        cfg = k.get("config", {})
        if k.get("key", "").startswith("bthomesensor:") and cfg.get("obj_id") in OBJ_DISTANZ:
            return cfg["id"], OBJ_DISTANZ[cfg["obj_id"]]
    raise LookupError(f"Kein BTHome-Distanzsensor auf {host} gefunden. Ist der BLU Distance im Shelly unter Komponenten angelegt?")


def hole(db: Path, host: str, passwort: str = "", sensor_id: int | None = None, faktor: float = 0.1) -> tuple[float, int]:
    """Aktuellen Wert abholen und speichern. Gibt (Abstand cm, Sensor-ID) zurück."""
    if sensor_id is None:
        sensor_id, faktor = finde_distanzsensor(host, passwort)
    status = _rpc(host, "BTHomeSensor.GetStatus", passwort, id=sensor_id)
    if status.get("value") is None:
        raise ValueError(f"Sensor {sensor_id} liefert keinen Wert: {status}")
    cm = float(status["value"]) * faktor
    ts = status.get("last_updated_ts") or datetime.now(timezone.utc).timestamp()
    zeit = datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")
    con = oeffne(db)
    con.execute("INSERT OR IGNORE INTO messwerte VALUES (?, ?)", (zeit, cm))
    con.commit()
    con.close()
    return cm, sensor_id


def tagesmediane(db: Path) -> list[tuple[date, float]]:
    """Median des Sensorabstands je Kalendertag (lokale Zeit)."""
    con = oeffne(db)
    tage: dict[date, list[float]] = {}
    for zeit, cm in con.execute("SELECT zeit, abstand_cm FROM messwerte ORDER BY zeit"):
        tage.setdefault(datetime.fromisoformat(zeit).astimezone(ZEITZONE).date(), []).append(cm)
    con.close()
    return [(d, statistics.median(w)) for d, w in sorted(tage.items())]
