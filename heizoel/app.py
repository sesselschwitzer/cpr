"""Dienst für den Container: Sensor abholen, Daten neu berechnen, Dashboard ausliefern."""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import berechnung
import sensor

BASIS = Path(__file__).resolve().parent
DATEN = Path(os.environ.get("HEIZOEL_DATEN", "/data"))
AUSGABE = DATEN / "ausgabe"
DASHBOARD = BASIS / "dashboard"
HA_URL = os.environ.get("HA_URL", "")
HA_TOKEN = os.environ.get("HA_TOKEN", "")
HA_ENTITY = os.environ.get("HA_ENTITY", "")
INTERVALL = int(os.environ.get("ABFRAGE_MINUTEN", "60")) * 60
PORT = int(os.environ.get("PORT", "8080"))

log = logging.getLogger("heizoel")


def erstausstattung() -> None:
    """Beim ersten Start die mitgelieferten Daten in den Datenordner kopieren (nie überschreiben)."""
    DATEN.mkdir(parents=True, exist_ok=True)
    for name in ("ablesungen.csv", "lieferungen.csv", "config.json"):
        if not (DATEN / name).exists():
            shutil.copy(BASIS / "data" / name, DATEN / name)
            log.info("%s angelegt", name)


def zyklus() -> None:
    if HA_URL and HA_TOKEN and HA_ENTITY:
        try:
            neu = sensor.hole(DATEN / "messwerte.sqlite", HA_URL, HA_TOKEN, HA_ENTITY)
            log.info("%d neue Sensorwerte", neu)
        except Exception as e:  # Netzwerk/HA weg: mit vorhandenen Daten weiterrechnen
            log.warning("Home Assistant nicht erreichbar: %s", e)
    else:
        log.warning("HA_URL, HA_TOKEN oder HA_ENTITY fehlt, nur manuelle Daten")
    try:
        berechnung.schreibe(berechnung.berechne(DATEN), AUSGABE)
        log.info("Dashboard-Daten aktualisiert")
    except Exception:
        log.exception("Berechnung fehlgeschlagen")


def schleife() -> None:
    while True:
        time.sleep(INTERVALL)
        zyklus()


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        name = path.split("?", 1)[0].lstrip("/")
        if name in ("daten.json", "daten.js"):
            return str(AUSGABE / name)
        return super().translate_path(path)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, *args) -> None:
        pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    erstausstattung()
    zyklus()
    threading.Thread(target=schleife, daemon=True).start()
    log.info("Dashboard auf Port %d", PORT)
    ThreadingHTTPServer(("", PORT), partial(Handler, directory=str(DASHBOARD))).serve_forever()
