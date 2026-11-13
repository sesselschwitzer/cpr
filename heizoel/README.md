# Heizöl-Dashboard (Home-Assistant-Add-on)

Zeigt Bestand, Tages-, Monats- und Heizjahresverbrauch der Öltanks (2 × 2.000 l).
Historie aus manuellen Ablesungen; neue Werte holt das Add-on direkt vom Shelly 1PM Gen4,
an dem der Shelly BLU Distance als BTHome-Gerät angelegt ist.

## Dateien

| Datei | Zweck |
|---|---|
| `config.yaml`, `Dockerfile`, `translations/` | Add-on-Definition für Home Assistant OS |
| `app.py` | Dienst: Shelly abfragen (Standard alle 10 min), neu rechnen, Dashboard ausliefern |
| `sensor.py` | findet den Distanzsensor im Shelly (`bthomesensor`, BTHome-Objekt 0x40), speichert Werte in `messwerte.sqlite` |
| `berechnung.py` | Kalibrierung über Lieferungen, Glättung, Verbrauch, Reichweite |
| `data/` | Startdaten: `ablesungen.csv`, `lieferungen.csv`, `config.json` |
| `dashboard/` | Weboberfläche (Chart.js lokal, kein Internet nötig) |

## Installation

1. Add-on **Samba share** installieren und starten (Einstellungen → Add-ons → Add-on Store).
2. Diesen Ordner `heizoel` in die Freigabe **`addons`** kopieren (`\\<HA-IP>\addons\heizoel`).
3. Add-on Store → ⋮ → **Nach Updates suchen** → unter **Lokale Add-ons** „Heizöl-Dashboard“ → Installieren.
4. Reiter **Konfiguration**: Shelly-Adresse prüfen → Speichern. Reiter **Info**: Starten, „In Seitenleiste anzeigen“ an.

## Im Betrieb

- Daten liegen in der Samba-Freigabe **`addon_configs`** im Ordner `…_heizoel`. Neue Lieferungen dort in `lieferungen.csv` eintragen.
- Diese Daten sind Teil der normalen Home-Assistant-Backups.
- Protokoll: Add-on → Reiter **Protokoll**.
- Update: neue Dateien nach `addons/heizoel` kopieren, `version` in `config.yaml` erhöhen, im Add-on **Neu erstellen**.

## Rechenweg

1. **Kalibrierung:** Liter/cm per Kleinste-Quadrate aus allen Lieferungen, aktuell 28,70 l/cm; Bezugspunkt 146 cm = 4.000 l.
2. **Sensor:** Füllstand = 157,9 cm − Abstand; je Tag zählt der Median; Liefertage werden ausgelassen.
3. **Lieferungen:** Ein Anstieg ≥ 5 cm ohne Eintrag in `lieferungen.csv` wird mit geschätzter Menge übernommen und als Hinweis angezeigt.
4. **Glättung:** Zwischen zwei Lieferungen darf der Füllstand nicht steigen (isotone Regression).
5. **Verbrauch:** je Intervall Literdifferenz (+ Lieferung), gleichmäßig auf die Tage verteilt.
6. **Reichweite:** Bestand abzüglich durchschnittlichem Verbrauch der Vorjahre am selben Kalendertag.

## Lokal testen

```bash
python3 berechnung.py
```

Danach `dashboard/index.html` im Browser öffnen.
