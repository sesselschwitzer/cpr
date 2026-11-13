"""Heizöl-Verbrauch: Kalibrierung und Verbrauchsberechnung.

Eingaben (im Datenordner):
  ablesungen.csv   manuelle Ablesungen (Historie)
  lieferungen.csv  Lieferungen laut Lieferschein
  config.json      Sensor-Nullpunkt, Bezugspunkt, Heizjahr-Beginn
  messwerte.sqlite Sensorwerte aus Home Assistant (optional, siehe sensor.py)

Ausgabe: daten.json und daten.js für das Dashboard.

Nur Standardbibliothek.
"""

from __future__ import annotations

import csv
import json
import os
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

BASIS = Path(__file__).resolve().parent
LIEFERSPRUNG_CM = 5.0  # Anstieg ab dem eine Lieferung angenommen wird


def lade_config(datenordner: Path) -> dict:
    return json.loads((datenordner / "config.json").read_text(encoding="utf-8"))


def lade_ablesungen(datenordner: Path) -> list[dict]:
    with open(datenordner / "ablesungen.csv", encoding="utf-8") as f:
        return [{
            "datum": date.fromisoformat(r["datum"]),
            "cm": float(r["fuellstand_cm"]),
            "notiz": r["notiz"] or "",
            "quelle": "manuell",
        } for r in csv.DictReader(f, delimiter=";")]


def lade_lieferungen(datenordner: Path) -> dict[date, float]:
    with open(datenordner / "lieferungen.csv", encoding="utf-8") as f:
        return {date.fromisoformat(r["datum"]): float(r["liter"]) for r in csv.DictReader(f, delimiter=";")}


def sensor_ablesungen(datenordner: Path, cfg: dict, ab: date, lieferungen: dict[date, float]) -> list[dict]:
    """Tagesmedian der Sensorwerte nach dem letzten manuellen Eintrag.

    Liefertage werden ausgelassen: der Median mischt dort Werte vor und nach der Befüllung.
    """
    db = datenordner / "messwerte.sqlite"
    if not db.exists():
        return []
    import sensor  # erst hier, damit berechnung.py auch ohne Sensor läuft
    return [{"datum": d, "cm": round(cfg["sensor_nullpunkt_cm"] - us, 1), "notiz": "", "quelle": "sensor"}
            for d, us in sensor.tagesmediane(db) if d > ab and d not in lieferungen]


def lieferungen_zuordnen(ablesungen, lieferungen, k_schaetz) -> tuple[dict[date, float], list[dict]]:
    """Ordnet jede Lieferung der ersten Ablesung ab ihrem Datum zu.

    Sprünge ohne eingetragene Lieferung werden als Lieferung mit geschätzter Menge übernommen.
    """
    zuordnung: dict[date, float] = {}
    for d, liter in lieferungen.items():
        nach = next((a["datum"] for a in ablesungen if a["datum"] >= d), None)
        if nach:
            zuordnung[nach] = zuordnung.get(nach, 0) + liter
    hinweise = []
    for a0, a1 in zip(ablesungen, ablesungen[1:]):
        if a1["cm"] - a0["cm"] >= LIEFERSPRUNG_CM and a1["datum"] not in zuordnung:
            geschaetzt = round((a1["cm"] - a0["cm"]) * k_schaetz)
            zuordnung[a1["datum"]] = geschaetzt
            a1["lieferung_geschaetzt"] = True
            hinweise.append({"datum": a1["datum"].isoformat(),
                             "text": f"Lieferung erkannt (ca. {geschaetzt} l), aber nicht in lieferungen.csv eingetragen. "
                                     f"Bitte Menge vom Lieferschein nachtragen."})
    return zuordnung, hinweise


