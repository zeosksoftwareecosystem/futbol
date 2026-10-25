from pathlib import Path
import zipfile, io, re, difflib, unicodedata, requests, shutil, tempfile, json
from datetime import datetime, timezone
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / 'open-matchday' / 'data'
REPO_ZIP = 'https://github.com/oladeeayo/open-matchday/archive/refs/heads/master.zip'

# ---- football-data.co.uk (ikinci mənbə) ----
FD_DIR = ROOT / 'football-data-uk'
FD_BASE = 'https://www.football-data.co.uk'
FD_LEAGUES = {
    'E0': 'England Premier League', 'E1': 'England Championship', 'E2': 'England League One',
    'E3': 'England League Two', 'EC': 'England Conference',
    'SC0': 'Scotland Premiership', 'SC1': 'Scotland Championship', 'SC2': 'Scotland League One', 'SC3': 'Scotland League Two',
    'D1': 'Germany Bundesliga', 'D2': 'Germany Bundesliga 2',
    'I1': 'Italy Serie A', 'I2': 'Italy Serie B',
    'SP1': 'Spain La Liga', 'SP2': 'Spain Segunda',
    'F1': 'France Ligue 1', 'F2': 'France Ligue 2',
    'N1': 'Netherlands Eredivisie', 'B1': 'Belgium Pro League',
    'P1': 'Portugal Primeira Liga', 'T1': 'Turkey Super Lig', 'G1': 'Greece Super League',
}
FD_RENAME = {
    'HomeTeam': 'home', 'AwayTeam': 'away', 'Time': 'time',
    'FTHG': 'ft_home', 'FTAG': 'ft_away', 'HTHG': 'ht_home', 'HTAG': 'ht_away',
    'HC': 'home_corners', 'AC': 'away_corners',
    'HS': 'home_shots', 'AS': 'away_shots', 'HST': 'home_target', 'AST': 'away_target',
}
FD_KEEP = ['date', 'time', 'home', 'away', 'league', 'ft_home', 'ft_away', 'ht_home', 'ht_away',
           'home_corners', 'away_corners',
           'home_shots', 'away_shots', 'home_target', 'away_target']

# ---- ESPN (üçüncü mənbə: qitə kubokları və Open Matchday-də olmayan yarışlar) ----
# API açarı lazım deyil. Rəsmi olmayan ictimai endpointdir, gələcəkdə dəyişə bilər.
ESPN_DIR = ROOT / 'espn-data'
# SofaScore — qeyri-rəsmi, sınaq məqsədli əlavə mənbə; əsas mənbələrdən asılı deyil.
SOFASCORE_DIR = ROOT / 'sofascore-data'
SOFASCORE_BASE = 'https://www.sofascore.com/api/v1/sport/football/scheduled-events'
ESPN_BASE = 'https://site.api.espn.com/apis/site/v2/sports/soccer'
# Açar: ESPN liqa kodu (slug). Dəyər: ESPN cavabında ad gəlməzsə istifadə olunan ad.
# Yeni yarış əlavə etmək üçün espn.com-da liqanın səhifəsinin URL-indəki kodu bura yaz.
# Kod yanlışdırsa, "Məlumatı yenilə"dən sonra sol paneldə xəbərdarlıq görünəcək.
ESPN_LEAGUES = {
    'afc.champions': 'AFC Champions League Elite',
    'afc.cup': 'AFC Champions League Two',
    'caf.champions': 'CAF Champions League',
    'caf.confed': 'CAF Confederation Cup',
    'conmebol.libertadores': 'Copa Libertadores',
    'conmebol.sudamericana': 'Copa Sudamericana',
    'concacaf.champions': 'CONCACAF Champions Cup',
    'concacaf.leagues.cup': 'Leagues Cup',
    # Avropa kubokları
    'uefa.champions': 'UEFA Champions League',
    'uefa.europa': 'UEFA Europa League',
    'uefa.europa.conf': 'UEFA Conference League',
    # Daxili kuboklar
    'eng.fa': 'England FA Cup',
    'eng.league_cup': 'England League Cup',
    'esp.copa_del_rey': 'Spain Copa del Rey',
    'ger.dfb_pokal': 'Germany DFB Pokal',
    'ita.coppa_italia': 'Italy Coppa Italia',
    'fra.coupe_de_france': 'France Coupe de France',
    # Avropa liqaları (football-data.co.uk əsas siyahısında olmayanlar)
    'aut.1': 'Austria Bundesliga', 'den.1': 'Denmark Superliga', 'swe.1': 'Sweden Allsvenskan',
    'nor.1': 'Norway Eliteserien', 'sui.1': 'Switzerland Super League', 'rus.1': 'Russia Premier League',
    'ukr.1': 'Ukraine Premier League', 'pol.1': 'Poland Ekstraklasa', 'cze.1': 'Czech First League',
    'cro.1': 'Croatia HNL', 'srb.1': 'Serbia SuperLiga', 'rou.1': 'Romania Liga I',
    'irl.1': 'Ireland Premier Division', 'fin.1': 'Finland Veikkausliiga', 'aze.1': 'Azerbaijan Premier League',
    'isr.1': 'Israel Premier League',
    # Amerika
    'usa.1': 'USA MLS', 'mex.1': 'Mexico Liga MX', 'bra.1': 'Brazil Serie A', 'bra.2': 'Brazil Serie B',
    'arg.1': 'Argentina Primera Division', 'col.1': 'Colombia Primera A', 'chi.1': 'Chile Primera Division',
    'uru.1': 'Uruguay Primera Division', 'ecu.1': 'Ecuador Serie A', 'per.1': 'Peru Liga 1', 'par.1': 'Paraguay Primera Division',
    # Asiya, Okeaniya, Afrika
    'jpn.1': 'Japan J1 League', 'kor.1': 'South Korea K League 1', 'chn.1': 'China Super League',
    'aus.1': 'Australia A-League', 'ind.1': 'India Super League', 'ksa.1': 'Saudi Pro League',
    'uae.1': 'UAE Pro League', 'qat.1': 'Qatar Stars League', 'egy.1': 'Egypt Premier League',
    'rsa.1': 'South Africa Premiership',
    # Milli komandalar
    'fifa.friendly': 'International Friendly', 'uefa.nations': 'UEFA Nations League',
    'uefa.euroq': 'UEFA Euro Qualifying', 'concacaf.nations.league': 'CONCACAF Nations League',
}
ESPN_STATS_PER_REFRESH = 300   # hər yeniləmədə neçə oyun üçün künc/kart statistikası yüklənsin (qalanı növbəti yeniləmələrdə)
ESPN_STATS_MAX_TRIES = 2       # statistikası gəlməyən oyun üçün neçə dəfə cəhd olunsun

# ---- football-data.co.uk "Extra Leagues" (yalnız hesab; qeyd: hər fayl bütün mövsümləri saxlayır) ----
FDX_DIR = ROOT / 'football-data-extra'
FDX_CODES = ['ARG', 'AUT', 'BRA', 'CHN', 'DNK', 'FIN', 'IRL', 'JPN', 'MEX', 'NOR', 'POL', 'ROU', 'RUS', 'SWE', 'SWZ', 'USA']
FDX_DAYS = 800   # son neçə günün oyunları saxlanılsın

# ---- international_results (GitHub, martj42; milli komandaların bütün nəticələri, CC0) ----
IR_DIR = ROOT / 'international-results'
IR_URL = 'https://raw.githubusercontent.com/martj42/international_results/master/results.csv'
IR_DAYS = 800   # son neçə günün oyunları saxlanılsın

# ---- openfootball (GitHub, açıq JSON; hesab + yarımvaxt hesabı) ----
OF_DIR = ROOT / 'openfootball-data'
OF_BASE = 'https://raw.githubusercontent.com/openfootball/football.json/master'
OF_LEAGUES = {
    'en.1': 'England Premier League', 'en.2': 'England Championship', 'en.3': 'England League One', 'en.4': 'England League Two',
    'de.1': 'Germany Bundesliga', 'de.2': 'Germany Bundesliga 2', 'es.1': 'Spain La Liga', 'es.2': 'Spain Segunda',
    'it.1': 'Italy Serie A', 'it.2': 'Italy Serie B', 'fr.1': 'France Ligue 1', 'fr.2': 'France Ligue 2',
    'nl.1': 'Netherlands Eredivisie', 'pt.1': 'Portugal Primeira Liga', 'tr.1': 'Turkey Super Lig',
    'at.1': 'Austria Bundesliga', 'be.1': 'Belgium Pro League', 'gr.1': 'Greece Super League',
    'sco.1': 'Scotland Premiership', 'at.2': 'Austria 2 Liga',
}  # mövsüm qovluqları (2026-27, 2025-26); fayl tapılmayan (404) kodlar səssizcə atlanır
# Təqvim ili ilə oynanan liqalar (qovluq adı: 2026, 2025)
OF_YEAR_LEAGUES = {
    'br.1': 'Brazil Serie A', 'br.2': 'Brazil Serie B', 'ar.1': 'Argentina Primera Division',
    'co.1': 'Colombia Primera A', 'jp.1': 'Japan J1 League', 'cn.1': 'China Super League',
    'mls': 'USA MLS', 'copa.l': 'Copa Libertadores',
}
# openfootball-da saat liqanın ölkəsinin yerli saatıdır. Qurşağı bəlli olmayan liqalarda (None) saat dəyişdirilmir.
OF_TZ = {
    'en.1': 'Europe/London', 'en.2': 'Europe/London', 'en.3': 'Europe/London', 'en.4': 'Europe/London', 'sco.1': 'Europe/London',
    'de.1': 'Europe/Berlin', 'de.2': 'Europe/Berlin', 'es.1': 'Europe/Madrid', 'es.2': 'Europe/Madrid',
    'it.1': 'Europe/Rome', 'it.2': 'Europe/Rome', 'fr.1': 'Europe/Paris', 'fr.2': 'Europe/Paris',
    'nl.1': 'Europe/Amsterdam', 'pt.1': 'Europe/Lisbon', 'tr.1': 'Europe/Istanbul', 'at.1': 'Europe/Vienna',
    'at.2': 'Europe/Vienna', 'be.1': 'Europe/Brussels', 'gr.1': 'Europe/Athens',
    'br.1': 'America/Sao_Paulo', 'br.2': 'America/Sao_Paulo', 'ar.1': 'America/Argentina/Buenos_Aires',
    'co.1': 'America/Bogota', 'jp.1': 'Asia/Tokyo', 'cn.1': 'Asia/Shanghai',
}
ESPN_DAYS_BACK_FIRST = 60   # ilk yükləmədə neçə gün geriyə
ESPN_DAYS_BACK = 14         # sonrakı yeniləmələrdə (köhnə nəticələr faylda saxlanılır)
ESPN_DAYS_AHEAD = 21        # neçə gün irəliyə (qarşıdakı oyunlar)

# Komanda adlarını iki mənbədə eyniləşdirmək üçün. Açar: təmizlənmiş ad (kiçik hərf, durğusuz).
# Uyğunlaşmayan komanda görsən, bura əlavə et: 'mənbədəki ad': 'ortaq ad'
ALIASES = {
    'man united': 'manchester united', 'man utd': 'manchester united',
    'man city': 'manchester city',
    'nottm forest': 'nottingham forest',
    'spurs': 'tottenham', 'tottenham hotspur': 'tottenham',
    'wolves': 'wolverhampton wanderers', 'wolverhampton': 'wolverhampton wanderers',
    'newcastle': 'newcastle united', 'west ham': 'west ham united', 'leeds': 'leeds united',
    'leicester': 'leicester city', 'norwich': 'norwich city', 'brighton': 'brighton and hove albion',
    'sheffield weds': 'sheffield wednesday', 'sheffield utd': 'sheffield united',
    'ath madrid': 'atletico madrid', 'ath bilbao': 'athletic bilbao', 'athletic club': 'athletic bilbao',
    'betis': 'real betis', 'sociedad': 'real sociedad', 'espanol': 'espanyol',
    'vallecano': 'rayo vallecano', 'celta': 'celta vigo',
    'inter': 'internazionale', 'inter milan': 'internazionale', 'milan': 'ac milan',
    'roma': 'as roma', 'verona': 'hellas verona',
    'paris sg': 'paris saint germain', 'psg': 'paris saint germain', 'st etienne': 'saint etienne',
    'marseille': 'olympique marseille', 'lyon': 'olympique lyonnais',
    'dortmund': 'borussia dortmund', 'leverkusen': 'bayer leverkusen',
    'ein frankfurt': 'eintracht frankfurt', 'mgladbach': 'borussia monchengladbach',
    'bayern munich': 'bayern munchen', '1 koln': 'koln', 'stuttgart': 'vfb stuttgart',
}
_DROP_TOKENS = {'fc', 'afc', 'cf', 'sc', 'fk', 'sk', 'cd', 'ud', 'rcd', 'the', 'club'}


_TRANSLIT = str.maketrans({'ø': 'o', 'Ø': 'O', 'æ': 'ae', 'Æ': 'AE', 'œ': 'oe', 'Œ': 'OE', 'ß': 'ss', 'đ': 'd', 'Đ': 'D',
                           'ð': 'd', 'Ð': 'D', 'þ': 'th', 'Þ': 'TH', 'ł': 'l', 'Ł': 'L', 'ı': 'i', 'İ': 'I'})


def team_key(name):
    s = unicodedata.normalize('NFKD', str(name).translate(_TRANSLIT)).encode('ascii', 'ignore').decode().lower()
    s = s.replace('&', ' and ')
    s = re.sub(r"['’.]", '', s)
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    s = ' '.join(t for t in s.split() if t not in _DROP_TOKENS)
    return ALIASES.get(s, s)


