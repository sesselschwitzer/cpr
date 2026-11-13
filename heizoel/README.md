# Heizöl-Dashboard

Prototyp: Verbrauchsauswertung aus manuellen Ablesungen (ab 30.10.2025 mit Shelly-BLU-Distance-Werten).

## Aufbau

- `data/ablesungen.csv`: Datum, Füllstand (cm), US-Sensorwert (cm), Notiz
- `data/lieferungen.csv`: Datum, gelieferte Liter
- `config.json`: Sensor-Nullpunkt (Füllstand = 157,9 − US), Bezugspunkt 146 cm = 4.000 l,
  optional fester Faktor `liter_pro_cm` (null = aus Lieferungen kalibrieren)
- `berechnung.py`: Kalibrierung, Glättung, Tages-/Monats-/Heizjahresverbrauch → `dashboard/daten.json` + `daten.js`
- `dashboard/index.html`: Dashboard (Chart.js lokal in `vendor/`, läuft ohne Internet)

## Benutzen

```bash
python3 heizoel/berechnung.py
```

Danach `heizoel/dashboard/index.html` im Browser öffnen.

## Rechenweg

1. **Kalibrierung:** Liter/cm per Kleinste-Quadrate aus den Lieferungen (Füllstandsprung vs. Lieferschein).
   Ergebnis 28,70 l/cm statt bisher 26,38 l/cm; alle 5 Lieferungen passen auf ±10 l.
2. **Glättung:** Zwischen zwei Lieferungen darf der Füllstand nicht steigen (isotone Regression).
3. **Verbrauch:** Je Ablesungsintervall Literdifferenz (+ Lieferung), gleichmäßig auf die Tage verteilt.
4. **Reichweite:** Bestand abzüglich durchschnittlichem Verbrauch der Vorjahre am selben Kalendertag.