def kalibriere(ablesungen, lieferungen_an, cfg) -> dict:
    """Liter/cm per Kleinste-Quadrate über alle Lieferungen mit Lieferschein (Gerade durch 0)."""
    punkte = []
    for a0, a1 in zip(ablesungen, ablesungen[1:]):
        if a1["datum"] in lieferungen_an and not a1.get("lieferung_geschaetzt"):
            punkte.append({"datum": a1["datum"].isoformat(), "liter": lieferungen_an[a1["datum"]],
                           "delta_cm": round(a1["cm"] - a0["cm"], 2)})
    k = cfg.get("liter_pro_cm") or (
        sum(p["liter"] * p["delta_cm"] for p in punkte) / sum(p["delta_cm"] ** 2 for p in punkte))
    c = cfg["referenz"]["liter"] - k * cfg["referenz"]["fuellstand_cm"]
    for p in punkte:
        p["liter_berechnet"] = round(k * p["delta_cm"])
    return {"liter_pro_cm": k, "offset": c, "lieferungen": punkte}


def monoton_fallend(werte: list[float]) -> list[float]:
    """Isotone Regression (Pool Adjacent Violators): nächstliegende nicht-steigende Folge."""
    bloecke: list[list[float]] = []
    for w in werte:
        bloecke.append([w, 1])
        while len(bloecke) > 1 and bloecke[-2][0] / bloecke[-2][1] < bloecke[-1][0] / bloecke[-1][1]:
            s, n = bloecke.pop()
            bloecke[-1][0] += s
            bloecke[-1][1] += n
    out: list[float] = []
    for s, n in bloecke:
        out += [s / n] * n
    return out


def glaette(ablesungen, lieferungen_an) -> list[float]:
    """Füllstand je Abschnitt zwischen Lieferungen monoton fallend machen (entfernt Messrauschen)."""
    ergebnis: list[float] = []
    segment: list[float] = []
    for a in ablesungen:
        if a["datum"] in lieferungen_an and segment:
            ergebnis += monoton_fallend(segment)
            segment = []
        segment.append(a["cm"])
    return ergebnis + monoton_fallend(segment)


def tagesverbrauch(ablesungen, cm_glatt, lieferungen_an, k, c) -> dict[date, float]:
    """Verbrauch je Intervall gleichmäßig auf die Tage verteilen."""
    tage: dict[date, float] = {}
    for i in range(1, len(ablesungen)):
        d0, d1 = ablesungen[i - 1]["datum"], ablesungen[i]["datum"]
        verbrauch = max((k * cm_glatt[i - 1] + c) + lieferungen_an.get(d1, 0) - (k * cm_glatt[i] + c), 0.0)
        n = (d1 - d0).days
        for j in range(1, n + 1):
            tage[d0 + timedelta(days=j)] = verbrauch / n
    return tage


def heizjahr(d: date, beginn: int) -> str:
    j = d.year if d.month >= beginn else d.year - 1
    return f"{j}/{str(j + 1)[2:]}"


def reichweite(tage: dict[date, float], heute: date, bestand: float, reserve: float) -> int | None:
    """Tage bis leer, mit dem durchschnittlichen Verbrauch der Vorjahre am selben Kalendertag."""
    profil: dict[tuple[int, int], list[float]] = defaultdict(list)
    for d, v in tage.items():
        profil[(d.month, d.day)].append(v)
    rest, d = bestand - reserve, heute
    for n in range(1, 3 * 365):
        d += timedelta(days=1)
        werte = profil.get((d.month, d.day)) or profil.get((d.month, 28)) or [0]
        rest -= sum(werte) / len(werte)
        if rest <= 0:
            return n
    return None