# ---- Liqa axtarışı: ölkə adları (ingiliscə, qısaltma və azərbaycanca) ----
COUNTRY_WORDS = {
    'england': 'eng ingiltere ingilis', 'eng': 'england ingiltere ingilis', 'scotland': 'sco sotlandiya', 'sco': 'scotland sotlandiya',
    'wales': 'uels', 'germany': 'ger almaniya', 'ger': 'germany almaniya', 'italy': 'ita italiya', 'ita': 'italy italiya',
    'spain': 'esp ispaniya', 'esp': 'spain ispaniya', 'france': 'fra fransa', 'fra': 'france fransa',
    'netherlands': 'ned holland niderland', 'ned': 'netherlands holland niderland', 'holland': 'niderland',
    'belgium': 'bel belcika', 'bel': 'belgium belcika', 'portugal': 'por portuqaliya', 'por': 'portugal portuqaliya',
    'turkey': 'tur turkiye', 'tur': 'turkey turkiye', 'greece': 'gre yunanistan', 'gre': 'greece yunanistan',
    'finland': 'fin finlandiya', 'fin': 'finland finlandiya', 'russia': 'rus rusiya', 'rus': 'russia rusiya',
    'ukraine': 'ukr ukrayna', 'ukr': 'ukraine ukrayna', 'azerbaijan': 'aze azerbaycan', 'aze': 'azerbaijan azerbaycan',
    'brazil': 'bra braziliya', 'bra': 'brazil braziliya', 'argentina': 'arg', 'arg': 'argentina',
    'usa': 'abs amerika mls', 'mls': 'usa abs amerika', 'japan': 'jpn yaponiya', 'jpn': 'japan yaponiya',
    'china': 'chn cin', 'chn': 'china cin', 'mexico': 'mex meksika', 'mex': 'mexico meksika',
    'sweden': 'swe isvec', 'swe': 'sweden isvec', 'norway': 'nor norvec', 'nor': 'norway norvec',
    'denmark': 'den danimarka', 'den': 'denmark danimarka', 'austria': 'aut avstriya', 'aut': 'austria avstriya',
    'switzerland': 'sui isvecre', 'sui': 'switzerland isvecre', 'ireland': 'irl irlandiya', 'irl': 'ireland irlandiya',
    'poland': 'pol polsa', 'pol': 'poland polsa', 'romania': 'rou ruminiya', 'rou': 'romania ruminiya',
    'champions league': 'uefa cempionlar liqasi', 'europa league': 'uefa avropa liqasi',
    'conference league': 'uefa konfrans liqasi', 'cup': 'kubok', 'pokal': 'kubok cup', 'copa': 'kubok cup',
    'premier': 'premyer', 'division': 'divizion', 'liga': 'liqa', 'ligue': 'liqa',
}


def norm_search(text):
    t = str(text).lower()
    for a, b in {'ə': 'e', 'ı': 'i', 'ö': 'o', 'ü': 'u', 'ş': 's', 'ç': 'c', 'ğ': 'g'}.items():
        t = t.replace(a, b)
    return unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode()


def league_search_blob(name):
    base = norm_search(name)
    extra = [w for key, w in COUNTRY_WORDS.items() if re.search(r'\b' + re.escape(key) + r'\b', base)]
    return base + ' ' + ' '.join(extra)


st.set_page_config(page_title='Futbol Filtri v6', page_icon='⚽', layout='wide')

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stMarkdown, button, input { font-family: 'Inter', sans-serif; }
.block-container { padding-top: 1.1rem; padding-bottom: 6rem; max-width: 1180px; }
header[data-testid="stHeader"] { background: transparent; }

