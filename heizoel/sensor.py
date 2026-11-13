"""Sensorwerte des Shelly BLU Distance aus Home Assistant holen und in SQLite speichern.

Holt den Verlauf seit dem letzten gespeicherten Wert (Home Assistant hält ihn
standardmäßig 10 Tage vor), so dass kurze Ausfälle des Containers keine Lücken
erzeugen. Werte werden in cm gespeichert.
"""

from __future__ import annotations

import json
import os
import sqlite3
import statistics
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ZEITZONE = ZoneInfo(os.environ.get("TZ", "Europe/Berlin"))
FAKTOR_CM = {"mm": 0.1, "cm": 1.0, "m": 100.0}


def oeffne(db: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE IF NOT EXISTS messwerte (zeit TEXT PRIMARY KEY, abstand_cm REAL NOT NULL)")
    return con


def _get(url: str, token: str):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def hole(db: Path, ha_url: str, token: str, entity: str) -> int:
    """Neue Werte abholen. Gibt die Anzahl neu gespeicherter Werte zurück."""
    ha_url = ha_url.rstrip("/")
    zustand = _get(f"{ha_url}/api/states/{entity}", token)
    einheit = zustand.get("attributes", {}).get("unit_of_measurement", "cm")
    if einheit not in FAKTOR_CM:
        raise ValueError(f"Unbekannte Einheit '{einheit}' bei {entity}")
    faktor = FAKTOR_CM[einheit]

    con = oeffne(db)
    letzte = con.execute("SELECT max(zeit) FROM messwerte").fetchone()[0]
    start = datetime.fromisoformat(letzte) if letzte else datetime.now(timezone.utc) - timedelta(days=10)
    url = (f"{ha_url}/api/history/period/{urllib.parse.quote(start.isoformat())}"
           f"?filter_entity_id={entity}&minimal_response&no_attributes")
    verlauf = _get(url, token)
    eintraege = [(e["last_changed"], e["state"]) for e in (verlauf[0] if verlauf else [])]
    # aktueller Zustand zusätzlich, damit auch Tage ohne Änderung einen Wert haben
    eintraege.append((datetime.now(timezone.utc).isoformat(timespec="seconds"), zustand["state"]))

    neu = 0
    for zeit, wert in eintraege:
        try:
            cm = float(wert) * faktor
        except (TypeError, ValueError):
            continue  # unavailable / unknown
        zeit = datetime.fromisoformat(zeit).astimezone(timezone.utc).isoformat(timespec="seconds")
        neu += con.execute("INSERT OR IGNORE INTO messwerte VALUES (?, ?)", (zeit, cm)).rowcount
    con.commit()
    con.close()
    return neu


def tagesmediane(db: Path) -> list[tuple[date, float]]:
    """Median des Sensorabstands je Kalendertag (lokale Zeit)."""
    con = oeffne(db)
    tage: dict[date, list[float]] = {}
    for zeit, cm in con.execute("SELECT zeit, abstand_cm FROM messwerte ORDER BY zeit"):
        tage.setdefault(datetime.fromisoformat(zeit).astimezone(ZEITZONE).date(), []).append(cm)
    con.close()
    return [(d, statistics.median(w)) for d, w in sorted(tage.items())]
