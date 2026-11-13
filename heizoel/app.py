"""Home-Assistant-Add-on: Sensor beim Shelly abholen, Daten neu berechnen, Dashboard ausliefern.

Einstellungen kommen aus /data/options.json (Add-on-Konfiguration in Home Assistant),
für lokale Tests ersatzweise aus Umgebungsvariablen.
"""

from __future__ import annotations

import json
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
DASHBOARD = BASIS / "dashboard"
log = logging.getLogger("heizoel")


def lade_optionen() -> dict:
    datei = Path("/data/options.json")
    opt = json.loads(datei.read_text()) if datei.exists() else {}
    return {
        "shelly_host": opt.get("shelly_host") or os.environ.get("SHELLY_HOST", ""),
        "shelly_passwort": opt.get("shelly_passwort") or os.environ.get("SHELLY_PASSWORT", ""),
        "abfrage_minuten": int(opt.get("abfrage_minuten") or os.environ.get("ABFRAGE_MINUTEN", 10)),
        "daten": Path(os.environ.get("HEIZOEL_DATEN", "/config")),
        "port": int(os.environ.get("PORT", 8080)),
    }


OPT = lade_optionen()
DATEN = OPT["daten"]
AUSGABE = DATEN / "ausgabe"
_sensor: dict = {}  # gefundene Sensor-ID und Faktor


def erstausstattung() -> None:
    """Beim ersten Start die mitgelieferten Daten in den Datenordner kopieren (nie überschreiben)."""
    DATEN.mkdir(parents=True, exist_ok=True)
    for name in ("ablesungen.csv", "lieferungen.csv", "config.json"):
        if not (DATEN / name).exists():
            shutil.copy(BASIS / "data" / name, DATEN / name)
            log.info("%s angelegt", name)


def abholen() -> None:
    if not OPT["shelly_host"]:
        log.warning("Keine Shelly-Adresse eingestellt (Add-on → Konfiguration → shelly_host)")
        return
    try:
        if not _sensor:
            _sensor["id"], _sensor["faktor"] = sensor.finde_distanzsensor(OPT["shelly_host"], OPT["shelly_passwort"])
            log.info("Distanzsensor gefunden: bthomesensor:%d", _sensor["id"])
        cm, _ = sensor.hole(DATEN / "messwerte.sqlite", OPT["shelly_host"], OPT["shelly_passwort"],
                            _sensor["id"], _sensor["faktor"])
        log.info("Abstand %.1f cm", cm)
    except Exception as e:  # Shelly kurz weg: beim nächsten Mal wieder versuchen
        _sensor.clear()
        log.warning("Shelly %s nicht abfragbar: %s", OPT["shelly_host"], e)


def berechnen() -> None:
    try:
        berechnung.schreibe(berechnung.berechne(DATEN), AUSGABE)
    except Exception:
        log.exception("Berechnung fehlgeschlagen")


def schleife() -> None:
    while True:
        time.sleep(OPT["abfrage_minuten"] * 60)
        abholen()
        berechnen()


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        name = path.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
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
    abholen()
    berechnen()
    threading.Thread(target=schleife, daemon=True).start()
    log.info("Dashboard läuft (Port %d)", OPT["port"])
    ThreadingHTTPServer(("", OPT["port"]), partial(Handler, directory=str(DASHBOARD))).serve_forever()