def berechne(datenordner: Path) -> dict:
    cfg = lade_config(datenordner)
    lieferungen = lade_lieferungen(datenordner)
    ablesungen = sorted(lade_ablesungen(datenordner), key=lambda a: a["datum"])
    ablesungen += sensor_ablesungen(datenordner, cfg, ablesungen[-1]["datum"], lieferungen)

    k_start = cfg.get("liter_pro_cm") or 28.7
    lieferungen_an, hinweise = lieferungen_zuordnen(ablesungen, lieferungen, k_start)
    kal = kalibriere(ablesungen, lieferungen_an, cfg)
    k, c = kal["liter_pro_cm"], kal["offset"]

    cm_glatt = glaette(ablesungen, lieferungen_an)
    tage = tagesverbrauch(ablesungen, cm_glatt, lieferungen_an, k, c)

    beginn = cfg["heizjahr_beginn_monat"]
    monate: dict[str, float] = defaultdict(float)
    hj: dict[str, dict] = defaultdict(lambda: {"liter": 0.0, "tage": 0})
    for d, v in tage.items():
        monate[d.strftime("%Y-%m")] += v
        h = hj[heizjahr(d, beginn)]
        h["liter"] += v
        h["tage"] += 1

    letzte = ablesungen[-1]
    heute = letzte["datum"]
    bestand = k * cm_glatt[-1] + c
    letzte30 = sum(v for d, v in tage.items() if d > heute - timedelta(days=30)) / 30
    hj_jetzt = heizjahr(heute, beginn)
    hj_start = date(int(hj_jetzt[:4]), beginn, 1)
    bisher = sum(v for d, v in tage.items() if hj_start <= d <= heute)
    vj_start, vj_ende = hj_start.replace(year=hj_start.year - 1), heute - timedelta(days=365)
    vorjahr = sum(v for d, v in tage.items() if vj_start <= d <= vj_ende)

    hinweise += [{"datum": a["datum"].isoformat(), "text": a["notiz"]}
                 for a in ablesungen if a["notiz"] and not a["notiz"].startswith("Heizung")]
    for a, g in zip(ablesungen, cm_glatt):
        if a["quelle"] == "manuell" and abs(a["cm"] - g) >= 0.25:
            hinweise.append({"datum": a["datum"].isoformat(),
                             "text": f"Füllstand {a['cm']:.1f} cm geglättet auf {g:.1f} cm".replace(".", ",") + f" (Anstieg ohne Lieferung = Messrauschen)"})
    hinweise.sort(key=lambda h: h["datum"])

    return {
        "stand": heute.isoformat(),
        "quelle_letzte": letzte["quelle"],
        "kalibrierung": kal,
        "kpi": {
            "bestand_liter": round(bestand),
            "fuellstand_cm": round(cm_glatt[-1], 1),
            "kapazitaet_liter": cfg["referenz"]["liter"],
            "verbrauch_30d_pro_tag": round(letzte30, 1),
            "reichweite_tage": reichweite(tage, heute, bestand, cfg["mindestbestand_liter"]),
            "heizjahr": hj_jetzt,
            "heizjahr_beginn": hj_start.isoformat(),
            "heizjahr_bisher": round(bisher),
            "vorjahr_gleicher_zeitraum": round(vorjahr),
        },
        "ablesungen": [{"datum": a["datum"].isoformat(), "cm": a["cm"], "cm_glatt": round(g, 2),
                        "liter": round(k * g + c), "quelle": a["quelle"]}
                       for a, g in zip(ablesungen, cm_glatt)],
        "lieferungen": [{"datum": d.isoformat(), "liter": l} for d, l in sorted(lieferungen_an.items())],
        "tage": [{"datum": d.isoformat(), "liter": round(v, 2)} for d, v in sorted(tage.items())],
        "monate": [{"monat": m, "liter": round(v)} for m, v in sorted(monate.items())],
        "heizjahre": [{"heizjahr": h, "liter": round(v["liter"]), "tage": v["tage"]} for h, v in sorted(hj.items())],
        "hinweise": hinweise,
    }


def schreibe(daten: dict, ausgabe: Path) -> None:
    ausgabe.mkdir(parents=True, exist_ok=True)
    text = json.dumps(daten, ensure_ascii=False, indent=1)
    (ausgabe / "daten.json").write_text(text, encoding="utf-8")
    (ausgabe / "daten.js").write_text(f"window.HEIZOEL = {text};\n", encoding="utf-8")


if __name__ == "__main__":
    datenordner = Path(os.environ.get("HEIZOEL_DATEN", BASIS / "data"))
    daten = berechne(datenordner)
    schreibe(daten, Path(os.environ.get("HEIZOEL_AUSGABE", BASIS / "dashboard")))
    k = daten["kalibrierung"]
    print(f"Liter/cm: {k['liter_pro_cm']:.2f}, Bestand {daten['kpi']['bestand_liter']} l, Stand {daten['stand']}")
    for h in daten["heizjahre"]:
        print(f"  {h['heizjahr']}: {h['liter']} l ({h['tage']} Tage)")
    for h in daten["hinweise"]:
        print(f"  Hinweis {h['datum']}: {h['text']}")
