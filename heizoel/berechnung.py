"""Heizöl-Verbrauch: Kalibrierung und Verbrauchsberechnung.

Liest data/ablesungen.csv und data/lieferungen.csv, kalibriert die
Umrechnung Füllstand -> Liter anhand der Lieferungen und schreibt
dashboard/daten.json (+ daten.js, damit index.html auch per file:// läuft).

Nur Standardbibliothek, damit es später unverändert im Container läuft.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

BASIS = Path(__file__).resolve().parent
ALTE_FORMEL = (26.378, -26.7)  # Liter = k*cm + c, aus der bisherigen Tabelle rekonstruiert


def lade_config() -> dict:
    return json.loads((BASIS / "config.json").read_text(encoding="utf-8"))


def lade_ablesungen() -> list[dict]:
    with open(BASIS / "data" / "ablesungen.csv", encoding="utf-8") as f:
        zeilen = []
        for r in csv.DictReader(f, delimiter=";"):
            zeilen.append({
                "datum": date.fromisoformat(r["datum"]),
                "cm": float(r["fuellstand_cm"]),
                "us": float(r["us_sensor_cm"]) if r["us_sensor_cm"] else None,
                "notiz": r["notiz"] or "",
            })
    return sorted(zeilen, key=lambda z: z["datum"])


def lade_lieferungen() -> dict[date, float]:
    with open(BASIS / "data" / "lieferungen.csv", encoding="utf-8") as f:
        return {date.fromisoformat(r["datum"]): float(r["liter"]) for r in csv.DictReader(f, delimiter=";")}


def kalibriere(ablesungen: list[dict], lieferungen: dict[date, float], cfg: dict) -> dict:
    """Liter/cm per Kleinste-Quadrate über alle Lieferungen (Gerade durch 0).

    Annahme: zwischen letzter Ablesung vor und erster nach der Lieferung wird
    kaum verbraucht (Abstand 1 Tag oder Sommer/Heizung aus).
    """
    punkte = []
    for i in range(1, len(ablesungen)):
        d = ablesungen[i]["datum"]
        if d in lieferungen:
            dh = ablesungen[i]["cm"] - ablesungen[i - 1]["cm"]
            punkte.append({"datum": d.isoformat(), "liter": lieferungen[d], "delta_cm": dh,
                           "tage_luecke": (d - ablesungen[i - 1]["datum"]).days})
    k_fit = sum(p["liter"] * p["delta_cm"] for p in punkte) / sum(p["delta_cm"] ** 2 for p in punkte)
    k = cfg["liter_pro_cm"] or k_fit
    c = cfg["referenz"]["liter"] - k * cfg["referenz"]["fuellstand_cm"]
    for p in punkte:
        p["liter_neu"] = round(k * p["delta_cm"])
        p["liter_alt"] = round(ALTE_FORMEL[0] * p["delta_cm"])
    return {"liter_pro_cm": k, "liter_pro_cm_fit": k_fit, "offset": c, "lieferungen": punkte}


def monoton_fallend(werte: list[float]) -> list[float]:
    """Isotone Regression (Pool Adjacent Violators): nächstliegende nicht-steigende Folge.

    Entfernt Messrauschen wie 'Füllstand steigt im Sommer ohne Lieferung'.
    """
    bloecke: list[list[float]] = []  # [summe, anzahl]
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


def glaette(ablesungen: list[dict], lieferungen: dict[date, float]) -> list[float]:
    """Füllstand je Segment zwischen Lieferungen monoton fallend machen."""
    ergebnis: list[float] = []
    segment: list[float] = []
    for a in ablesungen:
        if a["datum"] in lieferungen and segment:
            ergebnis += monoton_fallend(segment)
            segment = []
        segment.append(a["cm"])
    return ergebnis + monoton_fallend(segment)


def tagesverbrauch(ablesungen, cm_glatt, lieferungen, k, c) -> dict[date, float]:
    """Verbrauch je Intervall gleichmäßig auf die Tage verteilen (Tag = Verbrauch bis zu diesem Datum)."""
    tage: dict[date, float] = {}
    for i in range(1, len(ablesungen)):
        d0, d1 = ablesungen[i - 1]["datum"], ablesungen[i]["datum"]
        v0, v1 = k * cm_glatt[i - 1] + c, k * cm_glatt[i] + c
        verbrauch = v0 + lieferungen.get(d1, 0) - v1
        verbrauch = max(verbrauch, 0.0)  # Lieferintervalle: Rest ist Kalibrier-Rauschen
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


def main() -> None:
    cfg = lade_config()
    ablesungen = lade_ablesungen()
    lieferungen = lade_lieferungen()
    kal = kalibriere(ablesungen, lieferungen, cfg)
    k, c = kal["liter_pro_cm"], kal["offset"]

    cm_glatt = glaette(ablesungen, lieferungen)
    tage = tagesverbrauch(ablesungen, cm_glatt, lieferungen, k, c)
    tage_alt = tagesverbrauch(ablesungen, cm_glatt, lieferungen, *ALTE_FORMEL)

    monate: dict[str, float] = defaultdict(float)
    hj: dict[str, dict[str, float]] = defaultdict(lambda: {"neu": 0.0, "alt": 0.0, "tage": 0})
    for d, v in tage.items():
        monate[d.strftime("%Y-%m")] += v
        h = hj[heizjahr(d, cfg["heizjahr_beginn_monat"])]
        h["neu"] += v
        h["alt"] += tage_alt[d]
        h["tage"] += 1

    letzte = ablesungen[-1]
    heute = letzte["datum"]
    bestand = k * letzte["cm"] + c
    letzte30 = sum(v for d, v in tage.items() if d > heute - timedelta(days=30)) / 30
    vj_ende = heute.replace(year=heute.year - 1)
    hj_jetzt = heizjahr(heute, cfg["heizjahr_beginn_monat"])
    hj_start = date(int(hj_jetzt[:4]), cfg["heizjahr_beginn_monat"], 1)
    bisher = sum(v for d, v in tage.items() if hj_start <= d <= heute)
    vj_start = hj_start.replace(year=hj_start.year - 1)
    vorjahr = sum(v for d, v in tage.items() if vj_start <= d <= vj_ende)

    hinweise = [{"datum": a["datum"].isoformat(), "text": a["notiz"]}
                for a in ablesungen if a["notiz"] and not a["notiz"].startswith("Heizung")]
    for a, g in zip(ablesungen, cm_glatt):
        if abs(a["cm"] - g) >= 0.25:
            hinweise.append({"datum": a["datum"].isoformat(),
                             "text": f"Füllstand {a['cm']:.1f} cm geglättet auf {g:.1f} cm (Anstieg ohne Lieferung = Messrauschen)"})
    hinweise.sort(key=lambda h: h["datum"])

    daten = {
        "stand": heute.isoformat(),
        "kalibrierung": {**kal, "alt_liter_pro_cm": ALTE_FORMEL[0]},
        "kpi": {
            "bestand_liter": round(bestand),
            "fuellstand_cm": letzte["cm"],
            "kapazitaet_liter": cfg["referenz"]["liter"],
            "verbrauch_30d_pro_tag": round(letzte30, 1),
            "reichweite_tage": reichweite(tage, heute, bestand, cfg["mindestbestand_liter"]),
            "heizjahr": hj_jetzt,
            "heizjahr_bisher": round(bisher),
            "vorjahr_gleicher_zeitraum": round(vorjahr),
        },
        "ablesungen": [{"datum": a["datum"].isoformat(), "cm": a["cm"], "cm_glatt": round(g, 2),
                        "liter": round(k * g + c), "notiz": a["notiz"]}
                       for a, g in zip(ablesungen, cm_glatt)],
        "lieferungen": [{"datum": d.isoformat(), "liter": l} for d, l in sorted(lieferungen.items())],
        "tage": [{"datum": d.isoformat(), "liter": round(v, 2)} for d, v in sorted(tage.items())],
        "monate": [{"monat": m, "liter": round(v)} for m, v in sorted(monate.items())],
        "heizjahre": [{"heizjahr": h, "liter": round(v["neu"]), "liter_alt": round(v["alt"]),
                       "tage": v["tage"]} for h, v in sorted(hj.items())],
        "hinweise": hinweise,
    }
    out = BASIS / "dashboard"
    text = json.dumps(daten, ensure_ascii=False, indent=1)
    (out / "daten.json").write_text(text, encoding="utf-8")
    (out / "daten.js").write_text(f"window.HEIZOEL = {text};\n", encoding="utf-8")
    print(f"Liter/cm: {k:.2f} (Fit {kal['liter_pro_cm_fit']:.2f}), Offset {c:.0f} l")
    for p in kal["lieferungen"]:
        print(f"  {p['datum']}: geliefert {p['liter']:.0f}, neu {p['liter_neu']}, alt {p['liter_alt']}")
    for h in daten["heizjahre"]:
        print(f"  {h['heizjahr']}: {h['liter']} l (alt {h['liter_alt']}), {h['tage']} Tage")
    print(daten["kpi"])


if __name__ == "__main__":
    main()
