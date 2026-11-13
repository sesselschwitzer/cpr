# Heizöl-Dashboard

Zeigt Bestand, Tages-, Monats- und Heizjahresverbrauch der Öltanks (2 × 2.000 l).
Historie aus manuellen Ablesungen, neue Werte vom Shelly BLU Distance über Home Assistant.

## Dateien

| Datei | Zweck |
|---|---|
| `data/ablesungen.csv` | manuelle Ablesungen (Datum; Füllstand cm; US-Wert cm; Notiz) |
| `data/lieferungen.csv` | Lieferungen laut Lieferschein (Datum; Liter) |
| `data/config.json` | Sensor-Nullpunkt (Füllstand = 157,9 − US), Bezugspunkt 146 cm = 4.000 l, Heizjahr-Beginn (9 = September) |
| `berechnung.py` | Kalibrierung über Lieferungen, Glättung, Verbrauch, Reichweite |
| `sensor.py` | holt Sensorwerte aus Home Assistant, speichert sie in `messwerte.sqlite` |
| `app.py` | Container-Dienst: stündlich abholen + neu rechnen, Dashboard auf Port 8080 |
| `dashboard/` | Weboberfläche (Chart.js lokal, kein Internet nötig) |

## Installation auf der Synology (Container Manager)

1. **Token in Home Assistant anlegen:** Profil (unten links) → Sicherheit → Langlebige Zugangstoken → Token erstellen, Name „heizoel“. Token kopieren (wird nur einmal angezeigt).
2. **Entity-ID nachsehen:** Einstellungen → Geräte & Dienste → Entitäten → nach „distance“ suchen, z. B. `sensor.shelly_blu_distance_xxxx_distance`.
3. **Ordner auf dem NAS anlegen:** File Station → `docker/heizoel`. Den Inhalt dieses Ordners (`heizoel/` aus dem Repo) dorthin kopieren.
4. **`.env` anlegen:** `.env.example` kopieren nach `.env`, `HA_URL` (IP des NAS + Port 8123), `HA_TOKEN` und `HA_ENTITY` eintragen.
5. **Projekt erstellen:** Container Manager → Projekt → Erstellen → Name `heizoel`, Pfad `docker/heizoel`, „Vorhandene docker-compose.yml verwenden“ → Weiter → Fertig. Das Image wird gebaut und gestartet.
6. **Öffnen:** `http://<NAS-IP>:8090`
7. **In Home Assistant einbinden (optional):** Einstellungen → Dashboards → Dashboard hinzufügen → „Webseite“ → URL `http://<NAS-IP>:8090`.
   Wird Home Assistant über https aufgerufen, blockiert der Browser eine http-Seite im Rahmen; dann das Dashboard über den Synology-Reverse-Proxy ebenfalls per https bereitstellen.

Beim ersten Start werden `ablesungen.csv`, `lieferungen.csv` und `config.json` nach `docker/heizoel/daten/` kopiert. **Ab dann dort pflegen**, z. B. neue Lieferungen in `daten/lieferungen.csv` eintragen. Änderungen wirken beim nächsten stündlichen Durchlauf.
Protokoll: Container Manager → Container → heizoel → Protokoll.

## Rechenweg

1. **Kalibrierung:** Liter/cm per Kleinste-Quadrate aus allen Lieferungen (Füllstandssprung vs. Lieferschein), aktuell 28,70 l/cm.
2. **Sensorwerte:** Median je Tag; Liefertage werden ausgelassen.
3. **Lieferungen:** Ein Anstieg ≥ 5 cm ohne Eintrag in `lieferungen.csv` wird als Lieferung mit geschätzter Menge übernommen und als Hinweis angezeigt.
4. **Glättung:** Zwischen zwei Lieferungen darf der Füllstand nicht steigen (isotone Regression).
5. **Verbrauch:** je Intervall Literdifferenz (+ Lieferung), gleichmäßig auf die Tage verteilt.
6. **Reichweite:** Bestand abzüglich durchschnittlichem Verbrauch der Vorjahre am selben Kalendertag.

## Lokal ohne Docker

```bash
python3 berechnung.py
```

Danach `dashboard/index.html` im Browser öffnen.