.hero { background: linear-gradient(135deg, #0f766e 0%, #15803d 55%, #166534 100%);
        border-radius: 18px; padding: 26px 30px; color: #fff; margin-bottom: 20px;
        box-shadow: 0 10px 30px rgba(21,128,61,.25); }
.hero h1 { margin: 0; font-size: 28px; font-weight: 800; color: #fff; padding: 0; }
.hero p { margin: 6px 0 0; opacity: .92; font-size: 14px; max-width: 760px; }
.hero .tags span { display: inline-block; background: rgba(255,255,255,.18); border-radius: 999px;
                   padding: 3px 12px; font-size: 12px; margin: 12px 6px 0 0; }

.sec { font-size: 12px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase;
       opacity: .6; margin: 2px 0 6px; }
.rule { border: 1px dashed rgba(22,163,74,.55); background: rgba(22,163,74,.08); color: inherit;
        border-radius: 12px; padding: 10px 14px; font-size: 13.5px; margin: 10px 0 4px; }

div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 16px; }
button[kind="primary"] { border-radius: 12px; font-weight: 700; padding: .65rem 1rem;
                         background: linear-gradient(135deg, #16a34a, #0f766e); border: none; }
/* Analiz düyməsi səhifə ilə birlikdə sürüşməsin; ekranın üstündə sabit qalsın. */
div.st-key-analyze_button {
  position: fixed !important; left: 50% !important; right: auto !important;
  bottom: 22px !important; transform: translateX(-50%) !important;
  z-index: 99999 !important; width: auto !important; max-width: min(90vw, 310px) !important;
  margin: 0 !important; padding: 0 !important;
  filter: drop-shadow(0 6px 18px rgba(0,0,0,.25));
}
div.st-key-analyze_button button {
  min-height: 52px !important; width: auto !important; min-width: 220px !important;
  white-space: nowrap !important; border-radius: 15px !important;
}
@media (max-width: 600px) {
  div.st-key-analyze_button { left: 50% !important; right: auto !important; bottom: 12px !important; transform: translateX(-50%) !important; max-width: calc(100vw - 24px) !important; }
  div.st-key-analyze_button button { min-width: 0 !important; width: 100% !important; }
}
button[kind="primary"]:hover { filter: brightness(1.06); }
div[data-testid="stExpander"] { border-radius: 14px; border: 1px solid rgba(128,128,128,.28); margin-bottom: 8px; }
section[data-testid="stSidebar"] .stButton button { border-radius: 10px; font-weight: 600; }

.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 16px 0 6px; }
.stat { border: 1px solid rgba(128,128,128,.28); border-radius: 14px; padding: 14px 18px;
        background: rgba(128,128,128,.07); }
.stat .n { font-size: 28px; font-weight: 800; line-height: 1.1; }
.stat .l { font-size: 12px; opacity: .65; margin-top: 3px; }
.stat.good .n { color: #16a34a; }

.team-head { font-weight: 700; font-size: 15px; margin: 2px 0 8px; }
.mcard { border: 1px solid rgba(128,128,128,.28); border-radius: 12px; padding: 10px 12px;
         margin: 6px 0 8px; background: rgba(128,128,128,.07); text-align: center; }
.mcard .d { font-size: 11.5px; opacity: .6; }
.mcard .t { font-size: 13px; overflow-wrap: anywhere; }
.mcard .s { font-size: 21px; font-weight: 800; margin: 2px 0; }
.chip { display: inline-block; font-size: 11px; padding: 2px 9px; border-radius: 999px; margin: 5px 3px 0; font-weight: 600; }
.chip.h { background: rgba(168,85,247,.16); color: #9333ea; }
.chip.c { background: rgba(59,130,246,.16); color: #2563eb; }
.chip.y { background: rgba(234,179,8,.20); color: #b45309; }
.chip.s { background: rgba(100,116,139,.18); color: inherit; opacity: .85; }

.st-key-datenav [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: nowrap !important; gap: .5rem !important; }
.st-key-datenav [data-testid="stColumn"], .st-key-datenav [data-testid="column"] { min-width: 0 !important; width: auto !important; flex: 1 1 0 !important; }
.st-key-datenav [data-testid="stColumn"]:nth-child(2), .st-key-datenav [data-testid="column"]:nth-child(2) { flex: 3 1 0 !important; }
.st-key-datenav button { min-height: 2.6rem; font-weight: 700; }
/* Tarix oxları tarix sahəsinin iki tərəfində eyni sətirdə qalsın. */
[class*="st-key-start_date_row"] [data-testid="stHorizontalBlock"], [class*="st-key-end_date_row"] [data-testid="stHorizontalBlock"] { display:flex !important; flex-direction:row !important; flex-wrap:nowrap !important; gap:.3rem !important; align-items:center !important; }
[class*="st-key-start_date_row"] [data-testid="stColumn"], [class*="st-key-start_date_row"] [data-testid="column"], [class*="st-key-end_date_row"] [data-testid="stColumn"], [class*="st-key-end_date_row"] [data-testid="column"] { min-width:0 !important; width:auto !important; }
[class*="st-key-start_date_row"] [data-testid="stColumn"]:nth-child(1), [class*="st-key-start_date_row"] [data-testid="column"]:nth-child(1), [class*="st-key-end_date_row"] [data-testid="stColumn"]:nth-child(1), [class*="st-key-end_date_row"] [data-testid="column"]:nth-child(1), [class*="st-key-start_date_row"] [data-testid="stColumn"]:nth-child(3), [class*="st-key-start_date_row"] [data-testid="column"]:nth-child(3), [class*="st-key-end_date_row"] [data-testid="stColumn"]:nth-child(3), [class*="st-key-end_date_row"] [data-testid="column"]:nth-child(3) { flex:0 0 2.35rem !important; }
[class*="st-key-start_date_row"] [data-testid="stColumn"]:nth-child(2), [class*="st-key-start_date_row"] [data-testid="column"]:nth-child(2), [class*="st-key-end_date_row"] [data-testid="stColumn"]:nth-child(2), [class*="st-key-end_date_row"] [data-testid="column"]:nth-child(2) { flex:1 1 0 !important; }
[class*="st-key-start_date_row"] button, [class*="st-key-end_date_row"] button { min-height:2.55rem !important; height:2.55rem !important; padding:.15rem !important; }
[class*="st-key-start_date_row"] [data-testid="stDateInput"], [class*="st-key-end_date_row"] [data-testid="stDateInput"] { width:100% !important; min-width:0 !important; }
[class*="st-key-start_date_row"] [data-testid="stDateInput"] input, [class*="st-key-end_date_row"] [data-testid="stDateInput"] input { font-size:.86rem !important; padding-left:.4rem !important; padding-right:.15rem !important; }
[class*="st-key-moderow"] [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: nowrap !important; gap: .4rem !important; align-items: center !important; }
[class*="st-key-moderow"] [data-testid="stColumn"], [class*="st-key-moderow"] [data-testid="column"] { min-width: 0 !important; width: auto !important; }
[class*="st-key-moderow"] [data-testid="stColumn"]:nth-child(1), [class*="st-key-moderow"] [data-testid="column"]:nth-child(1) { flex: 5 1 0 !important; }
[class*="st-key-moderow"] [data-testid="stColumn"]:nth-child(2), [class*="st-key-moderow"] [data-testid="column"]:nth-child(2) { flex: 4 1 0 !important; }
[class*="st-key-moderow"] [data-testid="stRadio"] label p { font-size: .8rem !important; }
@media (max-width: 700px) {
  .block-container { padding: .65rem .65rem 6.5rem !important; max-width: 100% !important; }
  .hero { padding: 18px 16px !important; border-radius: 14px !important; margin-bottom: 12px !important; }
  .hero h1 { font-size: 21px !important; line-height: 1.25 !important; }
  .hero p { font-size: 13px !important; line-height: 1.45 !important; }
  .hero .tags span { font-size: 10px !important; padding: 3px 8px !important; margin: 8px 4px 0 0 !important; }
  .stats { grid-template-columns: 1fr !important; gap: 8px !important; }
  .stat { padding: 11px 13px !important; }
  .stat .n { font-size: 24px !important; }
  div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 12px !important; }
  div[data-testid="stExpander"] { border-radius: 11px !important; }
  div[data-testid="stCheckbox"] label p, div[data-testid="stRadio"] label p { font-size: .82rem !important; line-height: 1.3 !important; }
  div[data-testid="stNumberInput"] input, div[data-testid="stDateInput"] input, div[data-testid="stTextInput"] input { font-size: 16px !important; }
  div.st-key-analyze_button { bottom: calc(12px + env(safe-area-inset-bottom)) !important; width: calc(100vw - 32px) !important; max-width: 360px !important; }
  div.st-key-analyze_button button { width: 100% !important; min-height: 48px !important; font-size: 15px !important; border-radius: 13px !important; }
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)
st.markdown(
    '<div class="hero"><h1>⚽ Futbol Filtri</h1>'
    '<p>Hər komandanın son oyunlarını yoxlayır və bütün seçilmiş şərtlərə uyğun gələn matçları tapır.</p>'
    '<div class="tags"><span>Open Matchday</span><span>football-data.co.uk</span><span>ESPN</span><span>openfootball</span><span>API açarı lazım deyil</span></div></div>',
    unsafe_allow_html=True
)


def read_csv_safe(path):
    for enc in ('utf-8-sig', 'latin-1'):
        try:
            return pd.read_csv(path, encoding=enc, on_bad_lines='skip')
        except UnicodeDecodeError:
            continue
        except Exception:
            return None
    return None


BAKU_TZ = timezone(timedelta(hours=4), 'Asia/Baku')   # Azərbaycan həmişə UTC+4 (yay/qış saatı yoxdur)


def baku_today():
    return datetime.now(BAKU_TZ).date()


def to_baku(df, tz='UTC', tz_col=None):
    """date + time sütunlarını mənbənin saat qurşağından Bakı vaxtına çevirir (tarix də dəyişə bilər).
    tz: bütün sətirlər üçün saat qurşağı; tz_col: hər sətir üçün qurşağın yazıldığı sütun (None olan sətir toxunulmaz qalır).
    Saatı olmayan və ya 'HH:MM' formatında olmayan sətirlər dəyişmir."""
    if df is None or df.empty or 'time' not in df.columns or 'date' not in df.columns:
        return df
    df = df.copy()
    d = pd.to_datetime(df['date'], errors='coerce')
    t = df['time'].astype(str).str.strip()
    ok = d.notna() & t.str.fullmatch(r'\d{1,2}:\d{2}').fillna(False)
    df['date'] = d
    if not ok.any():
        return df
    naive = pd.to_datetime(d.dt.strftime('%Y-%m-%d') + ' ' + t, format='%Y-%m-%d %H:%M', errors='coerce')
    ok &= naive.notna()
    zones = df[tz_col] if tz_col else pd.Series(tz, index=df.index)
    out = pd.Series(pd.NaT, index=df.index, dtype='datetime64[ns]')
    for z in zones[ok].dropna().unique():
        m = ok & (zones == z)
        try:
            loc = naive[m].dt.tz_localize(z, ambiguous='NaT', nonexistent='shift_forward')
            out[m] = loc.dt.tz_convert('Asia/Baku').dt.tz_localize(None)
        except Exception:
            continue
    good = out.notna()
    if good.any():
        df.loc[good, 'date'] = out[good].dt.normalize()
        df.loc[good, 'time'] = out[good].dt.strftime('%H:%M')
    return df


def parse_fd_date(col):
    try:
        return pd.to_datetime(col, dayfirst=True, format='mixed', errors='coerce')
    except (TypeError, ValueError):
        return pd.to_datetime(col, dayfirst=True, errors='coerce')


def fd_seasons():
    now = datetime.now()
    y = now.year if now.month >= 7 else now.year - 1
    return [f'{(y - k) % 100:02d}{(y - k + 1) % 100:02d}' for k in range(2)]  # cari + əvvəlki mövsüm


def load_fd():
    res, fix = [], []
    if FD_DIR.exists():
        for f in FD_DIR.glob('*.csv'):
            df = read_csv_safe(f)
            if df is None or 'HomeTeam' not in df.columns or 'Date' not in df.columns:
                continue
            df = df.rename(columns=FD_RENAME)
            df['date'] = parse_fd_date(df['Date'])
            div = df['Div'] if 'Div' in df.columns else pd.Series('FD', index=df.index)
            df['league'] = div.map(FD_LEAGUES).fillna(div)
            if 'time' in df.columns:
                df['time'] = np.nan   # football-data.co.uk saat qurşağı dəqiq bəlli deyil; saat Open Matchday/openfootball/ESPN-dən götürülür
            df = df[[c for c in FD_KEEP if c in df.columns]]
            (fix if f.name == 'fixtures.csv' else res).append(df)
    return (pd.concat(fix, ignore_index=True) if fix else pd.DataFrame(),
            pd.concat(res, ignore_index=True) if res else pd.DataFrame())


def load_fdx():
    """football-data.co.uk/new/*.csv (əlavə liqalar: Braziliya, ABŞ, Yaponiya və s.) — yalnız hesab."""
    out = []
    if FDX_DIR.exists():
        for f in FDX_DIR.glob('*.csv'):
            df = read_csv_safe(f)
            if df is None or df.empty:
                continue
            df.columns = [str(c).strip() for c in df.columns]
            if not {'Home', 'Away', 'HG', 'AG', 'Date'} <= set(df.columns):
                continue
            d = pd.DataFrame({'date': parse_fd_date(df['Date']), 'time': df['Time'] if 'Time' in df.columns else '',
                              'home': df['Home'], 'away': df['Away'],
                              'ft_home': pd.to_numeric(df['HG'], errors='coerce'), 'ft_away': pd.to_numeric(df['AG'], errors='coerce')})
            ctry = df['Country'].astype(str) if 'Country' in df.columns else pd.Series(f.stem, index=df.index)
            lg = df['League'].astype(str) if 'League' in df.columns else pd.Series('', index=df.index)
            d['league'] = (ctry + ' ' + lg).str.strip()
            d = d.dropna(subset=['date', 'ft_home', 'ft_away'])
            d = d[d['date'] >= pd.Timestamp.now() - pd.Timedelta(days=FDX_DAYS)]
            out.append(d)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def load_ir():
    """Milli komandaların nəticələri (yalnız hesab; qarşıdakı oyunlar ESPN-dən gəlir)."""
    f = IR_DIR / 'results.csv'
    df = read_csv_safe(f) if f.exists() else None
    if df is None or df.empty or not {'date', 'home_team', 'away_team', 'home_score', 'away_score', 'tournament'} <= set(df.columns):
        return pd.DataFrame()
    d = pd.DataFrame({'date': pd.to_datetime(df['date'], errors='coerce'), 'home': df['home_team'], 'away': df['away_team'],
                      'ft_home': pd.to_numeric(df['home_score'], errors='coerce'), 'ft_away': pd.to_numeric(df['away_score'], errors='coerce'),
                      'league': 'International ' + df['tournament'].astype(str)})
    d = d.dropna(subset=['date', 'ft_home', 'ft_away'])
    return d[d['date'] >= pd.Timestamp.now() - pd.Timedelta(days=IR_DAYS)]


def refresh_ir():
    IR_DIR.mkdir(exist_ok=True)
    r = requests.get(IR_URL, timeout=60, headers={'User-Agent': 'FutbolFiltri/1.0'})
    r.raise_for_status()
    if len(r.content) < 1000:
        raise RuntimeError('boş cavab')
    (IR_DIR / 'results.csv').write_bytes(r.content)
    load_data.clear()


def _of_rows(data, league, tz=None):
    fix, res = [], []
    ok = lambda v: isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v)
    for m in data.get('matches', []) or []:
        try:
            h, a = m['team1'], m['team2']
            h = h.get('name') if isinstance(h, dict) else h
            a = a.get('name') if isinstance(a, dict) else a
            row = {'date': m['date'], 'time': m.get('time', ''), 'home': h, 'away': a, 'league': league, 'tz': tz}
        except (KeyError, TypeError, AttributeError):
            continue
        sc = m.get('score')
        ft = ht = None
        if isinstance(sc, dict):
            ft, ht = sc.get('ft'), sc.get('ht')
        elif isinstance(sc, list):
            ft = sc
        if ok(ft):
            row['ft_home'], row['ft_away'] = int(ft[0]), int(ft[1])
            if ok(ht) and ht[0] <= ft[0] and ht[1] <= ft[1]:
                row['ht_home'], row['ht_away'] = int(ht[0]), int(ht[1])
            res.append(row)
        elif not sc:
            fix.append(row)
    return fix, res


def load_of():
    fix, res = [], []
    if OF_DIR.exists():
        for f in OF_DIR.glob('*.json'):
            code = f.stem.split('_', 1)[-1]
            try:
                data = json.loads(f.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            fx, rs = _of_rows(data, OF_LEAGUES.get(code) or OF_YEAR_LEAGUES.get(code) or data.get('name', code), OF_TZ.get(code))
            fix += fx
            res += rs
    out = []
    for rows in (fix, res):
        df = to_baku(pd.DataFrame(rows), tz_col='tz') if rows else pd.DataFrame()
        out.append(df.drop(columns=['tz'], errors='ignore'))
    return out[0], out[1]


def of_years():
    return [str(datetime.now().year - k) for k in range(2)]


def of_seasons():
    now = datetime.now()
    y = now.year if now.month >= 7 else now.year - 1
    return [f'{y - k}-{(y - k + 1) % 100:02d}' for k in range(2)]


SRC_LABELS = {'FD': 'football-data.co.uk', 'OM': 'Open Matchday', 'ES': 'ESPN', 'OF': 'openfootball', 'IR': 'international_results', 'SS': 'SofaScore (sınaq)'}


def src_label(code):
    parts = [SRC_LABELS[p] for p in str(code).split('+') if p in SRC_LABELS]
    return ' + '.join(parts)


# Eyni adlı fərqli komandalar (məs. Braziliya "Santos" və Meksika "Santos Laguna").
# Açar: ümumi komanda açarı. Dəyər: [(liqa adında axtarılan sözlər, həmin liqalarda istifadə olunacaq açar), ...]
# Başqa belə komanda görsən buraya əlavə et.
AMBIGUOUS_TEAMS = {
    'santos': [(('mex', 'concacaf', 'leagues cup', 'leagues_cup'), 'santos laguna')],
}


def _split_ambiguous(df, col, league_norm):
    for key, rules in AMBIGUOUS_TEAMS.items():
        is_key = df[col] == key
        if not is_key.any():
            continue
        for words, new_key in rules:
            m = is_key & league_norm.apply(lambda l: any(w in l for w in words))
            df.loc[m, col] = new_key
    return df


def add_keys(df, src):
    if df.empty:
        return df
    df = df.copy()
    df['src'] = src
    df['date'] = pd.to_datetime(df.get('date'), errors='coerce').dt.normalize()
    df['home_k'] = df['home'].map(team_key)
    df['away_k'] = df['away'].map(team_key)
    if 'league' in df.columns:
        league_norm = df['league'].fillna('').astype(str).str.lower()
        df = _split_ambiguous(df, 'home_k', league_norm)
        df = _split_ambiguous(df, 'away_k', league_norm)
    return df


def _tokens_match(short, long_):
    used = set()
    for t in short:
        hit = next((j for j, u in enumerate(long_) if j not in used and (u == t or (len(t) >= 3 and u.startswith(t)) or (len(t) == 1 and u.startswith(t)))), None)
        if hit is None:
            return False
        used.add(hit)
    return True


def names_compatible(a, b):
    """'cheltenham' ~ 'cheltenham town', 'man city' ~ 'manchester city' kimi adları uyğun sayır."""
    if a == b:
        return True
    ta, tb = a.split(), b.split()
    if not ta or not tb:
        return False
    if (len(ta), sum(map(len, ta))) > (len(tb), sum(map(len, tb))):
        ta, tb = tb, ta
    return _tokens_match(ta, tb)


def _strong_votes(a, b):
    """Eyni gün (±1 gün) və bir komanda eynidirsə, digər tərəflər də eyni komandadır (komanda gündə bir oyun keçirir)."""
    strong = Counter()
    for off in (-1, 0, 1):
        bb = b.copy()
        bb['date'] = bb['date'] + pd.Timedelta(days=off)
        for side, other in (('away', 'home'), ('home', 'away')):
            mm = a.merge(bb, on=['date', f'{side}_k'], suffixes=('', '_om'))
            mm = mm[mm[f'{other}_k'] != mm[f'{other}_k_om']]
            for k, t in zip(mm[f'{other}_k'], mm[f'{other}_k_om']):
                strong[(k, t)] += 1
    return strong


def _best_votes(votes, min_share=0.6):
    """Hər açar üçün ən çox səs toplayan hədəfi seçir; səslərin ən azı min_share hissəsini toplamayıbsa (qeyri-müəyyən) əlavə etmir."""
    best, total = {}, Counter()
    for (k, target), n in votes.items():
        total[k] += n
        if k not in best or n > best[k][1]:
            best[k] = (target, n)
    return {k: v[0] for k, v in best.items() if k != v[0] and v[1] / total[k] >= min_share}


def learn_key_map(fd, om):
    """Eyni oyunun iki mənbədəki komanda adlarını müqayisə edib football-data adlarını digər mənbənin adlarına çevirən xəritə öyrənir.
    1-ci dövr: eyni gün, hər iki ad uyğundur ('man city' ~ 'manchester city') + bir komanda eynidirsə digəri də eynidir (±1 gün, ən azı 2 səs).
    Sonrakı dövrlər: öyrənilənləri tətbiq edib qalan adları (məsələn tarixi 1 gün sürüşən oyunlardan) yenə eyni qaydayla öyrənir."""
    if fd.empty or om.empty:
        return {}
    a = fd[['date', 'home_k', 'away_k']].dropna().drop_duplicates()
    b = om[['date', 'home_k', 'away_k']].dropna().drop_duplicates()
    originals = set(a['home_k']) | set(a['away_k'])
    kmap = {}
    cur = a
    for rnd in range(3):
        votes = Counter()
        if rnd == 0:
            m = cur.merge(b, on='date', suffixes=('', '_om'))
            for h, aw, ho, ao in zip(m['home_k'], m['away_k'], m['home_k_om'], m['away_k_om']):
                if h == ho and aw == ao:
                    continue
                if names_compatible(h, ho) and names_compatible(aw, ao):
                    if h != ho:
                        votes[(h, ho)] += 1
                    if aw != ao:
                        votes[(aw, ao)] += 1
        for pair, n in _strong_votes(cur, b).items():
            if n >= 2:
                votes[pair] += n
        new = _best_votes(votes)
        if not new:
            break
        for k in originals:
            c = kmap.get(k, k)
            if c in new:
                kmap[k] = new[c]
        cur = cur.copy()
        cur['home_k'] = cur['home_k'].map(lambda k: new.get(k, k))
        cur['away_k'] = cur['away_k'].map(lambda k: new.get(k, k))
    return kmap


def collapse_near_dates(df):
    """Eyni iki komandanın oyunu 1 gün fərqlə iki mənbədə yazılıbsa (saat qurşağı fərqi) bir oyun kimi birləşdirir.
    Saatı olan sətir (Bakı vaxtına çevrilmiş) əvvəl gəlir ki, tarix və saat uyğun qalsın."""
    if df.empty or not {'date', 'home_k', 'away_k'} <= set(df.columns):
        return df
    df = df.dropna(subset=['date', 'home_k', 'away_k']).copy()
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values(['home_k', 'away_k', 'date'], kind='stable').reset_index(drop=True)
    gap = df.groupby(['home_k', 'away_k'])['date'].diff()
    cid = ((gap.isna()) | (gap > pd.Timedelta(days=1))).cumsum()
    size = cid.map(cid.value_counts())
    single, multi = df[size == 1], df[size > 1].copy()
    if multi.empty:
        return df
    multi['_cid'] = cid[size > 1]
    if 'time' in multi.columns:
        multi['_ht'] = multi['time'].astype(str).str.strip().str.fullmatch(r'\d{1,2}:\d{2}').fillna(False)
    else:
        multi['_ht'] = False
    multi = multi.sort_values(['_cid', '_ht'], ascending=[True, False], kind='stable')
    agg = {c: 'first' for c in multi.columns if c not in ('src', '_cid', '_ht')}
    agg['src'] = lambda x: '+'.join(sorted(set('+'.join(x).split('+'))))
    merged = multi.groupby('_cid', sort=False).agg(agg).reset_index(drop=True)
    return pd.concat([single, merged], ignore_index=True)


def apply_key_map(df, kmap):
    if df.empty or not kmap:
        return df
    df = df.copy()
    df['home_k'] = df['home_k'].map(lambda k: kmap.get(k, k))
    df['away_k'] = df['away_k'].map(lambda k: kmap.get(k, k))
    return df


def learn_league_map(fd, om):
    """Eyni oyunun iki mənbədəki liqa adlarını müqayisə edib Open Matchday liqa adını football-data adına çevirir (təkrar liqa adları olmasın deyə)."""
    if fd.empty or om.empty:
        return {}
    keys = ['date', 'home_k', 'away_k']
    m = fd[keys + ['league']].merge(om[keys + ['league']], on=keys, suffixes=('_fd', '_om'))
    if m.empty:
        return {}
    counts = m.groupby(['league_om', 'league_fd']).size().reset_index(name='n').sort_values('n', ascending=False)
    return dict(counts.drop_duplicates('league_om').set_index('league_om')['league_fd'])


def pretty_league(name):
    t = str(name).replace('_', ' ').replace('-', ' ').strip()
    return t.title() if t.islower() else t


def load_espn():
    out = []
    for name in ('fixtures', 'results'):
        df = read_csv_safe(ESPN_DIR / f'{name}.csv') if (ESPN_DIR / f'{name}.csv').exists() else None
        if df is None or df.empty or not {'date', 'home', 'away'} <= set(df.columns):
            out.append(pd.DataFrame())
        else:
            out.append(to_baku(df.drop(columns=['id', 'slug', 'stats_try'], errors='ignore'), 'UTC'))
    return out[0], out[1]


def load_sofascore():
    """Diskdə saxlanmış SofaScore sınaq məlumatını oxuyur; şəbəkəyə özü qoşulmur."""
    out = []
    for name in ('fixtures', 'results'):
        path = SOFASCORE_DIR / f'{name}.csv'
        if not path.exists():
            out.append(pd.DataFrame())
            continue
        df = read_csv_safe(path)
        if df.empty or not {'date', 'home', 'away'} <= set(df.columns):
            out.append(pd.DataFrame())
            continue
        df = to_baku(df, 'UTC')
        out.append(df)
    return out[0], out[1]


def _sofa_day(day):
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; FootballFilter/1.0)', 'Accept': 'application/json'}
    resp = requests.get(f'{SOFASCORE_BASE}/{day.isoformat()}', headers=headers, timeout=8)
    resp.raise_for_status()
    return resp.json().get('events', [])


def refresh_sofascore():
    """SofaScore (qeyri-rəsmi) — son 14 gün və növbəti 21 gün, paralel sorğularla. Əlçatan deyilsə (403 və s.) xəta qaldırır, digər mənbələrə toxunmur."""
    SOFASCORE_DIR.mkdir(parents=True, exist_ok=True)
    today_ = baku_today()
    days = [today_ + timedelta(days=o) for o in range(-14, 22)]
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(_sofa_day, d) for d in days]
        got, last_err = [], None
        for f in futs:
            try:
                got.append(f.result())
            except Exception as e:
                last_err = e
                got.append(None)
    if all(g is None for g in got):
        raise RuntimeError(f'heç bir gün yüklənmədi ({last_err})')
    fixtures, results = [], []
    for events in got:
        for ev in events or []:
            try:
                home = (ev.get('homeTeam') or {}).get('name')
                away = (ev.get('awayTeam') or {}).get('name')
                ts = ev.get('startTimestamp')
                if not home or not away or not ts:
                    continue
                dt = pd.to_datetime(int(ts), unit='s', utc=True)
                t = ev.get('tournament') or {}
                league = t.get('name') or (t.get('uniqueTournament') or {}).get('name') or 'SofaScore'
                status = (ev.get('status') or {}).get('type', '')
                # date və time ayrı yazılır (UTC) — to_baku bunları Bakı vaxtına çevirir
                row = {'date': dt.strftime('%Y-%m-%d'), 'time': dt.strftime('%H:%M'), 'home': home, 'away': away, 'league': league}
                hs, aw = ev.get('homeScore') or {}, ev.get('awayScore') or {}
                if status == 'finished' and hs.get('current') is not None and aw.get('current') is not None:
                    row.update({'ft_home': hs.get('current'), 'ft_away': aw.get('current'),
                                'ht_home': hs.get('period1'), 'ht_away': aw.get('period1')})
                    results.append(row)
                elif status == 'notstarted':   # oynanmayan/ləğv/təxirə salınmış oyunlar qarşıdakı sayılmasın
                    fixtures.append(row)
            except Exception:
                continue
    for name, rows in (('fixtures', fixtures), ('results', results)):
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.drop_duplicates(subset=['date', 'home', 'away']).sort_values('date')
        df.to_csv(SOFASCORE_DIR / f'{name}.csv', index=False)
    load_data.clear()
    return len(results), len(fixtures)


def combine_sources(primary, secondary):
    """Eyni oyun (tarix + komanda açarı) iki cədvəldə varsa birləşdirir; boş xanaları ikinci cədvəl doldurur."""
    if secondary.empty:
        return primary
    if primary.empty:
        return secondary
    both = pd.concat([primary, secondary], ignore_index=True).dropna(subset=['date', 'home_k', 'away_k'])
    agg = {c: 'first' for c in both.columns if c not in ('date', 'home_k', 'away_k', 'src')}
    agg['src'] = lambda x: '+'.join(sorted(set('+'.join(x).split('+'))))
    return both.groupby(['date', 'home_k', 'away_k'], as_index=False, sort=False).agg(agg)


def merge_sources(fd, om):
    """Eyni oyun (tarix + komanda) iki mənbədə varsa birləşdirir: statistika üçün əvvəlcə football-data.co.uk, boşluğu Open Matchday doldurur.
    fd və om artıq add_keys + apply_key_map-dən keçmiş olmalıdır."""
    if fd.empty:
        return om, []
    if om.empty:
        return fd, []
    names = {}
    for side in ('home', 'away'):
        names.update(dict(zip(om[side + '_k'], om[side])))
    om_keys = set(om['home_k']) | set(om['away_k'])
    fd_names = {}
    for side in ('home', 'away'):
        fd_names.update(dict(zip(fd[side + '_k'], fd[side])))
    fd_only = sorted(n for k, n in fd_names.items() if k not in om_keys)
    both = pd.concat([fd, om], ignore_index=True).dropna(subset=['date', 'home_k', 'away_k'])
    agg = {c: 'first' for c in both.columns if c not in ('date', 'home_k', 'away_k', 'src')}
    agg['src'] = lambda x: '+'.join(sorted(set(x)))
    merged = both.groupby(['date', 'home_k', 'away_k'], as_index=False, sort=False).agg(agg)
    merged['home'] = merged['home_k'].map(names).fillna(merged['home'])
    merged['away'] = merged['away_k'].map(names).fillna(merged['away'])
    return merged, fd_only


def _similar_names(a, b, same_day=True):
    """Ad uyğunluğu: tam/prefiks/ixtisar ('s bratislava' ~ 'slovan bratislava'); eyni gündə əlavə olaraq yazılışca çox oxşar adlar."""
    if names_compatible(a, b):
        return True
    return same_day and difflib.SequenceMatcher(None, a, b).ratio() >= 0.85


def dedupe_games(df, has_score):
    """Eyni oyun fərqli ad yazılışları ilə təkrar qalıbsa birləşdirir (OM / openfootball / ESPN / SofaScore arasında).
    Şərt: tarix fərqi <= 1 gün, bir komanda eyni, digərinin adı oxşar (nəticələrdə hesab da eyni). Sürətlidir: yalnız eyni komanda+tarix cütləri müqayisə olunur."""
    if df.empty or not {'date', 'home_k', 'away_k'} <= set(df.columns):
        return df
    df = df.dropna(subset=['date', 'home_k', 'away_k']).copy()
    df['date'] = pd.to_datetime(df['date'])
    sc = ['ft_home', 'ft_away'] if has_score and {'ft_home', 'ft_away'} <= set(df.columns) else []
    kmap = {}
    for same, other in (('home_k', 'away_k'), ('away_k', 'home_k')):
        base = df[['date', same, other] + sc].drop_duplicates()
        for off in (-1, 0, 1):
            b = base.copy()
            b['date'] = b['date'] + pd.Timedelta(days=off)
            m = base.merge(b, on=['date', same], suffixes=('', '_b'))
            m = m[m[other] != m[other + '_b']]
            if sc:
                m = m[(m['ft_home'] == m['ft_home_b']) & (m['ft_away'] == m['ft_away_b'])]
            for x, y in zip(m[other], m[other + '_b']):
                if _similar_names(x, y, same_day=(off == 0)):
                    keep, drop = (x, y) if (len(x), x) >= (len(y), y) else (y, x)   # uzun ad qalır
                    kmap[drop] = keep
    def res(k):
        n = 0
        while k in kmap and n < 5:
            k, n = kmap[k], n + 1
        return k
    if kmap:
        best = {}
        for side in ('home', 'away'):
            for k, n in zip(df[side + '_k'], df[side]):
                k2 = res(k)
                if k2 not in best or len(str(n)) > len(str(best[k2])):
                    best[k2] = n
        df['home_k'], df['away_k'] = df['home_k'].map(res), df['away_k'].map(res)
        df['home'], df['away'] = df['home_k'].map(best).fillna(df['home']), df['away_k'].map(best).fillna(df['away'])
    agg = {c: 'first' for c in df.columns if c not in ('date', 'home_k', 'away_k', 'src')}
    agg['src'] = lambda x: '+'.join(sorted(set('+'.join(x).split('+'))))
    return df.groupby(['date', 'home_k', 'away_k'], as_index=False, sort=False).agg(agg)


@st.cache_resource(show_spinner=False)
def load_data(use_ss=False):
    fixtures, results = [], []
    for f in DATA_DIR.glob('*/*.csv'):
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        df['league'] = f.parent.name
        if f.name.startswith('fixtures_'):
            fixtures.append(df)
        elif f.name.startswith('results_'):
            results.append(df)
    # Open Matchday sənədinə görə saat sabit UTC+1 (CET-1) qaydasıdır
    om_fix = add_keys(to_baku(pd.concat(fixtures, ignore_index=True) if fixtures else pd.DataFrame(), 'Etc/GMT-1'), 'OM')
    om_res = add_keys(to_baku(pd.concat(results, ignore_index=True) if results else pd.DataFrame(), 'Etc/GMT-1'), 'OM')
    of_fix, of_res = load_of()
    om_fix = combine_sources(om_fix, add_keys(of_fix, 'OF'))
    om_res = combine_sources(om_res, add_keys(of_res, 'OF'))
    es_fix, es_res = load_espn()
    om_fix = combine_sources(om_fix, add_keys(es_fix, 'ES'))
    om_res = combine_sources(om_res, add_keys(es_res, 'ES'))
    ss_fix, ss_res = load_sofascore() if use_ss else (pd.DataFrame(), pd.DataFrame())
    om_fix = combine_sources(om_fix, add_keys(ss_fix, 'SS'))
    om_res = combine_sources(om_res, add_keys(ss_res, 'SS'))
    fd_fix, fd_res = load_fd()
    fd_fix, fd_res = add_keys(fd_fix, 'FD'), add_keys(fd_res, 'FD')
    fdx_res = add_keys(load_fdx(), 'FD')
    if not fdx_res.empty:
        fd_res = pd.concat([x for x in (fd_res, fdx_res) if not x.empty], ignore_index=True)
    ir_res = add_keys(load_ir(), 'IR')
    if not ir_res.empty:
        fd_res = pd.concat([x for x in (fd_res, ir_res) if not x.empty], ignore_index=True)
    fd_all = pd.concat([x for x in (fd_res, fd_fix) if not x.empty], ignore_index=True) if (not fd_res.empty or not fd_fix.empty) else pd.DataFrame()
    om_all = pd.concat([x for x in (om_res, om_fix) if not x.empty], ignore_index=True) if (not om_res.empty or not om_fix.empty) else pd.DataFrame()
    kmap = learn_key_map(fd_all, om_all)
    fd_fix, fd_res = apply_key_map(fd_fix, kmap), apply_key_map(fd_res, kmap)
    lmap = {**learn_league_map(fd_fix, om_fix), **learn_league_map(fd_res, om_res)}
    if lmap:
        for df_ in (om_fix, om_res):
            if not df_.empty:
                df_['league'] = df_['league'].map(lambda l: lmap.get(l, l))
    fix, fix_only = merge_sources(fd_fix, om_fix)
    res, res_only = merge_sources(fd_res, om_res)
    fix, res = dedupe_games(fix, False), dedupe_games(res, True)
    fix, res = collapse_near_dates(fix), collapse_near_dates(res)
    for df_ in (fix, res):
        if not df_.empty and 'league' in df_.columns:
            df_['league'] = df_['league'].map(pretty_league)
    # Hazırlıq addımları (əvvəl hər klikdə təkrarlanırdı) — indi yalnız bir dəfə
    if not fix.empty:
        fix['date'] = pd.to_datetime(fix.get('date'), errors='coerce')
    if not res.empty:
        res['date'] = pd.to_datetime(res.get('date'), errors='coerce')
        for c in ['ft_home', 'ft_away', 'ht_home', 'ht_away', 'home_corners', 'away_corners',
                  'home_shots', 'away_shots', 'home_target', 'away_target']:
            if c in res.columns:
                res[c] = pd.to_numeric(res[c], errors='coerce')
        res = res.dropna(subset=['date', 'home', 'away', 'ft_home', 'ft_away']).reset_index(drop=True)
    return fix, res, sorted(set(fix_only) | set(res_only))


def refresh_data():
    r = requests.get(REPO_ZIP, timeout=90, headers={'User-Agent': 'FutbolFiltri/1.0'})
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    base = next((n.split('/')[0] for n in z.namelist() if n.endswith('/README.md')), None)
    if not base:
        raise RuntimeError('GitHub ZIP daxilində layihə tapılmadı.')
    temp = Path(tempfile.mkdtemp())
    try:
        z.extractall(temp)
        source = temp / base / 'data'
        if not source.exists():
            raise RuntimeError('Yüklənən layihədə data qovluğu tapılmadı.')
        if DATA_DIR.exists():
            shutil.rmtree(DATA_DIR)
        shutil.copytree(source, DATA_DIR)
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    load_data.clear()


def refresh_fd():
    FD_DIR.mkdir(exist_ok=True)
    sess = requests.Session()
    sess.headers['User-Agent'] = 'FutbolFiltri/1.0'
    ok, failed = 0, []
    for season in fd_seasons():
        for code in FD_LEAGUES:
            try:
                r = sess.get(f'{FD_BASE}/mmz4281/{season}/{code}.csv', timeout=30)
                if r.status_code == 200 and len(r.content) > 200:
                    (FD_DIR / f'{season}_{code}.csv').write_bytes(r.content)
                    ok += 1
                else:
                    failed.append(f'{season}/{code}')
            except requests.RequestException:
                failed.append(f'{season}/{code}')
    try:
        r = sess.get(f'{FD_BASE}/fixtures.csv', timeout=30)
        if r.status_code == 200 and len(r.content) > 50:
            (FD_DIR / 'fixtures.csv').write_bytes(r.content)
            ok += 1
        else:
            failed.append('fixtures.csv')
    except requests.RequestException:
        failed.append('fixtures.csv')
    load_data.clear()
    return ok, failed


def refresh_fdx():
    FDX_DIR.mkdir(exist_ok=True)
    def one(code):
        try:
            r = requests.get(f'{FD_BASE}/new/{code}.csv', timeout=40, headers={'User-Agent': 'FutbolFiltri/1.0'})
            if r.status_code == 200 and len(r.content) > 200:
                (FDX_DIR / f'{code}.csv').write_bytes(r.content)
                return code, True
        except requests.RequestException:
            pass
        return code, False
    with ThreadPoolExecutor(max_workers=6) as ex:
        got = list(ex.map(one, FDX_CODES))
    load_data.clear()
    return sum(1 for _, ok in got if ok), [c for c, ok in got if not ok]


def refresh_of():
    OF_DIR.mkdir(exist_ok=True)
    jobs = [(s_, c) for s_ in of_seasons() for c in OF_LEAGUES] + [(y_, c) for y_ in of_years() for c in OF_YEAR_LEAGUES]
    def one(job):
        s_, c = job
        try:
            r = requests.get(f'{OF_BASE}/{s_}/{c}.json', timeout=30, headers={'User-Agent': 'FutbolFiltri/1.0'})
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict) and data.get('matches'):
                    (OF_DIR / f'{s_}_{c}.json').write_text(json.dumps(data), encoding='utf-8')
                    return True
            elif r.status_code == 404:
                return None   # bu mövsüm/liqa üçün fayl yoxdur — normaldır
        except (requests.RequestException, ValueError):
            pass
        return False
    with ThreadPoolExecutor(max_workers=8) as ex:
        got = list(ex.map(one, jobs))
    load_data.clear()
    return sum(1 for g in got if g), sum(1 for g in got if g is False)


def _espn_get(sess, params):
    return sess.get(f'{ESPN_BASE}/{params[0]}/scoreboard', params=params[1], timeout=25)


def _espn_score(v):
    if isinstance(v, dict):
        v = v.get('displayValue', v.get('value'))
    return pd.to_numeric(v, errors='coerce')


def _espn_ht(side):
    ls = side.get('linescores')
    if isinstance(ls, list) and len(ls) >= 2 and isinstance(ls[0], dict):
        return _espn_score(ls[0])
    return float('nan')


def _espn_parse(data, default_name, slug=''):
    """Bir scoreboard cavabından (fixtures, results) sətirləri çıxarır."""
    name = default_name
    try:
        name = data['leagues'][0].get('name') or default_name
    except (KeyError, IndexError, TypeError, AttributeError):
        pass
    fix, res = [], []
    for ev in data.get('events', []) or []:
        try:
            comp = ev['competitions'][0]
            sides = {c['homeAway']: c for c in comp['competitors']}
            h, a = sides['home'], sides['away']
            stype = ev['status']['type']
            dt = pd.to_datetime(ev['date'], utc=True)
            row = {'date': dt.strftime('%Y-%m-%d'), 'time': dt.strftime('%H:%M'),
                   'home': h['team']['displayName'], 'away': a['team']['displayName'], 'league': name,
                   'id': str(ev.get('id', '')), 'slug': slug}
            if stype.get('completed'):
                fh, fa = _espn_score(h.get('score')), _espn_score(a.get('score'))
                if pd.isna(fh) or pd.isna(fa):
                    continue
                row['ft_home'], row['ft_away'] = int(fh), int(fa)
                hh, ha = _espn_ht(h), _espn_ht(a)
                if pd.notna(hh) and pd.notna(ha) and hh <= fh and ha <= fa:
                    row['ht_home'], row['ht_away'] = int(hh), int(ha)
                res.append(row)
            elif stype.get('name') == 'STATUS_SCHEDULED':
                fix.append(row)
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return fix, res, name


def _espn_fetch_league(slug, default_name, start, end):
    """Bir liqa üçün tarix aralığını yükləyir. Qaytarır: (fix, res, xəta_mətni_və_ya_None)."""
    sess = requests.Session()
    sess.headers['User-Agent'] = 'FutbolFiltri/1.0'
    fix, res = [], []
    fmt = '%Y%m%d'
    try:
        probe = _espn_get(sess, (slug, {'dates': end.strftime(fmt), 'limit': 300}))
        if probe.status_code != 200:
            return fix, res, f'{slug} (HTTP {probe.status_code})'
        f, r, name = _espn_parse(probe.json(), default_name, slug)
        fix += f
        res += r
        # Əvvəl tarix aralığı ilə sına; işləməsə gün-gün yüklə.
        chunks, cur = [], start
        while cur <= end:
            nxt = min(cur + timedelta(days=13), end)
            chunks.append((cur, nxt))
            cur = nxt + timedelta(days=1)
        range_ok = None
        for c0, c1 in chunks:
            if range_ok is not False:
                rr = _espn_get(sess, (slug, {'dates': f'{c0.strftime(fmt)}-{c1.strftime(fmt)}', 'limit': 300}))
                if rr.status_code == 200:
                    range_ok = True
                    f, r, _ = _espn_parse(rr.json(), name, slug)
                    fix += f
                    res += r
                    continue
                range_ok = False
            d = c0
            while d <= c1:
                rd = _espn_get(sess, (slug, {'dates': d.strftime(fmt), 'limit': 300}))
                if rd.status_code == 200:
                    f, r, _ = _espn_parse(rd.json(), name, slug)
                    fix += f
                    res += r
                d += timedelta(days=1)
    except (requests.RequestException, ValueError) as e:
        return fix, res, f'{slug} ({type(e).__name__})'
    return fix, res, None


def _espn_stats(slug, event_id):
    """Bir oyunun künc, zərbə və qapıya dəqiq zərbə sayını ESPN 'summary' endpointindən çıxarır. Tapılmasa boş dict qaytarır."""
    try:
        r = requests.get(f'{ESPN_BASE}/{slug}/summary', params={'event': event_id}, timeout=25,
                         headers={'User-Agent': 'FutbolFiltri/1.0'})
        if r.status_code != 200:
            return {}
        data = r.json()
    except (requests.RequestException, ValueError):
        return {}
    side_of = {}
    try:
        for c in data['header']['competitions'][0]['competitors']:
            side_of[str(c['team']['id'])] = c.get('homeAway')
    except (KeyError, IndexError, TypeError):
        pass
    out = {}
    for t in (data.get('boxscore') or {}).get('teams', []) or []:
        side = t.get('homeAway') or side_of.get(str((t.get('team') or {}).get('id')))
        if side not in ('home', 'away'):
            continue
        for stt in t.get('statistics', []) or []:
            name, label = str(stt.get('name', '')).lower(), str(stt.get('label', '')).lower()
            val = pd.to_numeric(stt.get('displayValue', stt.get('value')), errors='coerce')
            if pd.isna(val):
                continue
            if name in ('woncorners', 'cornerkicks', 'corners') or 'corner' in label:
                out.setdefault(f'{side}_corners', int(val))
            elif name == 'shotsontarget' or label in ('shots on target', 'shots on goal'):
                out.setdefault(f'{side}_target', int(val))
            elif name == 'totalshots' or label in ('shots', 'total shots'):
                out.setdefault(f'{side}_shots', int(val))
    for a_, b_ in (('home_corners', 'away_corners'), ('home_shots', 'away_shots'), ('home_target', 'away_target')):
        if not (a_ in out and b_ in out):
            out.pop(a_, None)
            out.pop(b_, None)
    return out


def refresh_espn():
    ESPN_DIR.mkdir(exist_ok=True)
    old_res_path = ESPN_DIR / 'results.csv'
    first = not old_res_path.exists()
    today_ = datetime.utcnow().date()
    start = today_ - timedelta(days=ESPN_DAYS_BACK_FIRST if first else ESPN_DAYS_BACK)
    end = today_ + timedelta(days=ESPN_DAYS_AHEAD)
    all_fix, all_res, failed = [], [], []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {slug: ex.submit(_espn_fetch_league, slug, name, start, end) for slug, name in ESPN_LEAGUES.items()}
        for slug, fu in futs.items():
            f, r, err = fu.result()
            all_fix += f
            all_res += r
            if err:
                failed.append(err)
    key = ['date', 'home', 'away']
    res_all = pd.DataFrame(all_res)
    old = read_csv_safe(old_res_path) if old_res_path.exists() else None
    if old is not None and not old.empty:
        old = old.drop_duplicates(subset=key)
        if res_all.empty:
            res_all = old
        else:
            res_all = res_all.drop_duplicates(subset=key).set_index(key).combine_first(old.set_index(key)).reset_index()
    stats_done = stats_left = 0
    if not res_all.empty:
        for col in ('home_corners', 'away_corners', 'home_shots', 'away_shots',
                    'home_target', 'away_target', 'stats_try', 'id', 'slug'):
            if col not in res_all.columns:
                res_all[col] = float('nan')
        res_all['stats_try'] = pd.to_numeric(res_all['stats_try'], errors='coerce').fillna(0)
        need = (res_all['id'].notna() & res_all['slug'].notna()
                & (res_all['home_corners'].isna() | res_all['home_shots'].isna())
                & (res_all['stats_try'] < ESPN_STATS_MAX_TRIES))
        pend = res_all[need].sort_values('date', ascending=False).head(ESPN_STATS_PER_REFRESH)
        stats_left = int(need.sum()) - len(pend)
        if not pend.empty:
            with ThreadPoolExecutor(max_workers=8) as ex:
                got = list(ex.map(lambda t: _espn_stats(t[0], t[1]), zip(pend['slug'], pend['id'])))
            for idx, st_ in zip(pend.index, got):
                res_all.at[idx, 'stats_try'] += 1
                if st_:
                    stats_done += 1
                    for k, v in st_.items():
                        res_all.at[idx, k] = v
        res_all = res_all.sort_values('date')
        res_all.to_csv(old_res_path, index=False)
    fix_new = pd.DataFrame(all_fix)
    if not fix_new.empty:
        fix_new = fix_new.drop_duplicates(subset=['date', 'home', 'away']).sort_values(['date', 'time'])
        fix_new.to_csv(ESPN_DIR / 'fixtures.csv', index=False)
    load_data.clear()
    return len(res_all), len(fix_new), failed, stats_done, stats_left


# ---- Canlı və bu gün bitmiş oyunların hesabı (ESPN scoreboard, yalnız oyunda/bitmiş statuslar) ----
LIVE_EXTRA_SLUGS = ['eng.1', 'eng.2', 'esp.1', 'esp.2', 'ger.1', 'ger.2', 'ita.1', 'ita.2', 'fra.1', 'fra.2',
                    'ned.1', 'por.1', 'tur.1', 'sco.1', 'bel.1', 'gre.1']   # yanlış kod 404 verir və səssizcə atlanır


def _live_one(slug):
    t0 = datetime.utcnow().date()
    rng = f"{(t0 - timedelta(days=1)).strftime('%Y%m%d')}-{(t0 + timedelta(days=1)).strftime('%Y%m%d')}"
    try:
        r = requests.get(f'{ESPN_BASE}/{slug}/scoreboard', params={'dates': rng, 'limit': 300}, timeout=12,
                         headers={'User-Agent': 'FutbolFiltri/1.0'})
        if r.status_code != 200:
            return []
        data = r.json()
    except (requests.RequestException, ValueError):
        return []
    out = []
    for ev in data.get('events', []) or []:
        try:
            comp = ev['competitions'][0]
            sides = {c['homeAway']: c for c in comp['competitors']}
            h, a = sides['home'], sides['away']
            stt = ev['status']['type']
            state = stt.get('state', '')
            if state == 'post' and not stt.get('completed'):
                continue   # təxirə salınmış / ləğv edilmiş
            if state not in ('in', 'post'):
                continue
            hs, as_ = _espn_score(h.get('score')), _espn_score(a.get('score'))
            if pd.isna(hs) or pd.isna(as_):
                continue
            d = pd.to_datetime(ev['date'], utc=True).tz_localize(None).normalize()
            detail = str(stt.get('shortDetail') or ev['status'].get('displayClock') or '').strip()
            out.append({'home': h['team']['displayName'], 'away': a['team']['displayName'], 'hs': int(hs), 'as': int(as_),
                        'live': state == 'in', 'detail': detail, 'date': d})
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return out


@st.cache_data(ttl=60, show_spinner=False)
def fetch_live_scores():
    slugs = list(dict.fromkeys(list(ESPN_LEAGUES) + LIVE_EXTRA_SLUGS))
    with ThreadPoolExecutor(max_workers=12) as ex:
        parts = list(ex.map(_live_one, slugs))
    rows = [r for p in parts for r in p]
    for r in rows:
        r['home_k'], r['away_k'] = team_key(r['home']), team_key(r['away'])
    return rows


def lookup_score(hk, ak, date, res_idx, live_rows):
    """Oyunun hesabı: əvvəl canlı mənbə (ən təzə), sonra nəticələr bazası. Qaytarır (hesab, status) və ya ('', '')."""
    for r in live_rows:
        if abs((r['date'] - date).days) > 1:
            continue
        if (r['home_k'] == hk and r['away_k'] == ak) or (names_compatible(r['home_k'], hk) and names_compatible(r['away_k'], ak)):
            return f"{r['hs']}–{r['as']}", (f"Canlı · {r['detail']}" if r['live'] else 'Bitib')
    for d, fh, fa in res_idx.get((hk, ak), []):
        if abs((d - date).days) <= 1:
            return f'{fh}–{fa}', 'Bitib'
    return '', ''


# ---- Filtrlərin URL-də saxlanması: səhifə yenilənəndə (başqa appdan qayıdanda) quşlar itməsin ----
FILTERS_FILE = ROOT / 'saved_filters.json'
_PKEYS = {'_ran', 'btts', 'btts_no', 'under25', 'ht05_under', 'ht15_under', 'ht_draw', 'n_games', 'use_ss'}
_PPREF = ('match_', 'club_', 'min_', 'on_', 'mode_', 'corners_', 'shots_', 'target_')
if not st.session_state.get('_qp_restored'):
    try:
        _saved = {k: v for k, v in dict(st.query_params).items() if k.startswith('f_')}
        if not _saved and FILTERS_FILE.exists():   # ünvanda filtr yoxdursa (ana ekran ikonu ilə açılış) — serverdə saxlanmış sonuncu filtrlər
            _saved = json.loads(FILTERS_FILE.read_text(encoding='utf-8'))
        _same_day = _saved.get('f__saved_on') == baku_today().isoformat()
        for _k, _v in _saved.items():
            _k = _k[2:]
            if _k == '_saved_on':
                continue
            if _k in ('d_from', 'd_to'):   # tarixlər yalnız eyni gün içində bərpa olunur
                if _same_day:
                    st.session_state[_k] = datetime.strptime(_v, '%Y-%m-%d').date()
                continue
            st.session_state[_k] = True if _v == 'True' else (int(_v) if _v.lstrip('-').isdigit() else _v)
        if st.session_state.get('_ran'):
            st.session_state['auto_run'] = True   # yeniləmədən əvvəl analiz aparılıbsa, nəticələr avtomatik yenidən hesablanır
    except Exception:
        pass
    st.session_state['_qp_restored'] = True

with st.sidebar:
    st.header('Məlumat bazası')
    if 'refresh_msgs' in st.session_state:
        for kind, text in st.session_state.pop('refresh_msgs'):
            getattr(st, kind)(text)
    if st.button('🔄 Məlumatı yenilə', use_container_width=True):
        msgs = []
        with st.spinner('Məlumatlar yüklənir...'):
            try:
                refresh_data()
                msgs.append(('success', 'Open Matchday yeniləndi.'))
            except Exception as e:
                msgs.append(('error', f'Open Matchday yenilənmədi: {e}'))
            try:
                ok, failed = refresh_fd()
                msgs.append(('success', f'football-data.co.uk: {ok} fayl yükləndi.'))
                if failed:
                    msgs.append(('warning', f'Yüklənməyən fayllar ({len(failed)}): ' + ', '.join(failed[:15])))
            except Exception as e:
                msgs.append(('error', f'football-data.co.uk yenilənmədi: {e}'))
            try:
                ok, failed = refresh_fdx()
                msgs.append(('success', f'football-data.co.uk (əlavə liqalar): {ok} fayl yükləndi.'))
                if failed:
                    msgs.append(('warning', 'Yüklənməyən əlavə liqalar: ' + ', '.join(failed)))
            except Exception as e:
                msgs.append(('error', f'football-data.co.uk əlavə liqalar yenilənmədi: {e}'))
            try:
                refresh_ir()
                msgs.append(('success', 'international_results (milli komandalar) yeniləndi.'))
            except Exception as e:
                msgs.append(('error', f'international_results yenilənmədi: {e}'))
            try:
                ok, bad = refresh_of()
                msgs.append(('success', f'openfootball: {ok} fayl yükləndi.' + (f' Xətalı: {bad}.' if bad else '')))
            except Exception as e:
                msgs.append(('error', f'openfootball yenilənmədi: {e}'))
            try:
                n_res, n_fix, espn_failed, st_done, st_left = refresh_espn()
                msgs.append(('success', f'ESPN: {n_res} nəticə, {n_fix} qarşıdakı oyun. Künc/kart statistikası: {st_done} oyun yükləndi'
                             + (f', {st_left} oyun növbəti yeniləmədə davam edəcək.' if st_left > 0 else '.')))
                if espn_failed:
                    msgs.append(('warning', f'ESPN-də yüklənməyən yarışlar ({len(espn_failed)}): ' + ', '.join(espn_failed)))
            except Exception as e:
                msgs.append(('error', f'ESPN yenilənmədi: {e}'))
            try:
                ss_res_n, ss_fix_n = refresh_sofascore()
                msgs.append(('success', f'SofaScore sınaq mənbəyi: {ss_res_n} nəticə, {ss_fix_n} qarşıdakı oyun yükləndi.'))
            except Exception as e:
                msgs.append(('warning', f'SofaScore sınaq mənbəyi əlçatan olmadı: {e}. Digər mənbələr işləməyə davam edir.'))
        st.session_state['refresh_msgs'] = msgs
        st.rerun()
    use_ss = st.checkbox('SofaScore sınaq mənbəyini istifadə et (analizi yavaşladır)', value=False, key='use_ss')
    live_scores_on = st.checkbox('Canlı hesabları yoxla (analizi ləngidə bilər)', value=False, key='live_scores_on')
    st.caption('Yeniləmə və canlı hesablar internet tələb edir. Sürətli analiz üçün canlı hesab yoxlaması standart olaraq söndürülüb.')

fixtures, results, fd_only_teams = load_data(use_ss)
if fixtures.empty:
    st.error('Oyun cədvəlləri tapılmadı. ZIP-i tam çıxartdığını yoxla və ya sol paneldən yenilə.')
    st.stop()

today = baku_today()   # Bakı vaxtı ilə bu gün (server UTC olsa belə)
st.session_state.setdefault('d_from', today)
st.session_state.setdefault('d_to', today)


def _shift_dates(days):
    # Ümumi naviqasiya: tarix aralığının hər iki tərəfini birlikdə sürüşdür.
    if days == 0:
        st.session_state['d_from'] = st.session_state['d_to'] = baku_today()
    else:
        st.session_state['d_from'] = st.session_state['d_from'] + timedelta(days=days)
        st.session_state['d_to'] = st.session_state['d_to'] + timedelta(days=days)
    st.session_state['auto_run'] = True


def _shift_one_date(key, days):
    # Başlanğıc və son tarixi ayrıca əvvəlki/növbəti günə keçir.
    st.session_state[key] = st.session_state[key] + timedelta(days=days)
    st.session_state['auto_run'] = True


with st.container(border=True):
    st.markdown('<div class="sec">1 · Tarix və oyun sayı</div>', unsafe_allow_html=True)
    try:
        nav_box = st.container(key='datenav')
    except TypeError:   # köhnə Streamlit versiyası
        nav_box = st.container()
    with nav_box:
        n1, n2, n3 = st.columns([1, 3, 1])
        n1.button('◀', key='prev_day', on_click=_shift_dates, args=(-1,), use_container_width=True, help='Əvvəlki gün')
        _df, _dt = st.session_state['d_from'], st.session_state['d_to']
        _lab = f'📅 {_df:%d.%m.%Y}' if _df == _dt else f'📅 {_df:%d.%m} – {_dt:%d.%m.%Y}'
        n2.button(_lab + (' · bu gün' if _df == _dt == today else ''), key='today_btn', on_click=_shift_dates, args=(0,),
                  use_container_width=True, help='Basanda Bakı vaxtı ilə bu günə qayıdır')
        n3.button('▶', key='next_day', on_click=_shift_dates, args=(1,), use_container_width=True, help='Növbəti gün')
    st.caption('🕒 Tarix və saatlar Bakı vaxtı ilədir (UTC+4).')
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        st.caption('Başlanğıc tarixi')
        with st.container(key='start_date_row'):
            left, date_col, right = st.columns([1, 5, 1], gap='small')
            left.button('◀', key='from_prev', on_click=_shift_one_date, args=('d_from', -1), use_container_width=True, help='Başlanğıc tarixini bir gün geri çək')
            date_from = date_col.date_input('Başlanğıc tarixi', key='d_from', label_visibility='collapsed')
            right.button('▶', key='from_next', on_click=_shift_one_date, args=('d_from', 1), use_container_width=True, help='Başlanğıc tarixini bir gün irəli çək')
    with c2:
        st.caption('Son tarix')
        with st.container(key='end_date_row'):
            left, date_col, right = st.columns([1, 5, 1], gap='small')
            left.button('◀', key='to_prev', on_click=_shift_one_date, args=('d_to', -1), use_container_width=True, help='Son tarixini bir gün geri çək')
            date_to = date_col.date_input('Son tarix', key='d_to', label_visibility='collapsed')
            right.button('▶', key='to_next', on_click=_shift_one_date, args=('d_to', 1), use_container_width=True, help='Son tarixini bir gün irəli çək')
    with c3:
        n_games = st.number_input('Hər komandanın son neçə oyunu?', min_value=1, max_value=50, value=2, step=1, key='n_games')
    league_options = sorted({str(x) for x in set(fixtures['league'].dropna().unique()) | set(results['league'].dropna().unique()) if str(x).strip()})
    # Liqa seçimi: cədvəldə hər liqanın qarşısında quş (checkbox). İlk dəfə hamısı seçilmiş olur.
    known = st.session_state.get('lg_known', set())
    st.session_state.setdefault('lg_sel', set())
    st.session_state['lg_sel'] = (st.session_state['lg_sel'] & set(league_options)) | (set(league_options) - known)
    st.session_state['lg_known'] = set(league_options)
    st.session_state.setdefault('lg_ver', 0)
    # Seçilmiş tarix aralığında hansı liqalarda neçə oyun var (analizdəki məntiqlə eyni: keçmiş — nəticələr, bu gün və sonrası — cədvəl)
    d_from, d_to, d_today = pd.Timestamp(date_from), pd.Timestamp(date_to), pd.Timestamp(today)

    def _games_in_range(df, past):
        if df.empty:
            return df
        d = df['date'].dt.normalize()
        keep = (d >= d_from) & (d <= d_to) & ((d < d_today) if past else (d >= d_today))
        return df[keep]

    _rng = pd.concat([_games_in_range(results, True), _games_in_range(fixtures, False)], ignore_index=True)
    games_per_league = _rng.drop_duplicates(subset=['date', 'home_k', 'away_k'])['league'].value_counts().to_dict() if not _rng.empty else {}
    leagues_with_games = [l for l in league_options if games_per_league.get(l, 0) > 0]

    with st.expander(f'🏆 Liqalar — {len(league_options)} liqa var · seçilmiş tarixdə oyunu olan: {len(leagues_with_games)} (açıb seç)', expanded=False):
        lg_query = st.text_input('🔍 Liqa və ya ölkə axtar', placeholder='məs: almaniya, england, fin, champions, kubok ...', key='lg_query')
        q_tokens = norm_search(lg_query).split()
        visible = [l for l in league_options if all(t in league_search_blob(l) for t in q_tokens)]
        # oyunu olan liqalar yuxarıda (oyun sayına görə), qalanlar əlifba ilə
        visible.sort(key=lambda l: (-games_per_league.get(l, 0), l))
        b1, b2, b3 = st.columns(3)
        if b1.button('✅ Göstərilənləri seç' if q_tokens else '✅ Hamısını seç', use_container_width=True):
            st.session_state['lg_sel'] = st.session_state['lg_sel'] | set(visible)
            st.session_state['lg_ver'] += 1
        if b2.button('⬜ Göstərilənləri təmizlə' if q_tokens else '⬜ Təmizlə', use_container_width=True):
            st.session_state['lg_sel'] = st.session_state['lg_sel'] - set(visible)
            st.session_state['lg_ver'] += 1
        if b3.button('🎯 Yalnız oyunu olanları seç', use_container_width=True):
            st.session_state['lg_sel'] = (st.session_state['lg_sel'] - set(visible)) | {l for l in visible if games_per_league.get(l, 0) > 0}
            st.session_state['lg_ver'] += 1
        if visible:
            lg_df = pd.DataFrame({
                'Seç': [l in st.session_state['lg_sel'] for l in visible],
                'Liqa': visible,
                'Oyun': [int(games_per_league.get(l, 0)) for l in visible],
            })
            lg_edit = st.data_editor(
                lg_df, hide_index=True, disabled=['Liqa', 'Oyun'], height=340, use_container_width=True,
                column_config={'Seç': st.column_config.CheckboxColumn('Seç', width='small'),
                               'Liqa': st.column_config.TextColumn('Liqa', width='large'),
                               'Oyun': st.column_config.NumberColumn('Oyun sayı', width='small', help='Seçilmiş tarix aralığındakı oyun sayı')},
                key=f"lg_editor_{st.session_state['lg_ver']}_{norm_search(lg_query).strip()}_{date_from}_{date_to}")
            chosen = set(lg_edit.loc[lg_edit['Seç'], 'Liqa'])
            st.session_state['lg_sel'] = (st.session_state['lg_sel'] - set(visible)) | chosen
        else:
            st.info('Belə liqa tapılmadı. Başqa söz yaz (məs: ölkə adı).')
    sel_leagues = st.session_state['lg_sel']
    st.caption(f'Seçilmiş liqa: {len(sel_leagues)} / {len(league_options)}')

MODE_HELP = 'Oyunda: iki komandanın göstəricilərinin cəmi. Klub: yoxlanılan klubun öz göstəricisi (hər komanda üçün ayrıca).'


def _mode_row(key, title=None, checkbox=None):
    """Başlığın (və ya seçim qutusunun) sağında 'Oyunda | Klub' seçimi."""
    try:
        box = st.container(key='moderow_' + key)
    except TypeError:   # köhnə Streamlit
        box = st.container()
    with box:
        left, right = st.columns([5, 4])
        on = None
        if checkbox is not None:
            on = left.checkbox(checkbox, key='on_' + key)
        else:
            left.markdown(f'**{title}**')
        mode = right.radio('Rejim', ['Oyunda', 'Klub'], horizontal=True, key='mode_' + key, label_visibility='collapsed', help=MODE_HELP)
    return on, mode


def _min_input(on, mode, key, name, total_cfg, club_cfg):
    if mode == 'Oyunda':
        label, (default, maxv) = f'Matç üzrə minimum ümumi {name}', total_cfg
    else:
        label, (default, maxv) = f'Klub üzrə minimum {name} (hər oyunda)', club_cfg
    return st.number_input(label, min_value=0, max_value=maxv, value=default, disabled=not on, key=f'min_{key}_{mode}')


with st.container(border=True):
    st.markdown('<div class="sec">2 · Filtrlər</div>', unsafe_allow_html=True)
    cols = st.columns(3)
    with cols[0]:
        st.markdown("**⚽ Qol filtrləri**")
        btts = st.checkbox('BTTS — hər iki komanda qol vurub', key='btts')
        btts_no = st.checkbox('BTTS yox — ən azı bir komanda qol vurmayıb', key='btts_no')
        st.caption("Matç üzrə — hər iki komandanın qollarının cəmi")
        match_goal_25 = st.checkbox('Matç 2.5 üst', key='match_goal_25')
        under25 = st.checkbox('Matç 2.5 alt', key='under25')
        match_goal_35 = st.checkbox('Matç 3.5 üst', key='match_goal_35')
        match_goal_45 = st.checkbox('Matç 4.5 üst', key='match_goal_45')
        st.caption("Klub üzrə — hər klubun öz qolları")
        club_goal_05 = st.checkbox('Klub 0.5 üst', key='club_goal_05')
        club_goal_15 = st.checkbox('Klub 1.5 üst', key='club_goal_15')
        club_goal_25 = st.checkbox('Klub 2.5 üst', key='club_goal_25')
    with cols[1]:
        st.markdown("**⏱️ 1-ci hissə**")
        st.caption("Matç üzrə — ilk hissədəki ümumi qollar")
        match_ht05 = st.checkbox('1-ci hissə 0.5 üst', key='match_ht05')
        ht05_under = st.checkbox('1-ci hissə 0.5 alt (qol yoxdur)', key='ht05_under')
        match_ht15 = st.checkbox('1-ci hissə 1.5 üst', key='match_ht15')
        ht15_under = st.checkbox('1-ci hissə 1.5 alt', key='ht15_under')
        ht_draw = st.checkbox('1-ci hissə heç-heçə', key='ht_draw')
        st.caption("Klub üzrə — hər klubun ilk hissə qolları")
        club_ht05 = st.checkbox('Klub 1-ci hissə 0.5 üst', key='club_ht05')
        club_ht15 = st.checkbox('Klub 1-ci hissə 1.5 üst', key='club_ht15')
    with cols[2]:
        st.markdown('**📊 Statistika**')
        st.caption('Künc zərbələri')
        corners_match_on = st.checkbox('Oyunda künc minimumu', key='corners_match_on')
        min_corners_match = st.number_input('Matç üzrə ümumi künc sayı', min_value=0, max_value=30, value=9, step=1, disabled=not corners_match_on, key='min_corners_match')
        corners_club_on = st.checkbox('Klub üzrə künc minimumu', key='corners_club_on')
        min_corners_club = st.number_input('Hər klub üçün künc sayı', min_value=0, max_value=20, value=4, step=1, disabled=not corners_club_on, key='min_corners_club')
        st.caption('Qapıya zərbələr')
        shots_match_on = st.checkbox('Oyunda zərbə minimumu', key='shots_match_on')
        min_shots_match = st.number_input('Matç üzrə ümumi zərbə sayı', min_value=0, max_value=60, value=22, step=1, disabled=not shots_match_on, key='min_shots_match')
        shots_club_on = st.checkbox('Klub üzrə zərbə minimumu', key='shots_club_on')
        min_shots_club = st.number_input('Hər klub üçün zərbə sayı', min_value=0, max_value=40, value=11, step=1, disabled=not shots_club_on, key='min_shots_club')
        st.caption('Qapıya dəqiq zərbələr')
        target_match_on = st.checkbox('Oyunda dəqiq zərbə minimumu', key='target_match_on')
        min_target_match = st.number_input('Matç üzrə ümumi dəqiq zərbə', min_value=0, max_value=30, value=8, step=1, disabled=not target_match_on, key='min_target_match')
        target_club_on = st.checkbox('Klub üzrə dəqiq zərbə minimumu', key='target_club_on')
        min_target_club = st.number_input('Hər klub üçün dəqiq zərbə', min_value=0, max_value=20, value=4, step=1, disabled=not target_club_on, key='min_target_club')
    st.markdown('<div class="rule">Hər komandanın seçilən son oyunlarının <b>HAMISI</b> bütün şərtlərə uyğun olmalıdır.</div>', unsafe_allow_html=True)

criteria_selected = any([
    btts, btts_no, ht05_under, ht15_under, ht_draw, under25,
    match_goal_25, match_goal_35, match_goal_45,
    club_goal_05, club_goal_15, club_goal_25,
    match_ht05, match_ht15, club_ht05, club_ht15,
    corners_match_on, corners_club_on, shots_match_on, shots_club_on,
    target_match_on, target_club_on
])
def save_filters():
    try:
        _persist = {'f_' + k: str(v) for k, v in st.session_state.items()
                    if isinstance(k, str) and (k in _PKEYS or k.startswith(_PPREF)) and isinstance(v, (bool, int, str)) and v is not False}
        for _dk in ('d_from', 'd_to'):
            if _dk in st.session_state:
                _persist['f_' + _dk] = st.session_state[_dk].isoformat()
        _persist['f__saved_on'] = baku_today().isoformat()
        if dict(st.query_params) != _persist:
            st.query_params.clear()
            st.query_params.update(_persist)
        if _persist != st.session_state.get('_last_saved'):
            FILTERS_FILE.write_text(json.dumps(_persist, ensure_ascii=False), encoding='utf-8')
            st.session_state['_last_saved'] = _persist
    except Exception:
        pass


save_filters()
if not criteria_selected:
    st.info('Ən azı bir filtr seç. Tarixə uyğun oyunlar aşağıda görünür, analiz üçün isə filtr lazımdır.')


def _num(df, col):
    return pd.to_numeric(df[col], errors='coerce') if col in df.columns else pd.Series(np.nan, index=df.index)


def _lbl(mode):
    return 'oyunda' if mode == 'Oyunda' else 'klub'


def _atleast(d, col_h, col_a, mode, thr):
    """'Oyunda' rejimi: iki komandanın cəmi ≥ thr. 'Klub' rejimi: hər komandanın öz göstəricisi ≥ thr (ev və qonaq üçün ayrıca)."""
    a, b = _num(d, col_h), _num(d, col_a)
    has = a.notna() & b.notna()
    if mode == 'Klub':
        return a >= thr, b >= thr, has
    p = (a + b) >= thr
    return p, p, has


def active_conditions():
    """Seçilmiş filtrlərin siyahısı: (ad, funksiya). Funksiya DataFrame alıb
    (ev sahibi baxışından ödənir, qonaq baxışından ödənir, lazımi məlumat var) qaytarır.
    'Oyunda' rejimində iki baxış eynidir; 'Klub' rejimində hər klubun öz göstəricisi yoxlanılır."""
    def same(fn):
        def inner(d):
            p, has = fn(d)
            return p, p, has
        return inner

    def ft(d):
        hg, ag = _num(d, 'ft_home'), _num(d, 'ft_away')
        return hg, ag, hg.notna() & ag.notna()

    def ht(d):
        a, b = _num(d, 'ht_home'), _num(d, 'ht_away')
        return a, b, a.notna() & b.notna()

    conds = []
    if btts:
        conds.append(('BTTS', same(lambda d: (lambda hg, ag, has: ((hg > 0) & (ag > 0), has))(*ft(d)))))
    if btts_no:
        conds.append(('BTTS yox', same(lambda d: (lambda hg, ag, has: (~((hg > 0) & (ag > 0)), has))(*ft(d)))))
    for on, label, mode, line in (
        (match_goal_25, 'Matç 2.5 üst', 'Oyunda', 2.5),
        (match_goal_35, 'Matç 3.5 üst', 'Oyunda', 3.5),
        (match_goal_45, 'Matç 4.5 üst', 'Oyunda', 4.5),
        (club_goal_05, 'Klub 0.5 üst', 'Klub', 0.5),
        (club_goal_15, 'Klub 1.5 üst', 'Klub', 1.5),
        (club_goal_25, 'Klub 2.5 üst', 'Klub', 2.5),
    ):
        if on:
            conds.append((label, (lambda thr, mode_: lambda d: _atleast(d, 'ft_home', 'ft_away', mode_, thr))(int(line) + 1, mode)))
    if under25:
        conds.append(('Matç 2.5 alt', same(lambda d: (lambda hg, ag, has: (hg + ag <= 2, has))(*ft(d)))))
    for on, label, mode, line in (
        (match_ht05, '1-ci hissə 0.5 üst', 'Oyunda', 0.5),
        (match_ht15, '1-ci hissə 1.5 üst', 'Oyunda', 1.5),
        (club_ht05, 'Klub 1-ci hissə 0.5 üst', 'Klub', 0.5),
        (club_ht15, 'Klub 1-ci hissə 1.5 üst', 'Klub', 1.5),
    ):
        if on:
            conds.append((label, (lambda thr, mode_: lambda d: _atleast(d, 'ht_home', 'ht_away', mode_, thr))(int(line) + 1, mode)))
    if ht05_under:
        conds.append(('1-ci hissə 0.5 alt', same(lambda d: (lambda a, b, has: (a + b == 0, has))(*ht(d)))))
    if ht15_under:
        conds.append(('1-ci hissə 1.5 alt', same(lambda d: (lambda a, b, has: (a + b <= 1, has))(*ht(d)))))
    if ht_draw:
        conds.append(('1-ci hissə heç-heçə', same(lambda d: (lambda a, b, has: (a == b, has))(*ht(d)))))
    for on, label, mode, threshold in (
        (corners_match_on, f'Matç künc ≥ {int(min_corners_match)}', 'Oyunda', min_corners_match),
        (corners_club_on, f'Klub künc ≥ {int(min_corners_club)}', 'Klub', min_corners_club),
        (shots_match_on, f'Matç zərbə ≥ {int(min_shots_match)}', 'Oyunda', min_shots_match),
        (shots_club_on, f'Klub zərbə ≥ {int(min_shots_club)}', 'Klub', min_shots_club),
        (target_match_on, f'Matç dəqiq zərbə ≥ {int(min_target_match)}', 'Oyunda', min_target_match),
        (target_club_on, f'Klub dəqiq zərbə ≥ {int(min_target_club)}', 'Klub', min_target_club),
    ):
        if on:
            col_h, col_a = (
                ('home_corners', 'away_corners') if 'künc' in label else
                ('home_shots', 'away_shots') if 'zərbə' in label and 'dəqiq' not in label else
                ('home_target', 'away_target')
            )
            conds.append((label, (lambda c1, c2, mode_, thr: lambda d: _atleast(d, c1, c2, mode_, thr))(col_h, col_a, mode, threshold)))
    return conds


def side_pass_vec(df):
    """Hər keçmiş oyun üçün iki cavab: ev sahibi klub baxışından və qonaq klub baxışından bütün seçilmiş şərtlər ödənirmi?
    Məlumat çatmırsa ödənmir sayılır."""
    ok = _num(df, 'ft_home').notna() & _num(df, 'ft_away').notna()
    ph, pa = ok.copy(), ok.copy()
    for _, fn in active_conditions():
        p_h, p_a, has = fn(df)
        ph = ph & p_h.fillna(False) & has
        pa = pa & p_a.fillna(False) & has
    return ph, pa


def match_pass_vec(df):
    """Oyunun özü hər iki klub baxışından şərtləri ödəyirmi (geriyə testdə 'tutdu' sayılması üçün)."""
    ph, pa = side_pass_vec(df)
    return ph & pa


def has_data_vec(df):
    """Seçilmiş şərtləri yoxlamaq üçün lazımi məlumat (hesab, 1-ci hissə, künc, zərbə) var?"""
    ok = _num(df, 'ft_home').notna() & _num(df, 'ft_away').notna()
    for _, fn in active_conditions():
        ok = ok & fn(df)[2]
    return ok


def conditions_contradict():
    """Seçilmiş filtrlər heç bir mümkün hesab/statistika ilə (heç bir klub baxışından) eyni anda ödənə bilməzsə True."""
    rows = [(hg, ag, a, b) for hg in range(8) for ag in range(8) for a in range(hg + 1) for b in range(ag + 1)]
    g = pd.DataFrame(rows, columns=['ft_home', 'ft_away', 'ht_home', 'ht_away'])
    g['home_corners'] = g['away_corners'] = g['home_shots'] = g['away_shots'] = g['home_target'] = g['away_target'] = 99
    ph, pa = side_pass_vec(g)
    return not bool((ph | pa).any())


def backtest_qualified(R, n):
    """R: nəticələr (sütunlar: date, home_k, away_k, flag_h, flag_a). Hər oyun üçün: oyundan əvvəl hər iki komandanın son n oyununun HAMISI flag=True idi?
    (Əsas analizdəki team_last məntiqi ilə eyni, lakin hamısı bir dəfəyə hesablanır.)"""
    R = R.reset_index(drop=True)
    L = pd.concat([
        pd.DataFrame({'rid': R.index, 'team': R['home_k'], 'date': R['date'], 'flag': R['flag_h'].astype(int), 'side': 'h'}),
        pd.DataFrame({'rid': R.index, 'team': R['away_k'], 'date': R['date'], 'flag': R['flag_a'].astype(int), 'side': 'a'}),
    ], ignore_index=True).sort_values(['team', 'date', 'rid'], kind='stable').reset_index(drop=True)
    g = L.groupby('team')
    cs = g['flag'].cumsum()
    prev = cs.groupby(L['team']).shift(1).fillna(0)
    old = cs.groupby(L['team']).shift(n + 1).fillna(0)
    L['ok'] = (g.cumcount() >= n) & ((prev - old) == n)
    okh = L[L['side'] == 'h'].set_index('rid')['ok'].reindex(R.index).fillna(False)
    oka = L[L['side'] == 'a'].set_index('rid')['ok'].reindex(R.index).fillna(False)
    return (okh & oka).values


@st.cache_resource(show_spinner=False)
def _team_index_cached(_res, token):
    n = len(_res)
    teams = np.concatenate([_res['home_k'].values, _res['away_k'].values])
    dates = np.concatenate([_res['date'].values, _res['date'].values])
    pos = np.concatenate([np.arange(n), np.arange(n)])
    order = np.lexsort((pos, dates, teams))
    teams, dates, pos = teams[order], dates[order], pos[order]
    uniq, start = np.unique(teams, return_index=True)
    end = np.append(start[1:], len(teams))
    return {t: (dates[a:b], pos[a:b]) for t, a, b in zip(uniq, start, end)}


def build_team_index(res):
    """Hər komanda üçün oyun tarixləri (sıralı) və results-dakı mövqelər — keşlənir."""
    return _team_index_cached(res, (len(res), str(res['date'].max())))


def team_last_pos(idx, team_k, date, n):
    """Komandanın `date`-dən əvvəlki son n oyununun mövqeləri (yeni → köhnə). Çatmırsa None."""
    item = idx.get(team_k)
    if item is None:
        return None
    dates, pos = item
    i = int(np.searchsorted(dates, date.to_datetime64(), side='left'))
    if i < n:
        return None
    return pos[i - n:i][::-1]

run_clicked = st.button('🔎 Oyunları analiz et', type='primary', key='analyze_button')

# Düymə sabit CSS mövqeyində qalır. Drag JS silinib ki, klik hadisəsini bloklamasın.
auto_run = st.session_state.pop('auto_run', False)   # ◀ ▶ düymələri sonrası analiz avtomatik işləyir
if run_clicked or (auto_run and criteria_selected):
    if date_from > date_to:
        st.error('Başlanğıc tarixi son tarixdən böyük ola bilməz.')
        st.stop()
    if not criteria_selected:
        st.warning('Zəhmət olmasa ən azı bir filtr seç.')
        st.stop()
    if conditions_contradict():
        st.warning('Seçilmiş filtrlər bir-birinə ziddir (məsələn "2.5 üst" və "2.5 alt"), heç bir oyun uyğun gəlməyəcək. Filtrləri dəyiş.')
        st.stop()
    st.session_state['_ran'] = True
    save_filters()
    today = baku_today()
    results['_pass_h'], results['_pass_a'] = side_pass_vec(results)   # keçmiş oyunların hər biri filtrə uyğundurmu (bir dəfə hesablanır)
    target_cols = ['date', 'time', 'home', 'away', 'league', 'home_k', 'away_k', 'src']
    fixture_targets = fixtures[
        (fixtures['date'].dt.date >= date_from) &
        (fixtures['date'].dt.date <= date_to) &
        (fixtures['date'].dt.date >= today)
    ].copy()
    result_targets = results[
        (results['date'].dt.date >= date_from) &
        (results['date'].dt.date <= date_to) &
        (results['date'].dt.date < today)
    ].copy()
    if not sel_leagues:
        st.warning('Heç bir liqa seçilməyib. "Liqalar" bölməsindən ən azı bir liqa seç.')
        st.stop()
    if len(sel_leagues) < len(league_options):
        fixture_targets = fixture_targets[fixture_targets['league'].isin(sel_leagues)]
        result_targets = result_targets[result_targets['league'].isin(sel_leagues)]
    for frame in (fixture_targets, result_targets):
        for col in target_cols:
            if col not in frame.columns:
                frame[col] = '' if col in ('time', 'league') else pd.NaT if col == 'date' else ''
    day_games = pd.concat([result_targets[target_cols], fixture_targets[target_cols]], ignore_index=True)
    day_games = day_games.dropna(subset=['date', 'home', 'away']).copy()
    day_games['_source_priority'] = (day_games['date'].dt.date >= today).astype(int)
    day_games = day_games.sort_values('_source_priority', ascending=False)
    day_games = day_games.drop_duplicates(subset=['date', 'home_k', 'away_k']).drop(columns=['_source_priority']).copy()
    if day_games.empty:
        st.warning('Bu tarix aralığında bazada oyun tapılmadı. Məlumatı yeniləməyi yoxla.')
        st.stop()

    import time as _t
    _t0 = _t.perf_counter()
    passed, skipped = [], 0
    progress = st.progress(0)
    n_int = int(n_games)
    team_idx = build_team_index(results)
    _t1 = _t.perf_counter()
    hk_arr, ph_arr, pa_arr = results['home_k'].values, results['_pass_h'].values, results['_pass_a'].values
    total_games = len(day_games)
    step = max(1, total_games // 12)  # progress UI yeniləmələrini azaldıb interfeysi sürətləndir
    for i, game in enumerate(day_games.itertuples(index=False)):
        league, date, home, away = game.league, game.date, game.home, game.away
        hp = team_last_pos(team_idx, game.home_k, date, n_int)
        ap = team_last_pos(team_idx, game.away_k, date, n_int)
        if hp is None or ap is None:
            skipped += 1
        elif (np.where(hk_arr[hp] == game.home_k, ph_arr[hp], pa_arr[hp]).all()
              and np.where(hk_arr[ap] == game.away_k, ph_arr[ap], pa_arr[ap]).all()):
            hhist, ahist = results.iloc[hp], results.iloc[ap]
            passed.append({
                'Tarix': date.strftime('%Y-%m-%d'),
                '_hk': game.home_k,
                '_ak': game.away_k,
                'Saat': str(getattr(game, 'time', '')),
                'Çempionat': league,
                'Mənbə': src_label(getattr(game, 'src', '')),
                'Ev sahibi': home,
                'Qonaq': away,
                'Son oyun sayı': n_int,
                'Ev sahibinin əvvəlki nəticələri': hhist.to_dict('records'),
                'Qonağın əvvəlki nəticələri': ahist.to_dict('records')
            })
        if i % step == 0:
            progress.progress((i + 1) / total_games)
    progress.empty()
    _t2 = _t.perf_counter()
    if passed:
        res_idx = {}
        lo, hi = pd.Timestamp(date_from) - pd.Timedelta(days=1), pd.Timestamp(date_to) + pd.Timedelta(days=1)
        rr = results.loc[(results['date'] >= lo) & (results['date'] <= hi), ['home_k', 'away_k', 'date', 'ft_home', 'ft_away']]
        for hk_, ak_, d_, fh_, fa_ in rr.itertuples(index=False):
            res_idx.setdefault((hk_, ak_), []).append((d_, int(fh_), int(fa_)))
        live_rows = []
        if live_scores_on and any(pd.to_datetime(it['Tarix']).date() >= today - timedelta(days=1) for it in passed):
            with st.spinner('Canlı hesablar yoxlanılır...'):
                try:
                    live_rows = fetch_live_scores()
                except Exception:
                    live_rows = []
        for it in passed:
            it['Hesab'], it['Status'] = lookup_score(it['_hk'], it['_ak'], pd.to_datetime(it['Tarix']), res_idx, live_rows)
    _t3 = _t.perf_counter()
    st.caption(f'⏱ indeks {_t1-_t0:.1f}s · yoxlama {_t2-_t1:.1f}s · hesab/canlı {_t3-_t2:.1f}s · oyun: {len(day_games)}, uyğun: {len(passed)}')
    st.markdown(
        f'<div class="stats">'
        f'<div class="stat"><div class="n">{len(day_games)}</div><div class="l">Yoxlanılan oyun</div></div>'
        f'<div class="stat good"><div class="n">{len(passed)}</div><div class="l">Uyğun oyun</div></div>'
        f'<div class="stat"><div class="n">{skipped}</div><div class="l">Tarixçəsi çatmayan oyun</div></div>'
        f'</div>',
        unsafe_allow_html=True
    )
    st.caption('Komandaların əvvəlki oyunları liqa və kubok daxil olmaqla bütün mövcud nəticələrdən, hədəf oyunun tarixindən əvvəl axtarılır. Saatlar Bakı vaxtı ilədir.')

    if passed:
        out = pd.DataFrame(passed)
        st.subheader('⚽ Uyğun oyunlar')
        st.caption('Hər oyunun üzərinə basaraq açın. Komandaların əvvəlki oyunları yan-yana göstərilir.')
        for idx, item in enumerate(passed, start=1):
            time_text = str(item.get('Saat', '')).strip()
            if time_text.lower() in ('nan', 'nat', 'none', ''):
                time_text = 'Saat məlum deyil'
            league_text = str(item.get('Çempionat', '')).replace('_', ' ').replace('-', ' ').strip()
            title = f"⚽ {item['Tarix']} · {time_text} · {item['Ev sahibi']} — {item['Qonaq']}"
            _live = str(item.get('Status', '')).startswith('Canlı')
            if item.get('Hesab'):
                title += f" · {'🔴' if _live else '✅'} {item['Hesab']}"
            with st.expander(title, expanded=False):
                if item.get('Hesab'):
                    st.markdown(f"**{'🔴' if _live else '✅'} {item['Hesab']}** · {item['Status']}")
                st.caption(f"{league_text} · Hər komandanın son {item['Son oyun sayı']} oyunu · Mənbə: {item['Mənbə'] or 'məlum deyil'}")
                left, right = st.columns(2)
                for col, team_name, history_key in [
                    (left, item['Ev sahibi'], 'Ev sahibinin əvvəlki nəticələri'),
                    (right, item['Qonaq'], 'Qonağın əvvəlki nəticələri')
                ]:
                    with col:
                        st.markdown(f'<div class="team-head">🏟️ {team_name}</div>', unsafe_allow_html=True)
                        history = item[history_key]
                        for old_match in history:
                            old_date = pd.to_datetime(old_match.get('date'), errors='coerce')
                            date_text = old_date.strftime('%d.%m.%Y') if pd.notna(old_date) else 'Tarix məlum deyil'
                            old_time = str(old_match.get('time', '')).strip()
                            if old_time.lower() in ('nan', 'nat', 'none', ''):
                                old_time = ''
                            hg, ag = old_match.get('ft_home'), old_match.get('ft_away')
                            score = f'{int(hg)}–{int(ag)}' if pd.notna(hg) and pd.notna(ag) else 'Hesab yoxdur'
                            old_home, old_away = str(old_match.get('home', '')), str(old_match.get('away', ''))
                            chips = ''
                            hth, hta = old_match.get('ht_home'), old_match.get('ht_away')
                            if pd.notna(hth) and pd.notna(hta):
                                chips += f'<span class="chip h">1-ci hissə {int(hth)}–{int(hta)}</span>'
                            hcn, acn = old_match.get('home_corners'), old_match.get('away_corners')
                            if pd.notna(hcn) and pd.notna(acn):
                                chips += f'<span class="chip c">Künc {int(hcn + acn)}</span>'
                            hsh, ash = old_match.get('home_shots'), old_match.get('away_shots')
                            hst_, ast_ = old_match.get('home_target'), old_match.get('away_target')
                            if pd.notna(hsh) and pd.notna(ash):
                                chips += f'<span class="chip c">Zərbə {int(hsh + ash)}</span>'
                            if pd.notna(hst_) and pd.notna(ast_):
                                chips += f'<span class="chip c">Qapıya {int(hst_ + ast_)}</span>'
                            src_text = src_label(old_match.get('src', ''))
                            if src_text:
                                chips += f'<span class="chip s">{src_text}</span>'
                            st.markdown(
                                f'<div class="mcard">'
                                f'<div class="d">{date_text}{(" · " + old_time) if old_time else ""}</div>'
                                f'<div class="t">{old_home}</div>'
                                f'<div class="s">{score}</div>'
                                f'<div class="t">{old_away}</div>'
                                f'<div>{chips}</div></div>',
                                unsafe_allow_html=True
                            )
        out = out.drop(columns=['Ev sahibinin əvvəlki nəticələri', 'Qonağın əvvəlki nəticələri', '_hk', '_ak'])
        st.download_button('⬇️ Nəticələri CSV kimi yüklə', out.to_csv(index=False).encode('utf-8-sig'), file_name='futbol_filtri_neticeleri.csv', mime='text/csv')
    else:
        st.info('Seçilən şərtlərə uyğun oyun tapılmadı. Tarix aralığını genişləndir və ya filtrləri dəyiş.')

BT_PERIODS = [30, 60, 90, 180, 365, 730]


def _bt_summary(R, days, leagues_all, today_ts):
    """Seçilmiş dövr üçün: yoxlanılan oyunlar (E), filtrə uyğun olanlar (Q)."""
    period = (R['date'] >= today_ts - pd.Timedelta(days=int(days))) & (R['date'] < today_ts) & R['has']
    if not leagues_all:
        period &= R['league'].isin(sel_leagues)
    E = R[period]
    return E, E[E['qual']]


with st.expander('📈 Geriyə test — seçilmiş filtr keçmişdə neçə faiz tutub?', expanded=False):
    st.caption('Keçmiş oyunlara baxılır: oyundan əvvəl hər iki komandanın son N oyunu seçilmiş filtrlərin hamısına uyğun olubsa, həmin oyunun özü də eyni filtrlərə uyğun gəldimi? '
               'Nəticə filtri dəyişdikcə avtomatik yenilənir. Keçmiş faiz gələcək nəticəyə zəmanət vermir.')
    bt_days = st.select_slider('Ətraflı baxılan dövr', options=BT_PERIODS, value=180, format_func=lambda d: f'son {d} gün', key='bt_days')
    bt_on = st.toggle('Geriyə testi hesabla (ağırdır, lazım olanda qoş)', key='bt_on', value=False)
    if not bt_on:
        st.caption('Filtr seçəndə səhifə tez işləsin deyə geriyə test söndürülüb.')
    elif not criteria_selected:
        st.info('Yuxarıdan ən azı bir filtr seç, faiz burada avtomatik görünəcək.')
    elif conditions_contradict():
        st.warning('Seçilmiş filtrlər bir-birinə ziddir (məsələn "2.5 üst" və "2.5 alt").')
    elif not sel_leagues:
        st.warning('Heç bir liqa seçilməyib.')
    else:
        try:
            bt_key = (tuple(n for n, _ in active_conditions()), int(n_games), len(results), str(results['date'].max()), str(baku_today()))
            if st.session_state.get('bt_cache_key') != bt_key:
                with st.spinner('Geriyə test hesablanır...'):
                    R = results.copy().reset_index(drop=True)
                    R['flag_h'], R['flag_a'] = side_pass_vec(R)
                    R['flag'] = R['flag_h'] & R['flag_a']
                    R['has'] = has_data_vec(R)
                    R['qual'] = backtest_qualified(R, int(n_games))
                    st.session_state['bt_cache'], st.session_state['bt_cache_key'] = R, bt_key
            R = st.session_state['bt_cache']
            bt_today = pd.Timestamp(baku_today())
            all_leagues = len(sel_leagues) >= len(league_options)

            # Bütün dövrlər üzrə qısa cədvəl — seçilmiş dövrdə uyğun oyun olmasa belə faiz görünsün
            prow = []
            for d in BT_PERIODS:
                E_, Q_ = _bt_summary(R, d, all_leagues, bt_today)
                prow.append({'Dövr': f'son {d} gün', 'Yoxlanılan oyun': len(E_), 'Filtrə uyğun': len(Q_),
                             'Tutdu': int(Q_['flag'].sum()),
                             'Faiz': f"{Q_['flag'].mean() * 100:.1f}%" if len(Q_) else '—',
                             'Baza faizi': f"{E_['flag'].mean() * 100:.1f}%" if len(E_) else '—'})
            st.markdown('**Dövrlər üzrə nəticə**')
            st.dataframe(pd.DataFrame(prow), hide_index=True, use_container_width=True)

            E, Q = _bt_summary(R, bt_days, all_leagues, bt_today)
            if E.empty:
                st.info(f'Son {int(bt_days)} gündə seçilmiş liqalarda yoxlanıla bilən oyun yoxdur (lazımi statistika çatmır və ya oyun yoxdur).')
            elif Q.empty:
                st.info(f'Son {int(bt_days)} gündə hər iki komandanın son {int(n_games)} oyunu bütün şərtlərə uyğun gələn oyun yoxdur. '
                        f'Yoxlanılan oyun: {len(E)}, baza faizi: {E["flag"].mean() * 100:.1f}%. Daha uzun dövr seç, "son neçə oyun" sayını azalt və ya filtrləri yüngülləşdir.')
            else:
                hits = int(Q['flag'].sum())
                base = float(E['flag'].mean())
                m1, m2, m3, m4 = st.columns(4)
                m1.metric('Filtrə uyğun oyun', len(Q))
                m2.metric('Özü də uyğun gəldi', hits)
                m3.metric('Keçmiş faiz', f'{hits / len(Q) * 100:.1f}%')
                m4.metric('Baza faizi', f'{base * 100:.1f}%', help='Tarixçəyə baxmadan bütün oyunlarda eyni şərtlərin ödənmə faizi')
                lift = hits / len(Q) - base
                st.caption(f'Yoxlanılan oyun: {len(E)} · filtr baza faizinə nisbətən {lift * 100:+.1f} faiz bəndi fərq yaradıb.'
                           + (' ⚠️ Nümunə kiçikdir (30-dan az oyun), nəticəyə etibar etmə.' if len(Q) < 30 else ''))
                conds = active_conditions()
                if len(conds) > 1:
                    rows = [{'Şərt': name, 'Faiz': round(float((lambda r: (r[0] & r[1] & r[2]).mean())(fn(Q)) * 100), 1)} for name, fn in conds]
                    st.markdown('**Şərtlər üzrə (uyğun oyunlarda ayrı-ayrılıqda)**')
                    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
                by = Q.groupby('league').agg(Oyun=('flag', 'size'), Uyğun=('flag', 'sum')).reset_index()
                by['Faiz'] = (by['Uyğun'] / by['Oyun'] * 100).round(1)
                by = by.rename(columns={'league': 'Liqa'}).sort_values(['Oyun', 'Faiz'], ascending=False).head(20)
                st.markdown('**Liqa üzrə (ən çox oyun olan 20)**')
                st.dataframe(by, hide_index=True, use_container_width=True)
        except Exception as e:
            st.error(f'Geriyə test hesablanmadı: {e}')

with st.expander('Məlumat bazası haqqında'):
    st.write(f'Çempionat qovluqları: {len(list(DATA_DIR.iterdir())) if DATA_DIR.exists() else 0}. Qarşıdakı oyun sətri: {len(fixtures)}. Tarixi nəticə sətri: {len(results)}. Siyahıdakı liqa sayı: {len(league_options)}.')
    st.write('Mənbələr: Open Matchday — https://github.com/oladeeayo/open-matchday, football-data.co.uk (əsas və əlavə liqalar), openfootball (https://github.com/openfootball/football.json), international_results (https://github.com/martj42/international_results, milli komandalar) ESPN (qitə kubokları, daxili kuboklar və onlarla liqa) və SofaScore (qeyri-rəsmi sınaq mənbəyi; əsas mənbə deyil). SofaScore-dan hazırda oyun təqvimi və yekun hesab/yarımvaxt hesabı götürülür; künc və kart statistikası zəmanətli deyil. Eyni oyun bir neçə mənbədə varsa statistika üçün əvvəlcə football-data.co.uk, sonra Open Matchday, sonra openfootball, sonra ESPN götürülür. Künc, zərbə və qapıya dəqiq zərbə statistikası football-data.co.uk əsas liqalarında, Open Matchday-də və ESPN-in yüklədiyi oyunlarda var. Statistikası olmayan oyunlar müvafiq statistik filtrdə uyğun sayılmır.')
    st.write(f'Əlavə liqa faylları (football-data.co.uk/new): {len(list(FDX_DIR.glob("*.csv"))) if FDX_DIR.exists() else 0}. openfootball faylları: {len(list(OF_DIR.glob("*.json"))) if OF_DIR.exists() else 0}.')
    if FD_DIR.exists() and any(FD_DIR.glob('*.csv')):
        st.write(f'football-data.co.uk faylları: {len(list(FD_DIR.glob("*.csv")))}.')
    else:
        st.write('football-data.co.uk hələ yüklənməyib — sol paneldən "Məlumatı yenilə" düyməsinə bas.')
    if (ESPN_DIR / 'results.csv').exists():
        st.write('ESPN fayllarından oxunan nəticə sayı: ' + str(len(read_csv_safe(ESPN_DIR / 'results.csv'))) + '.')
    else:
        st.write('ESPN hələ yüklənməyib — sol paneldən "Məlumatı yenilə" düyməsinə bas.')
    if fd_only_teams:
        st.write(f'Yalnız football-data.co.uk-də tapılan komandalar: {len(fd_only_teams)}. Əgər bunların arasında Open Matchday-də başqa cür yazılan komanda varsa, app.py-dakı ALIASES siyahısına əlavə et.')
        st.code('\n'.join(fd_only_teams))
