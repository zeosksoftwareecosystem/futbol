from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from data_sources.espn import ESPNSource
from data_sources.openfootball import OpenFootballSource
from engine.pressure import calculate_pressure
from engine.snapshots import save_snapshot, recent_deltas

ESPN_LEAGUES = [
    "eng.1","eng.2","esp.1","esp.2","ger.1","ger.2","ita.1","ita.2","fra.1","fra.2",
    "ned.1","por.1","sco.1","usa.1","mex.1","bra.1","arg.1","tur.1","gre.1","bel.1",
    "uefa.champions","uefa.europa","uefa.europa.conf","fifa.world","fifa.friendly",
    "jpn.1","aus.1","ksa.1","ind.1","irl.1","swe.1","nor.1","den.1","aut.1","sui.1",
    "pol.1","cze.1","rou.1","ukr.1","cro.1","ser.1"
]

def get_source_catalog():
    return [
        {"name":"ESPN public scoreboard/summary", "role":"Cari oyunlar, hesab, status və mənbədə mövcud olan oyun statistikası", "status":"Açıq, API açarı tələb etmir; qeyri-rəsmi endpoint"},
        {"name":"OpenFootball JSON", "role":"Tarixi/təqvim oyunları və nəticələr üçün ehtiyat mənbə", "status":"Açıq CC0 dataset; canlı statistik mənbə deyil"}
    ]

def _dates(start, end):
    d = date.fromisoformat(start); last = date.fromisoformat(end)
    while d <= last:
        yield d
        d += timedelta(days=1)

def _normalise(raw, source):
    pressure = calculate_pressure(raw)
    delta = recent_deltas(raw.get("event_id"))
    return {
        "event_id": raw.get("event_id"), "kickoff": raw.get("kickoff","N/A"),
        "league": raw.get("league","N/A"), "country": raw.get("country","N/A"),
        "home": raw.get("home","N/A"), "away": raw.get("away","N/A"),
        "score": raw.get("score","N/A"), "minute": raw.get("minute","N/A"),
        "status": raw.get("status","UPCOMING"), "xg": raw.get("xg","N/A"),
        "shots": raw.get("shots","N/A"), "sot": raw.get("sot","N/A"),
        "shots_box": raw.get("shots_box","N/A"), "big_chances": raw.get("big_chances","N/A"),
        "dangerous_attacks": raw.get("dangerous_attacks","N/A"),
        "corners": raw.get("corners","N/A"), "possession": raw.get("possession","N/A"),
        "red_cards": raw.get("red_cards","N/A"),
        "last5_pressure": delta.get("last5_pressure","N/A"),
        "last10_pressure": delta.get("last10_pressure","N/A"),
        "goal_pressure": pressure["goal"], "corner_pressure": pressure["corner"],
        "goal_confidence": pressure["goal_confidence"],
        "corner_confidence": pressure["corner_confidence"], "source": source
    }

def scan_date_range(start, end):
    espn = ESPNSource()
    openfootball = OpenFootballSource()
    tasks = [(d.isoformat(), league) for d in _dates(start,end) for league in ESPN_LEAGUES]
    found, warnings = {}, []
    errors, leagues_checked = 0, set()
    # Bounded concurrency: avoids flooding public endpoints.
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(espn.scoreboard, day, league): (day,league) for day,league in tasks}
        for fut in as_completed(futures):
            day, league = futures[fut]
            try:
                rows = fut.result()
                leagues_checked.add(league)
                for item in rows:
                    key = str(item.get("event_id") or (item.get("kickoff"),item.get("home"),item.get("away")))
                    found[key] = item
            except Exception as e:
                errors += 1
                if len(warnings) < 8: warnings.append(f"ESPN {league} {day}: {e}")
    # Static open dataset is intentionally not mixed into LIVE feed; it is a fallback for scheduled/results.
    if not found:
        warnings.append("ESPN scoreboard nəticə qaytarmadı. OpenFootball yalnız statik təqvim/nəticə mənbəyidir və canlı statistikaları əvəz etmir.")
    rows = []
    for raw in found.values():
        save_snapshot(raw)
        rows.append(_normalise(raw, "ESPN"))
    rows.sort(key=lambda x: (x["kickoff"],x["league"],x["home"]))
    return {"matches":rows, "stats":{
        "leagues_checked":len(leagues_checked), "request_errors":errors,
        "matches_with_stats":sum(1 for x in rows if any(x[k] != "N/A" for k in ("xg","shots","sot","corners"))),
        "source_note":"ESPN açıq endpoint. Əhatə liqadan asılıdır; bütün dünya liqaları üçün zəmanət yoxdur."
    }, "warnings":warnings}
