# Projektentscheidungen Heizöl-Dashboard

- Umrechnung Füllstand → Liter ausschließlich über die Kalibrierung aus den Lieferungen (aktuell 28,70 l/cm, Bezugspunkt 146 cm = 4.000 l). Die alte Formel (26,38 l/cm) ist verworfen und wird nirgends mehr angezeigt oder berechnet.
- Heizjahr beginnt am 1. September (`heizjahr_beginn_monat: 9`).
- Füllstand cm = 157,9 − Ultraschallwert cm. US-Sensor (Shelly BLU Distance) erst ab 30.10.2025.
- Tageswerte aus manuellen Ablesungen sind Intervall-Durchschnitte; so im Dashboard kennzeichnen.
- Kein externes Netz im Dashboard (Chart.js liegt in `dashboard/vendor/`).
- Läuft als lokales Add-on in Home Assistant OS (VM auf der Synology), nicht als Container auf der Synology.
- Sensorquelle: direkt der Shelly 1PM Gen4 (192.168.178.27) per RPC, nicht Home Assistant – die Shelly-Integration reicht den BTHome-Sensor dort nicht weiter.
