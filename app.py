from pathlib import Path
import functools, zipfile, io, re, difflib, unicodedata, requests, shutil, tempfile, json
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
    'cze.1': 'Czech First League',
    'rou.1': 'Romania Liga I',
    'irl.1': 'Ireland Premier Division', 'fin.1': 'Finland Veikkausliiga',     'isr.1': 'Israel Premier League',
    # Amerika
    'usa.1': 'USA MLS', 'mex.1': 'Mexico Liga MX', 'bra.1': 'Brazil Serie A', 'bra.2': 'Brazil Serie B',
    'arg.1': 'Argentina Primera Division', 'col.1': 'Colombia Primera A', 'chi.1': 'Chile Primera Division',
    'uru.1': 'Uruguay Primera Division', 'ecu.1': 'Ecuador Serie A', 'per.1': 'Peru Liga 1', 'par.1': 'Paraguay Primera Division',
    # Asiya, Okeaniya, Afrika
    'jpn.1': 'Japan J1 League', 'chn.1': 'China Super League',
    'aus.1': 'Australia A-League', 'ind.1': 'India Super League', 'ksa.1': 'Saudi Pro League',
        'rsa.1': 'South Africa Premiership',
    # Milli komandalar
    'fifa.friendly': 'International Friendly', 'uefa.nations': 'UEFA Nations League',
    'uefa.euroq': 'UEFA Euro Qualifying', 'concacaf.nations.league': 'CONCACAF Nations League',
}
ESPN_STATS_PER_REFRESH = 1000   # hər yeniləmədə neçə oyun üçün künc/kart statistikası yüklənsin (qalanı növbəti yeniləmələrdə)
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


@functools.lru_cache(maxsize=None)
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
.block-container { padding-top: .8rem; padding-bottom: 6rem; max-width: 1180px; }
.block-container [data-testid="stVerticalBlock"] { gap: .55rem; }
div[data-testid="stExpander"] summary { padding: .35rem .75rem; }
div[data-testid="stCaptionContainer"], .stCaption { line-height: 1.3; }
div[data-testid="stVerticalBlockBorderWrapper"] { padding-top: .1rem; }
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
/* Kupon düyməsi analiz düyməsinin solunda üzən vəziyyətdə qalır. */
div.st-key-coupon_float_button {
  position: fixed !important; left: calc(50% - 205px) !important; right: auto !important;
  bottom: 22px !important; z-index: 100000 !important; width: auto !important;
  margin: 0 !important; padding: 0 !important; filter: drop-shadow(0 6px 18px rgba(0,0,0,.22));
}
div.st-key-coupon_float_button button { min-height: 52px !important; border-radius: 15px !important; white-space: nowrap !important; }
div.st-key-coupon_float_panel {
  position: fixed !important; left: 12px !important; bottom: 84px !important;
  z-index: 100001 !important; width: min(420px, calc(100vw - 24px)) !important;
  max-height: 65vh !important; overflow-y: auto !important;
  padding: 12px !important; border: 1px solid rgba(128,128,128,.4) !important;
  border-radius: 16px !important; background: var(--background-color, white) !important;
  box-shadow: 0 10px 35px rgba(0,0,0,.28) !important;
}
@media (max-width: 600px) {
  div.st-key-analyze_button { left: auto !important; right: 12px !important; bottom: 12px !important; transform: none !important; max-width: calc(100vw - 150px) !important; }
  div.st-key-analyze_button button { min-width: 0 !important; width: 100% !important; }
  div.st-key-coupon_float_button { left: 12px !important; bottom: 12px !important; }
  div.st-key-coupon_float_button button { min-width: 0 !important; max-width: 135px !important; font-size: 12px !important; }
  div.st-key-coupon_float_panel { left: 8px !important; bottom: 74px !important; width: calc(100vw - 16px) !important; max-height: 65vh !important; }
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


SRC_LABELS = {'FD': 'football-data.co.uk', 'OM': 'Open Matchday', 'ES': 'ESPN', 'OF': 'openfootball', 'IR': 'international_results'}


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


def _map_keys(series):
    """team_key-i hər sətir üçün yox, yalnız unikal adlar üçün çağırır (dəfələrlə sürətlidir)."""
    codes, uniq = pd.factorize(series)
    keys = np.array([team_key(x) for x in uniq] + [team_key(float('nan'))], dtype=object)   # -1 (boş ad) sonuncu elementə düşür
    return pd.Series(keys[codes], index=series.index)


def add_keys(df, src):
    if df.empty:
        return df
    df = df.copy()
    df['src'] = src
    df['date'] = pd.to_datetime(df.get('date'), errors='coerce').dt.normalize()
    df['home_k'] = _map_keys(df['home'])
    df['away_k'] = _map_keys(df['away'])
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


@functools.lru_cache(maxsize=500000)
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
    """Eyni oyun fərqli ad yazılışları ilə təkrar qalıbsa birləşdirir (OM / openfootball / ESPN arasında).
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


@st.cache_resource(show_spinner='⏳ Məlumat bazası hazırlanır (yenidən başladıqdan sonra ilk açılışda bir az çəkə bilər)...')
def load_data():
    import time as _tm
    _t0 = _tm.perf_counter()
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
    print(f'load_data hazır: {_tm.perf_counter() - _t0:.1f} san, nəticə={len(res)}, cədvəl={len(fix)}', flush=True)
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
    ok, failed = 0, []
    jobs = [(season, code) for season in fd_seasons() for code in FD_LEAGUES]

    def one(job):
        season, code = job
        try:
            r = requests.get(f'{FD_BASE}/mmz4281/{season}/{code}.csv', timeout=15, headers={'User-Agent': 'FutbolFiltri/1.0'})
            if r.status_code == 200 and len(r.content) > 200:
                (FD_DIR / f'{season}_{code}.csv').write_bytes(r.content)
                return f'{season}/{code}', True
        except requests.RequestException:
            pass
        return f'{season}/{code}', False

    with ThreadPoolExecutor(max_workers=10) as ex:
        for name, good in ex.map(one, jobs):
            if good:
                ok += 1
            else:
                failed.append(name)
    try:
        r = requests.get(f'{FD_BASE}/fixtures.csv', timeout=15, headers={'User-Agent': 'FutbolFiltri/1.0'})
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
        r = requests.get(f'{ESPN_BASE}/{slug}/summary', params={'event': event_id}, timeout=15,
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
            with ThreadPoolExecutor(max_workers=16) as ex:
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
        r = requests.get(f'{ESPN_BASE}/{slug}/scoreboard', params={'dates': rng, 'limit': 300}, timeout=5,
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


@st.cache_data(ttl=180, show_spinner=False)
def fetch_live_scores():
    # Ümumi vaxt limiti 8 san: ESPN yavaş olsa belə səhifə donmur, gələnlərlə kifayətlənir
    from concurrent.futures import as_completed, TimeoutError as _FTimeout
    slugs = list(dict.fromkeys(list(ESPN_LEAGUES) + LIVE_EXTRA_SLUGS))
    ex = ThreadPoolExecutor(max_workers=24)
    futs = [ex.submit(_live_one, sl) for sl in slugs]
    rows = []
    try:
        for f in as_completed(futs, timeout=8):
            try:
                rows.extend(f.result())
            except Exception:
                pass
    except _FTimeout:
        pass
    ex.shutdown(wait=False, cancel_futures=True)
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
_PKEYS = {'_ran', 'btts', 'btts_no', 'under25', 'ht05_under', 'ht15_under', 'ht_draw', 'n_games'}
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
        # Əvvəlki analiz olması yeni açılışda avtomatik analiz başlatmır.
    except Exception:
        pass
    st.session_state['_qp_restored'] = True

# ---- Məlumat bazasının yenilənməsi: ARXA PLANDA işləyir, səhifə donmur ----
import threading as _rf_threading
import time as _rf_time


LAST_REFRESH_FILE = ROOT / 'last_refresh.txt'
AUTO_REFRESH_HOUR = 7   # Bakı vaxtı ilə hər səhər


def _read_last_refresh():
    try:
        return pd.Timestamp(LAST_REFRESH_FILE.read_text(encoding='utf-8').strip())
    except Exception:
        return None


@st.cache_resource
def _refresh_state():
    return {'running': False, 'started': 0.0, 'status': {}, 'msgs': None}


def _j_om():
    refresh_data()
    return [('success', 'Open Matchday yeniləndi.')]


def _j_fd():
    ok, failed = refresh_fd()
    m = [('success', f'football-data.co.uk: {ok} fayl yükləndi.')]
    if failed:
        m.append(('warning', f'Yüklənməyən fayllar ({len(failed)}): ' + ', '.join(failed[:15])))
    return m


def _j_fdx():
    ok, failed = refresh_fdx()
    m = [('success', f'football-data.co.uk (əlavə liqalar): {ok} fayl yükləndi.')]
    if failed:
        m.append(('warning', 'Yüklənməyən əlavə liqalar: ' + ', '.join(failed)))
    return m


def _j_ir():
    refresh_ir()
    return [('success', 'international_results (milli komandalar) yeniləndi.')]


def _j_of():
    ok, bad = refresh_of()
    return [('success', f'openfootball: {ok} fayl yükləndi.' + (f' Xətalı: {bad}.' if bad else ''))]


def _j_es():
    n_res, n_fix, espn_failed, st_done, st_left = refresh_espn()
    m = [('success', f'ESPN: {n_res} nəticə, {n_fix} qarşıdakı oyun. Künc/kart statistikası: {st_done} oyun yükləndi'
          + (f', {st_left} oyun növbəti yeniləmədə davam edəcək.' if st_left > 0 else '.'))]
    if espn_failed:
        m.append(('warning', f'ESPN-də yüklənməyən yarışlar ({len(espn_failed)}): ' + ', '.join(espn_failed)))
    return m


_REFRESH_JOBS = [('Open Matchday', _j_om), ('football-data.co.uk', _j_fd), ('football-data.co.uk (əlavə liqalar)', _j_fdx),
                 ('international_results', _j_ir), ('openfootball', _j_of), ('ESPN', _j_es)]


def _refresh_start(state):
    state['running'], state['started'], state['msgs'] = True, _rf_time.time(), None
    state['status'] = {nm: 'gözləyir' for nm, _ in _REFRESH_JOBS}
    results_ = {}

    def worker(nm, fn):
        state['status'][nm] = 'yüklənir…'
        try:
            results_[nm] = fn()
            state['status'][nm] = 'hazırdır ✓'
        except Exception as e:
            results_[nm] = [('error', f'{nm} yenilənmədi: {e}')]
            state['status'][nm] = 'xəta ✗'

    def main():
        try:
            ts = [_rf_threading.Thread(target=worker, args=(nm, fn), daemon=True) for nm, fn in _REFRESH_JOBS]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
            msgs_ = []
            for nm, _ in _REFRESH_JOBS:
                msgs_.extend(results_.get(nm, []))
            state['msgs'] = msgs_
        finally:
            state['running'] = False
            try:
                LAST_REFRESH_FILE.write_text(pd.Timestamp.now(tz='Asia/Baku').isoformat(), encoding='utf-8')
            except Exception:
                pass

    _rf_threading.Thread(target=main, daemon=True).start()


def _refresh_panel():
    state = _refresh_state()
    if state['running'] and _rf_time.time() - state['started'] > 900:   # 15 dəqiqədən çox donubsa — təzədən başlamağa icazə ver
        state['running'] = False
    if state['running']:
        st.info('⏳ Yenilənir… səhifəni bağlasan da yükləmə serverdə davam edir.')
        for nm, stt in list(state['status'].items()):
            st.write(f'• {nm}: {stt}')
        st.caption(f'Keçən vaxt: {int(_rf_time.time() - state["started"])} san.')
    elif state['msgs'] is not None:
        st.rerun()   # bitdi — məlumatı yenidən yüklə və nəticə mesajlarını göstər
    else:
        if st.button('🔄 Məlumatı yenilə', use_container_width=True, key='refresh_btn'):
            _refresh_start(state)
            st.rerun()


@st.cache_resource
def _scheduler_start(_state):
    """Hər gün Bakı vaxtı ilə 07:00-da avtomatik yeniləmə. Tətbiq yatıbsa, oyananda buraxılmış yeniləməni dərhal edir."""
    def loop():
        while True:
            try:
                now = pd.Timestamp.now(tz='Asia/Baku')
                due = now.normalize() + pd.Timedelta(hours=AUTO_REFRESH_HOUR)
                last = _read_last_refresh()
                if now >= due and (last is None or last < due) and not _state['running']:
                    _refresh_start(_state)
            except Exception:
                pass
            _rf_time.sleep(60)
    _rf_threading.Thread(target=loop, daemon=True).start()
    return True


_scheduler_start(_refresh_state())
_rs0 = _refresh_state()
with st.container(border=True):
    st.markdown('**📚 Məlumat bazası**')
    if _rs0['msgs'] is not None and not _rs0['running']:
        st.session_state['refresh_msgs'] = _rs0['msgs']
        _rs0['msgs'] = None
    if 'refresh_msgs' in st.session_state:
        for kind, text in st.session_state.pop('refresh_msgs'):
            getattr(st, kind)(text)
    if hasattr(st, 'fragment'):
        st.fragment(run_every=(2 if _rs0['running'] else None))(_refresh_panel)()
    else:
        _refresh_panel()
        if _rs0['running']:
            if st.button('↻ Statusa bax', use_container_width=True):
                st.rerun()
    _lr = _read_last_refresh()
    st.caption(f'🕖 Avtomatik yeniləmə: hər gün {AUTO_REFRESH_HOUR:02d}:00 (Bakı). Sonuncu yeniləmə: '
               + (_lr.strftime('%Y-%m-%d %H:%M') if _lr is not None else 'məlum deyil'))
    st.caption('Yeniləmə internet tələb edir. Əvvəl yüklənmiş məlumatlar internet olmadan da analiz edilə bilər.')

fixtures, results, fd_only_teams = load_data()
if fixtures.empty:
    st.error('Oyun cədvəlləri tapılmadı. ZIP-i tam çıxartdığını yoxla və ya yuxarıdakı "Məlumatı yenilə" düyməsindən yenilə.')
    st.stop()

# ---- Adla saxlanılan filtr dəstləri ----
NAMED_FILTERS_FILE = ROOT / 'named_filters.json'
_PRESET_PREFIXES = ('match_', 'club_', 'min_', 'on_', 'mode_', 'corners_', 'shots_', 'target_')
_PRESET_EXPLICIT = {'btts', 'btts_no', 'under25', 'ht05_under', 'ht15_under', 'ht_draw',
                    'match_goal_15', 'match_goal_25', 'match_goal_35', 'match_goal_45', 'club_goal_05',
                    'club_goal_15', 'club_goal_25', 'match_ht05', 'match_ht15',
                    'club_ht05', 'club_ht15', 'n_games', 'd_from', 'd_to'}

def _read_named_filters():
    try:
        data = json.loads(NAMED_FILTERS_FILE.read_text(encoding='utf-8')) if NAMED_FILTERS_FILE.exists() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _apply_named_filter(name):
    presets = _read_named_filters()
    payload = presets.get(name, {})
    for key, value in payload.items():
        if key.startswith('_meta_'):
            continue
        if key in ('d_from', 'd_to'):
            try:
                st.session_state[key] = datetime.strptime(value, '%Y-%m-%d').date()
            except Exception:
                pass
        elif key == 'lg_sel':
            st.session_state[key] = set(value or [])
        else:
            st.session_state[key] = value

# Yadda saxlanılan filtrlər ana səhifədə siyahı kimi görünür.
_named_filters = _read_named_filters()
_SHOW_SAVED_FILTERS = True
if _SHOW_SAVED_FILTERS:
    with st.container(border=True):
        st.markdown('**📌 Yadda saxlanılan filtrlər**')
        if not _named_filters:
            st.caption('Hələ saxlanmış filtr yoxdur. Analiz etdikdən sonra "💾 Bu filtri yadda saxla" düyməsi ilə saxlaya bilərsən.')
        for _idx, (_preset_name, _preset_data) in enumerate(list(_named_filters.items())):
            _preset_data = _preset_data if isinstance(_preset_data, dict) else {}
            _meta_filters = _preset_data.get('_meta_filters', [])
            _meta_n = _preset_data.get('_meta_n_games', None)
            _meta_hits = _preset_data.get('_meta_hits', None)
            _meta_dates = _preset_data.get('_meta_dates', '')
            _summary = ' + '.join(_meta_filters) if _meta_filters else 'Əvvəlki versiyada saxlanmış filtr'
            _count_text = (f"Son {_meta_n} oyun" if _meta_n else 'Oyun sayı qeyd edilməyib')
            if _meta_hits is not None:
                _count_text += f' · {_meta_hits} uyğun oyun'
            if _meta_dates:
                _count_text += f' · {_meta_dates}'
            _r1, _r2 = st.columns([5, 1])
            _r1.markdown(f'**{_preset_name}**')
            _r1.caption(f'{_count_text}  |  {_summary}')
            if _r2.button('📂 Yüklə', key=f'load_named_filter_{_idx}', use_container_width=True):
                _apply_named_filter(_preset_name)
                st.session_state['_loaded_preset_msg'] = f'“{_preset_name}” filtri tətbiq edildi. Analizi yenidən başladın.'
                st.rerun()
            if _r2.button('🗑️ Sil', key=f'delete_named_filter_{_idx}', use_container_width=True):
                _named_filters.pop(_preset_name, None)
                try:
                    NAMED_FILTERS_FILE.write_text(json.dumps(_named_filters, ensure_ascii=False, indent=2), encoding='utf-8')
                except Exception as e:
                    st.error(f'Filtri silmək olmadı: {e}')
                st.rerun()
        _bk1, _bk2 = st.columns(2)
        if _named_filters:
            _bk1.download_button('⬇️ Filtrləri fayla yüklə (ehtiyat nüsxə)', json.dumps(_named_filters, ensure_ascii=False, indent=2).encode('utf-8'),
                                 'named_filters.json', 'application/json', key='nf_download', use_container_width=True)
        _up = _bk2.file_uploader('Filtrləri geri yüklə (named_filters.json)', type='json', key='nf_upload')
        if _up is not None and st.session_state.get('_nf_up_sig') != (_up.name, _up.size):
            try:
                _new = json.loads(_up.getvalue().decode('utf-8'))
                if not isinstance(_new, dict):
                    raise ValueError('fayl düzgün formatda deyil')
                _cur = _read_named_filters()
                _cur.update(_new)
                NAMED_FILTERS_FILE.write_text(json.dumps(_cur, ensure_ascii=False, indent=2), encoding='utf-8')
                st.session_state['_nf_up_sig'] = (_up.name, _up.size)
                st.session_state['_loaded_preset_msg'] = f'{len(_new)} filtr bərpa olundu.'
                st.rerun()
            except Exception as e:
                st.error(f'Filtrləri bərpa etmək olmadı: {e}')
        st.caption('⚠️ Tətbiq yenilənəndə (GitHub-a yeni app.py yükləyəndə) server fayllarını sıfırlayır və saxlanmış filtrlər silinir. '
                   'Daimi qalması üçün "Filtrləri fayla yüklə" ilə faylı endirib GitHub-da app.py-ın yanına yüklə.')
if st.session_state.get('_loaded_preset_msg'):
    st.info(st.session_state.pop('_loaded_preset_msg'))

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
    # Tarix dəyişəndə analiz avtomatik başlamır; istifadəçi düyməni özü basır.


def _shift_one_date(key, days):
    # Başlanğıc və son tarixi ayrıca əvvəlki/növbəti günə keçir.
    st.session_state[key] = st.session_state[key] + timedelta(days=days)
    # Tək tarixi dəyişmək analiz başlatmır.


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

    @st.cache_data(show_spinner=False, max_entries=64)
    def _games_per_league(_fx, _rs, d_from, d_to, d_today, sig):
        def _in(df, past):
            if df.empty:
                return df
            d = df['date'].dt.normalize()
            keep = (d >= d_from) & (d <= d_to) & ((d < d_today) if past else (d >= d_today))
            return df[keep]
        rng = pd.concat([_in(_rs, True), _in(_fx, False)], ignore_index=True)
        if rng.empty:
            return {}
        return rng.drop_duplicates(subset=['date', 'home_k', 'away_k'])['league'].value_counts().to_dict()

    games_per_league = _games_per_league(fixtures, results, d_from, d_to, d_today, (len(fixtures), len(results), str(results['date'].max())))
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
        match_goal_15 = st.checkbox('Matç 1.5 üst', key='match_goal_15')
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
        st.caption("Ev / səfər üzrə — klubun yalnız evdəki və ya yalnız səfərdəki son oyunlarına baxılır")
        club_ht05_home = st.checkbox('İlk hissə 0.5 üst (ev klubu evdə)', key='club_ht05_home',
                                     help='Ev sahibi klubun evdəki son N oyununun hamısında klub ilk hissədə qol vurub.')
        club_ht05_away = st.checkbox('İlk hissə 0.5 üst (səfər klubu səfərdə)', key='club_ht05_away',
                                     help='Qonaq klubun səfərdəki son N oyununun hamısında klub ilk hissədə qol vurub.')
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
    st.markdown('<div class="rule">Hər komandanın seçilən son oyunlarının <b>HAMISI</b> bütün şərtlərə uyğun olmalıdır. Ev/səfər filtrlərində isə yalnız klubun evdəki (və ya səfərdəki) son oyunlarına baxılır.</div>', unsafe_allow_html=True)

criteria_selected = any([
    btts, btts_no, ht05_under, ht15_under, ht_draw, under25,
    match_goal_15, match_goal_25, match_goal_35, match_goal_45,
    club_goal_05, club_goal_15, club_goal_25,
    match_ht05, match_ht15, club_ht05, club_ht15, club_ht05_home, club_ht05_away,
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
        (match_goal_15, 'Matç 1.5 üst', 'Oyunda', 1.5),
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


VENUE_LABELS = (('club_ht05_home', 'İlk hissə 0.5 üst (ev klubu evdə)'), ('club_ht05_away', 'İlk hissə 0.5 üst (səfər klubu səfərdə)'))


def venue_flags():
    """(ev klubu evdə, səfər klubu səfərdə) filtrləri seçilibmi?"""
    return bool(club_ht05_home), bool(club_ht05_away)


def venue_labels():
    vh, va = venue_flags()
    return [lab for on, (_, lab) in zip((vh, va), VENUE_LABELS) if on]


def venue_game_flags(df):
    """Oynanmış oyunun özü üçün: (məlumat var, ev/səfər filtrləri ödənir)."""
    vh, va = venue_flags()
    has = pd.Series(True, index=df.index)
    ok = pd.Series(True, index=df.index)
    if vh:
        x = _num(df, 'ht_home')
        has &= x.notna()
        ok &= (x >= 1).fillna(False)
    if va:
        x = _num(df, 'ht_away')
        has &= x.notna()
        ok &= (x >= 1).fillna(False)
    return has, ok


def build_venue_history(res, side):
    """Yalnız evdəki ('h') və ya yalnız səfərdəki ('a') oyunlardan komanda tarixçəsi; bayraq = klub ilk hissədə qol vurub."""
    team = res['home_k' if side == 'h' else 'away_k'].values
    v = _num(res, 'ht_home' if side == 'h' else 'ht_away')
    flags = (v.fillna(0).values >= 1).astype(np.int64)
    codes, uniques = pd.factorize(team)
    key = codes.astype(np.int64) * DAY_BASE + _day_int(res['date'])
    order = np.argsort(key, kind='stable')
    key, flags, pos = key[order], flags[order], np.arange(len(res))[order]
    return {'key': key, 'cs': np.concatenate([[0], np.cumsum(flags)]), 'pos': pos,
            'code_of': {t: i for i, t in enumerate(uniques)}}


def get_venue_history(side):
    key = ('venue', side, len(results), str(results['date'].max()))
    cached = st.session_state.get('_vhist_' + side)
    if cached and cached[0] == key:
        return cached[1]
    H = build_venue_history(results, side)
    st.session_state['_vhist_' + side] = (key, H)
    return H


def venue_qualified(R, n, side):
    """Geriyə test üçün: komandanın yalnız ev (side='h') / səfər ('a') oyunlarında son n oyunun hamısında klub ilk hissədə qol vurubmu?"""
    R = R.reset_index(drop=True)
    x = _num(R, 'ht_home' if side == 'h' else 'ht_away')
    L = pd.DataFrame({'rid': R.index, 'team': R['home_k' if side == 'h' else 'away_k'], 'date': R['date'],
                      'flag': (x.fillna(0) >= 1).astype(int)}).sort_values(['team', 'date', 'rid'], kind='stable').reset_index(drop=True)
    g = L.groupby('team')
    cs = g['flag'].cumsum()
    prev = cs.groupby(L['team']).shift(1).fillna(0)
    old = cs.groupby(L['team']).shift(n + 1).fillna(0)
    L['ok'] = (g.cumcount() >= n) & ((prev - old) == n)
    return L.set_index('rid')['ok'].reindex(R.index).fillna(False).values


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


# ======================= ANALİZ MÜHƏRRİKİ (vektorlaşdırılmış) =======================
# Hər oyun üçün ayrıca dövr yoxdur: bütün hədəf oyunlar bir dəfəyə yoxlanılır.
DAY_BASE = 100000   # açar = komanda_kodu * DAY_BASE + gün_nömrəsi
SHOW_STEP = 30      # bir dəfəyə neçə oyun kartı göstərilsin
HIST_COLS = ['date', 'time', 'home', 'away', 'ft_home', 'ft_away', 'ht_home', 'ht_away',
             'home_corners', 'away_corners', 'home_shots', 'away_shots', 'home_target', 'away_target', 'src']


def _day_int(dates):
    return pd.to_datetime(dates).values.astype('datetime64[D]').astype('int64')


def build_history(res, ph, pa):
    """Keçmiş oyunlardan komanda üzrə sıralı tarixçə qurur: hər komanda-oyun cütü üçün (açar, uyğunluq bayrağı, mövqe)."""
    n = len(res)
    teams = np.concatenate([res['home_k'].values, res['away_k'].values])
    codes, uniques = pd.factorize(teams)
    days = np.concatenate([_day_int(res['date'])] * 2)
    flags = np.concatenate([np.asarray(ph, dtype=bool), np.asarray(pa, dtype=bool)]).astype(np.int64)
    pos = np.concatenate([np.arange(n)] * 2)
    key = codes.astype(np.int64) * DAY_BASE + days
    order = np.argsort(key, kind='stable')
    key, flags, pos = key[order], flags[order], pos[order]
    return {'key': key, 'cs': np.concatenate([[0], np.cumsum(flags)]), 'pos': pos,
            'code_of': {t: i for i, t in enumerate(uniques)}}


def check_side(H, team_arr, day_arr, n):
    """Hər hədəf oyun üçün: komandanın oyundan əvvəlki n oyunu varmı (enough) və hamısı uyğundurmu (ok)? hi — tarixçədəki son mövqe."""
    codes = np.fromiter((H['code_of'].get(t, -1) for t in team_arr), dtype=np.int64, count=len(team_arr))
    hi = np.searchsorted(H['key'], codes * DAY_BASE + day_arr, side='left')
    lo = np.searchsorted(H['key'], codes * DAY_BASE, side='left')
    enough = (codes >= 0) & ((hi - lo) >= n)
    hi_s = np.where(enough, hi, n)
    ok = enough & ((H['cs'][hi_s] - H['cs'][hi_s - n]) == n)
    return enough, ok, hi


def get_history():
    """Filtrlər dəyişməyibsə əvvəl qurulmuş tarixçə təkrar istifadə olunur."""
    key = (tuple(n for n, _ in active_conditions()), len(results), str(results['date'].max()))
    cached = st.session_state.get('_hist_cache')
    if cached and cached[0] == key:
        return cached[1]
    ph, pa = side_pass_vec(results)
    H = build_history(results, ph.values, pa.values)
    st.session_state['_hist_cache'] = (key, H)
    return H


def analyze(n, date_from, date_to, sel_leagues, all_leagues):
    """Seçilmiş tarix aralığındakı oyunları yoxlayır. Oyun yoxdursa None qaytarır."""
    today = baku_today()
    target_cols = ['date', 'time', 'home', 'away', 'league', 'home_k', 'away_k', 'src']
    fix_t = fixtures[(fixtures['date'].dt.date >= max(date_from, today)) & (fixtures['date'].dt.date <= date_to)].copy()
    res_t = results[(results['date'].dt.date >= date_from) & (results['date'].dt.date <= date_to) & (results['date'].dt.date < today)].copy()
    if not all_leagues:
        fix_t = fix_t[fix_t['league'].isin(sel_leagues)]
        res_t = res_t[res_t['league'].isin(sel_leagues)]
    for frame in (fix_t, res_t):
        for col in target_cols:
            if col not in frame.columns:
                frame[col] = pd.NaT if col == 'date' else ''
    dg = pd.concat([res_t[target_cols], fix_t[target_cols]], ignore_index=True).dropna(subset=['date', 'home', 'away'])
    if dg.empty:
        return None
    # eyni oyun həm nəticələrdə, həm cədvəldə varsa — bu gün və sonrası üçün cədvəl üstün tutulur
    dg['_prio'] = (dg['date'].dt.date >= today).astype(int)
    dg = dg.sort_values('_prio', ascending=False, kind='stable').drop_duplicates(subset=['date', 'home_k', 'away_k']).drop(columns=['_prio']).reset_index(drop=True)

    H = get_history()
    days = _day_int(dg['date'])
    en_h, ok_h, hi_h = check_side(H, dg['home_k'].values, days, n)
    en_a, ok_a, hi_a = check_side(H, dg['away_k'].values, days, n)
    vh, va = venue_flags()
    Hh, Ha = H, H
    if vh:   # ev klubu — yalnız evdəki son n oyun
        Hh = get_venue_history('h')
        en_v, ok_v, hi_h = check_side(Hh, dg['home_k'].values, days, n)
        en_h, ok_h = en_h & en_v, ok_h & ok_v
    if va:   # qonaq klub — yalnız səfərdəki son n oyun
        Ha = get_venue_history('a')
        en_v, ok_v, hi_a = check_side(Ha, dg['away_k'].values, days, n)
        en_a, ok_a = en_a & en_v, ok_a & ok_v
    skipped = int((~(en_h & en_a)).sum())
    hit = np.flatnonzero(ok_h & ok_a)

    passed = []
    if len(hit):
        h_pos = [Hh['pos'][hi_h[i] - n:hi_h[i]][::-1] for i in hit]   # yeni → köhnə
        a_pos = [Ha['pos'][hi_a[i] - n:hi_a[i]][::-1] for i in hit]
        cols = [c for c in HIST_COLS if c in results.columns]
        recs = results.iloc[np.concatenate(h_pos + a_pos)][cols].to_dict('records')
        k = len(hit) * n
        for j, i in enumerate(hit):
            g = dg.iloc[i]
            passed.append({
                'Tarix': g['date'].strftime('%Y-%m-%d'),
                'Saat': str(g.get('time', '')),
                'Çempionat': g['league'],
                'Mənbə': src_label(g.get('src', '')),
                'Ev sahibi': g['home'],
                'Qonaq': g['away'],
                'Son oyun sayı': int(n),
                '_hk': g['home_k'], '_ak': g['away_k'],
                '_hh': recs[j * n:(j + 1) * n],
                '_ah': recs[k + j * n:k + (j + 1) * n],
            })
        # hesab / canlı status
        lo, hi_ = pd.Timestamp(date_from) - pd.Timedelta(days=1), pd.Timestamp(date_to) + pd.Timedelta(days=1)
        rr = results.loc[(results['date'] >= lo) & (results['date'] <= hi_), ['home_k', 'away_k', 'date', 'ft_home', 'ft_away']]
        res_idx = {}
        for hk_, ak_, d_, fh_, fa_ in rr.itertuples(index=False):
            res_idx.setdefault((hk_, ak_), []).append((d_, int(fh_), int(fa_)))
        live_rows = []   # canlı hesab söndürülüb (yavaşladırdı); hesab yalnız nəticələr bazasından götürülür
        for it in passed:
            it['Hesab'], it['Status'] = lookup_score(it['_hk'], it['_ak'], pd.to_datetime(it['Tarix']), res_idx, live_rows)
        # Başlıqda göstəriləcək statistika: seçilmiş filtrə uyğun (künc / zərbə / qapıya zərbə / hesab + 1-ci hissə)
        _fn = ' | '.join(n_ for n_, _ in active_conditions())
        want_corners = 'künc' in _fn
        want_target = 'dəqiq zərbə' in _fn
        want_shots = 'zərbə' in _fn.replace('dəqiq zərbə', '')
        want_score = any(not any(x in n_ for x in ('künc', 'zərbə')) for n_, _ in active_conditions())   # qol/BTTS/1-ci hissə filtri varsa hesab da göstərilir
        _scols = [c for c in ('ht_home', 'ht_away', 'home_corners', 'away_corners', 'home_shots', 'away_shots', 'home_target', 'away_target') if c in results.columns]
        sr = results.loc[(results['date'] >= lo) & (results['date'] <= hi_), ['home_k', 'away_k', 'date', 'ft_home', 'ft_away'] + _scols]
        stat_idx = {}
        for row in sr.to_dict('records'):
            stat_idx.setdefault((row['home_k'], row['away_k']), []).append(row)

        def _pair(r, a, b):
            x, y = r.get(a), r.get(b)
            if x is None or y is None or pd.isna(x) or pd.isna(y):
                return None
            return int(x), int(y)

        for it in passed:
            d0 = pd.to_datetime(it['Tarix'])
            r = next((r_ for r_ in stat_idx.get((it['_hk'], it['_ak']), []) if abs((r_['date'] - d0).days) <= 1), None)
            if r is None and d0.date() >= today:   # hələ oynanmamış oyun — göstəriləcək statistika yoxdur
                it['Statistika'] = ''
                continue
            parts = []
            _rec = r
            # bitmiş oyun filtrə uyğun gəlib-gəlmədiyi: True ✅ / False ❌ / məlumat yoxdursa None ❔
            it['Tutdu'] = None
            if _rec is not None:
                try:
                    _df1 = pd.DataFrame([_rec])
                    _vhas, _vok = venue_game_flags(_df1)
                    if bool(has_data_vec(_df1).iloc[0]) and bool(_vhas.iloc[0]):
                        it['Tutdu'] = bool(match_pass_vec(_df1).iloc[0]) and bool(_vok.iloc[0])
                except Exception:
                    it['Tutdu'] = None
            r = r or {}
            for want, a, b, label in ((want_corners, 'home_corners', 'away_corners', 'Künc'),
                                      (want_shots, 'home_shots', 'away_shots', 'Zərbə'),
                                      (want_target, 'home_target', 'away_target', 'Qapıya')):
                if want:
                    c = _pair(r, a, b)
                    parts.append(f'{label} {c[0]}–{c[1]} ({c[0] + c[1]})' if c else f'{label}: statistika yoxdur')
            if want_score or not parts:
                ft = _pair(r, 'ft_home', 'ft_away')
                ht = _pair(r, 'ht_home', 'ht_away')
                if ft:
                    parts.append(f'{ft[0]}–{ft[1]}' + (f' (1-ci hissə {ht[0]}–{ht[1]})' if ht else ''))
            it['Statistika'] = ' · '.join(parts)
    return {'passed': passed, 'checked': len(dg), 'skipped': skipped,
            'filters': [n_ for n_, _ in active_conditions()] + venue_labels(), 'n_games': int(n),
            'date_from': str(date_from), 'date_to': str(date_to),
            'leagues': 'Hamısı' if all_leagues else f'{len(sel_leagues)} liqa'}


def hist_cards_html(records):
    """Komandanın əvvəlki oyunlarının kartları — tək HTML sətri kimi (hər kart üçün ayrıca st.markdown yoxdur)."""
    import html as _html
    parts = []
    for m in records:
        d = pd.to_datetime(m.get('date'), errors='coerce')
        date_text = d.strftime('%d.%m.%Y') if pd.notna(d) else 'Tarix məlum deyil'
        t = str(m.get('time', '')).strip()
        t = '' if t.lower() in ('nan', 'nat', 'none') else t
        hg, ag = m.get('ft_home'), m.get('ft_away')
        score = f'{int(hg)}–{int(ag)}' if pd.notna(hg) and pd.notna(ag) else 'Hesab yoxdur'
        chips = ''
        a, b = m.get('ht_home'), m.get('ht_away')
        if pd.notna(a) and pd.notna(b):
            chips += f'<span class="chip h">1-ci hissə {int(a)}–{int(b)}</span>'
        for label, ck, ak in (('Künc', 'home_corners', 'away_corners'), ('Zərbə', 'home_shots', 'away_shots'), ('Qapıya', 'home_target', 'away_target')):
            a, b = m.get(ck), m.get(ak)
            if pd.notna(a) and pd.notna(b):
                chips += f'<span class="chip c">{label} {int(a + b)}</span>'
        st_ = src_label(m.get('src', ''))
        if st_:
            chips += f'<span class="chip s">{st_}</span>'
        parts.append(
            f'<div class="mcard"><div class="d">{date_text}{(" · " + t) if t else ""}</div>'
            f'<div class="t">{_html.escape(str(m.get("home", "")))}</div><div class="s">{score}</div>'
            f'<div class="t">{_html.escape(str(m.get("away", "")))}</div><div>{chips}</div></div>')
    return ''.join(parts)


# Kupon faylda saxlanılır ki, səhifə yenilənəndə və tətbiq yenidən açılanda itməsin.
COUPON_FILE = ROOT / "football_coupon.json"

def _load_coupon_file():
    try:
        if COUPON_FILE.exists():
            data = json.loads(COUPON_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []

def _save_coupon_file():
    try:
        COUPON_FILE.write_text(json.dumps(st.session_state.get("football_coupon", []), ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception as exc:
        st.warning(f"Kupon fayla yazıla bilmədi: {exc}")
        return False

# İlk açılışda kuponu diskdən bərpa et.
if "football_coupon" not in st.session_state:
    st.session_state["football_coupon"] = _load_coupon_file()

def _coupon_market_options():
    """Seçim üçün əsas futbol bazarları və hazırkı filtrdəki bazarlar."""
    opts = [
        'Matç nəticəsi: 1', 'Matç nəticəsi: X', 'Matç nəticəsi: 2',
        'İki komanda da qol vuracaq: Hə', 'İki komanda da qol vuracaq: Yox',
        'Matç qolları: 0.5 üst', 'Matç qolları: 1.5 üst', 'Matç qolları: 2.5 üst',
        'Matç qolları: 3.5 üst', 'Matç qolları: 4.5 üst',
        'Matç qolları: 1.5 alt', 'Matç qolları: 2.5 alt', 'Matç qolları: 3.5 alt',
        '1-ci hissə qolu: 0.5 üst', '1-ci hissə qolları: 1.5 üst',
        '1-ci hissə qolları: 0.5 alt', '1-ci hissə qolları: 1.5 alt',
    ]
    opts += [f'Ümumi künclər: {x} üst' for x in (6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5)]
    opts += [f'Ümumi künclər: {x} alt' for x in (8.5, 9.5, 10.5, 11.5, 12.5)]
    # Hazırkı analiz filtrində seçilən şərtləri də seçim siyahısına daxil et.
    for name, _ in active_conditions():
        if name not in opts:
            opts.append(name)
    return opts


def _render_coupon():
    """Kupon yalnız tətbiq sessiyasında saxlanılır; seçimlər başlanma vaxtına görə düzülür."""
    coupon = st.session_state.setdefault('football_coupon', [])
    st.markdown('### 🎟️ Kupon')
    if not coupon:
        st.caption('Hələ kupona oyun əlavə edilməyib. Uyğun oyunların yanındakı ➕ düyməsindən başla.')
        return
    def sort_key(x):
        d = pd.to_datetime(x.get('Tarix'), errors='coerce')
        t = pd.to_datetime(str(x.get('Saat', '')), format='%H:%M', errors='coerce')
        if pd.isna(d):
            return pd.Timestamp.max
        dt = pd.Timestamp(d.date())
        if pd.notna(t):
            dt += pd.Timedelta(hours=t.hour, minutes=t.minute)
        return dt
    coupon.sort(key=sort_key)
    st.caption('Oyunlar ən tez başlayandan gec başlayana, tarix və saata görə sıralanır.')
    for i, leg in enumerate(coupon):
        c1, c2 = st.columns([5, 1])
        with c1:
            st.markdown(f"**{leg.get('Tarix', '')} · {leg.get('Saat', 'Saat məlum deyil')}**  ")
            st.write(f"{leg.get('Ev sahibi', '')} — {leg.get('Qonaq', '')}")
            st.caption(f"Seçim: {leg.get('Seçim', '')} · {leg.get('Çempionat', '')}")
        with c2:
            if st.button('✖', key=f'coupon_remove_{leg.get("id", i)}', help='Kupondan sil'):
                st.session_state['football_coupon'] = [x for j, x in enumerate(coupon) if j != i]
                _save_coupon_file()
                st.rerun()
    if st.button('🗑️ Kuponu təmizlə', key='coupon_clear', use_container_width=True):
        st.session_state['football_coupon'] = []
        _save_coupon_file()
        st.rerun()


def render_analysis(A, cur_key):
    passed = A['passed']
    # Sıralama: başlamayan oyunlar (ən tez başlayacaq əvvəl), sonra canlı oyunlar,
    # sonda bitmiş oyunlar (ən yeni tarix əvvəl).
    try:
        _now_sort = pd.Timestamp.now(tz='Asia/Baku').tz_localize(None)
        def _match_sort_key(_item):
            _date = pd.to_datetime(_item.get('Tarix'), errors='coerce')
            _time_raw = str(_item.get('Saat', '')).strip()
            _time = pd.to_datetime(_time_raw, format='%H:%M', errors='coerce') if _time_raw.lower() not in ('', 'nan', 'nat', 'none', 'saat məlum deyil') else pd.NaT
            if pd.notna(_date):
                _dt = pd.Timestamp(_date.date())
                if pd.notna(_time):
                    _dt += pd.Timedelta(hours=_time.hour, minutes=_time.minute)
            else:
                _dt = pd.Timestamp.max
            _status = str(_item.get('Status', '')).strip().lower()
            if _status.startswith('canlı'):
                return (1, _dt)
            if _status == 'bitib' or _item.get('Hesab'):
                return (2, -_dt.value if _dt != pd.Timestamp.max else 0)
            if _dt >= _now_sort:
                return (0, _dt.value)
            # Keçmiş tarixli, statusu müəyyən edilməyən oyunları bitmiş oyunlar bölməsinə sal.
            return (2, -_dt.value if _dt != pd.Timestamp.max else 0)
        passed.sort(key=_match_sort_key)
    except Exception:
        pass
    st.markdown(
        f'<div class="stats">'
        f'<div class="stat"><div class="n">{A["checked"]}</div><div class="l">Yoxlanılan oyun</div></div>'
        f'<div class="stat good"><div class="n">{len(passed)}</div><div class="l">Uyğun oyun</div></div>'
        f'<div class="stat"><div class="n">{A["skipped"]}</div><div class="l">Tarixçəsi çatmayan oyun</div></div>'
        f'</div>', unsafe_allow_html=True)
    st.caption('Komandaların əvvəlki oyunları liqa və kubok daxil olmaqla bütün mövcud nəticələrdən, hədəf oyunun tarixindən əvvəl axtarılır. '
               f'Saatlar Bakı vaxtı ilədir. ⏱ {A.get("secs", 0):.1f} san.')
    if A.get('filters'):
        _used_filters = ' + '.join(A['filters'])
        _auto_base = f"Son {A['n_games']} oyun — {_used_filters}"
        _auto_title = _auto_base
        st.markdown('### 🎯 Analiz filtri')
        st.info(f"**{_auto_title}**\n\nHər komandanın son **{A['n_games']}** oyununda bütün seçilmiş şərtlər yoxlanılır.\n\nTarix: **{A.get('date_from', '')} → {A.get('date_to', '')}** · Liqalar: **{A.get('leagues', '—')}** · Uyğun oyun sayı: **{len(passed)}**")
        if st.button('💾 Bu filtri yadda saxla', key='save_named_filter_auto', use_container_width=True):
            _payload = {}
            for _k, _v in st.session_state.items():
                if isinstance(_k, str) and (_k in _PRESET_EXPLICIT or _k.startswith(_PRESET_PREFIXES)):
                    if isinstance(_v, (bool, int, float, str)):
                        _payload[_k] = _v
            for _dk in ('d_from', 'd_to'):
                if _dk in st.session_state:
                    _payload[_dk] = st.session_state[_dk].isoformat()
            if 'lg_sel' in st.session_state:
                _payload['lg_sel'] = sorted(str(x) for x in st.session_state['lg_sel'])
            _payload['_meta_filters'] = A.get('filters', [])
            _payload['_meta_n_games'] = A.get('n_games')
            _payload['_meta_hits'] = len(passed)
            _payload['_meta_dates'] = f"{A.get('date_from', '')} → {A.get('date_to', '')}"
            _all_presets = _read_named_filters()
            _name = _auto_base
            _suffix = 2
            while _name in _all_presets:
                _name = f'{_auto_base} ({_suffix})'
                _suffix += 1
            _all_presets[_name] = _payload
            try:
                NAMED_FILTERS_FILE.write_text(json.dumps(_all_presets, ensure_ascii=False, indent=2), encoding='utf-8')
                st.success(f'“{_name}” adı ilə yadda saxlanıldı. Filtr ana səhifədəki siyahıda görünəcək.')
                st.rerun()
            except Exception as e:
                st.error(f'Filtri yadda saxlamaq olmadı: {e}')
    else:
        st.caption('Bu analiz üçün aktiv filtr adı mövcud deyil.')
    if A.get('key') != cur_key:
        st.warning('Filtrlər və ya tarix dəyişib — göstərilən nəticə əvvəlki seçimlərə aiddir. Yenisi üçün "Oyunları analiz et" düyməsinə bas.')
    if not passed:
        st.info('Seçilən şərtlərə uyğun oyun tapılmadı. Tarix aralığını genişləndir və ya filtrləri dəyiş.')
        return
    st.subheader('⚽ Uyğun oyunlar')
    st.markdown(f'**İstifadə olunan filtr:** {" + ".join(A.get("filters", []))}  ·  **Son oyun sayı:** {A.get("n_games", "—")}  ·  **Tapılan oyun:** {len(passed)}')
    st.caption('Hər oyunun üzərinə basaraq açın. Komandaların əvvəlki oyunları yan-yana göstərilir.')
    show_n = st.session_state.get('show_n', SHOW_STEP)
    for item in passed[:show_n]:
        time_text = str(item.get('Saat', '')).strip()
        if time_text.lower() in ('nan', 'nat', 'none', ''):
            time_text = 'Saat məlum deyil'
        league_text = str(item.get('Çempionat', '')).replace('_', ' ').replace('-', ' ').strip()
        _is_past = pd.to_datetime(item['Tarix']).date() < baku_today()   # keçmiş tarixdə tapılan oyunun tarixi qırmızı
        _date_txt = f":red[{item['Tarix']}]" if _is_past else item['Tarix']
        title = f"⚽ {_date_txt} · {time_text} · {item['Ev sahibi']} — {item['Qonaq']}"
        live = str(item.get('Status', '')).startswith('Canlı')
        _t = item.get('Tutdu')
        _mark = '🔴' if live else ('✅' if _t is True else '❌' if _t is False else '❔')
        if item.get('Statistika'):
            title += f" · {_mark} {item['Statistika']}"
        elif item.get('Hesab'):
            title += f" · {_mark} {item['Hesab']}"
        with st.expander(title, expanded=False):
            if item.get('Hesab'):
                st.markdown(f"**{_mark} {item['Hesab']}** · {item['Status']}")
            st.caption(f"{league_text} · Hər komandanın son {item['Son oyun sayı']} oyunu · Mənbə: {item['Mənbə'] or 'məlum deyil'}")
            _match_dt = pd.to_datetime(item.get('Tarix'), errors='coerce')
            _match_time = pd.to_datetime(str(item.get('Saat', '')), format='%H:%M', errors='coerce')
            _kickoff = pd.Timestamp.max
            if pd.notna(_match_dt):
                _kickoff = pd.Timestamp(_match_dt.date())
                if pd.notna(_match_time):
                    _kickoff += pd.Timedelta(hours=_match_time.hour, minutes=_match_time.minute)
            _now_baku = pd.Timestamp.now(tz='Asia/Baku').tz_localize(None)
            _not_started = pd.notna(_match_dt) and _kickoff >= _now_baku and not live and not item.get('Hesab')
            _coupon_id = f"{item.get('Tarix')}|{item.get('Saat')}|{item.get('_hk')}|{item.get('_ak')}"
            if _not_started:
                if st.button('➕ Kupona əlavə et', key=f"coupon_pick_{_coupon_id}", use_container_width=True):
                    st.session_state['coupon_pick_id'] = _coupon_id
                if st.session_state.get('coupon_pick_id') == _coupon_id:
                    _options = _coupon_market_options()
                    _chosen = st.selectbox('Kupon üçün bazar/seçim', _options, key=f"coupon_market_{_coupon_id}")
                    if st.button('✅ Seçimi təsdiqlə və kupona əlavə et', key=f"coupon_add_{_coupon_id}", type='primary', use_container_width=True):
                        _coupon = st.session_state.setdefault('football_coupon', [])
                        if not any(x.get('match_id') == _coupon_id and x.get('Seçim') == _chosen for x in _coupon):
                            _coupon.append({'id': _coupon_id + '|' + _chosen, 'match_id': _coupon_id, 'Tarix': item.get('Tarix', '') , 'Saat': item.get('Saat', ''),
                                            'Ev sahibi': item.get('Ev sahibi', ''), 'Qonaq': item.get('Qonaq', ''),
                                            'Çempionat': item.get('Çempionat', ''), 'Seçim': _chosen})
                            _save_coupon_file()
                        st.session_state.pop('coupon_pick_id', None)
                        st.success('Seçim kupona əlavə edildi.')
                        st.rerun()
            left, right = st.columns(2)
            for col, name, key in ((left, item['Ev sahibi'], '_hh'), (right, item['Qonaq'], '_ah')):
                with col:
                    st.markdown(f'<div class="team-head">🏟️ {name}</div>' + hist_cards_html(item[key]), unsafe_allow_html=True)
    if len(passed) > show_n:
        if st.button(f'⬇️ Daha çox göstər ({show_n} / {len(passed)})', use_container_width=True, key='show_more'):
            st.session_state['show_n'] = show_n + SHOW_STEP
            st.rerun()
    out = pd.DataFrame([{k: v for k, v in it.items() if not k.startswith('_')} for it in passed])
    out['Tətbiq olunan filtrlər'] = ' + '.join(A.get('filters', []))
    out['Hər komandanın yoxlanan son oyunu'] = A.get('n_games', '')
    out['Analiz tarix aralığı'] = f"{A.get('date_from', '')} → {A.get('date_to', '')}"
    out['Liqa seçimi'] = A.get('leagues', '')
    try:
        import io as _io
        _buf = _io.BytesIO()
        with pd.ExcelWriter(_buf, engine='openpyxl') as _xw:
            out.to_excel(_xw, index=False, sheet_name='Nəticələr')
            _ws = _xw.sheets['Nəticələr']
            from openpyxl.styles import Font, PatternFill, Alignment
            for _c in _ws[1]:
                _c.font = Font(bold=True, color='FFFFFF')
                _c.fill = PatternFill('solid', fgColor='15803D')
                _c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            for _col in _ws.columns:
                _w = max(len(str(_c.value)) if _c.value is not None else 0 for _c in _col)
                _ws.column_dimensions[_col[0].column_letter].width = min(max(_w + 3, 10), 45)
            _ws.freeze_panes = 'A2'
            _ws.auto_filter.ref = _ws.dimensions
        st.download_button('⬇️ Nəticələri Excel kimi yüklə', _buf.getvalue(),
                           file_name='futbol_filtri_neticeleri.xlsx',
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except ImportError:   # openpyxl yoxdursa: Excel-in Azərbaycan tənzimləməsində düzgün açılan CSV (ayırıcı ;)
        st.download_button('⬇️ Nəticələri CSV kimi yüklə', out.to_csv(index=False, sep=';').encode('utf-8-sig'),
                           file_name='futbol_filtri_neticeleri.csv', mime='text/csv')


# Üzən kupon paneli və analiz düyməsi: kupon solda, analiz sağda.
with st.container(key="coupon_float_button"):
    _coupon_count = len(st.session_state.get("football_coupon", []))
    _coupon_label = f"🎟️ Kuponlar ({_coupon_count})"
    if st.button(_coupon_label, key="coupon_float_toggle", use_container_width=True):
        st.session_state["show_coupon_float"] = not st.session_state.get("show_coupon_float", False)

if st.session_state.get("show_coupon_float", False):
    with st.container(key="coupon_float_panel"):
        _p1, _p2 = st.columns([4, 1])
        with _p1:
            st.markdown("### 🎟️ Kuponlar")
        with _p2:
            if st.button("✖", key="coupon_float_close", help="Paneli bağla"):
                st.session_state["show_coupon_float"] = False
                st.rerun()
        _render_coupon()

run_clicked = st.button('🔎 Oyunları analiz et', type='primary', key='analyze_button')
cur_key = (tuple(n for n, _ in active_conditions()) if criteria_selected else (), int(n_games), str(date_from), str(date_to),
           len(sel_leagues), len(results), str(results['date'].max()))

# Analiz yalnız istifadəçi düyməni basanda işə düşür.
if run_clicked:
    problem = None
    if date_from > date_to:
        problem = ('error', 'Başlanğıc tarixi son tarixdən böyük ola bilməz.')
    elif not criteria_selected:
        problem = ('warning', 'Zəhmət olmasa ən azı bir filtr seç.')
    elif conditions_contradict():
        problem = ('warning', 'Seçilmiş filtrlər bir-birinə ziddir (məsələn "2.5 üst" və "2.5 alt"), heç bir oyun uyğun gəlməyəcək. Filtrləri dəyiş.')
    elif not sel_leagues:
        problem = ('warning', 'Heç bir liqa seçilməyib. "Liqalar" bölməsindən ən azı bir liqa seç.')
    if problem:
        st.session_state.pop('analysis', None)
        getattr(st, problem[0])(problem[1])
    else:
        st.session_state['_ran'] = True
        save_filters()
        import time as _t
        _t0 = _t.perf_counter()
        with st.spinner('Analiz edilir...'):
            _A = analyze(int(n_games), date_from, date_to, sel_leagues, len(sel_leagues) >= len(league_options))
        if _A is None:
            st.session_state.pop('analysis', None)
            st.warning('Bu tarix aralığında bazada oyun tapılmadı. Məlumatı yeniləməyi yoxla.')
        else:
            _A['key'], _A['secs'] = cur_key, _t.perf_counter() - _t0
            st.session_state['analysis'] = _A
            st.session_state['show_n'] = SHOW_STEP

if st.session_state.get('analysis'):
    render_analysis(st.session_state['analysis'], cur_key)


# ===== KOFSENT BÖLMƏSİ (başlanğıc) =====
# Seçilmiş kofsentlərə yaxın olan keçmiş oyunları tapır və analiz edir (1/X/2, üst/alt, I yarı, hər iki komanda qol vurur).
# Öz qovluğunu istifadə edir (football-data-odds), mövcud məlumat bazasına toxunmur.
KO_DIR = ROOT / 'football-data-odds'
KO_N_SEASONS = 8
KO_SRC = {   # kofsent mənbəyi: football-data.co.uk fayllarındakı sütunlar
    'avg': {'label': 'Orta bazar', 'cols': {
        'h': ['AvgH', 'BbAvH', 'B365H', 'PSH', 'BWH', 'WHH'],
        'd': ['AvgD', 'BbAvD', 'B365D', 'PSD', 'BWD', 'WHD'],
        'a': ['AvgA', 'BbAvA', 'B365A', 'PSA', 'BWA', 'WHA'],
        'o': ['Avg>2.5', 'BbAv>2.5', 'B365>2.5', 'P>2.5'],
        'u': ['Avg<2.5', 'BbAv<2.5', 'B365<2.5', 'P<2.5']}},
    'b365': {'label': 'Bet365', 'cols': {
        'h': ['B365H'], 'd': ['B365D'], 'a': ['B365A'], 'o': ['B365>2.5'], 'u': ['B365<2.5']}},
    'ps': {'label': 'Pinnacle', 'cols': {
        'h': ['PSH', 'PH'], 'd': ['PSD', 'PD'], 'a': ['PSA', 'PA'], 'o': ['P>2.5'], 'u': ['P<2.5']}},
}


def ko_seasons(n=KO_N_SEASONS):
    now = datetime.now()
    y = now.year if now.month >= 7 else now.year - 1
    return [f'{(y - k) % 100:02d}{(y - k + 1) % 100:02d}' for k in range(n)]


import threading
import time as _ko_time


def ko_fetch_fixtures():
    try:
        r = requests.get(f'{FD_BASE}/fixtures.csv', timeout=20, headers={'User-Agent': 'FutbolFiltri/1.0'})
        if r.status_code == 200 and len(r.content) > 50:
            KO_DIR.mkdir(exist_ok=True)
            (KO_DIR / 'fixtures.csv').write_bytes(r.content)
            return True
    except requests.RequestException:
        pass
    return False


def ko_refresh():
    """Son 8 mövsümün fayllarını və fixtures.csv-ni yükləyir. (uğurlu, cəmi, fixtures_ok) qaytarır."""
    KO_DIR.mkdir(exist_ok=True)
    jobs = [(s, c) for s in ko_seasons() for c in FD_LEAGUES]

    def one(job):
        s, c = job
        try:
            r = requests.get(f'{FD_BASE}/mmz4281/{s}/{c}.csv', timeout=20, headers={'User-Agent': 'FutbolFiltri/1.0'})
            if r.status_code == 200 and len(r.content) > 200:
                (KO_DIR / f'{s}_{c}.csv').write_bytes(r.content)
                return True
        except requests.RequestException:
            pass
        return False

    with ThreadPoolExecutor(max_workers=10) as ex:
        ok = sum(1 for x in ex.map(one, jobs) if x)
    return ok, len(jobs), ko_fetch_fixtures()


@st.cache_resource
def _ko_bg():
    return {'running': False, 'last': 0.0}


def ko_bg_start(force=False):
    """Fayllar yoxdursa (məs. tətbiq yenidən başlayıb) və ya fixtures köhnədirsə, özü arxa planda yükləyir. True = yüklənir.
    force=True: düyməyə basılıb, bütün tarixçə yenidən yüklənir."""
    state = _ko_bg()
    if state['running']:
        return True
    KO_DIR.mkdir(exist_ok=True)
    need_hist = force or not any(KO_DIR.glob('[0-9]*_*.csv'))
    fxp = KO_DIR / 'fixtures.csv'
    need_fx = (not fxp.exists()) or (_ko_time.time() - fxp.stat().st_mtime > 6 * 3600)
    if not force and (not (need_hist or need_fx) or _ko_time.time() - state['last'] < 600):   # uğursuz olsa 10 dəqiqə gözlə
        return False
    state['last'], state['running'] = _ko_time.time(), True

    def job():
        try:
            if need_hist:
                ko_refresh()
            else:
                ko_fetch_fixtures()
        except Exception:
            pass
        finally:
            state['running'] = False

    threading.Thread(target=job, daemon=True).start()
    return True


def _ko_pick(df, cols):
    """Bir bazar üçün ilk mövcud kofsent sütununu götürür (orta bazar → konkret bukmekerlər)."""
    present = [c for c in cols if c in df.columns]
    if not present:
        return pd.Series(np.nan, index=df.index)
    x = df[present].apply(pd.to_numeric, errors='coerce')
    x = x.where(x > 1)
    return x.bfill(axis=1).iloc[:, 0]


def _ko_prepare(df):
    if df is None or df.empty or 'HomeTeam' not in df.columns or 'Date' not in df.columns:
        return None
    out = pd.DataFrame({'date': parse_fd_date(df['Date']), 'home': df['HomeTeam'], 'away': df['AwayTeam']})
    div = df['Div'] if 'Div' in df.columns else pd.Series('FD', index=df.index)
    out['league'] = div.map(FD_LEAGUES).fillna(div)
    out['time'] = df['Time'].astype(str) if 'Time' in df.columns else ''
    for sk, sv in KO_SRC.items():
        for k, cols in sv['cols'].items():
            out[f'{sk}_{k}'] = _ko_pick(df, cols)
    for src, dst in (('FTHG', 'ft_h'), ('FTAG', 'ft_a'), ('HTHG', 'ht_h'), ('HTAG', 'ht_a')):
        out[dst] = pd.to_numeric(df[src], errors='coerce') if src in df.columns else np.nan
    return out


def ko_sig():
    if not KO_DIR.exists():
        return ()
    return tuple((f.name, f.stat().st_size) for f in sorted(KO_DIR.glob('[0-9]*_*.csv')))


@st.cache_data(show_spinner='Kofsent tarixçəsi oxunur...')
def ko_load_history(sig):
    frames = []
    for f in sorted(KO_DIR.glob('[0-9]*_*.csv')):
        p = _ko_prepare(read_csv_safe(f))
        if p is not None:
            frames.append(p)
    if not frames:
        return pd.DataFrame()
    h = pd.concat(frames, ignore_index=True)
    h = h.dropna(subset=['date', 'ft_h', 'ft_a'])
    return h.sort_values('date', ascending=False).reset_index(drop=True)


def ko_load_fixtures():
    p = KO_DIR / 'fixtures.csv'
    if not p.exists():
        p = FD_DIR / 'fixtures.csv'
    if not p.exists():
        return pd.DataFrame()
    f = _ko_prepare(read_csv_safe(p))
    if f is None:
        return pd.DataFrame()
    return f.dropna(subset=['date'])


# ---- Yaxın oyunlar: The Odds API (pulsuz açar lazımdır, ayda 500 kredit) ----
ODDS_API = 'https://api.the-odds-api.com/v4'


def ko_api_key():
    try:
        k = st.secrets.get('ODDS_API_KEY', '')
    except Exception:
        k = ''
    return str(k or '').strip()


@st.cache_data(ttl=3600, show_spinner=False)
def ko_api_sports(key):
    r = requests.get(f'{ODDS_API}/sports', params={'apiKey': key}, timeout=20)
    r.raise_for_status()
    return [(x['key'], f"{x.get('description') or x['title']}") for x in r.json()
            if x.get('group') == 'Soccer' and x.get('active') and not x.get('has_outrights')]


def _ko_mean(v):
    v = [x for x in v if x]
    return round(sum(v) / len(v), 3) if v else np.nan


def _ko_api_row(ev, league):
    per, pin, b365 = [], None, None
    for b in ev.get('bookmakers', []):
        h = d = a = o = u = None
        for m in b.get('markets', []):
            if m.get('key') == 'h2h':
                for oc in m.get('outcomes', []):
                    if oc.get('name') == ev.get('home_team'):
                        h = oc.get('price')
                    elif oc.get('name') == ev.get('away_team'):
                        a = oc.get('price')
                    elif oc.get('name') == 'Draw':
                        d = oc.get('price')
            elif m.get('key') == 'totals':
                for oc in m.get('outcomes', []):
                    if oc.get('point') == 2.5:
                        if oc.get('name') == 'Over':
                            o = oc.get('price')
                        elif oc.get('name') == 'Under':
                            u = oc.get('price')
        tup = (h, d, a, o, u)
        per.append(tup)
        if b.get('key') == 'pinnacle':
            pin = tup
        if b.get('key') == 'bet365':
            b365 = tup
    avg = tuple(_ko_mean([t[i] for t in per]) for i in range(5))
    t = pd.to_datetime(ev.get('commence_time'), utc=True).tz_convert(None) + pd.Timedelta(hours=4)   # Bakı vaxtı
    row = {'date': t.normalize(), 'time': f'{t:%H:%M}', 'home': ev.get('home_team'), 'away': ev.get('away_team'), 'league': league}
    for sk, tup in (('avg', avg), ('ps', pin or (None,) * 5), ('b365', b365 or avg)):   # Odds API-də Bet365 yoxdursa orta kofsent
        for k, v in zip('hdaou', tup):
            row[f'{sk}_{k}'] = v if v else np.nan
    return row


def ko_api_fetch(key, sports, names):
    rows, errs, left = [], [], None
    for sk in sports:
        try:
            r = requests.get(f'{ODDS_API}/sports/{sk}/odds', timeout=25, params={
                'apiKey': key, 'regions': 'eu', 'markets': 'h2h,totals', 'oddsFormat': 'decimal', 'dateFormat': 'iso'})
        except requests.RequestException as e:
            errs.append(f'{names.get(sk, sk)}: {e}')
            continue
        left = r.headers.get('x-requests-remaining', left)
        if r.status_code != 200:
            errs.append(f'{names.get(sk, sk)}: HTTP {r.status_code}')
            continue
        rows += [_ko_api_row(ev, names.get(sk, sk)) for ev in r.json()]
    return (pd.DataFrame(rows) if rows else pd.DataFrame()), errs, left


def ko_batch(f, hist, tol, years, sel):
    """Siyahıdakı hər oyun üçün: keçmişdə eyni kofsentli oyunlar neçə faiz necə bitib."""
    cut = pd.Timestamp(baku_today()) - pd.Timedelta(days=365 * years)
    H = hist[hist['date'] >= cut]
    if sel:
        H = H[H['league'].isin(sel)]
    oh, od, oa = (H[c].to_numpy(float) for c in ('o_h', 'o_d', 'o_a'))
    fh, fa = H['ft_h'].to_numpy(float), H['ft_a'].to_numpy(float)
    hh, ha = H['ht_h'].to_numpy(float), H['ht_a'].to_numpy(float)
    tot = fh + fa
    rows = []
    for _, r in f.iterrows():
        if not all(pd.notna(r[c]) and r[c] > 1 for c in ('o_h', 'o_d', 'o_a')):
            continue
        with np.errstate(invalid='ignore'):
            m = ((np.abs(oh - r['o_h']) <= r['o_h'] * tol / 100) & (np.abs(od - r['o_d']) <= r['o_d'] * tol / 100)
                 & (np.abs(oa - r['o_a']) <= r['o_a'] * tol / 100))
        n = int(m.sum())
        raw = [1 / r['o_h'], 1 / r['o_d'], 1 / r['o_a']]
        sm = sum(raw)
        row = {'Tarix': f"{r['date']:%d.%m}", 'Saat': '' if str(r['time']) in ('', 'nan') else r['time'], 'Liqa': r['league'],
               'Ev sahibi': r['home'], 'Qonaq': r['away'],
               'Kofsent': f"{r['o_h']:.2f} / {r['o_d']:.2f} / {r['o_a']:.2f}",
               'Bukmeker 1/X/2 %': ' / '.join(f'{x / sm * 100:.0f}' for x in raw), 'Oxşar oyun': n}
        if n:
            def p(mask):
                return round(float(mask[m].sum()) / n * 100, 1)
            p1, px, p2 = p(fh > fa), p(fh == fa), p(fh < fa)
            hm = m & ~np.isnan(hh) & ~np.isnan(ha)
            k = int(hm.sum())
            row.update({'1 %': p1, 'X %': px, '2 %': p2,
                        'Ən çox': ['1', 'X', '2'][int(np.argmax([p1, px, p2]))],
                        'Üst 1.5 %': p(tot > 1.5), 'Üst 2.5 %': p(tot > 2.5), 'Hər ikisi vurur %': p((fh > 0) & (fa > 0)),
                        'I yarı üst 0.5 %': round(float(((hh + ha) > 0.5)[hm].sum()) / k * 100, 1) if k else None,
                        'Orta qol': round(float(tot[m].mean()), 2)})
        row['Etibar'] = '' if n >= 30 else ('⚠️ az oyun' if n else '⚠️ yoxdur')
        rows.append(row)
    return pd.DataFrame(rows)


def _ko_pct(a, b):
    return f'{a / b * 100:.1f}%' if b else '-'


def render_kofsent_section():
    st.caption('Kofsentləri seç (və ya əllə yaz) — proqram keçmişdə eyni kofsentli oyunları tapıb nəticələrini göstərir: '
               '1/X/2, üst/alt, ilk yarı, hər iki komanda qol vurur. Mənbə: football-data.co.uk (əsas Avropa liqaları). '
               'Keçmiş faiz gələcək nəticəyə zəmanət vermir.')
    _clicked = st.button('🔄 Kofsent məlumatını yenilə', key='ko_dl',
                         help='Yaxın oyunların siyahısı dərhal yenilənir, 8 mövsümlük tarixçə isə arxa planda yüklənir. Adətən lazım deyil, tətbiq özü yeniləyir.')
    if _clicked:
        _fx_ok = ko_fetch_fixtures()
        _fxn = ko_load_fixtures()
        if _fx_ok and not _fxn.empty:
            st.success(f'Yaxın oyunlar siyahısı yeniləndi: {len(_fxn)} oyun, tarixləri {_fxn["date"].min():%d.%m.%Y} – {_fxn["date"].max():%d.%m.%Y}. '
                       'Sayt hələ yeni oyunları qoymayıbsa, siyahı köhnə qalır.')
        elif not _fx_ok:
            st.warning('football-data.co.uk-dən yaxın oyunlar yüklənmədi (sayt cavab vermədi). Bir az sonra yenidən yoxla.')
    busy = ko_bg_start(force=_clicked)
    if busy:
        st.info('⏳ Kofsent tarixçəsi arxa planda yüklənir (2-5 dəqiqə). Səhifəni bağlaya bilərsən; bir azdan "Yoxla" düyməsinə bas.')
        st.button('🔄 Yoxla', key='ko_recheck')
    hist = ko_load_history(ko_sig())
    if hist.empty:
        if not busy:
            st.info('Tarixçə hələ yüklənməyib. Yuxarıdakı düyməyə bas.')
        return

    # ---- Kofsent mənbəyi: arxivdəki hansı bukmekerin kofsenti ilə müqayisə olunsun ----
    src = st.radio('Kofsent mənbəyi', list(KO_SRC), index=1, horizontal=True,
                   format_func=lambda k: KO_SRC[k]['label'], key='ko_src',
                   on_change=lambda: st.session_state.update(ko_game='—'),
                   help='Arxivdə yalnız bu bukmekerlər var: Bet365, Pinnacle və bir çox bukmekerin orta kofsenti. '
                        '1xBet, Melbet və s. arxivdə yoxdur, onların kofsenti adətən bir neçə faiz fərqlənir, "Kofsent fərqi" bunu əhatə edir.')
    hist = hist.assign(**{f'o_{k}': hist[f'{src}_{k}'] for k in 'hdaou'})

    # ---- Yaxın oyunlar (bütün liqalar): The Odds API ----
    _api_on = st.toggle('🌍 Daha çox liqa və yaxın oyunlar (The Odds API)', key='ko_api_show',
                        help='football-data.co.uk-nin faylı yalnız həftə sonu və əsas liqaları saxlayır.')
    if _api_on:
        key = ko_api_key()
        if not key:
            key = st.text_input('The Odds API açarı', type='password', key='ko_api_key_in',
                                help='Pulsuz açar: the-odds-api.com → "Get API Key". Ayda 500 kredit. Daimi saxlamaq üçün Streamlit Secrets-də ODDS_API_KEY adı ilə yazın.').strip()
        if not key:
            st.caption('Açar yazsan, istənilən liqanın yaxın oyunları kofsentləri ilə gələcək.')
        else:
            try:
                sports = ko_api_sports(key)
            except Exception as e:
                sports = []
                st.error(f'Açar qəbul olunmadı və ya xəta: {e}')
            names = dict(sports)
            _c = st.columns([3, 1])
            chosen = _c[0].multiselect('Liqalar', list(names), format_func=lambda k_: names[k_], key='ko_api_leagues',
                                       help='Hər liqa 2 kredit çəkir. Yalnız lazım olanları seç.')
            _c[1].markdown('<div style="height:1.7rem"></div>', unsafe_allow_html=True)
            if _c[1].button('📡 Gətir', key='ko_api_go', disabled=not chosen, use_container_width=True):
                with st.spinner('Yüklənir...'):
                    dfa, errs, left = ko_api_fetch(key, chosen, names)
                st.session_state['ko_api_df'] = dfa
                if errs:
                    st.warning('Yüklənməyənlər: ' + '; '.join(errs))
                st.success(f'{len(dfa)} oyun gətirildi.' + (f' Qalan kredit: {left}.' if left is not None else ''))
            if st.session_state.get('ko_api_df') is not None and len(st.session_state['ko_api_df']):
                st.caption('Bet365 Odds API-də yoxdur: "Bet365" seçsən orta kofsent göstərilir.')

    # ---- Oyun seçimi (kofsentlər avtomatik dolur) ----
    fx = ko_load_fixtures()
    api_df = st.session_state.get('ko_api_df')
    if api_df is not None and len(api_df):
        fx = pd.concat([fx, api_df], ignore_index=True) if not fx.empty else api_df.copy()
    if not fx.empty:
        fx = fx.assign(**{f'o_{k}': fx[f'{src}_{k}'] for k in 'hdaou'})
    lookup = {}
    f = pd.DataFrame()
    if not fx.empty:
        span = st.radio('Oyunlar', ['Bu gün', 'Bu gün + sabah', 'Növbəti 7 gün', 'Fayldakı hamısı'], horizontal=True, key='ko_span')
        days = {'Bu gün': 0, 'Bu gün + sabah': 1, 'Növbəti 7 gün': 7}.get(span)
        t0 = baku_today()
        f = fx if days is None else fx[(fx['date'].dt.date >= t0) & (fx['date'].dt.date <= t0 + timedelta(days=days))]
        f = f.dropna(subset=['o_h', 'o_d', 'o_a'], how='all').sort_values(['date', 'time'])
        if f.empty:
            st.caption(f'Bu seçim üçün oyun yoxdur. Fayldakı oyunların tarixi: {fx["date"].min():%d.%m.%Y} – {fx["date"].max():%d.%m.%Y}. '
                       '"Fayldakı hamısı"nı seç və ya kofsentləri əllə yaz.')
        else:
            _fcfg = {c_: st.column_config.NumberColumn(c_, format='%.2f') for c_ in ('1', 'X', '2', '2.5 üst', '2.5 alt')}
            st.dataframe(pd.DataFrame({
                'Tarix': f['date'].dt.strftime('%d.%m.%Y'),
                'Saat': f['time'].replace('nan', ''),
                'Liqa': f['league'], 'Ev sahibi': f['home'], 'Qonaq': f['away'],
                '1': f['o_h'], 'X': f['o_d'], '2': f['o_a'], '2.5 üst': f['o_o'], '2.5 alt': f['o_u'],
            }), hide_index=True, use_container_width=True, column_config=_fcfg, height=min(420, 38 + 35 * len(f)))
        for _, r in f.iterrows():
            fmt = lambda v: f'{v:.2f}' if pd.notna(v) else '-'
            lab = f"{r['date']:%d.%m} {r['time'] if r['time'] not in ('', 'nan') else ''} · {r['league']} · {r['home']} – {r['away']} · {fmt(r['o_h'])} / {fmt(r['o_d'])} / {fmt(r['o_a'])}"
            lookup[lab] = r
    if lookup:
        for k in ('ko_h', 'ko_d', 'ko_a', 'ko_o', 'ko_u'):
            st.session_state.setdefault(k, 0.0)

        def _ko_pick_game():
            r = lookup.get(st.session_state.get('ko_game'))
            if r is not None:
                for key, col in (('ko_h', 'o_h'), ('ko_d', 'o_d'), ('ko_a', 'o_a'), ('ko_o', 'o_o'), ('ko_u', 'o_u')):
                    st.session_state[key] = round(float(r[col]), 2) if pd.notna(r[col]) else 0.0

        st.selectbox('Oyun seç (kofsentlər aşağıda avtomatik dolacaq)', ['—'] + list(lookup), key='ko_game', on_change=_ko_pick_game)
    else:
        st.caption('Seçilmiş günlər üçün kofsentli oyun tapılmadı (fixtures.csv yalnız əsas liqaların yaxın oyunlarını saxlayır, '
                   'məlumatı yeniləyin). Kofsentləri aşağıda əllə yaz.')
        for k in ('ko_h', 'ko_d', 'ko_a', 'ko_o', 'ko_u'):
            st.session_state.setdefault(k, 0.0)

    c = st.columns(5)
    h = c[0].number_input('1 (ev sahibi)', 0.0, 100.0, step=0.01, format='%.2f', key='ko_h')
    d = c[1].number_input('X (heç-heçə)', 0.0, 100.0, step=0.01, format='%.2f', key='ko_d')
    a = c[2].number_input('2 (qonaq)', 0.0, 100.0, step=0.01, format='%.2f', key='ko_a')
    o = c[3].number_input('2.5 üst', 0.0, 100.0, step=0.01, format='%.2f', key='ko_o')
    u = c[4].number_input('2.5 alt', 0.0, 100.0, step=0.01, format='%.2f', key='ko_u')
    st.caption('0 yazılan kofsent nəzərə alınmır. Məsələn yalnız 1 = 1.25 yazsan, 1 kofsenti ~1.25 olan bütün oyunlar tapılacaq.')

    c2 = st.columns(3)
    tol = c2[0].slider('Kofsent fərqi (±%)', 1, 15, 4, key='ko_tol',
                       help='4% olsa 3.20 üçün 3.07–3.33 aralığındakı oyunlar tapılır. Az oyun tapılsa artır.')
    years = c2[1].slider('Neçə il geriyə', 1, KO_N_SEASONS, KO_N_SEASONS, key='ko_years')
    leagues = sorted(hist['league'].dropna().unique())
    sel = c2[2].multiselect('Liqa (boş = hamısı)', leagues, key='ko_leagues')

    if len(f):
        st.divider()
        if st.toggle('📊 Yuxarıdakı bütün oyunlar üçün keçmiş analizi avtomatik göstər', value=True, key='ko_batch_on'):
            B = ko_batch(f, hist, tol, years, sel)
            if B.empty:
                st.info('Bu oyunların 1/X/2 kofsentləri tam deyil, analiz hesablanmadı.')
            else:
                st.caption('Hər oyun üçün: keçmişdə eyni 1/X/2 kofsentli oyunlarda nəticələrin faizi. "Bukmeker %" kofsentin özündən çıxan gözləntidir. '
                           'Sütun başlığına basıb sıralaya bilərsən. Oxşar oyun 30-dan azdırsa, faizə etibar etmə.')
                st.dataframe(B, hide_index=True, use_container_width=True, height=min(560, 38 + 35 * len(B)))
        st.divider()
        st.markdown('**Tək oyunu ətraflı analiz et** (yuxarıdan oyun seç və ya kofsentləri yaz):')

    given = [(col, v) for col, v in (('o_h', h), ('o_d', d), ('o_a', a), ('o_o', o), ('o_u', u)) if v > 1]
    if not given:
        st.info('Ən azı bir kofsent yaz və ya yuxarıdan oyun seç.')
        return
    mask = hist['date'] >= (pd.Timestamp(baku_today()) - pd.Timedelta(days=365 * years))
    for col, v in given:
        mask &= (hist[col] - v).abs() <= v * tol / 100
    if sel:
        mask &= hist['league'].isin(sel)
    M = hist[mask]
    n = len(M)
    base_n = int((hist['date'] >= (pd.Timestamp(baku_today()) - pd.Timedelta(days=365 * years))).sum())
    st.markdown(f'**Tapılan keçmiş oyun: {n}** (bazada {base_n} oyun)')
    if n == 0:
        st.warning('Bu kofsentlərlə oyun tapılmadı. "Kofsent fərqi"ni artır və ya bəzi kofsentləri 0 et.')
        return
    if n < 30:
        st.warning('⚠️ 30-dan az oyun var, faizlər təsadüfi ola bilər.')

    tot = M['ft_h'] + M['ft_a']
    # ---- 1 / X / 2 ----
    w1, wx, w2 = int((M['ft_h'] > M['ft_a']).sum()), int((M['ft_h'] == M['ft_a']).sum()), int((M['ft_h'] < M['ft_a']).sum())
    imp = ['', '', '']
    if h > 1 and d > 1 and a > 1:
        raw = [1 / h, 1 / d, 1 / a]
        s = sum(raw)
        imp = [f'{r / s * 100:.1f}%' for r in raw]
    m = st.columns(3)
    for col, lab, cnt, im in zip(m, ('1 (ev sahibi qalib)', 'X (heç-heçə)', '2 (qonaq qalib)'), (w1, wx, w2), imp):
        col.metric(lab, f'{cnt} / {n}', _ko_pct(cnt, n), delta_color='off', help=f'Bukmekerin gözləntisi: {im}' if im else None)
    if imp[0]:
        st.caption(f'Bukmekerin gözləntisi (marjasız): 1 = {imp[0]}, X = {imp[1]}, 2 = {imp[2]}')

    # ---- Üst / Alt ----
    rows = []
    for ln in (0.5, 1.5, 2.5, 3.5, 4.5):
        ov = int((tot > ln).sum())
        rows.append({'Xətt': f'{ln}', 'Üst (oyun)': ov, 'Üst %': _ko_pct(ov, n), 'Alt (oyun)': n - ov, 'Alt %': _ko_pct(n - ov, n)})
    st.markdown('**Üst / Alt (tam oyun)**')
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    btts = int(((M['ft_h'] > 0) & (M['ft_a'] > 0)).sum())
    st.caption(f'Orta qol: {tot.mean():.2f} · Hər iki komanda qol vurur: bəli {btts} ({_ko_pct(btts, n)}), xeyr {n - btts} ({_ko_pct(n - btts, n)})')

    # ---- İlk yarı ----
    HT = M.dropna(subset=['ht_h', 'ht_a'])
    k = len(HT)
    st.markdown(f'**İlk yarı** (məlumatı olan oyun: {k})')
    if k:
        hts = HT['ht_h'] + HT['ht_a']
        rows = []
        for ln in (0.5, 1.5):
            ov = int((hts > ln).sum())
            rows.append({'Xətt': f'I yarı {ln}', 'Üst (oyun)': ov, 'Üst %': _ko_pct(ov, k), 'Alt (oyun)': k - ov, 'Alt %': _ko_pct(k - ov, k)})
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        a1, ax, a2 = int((HT['ht_h'] > HT['ht_a']).sum()), int((HT['ht_h'] == HT['ht_a']).sum()), int((HT['ht_h'] < HT['ht_a']).sum())
        st.caption(f'I yarı nəticə: 1 = {_ko_pct(a1, k)}, X = {_ko_pct(ax, k)}, 2 = {_ko_pct(a2, k)} · I yarıda orta qol: {hts.mean():.2f}')
    else:
        st.caption('Bu oyunlar üçün ilk yarı məlumatı yoxdur.')

    # ---- Ən çox rast gələn hesablar ----
    sc = (M['ft_h'].astype(int).astype(str) + '-' + M['ft_a'].astype(int).astype(str)).value_counts().head(6)
    st.caption('Ən çox rast gələn hesablar: ' + ' · '.join(f'{s_} ({c_} dəfə, {_ko_pct(c_, n)})' for s_, c_ in sc.items()))

    # ---- Oyun siyahısı ----
    show = pd.DataFrame({
        'Tarix': M['date'].dt.strftime('%d.%m.%Y'),
        'Liqa': M['league'],
        'Ev sahibi': M['home'],
        'Qonaq': M['away'],
        'Hesab': M['ft_h'].astype(int).astype(str) + '-' + M['ft_a'].astype(int).astype(str),
        'I yarı': [f'{int(x)}-{int(y)}' if pd.notna(x) and pd.notna(y) else '?' for x, y in zip(M['ht_h'], M['ht_a'])],
        'Kofsent 1 / X / 2': [' / '.join(f'{v:.2f}' if pd.notna(v) else '-' for v in r) for r in zip(M['o_h'], M['o_d'], M['o_a'])],
        '2.5 üst/alt kof.': [' / '.join(f'{v:.2f}' if pd.notna(v) else '-' for v in r) for r in zip(M['o_o'], M['o_u'])],
    })
    st.markdown('**Keçmiş oyunlar (yeni → köhnə)**')
    st.dataframe(show, hide_index=True, use_container_width=True, height=420)
    st.download_button('⬇️ Siyahını CSV kimi yüklə', show.to_csv(index=False).encode('utf-8-sig'), 'kofsent_kecmis.csv', 'text/csv', key='ko_csv')


with st.expander('🎯 Kofsent üzrə keçmiş analiz — eyni kofsentli keçmiş oyunlar', expanded=False):
    try:
        render_kofsent_section()
    except Exception as e:
        st.error(f'Kofsent bölməsi xəta verdi: {e}')
# ===== KOFSENT BÖLMƏSİ (son) =====

with st.expander('Məlumat bazası haqqında'):
    show_info = st.checkbox('Ətraflı məlumatı göstər (yavaş ola bilər)', key='show_info', value=False)
    if not show_info:
        st.caption('Ətraflı məlumat üçün yuxarıdakı qutunu işarələ.')
    else:
        st.write(f'Çempionat qovluqları: {len(list(DATA_DIR.iterdir())) if DATA_DIR.exists() else 0}. Qarşıdakı oyun sətri: {len(fixtures)}. Tarixi nəticə sətri: {len(results)}. Siyahıdakı liqa sayı: {len(league_options)}.')
        st.write('Mənbələr: Open Matchday — https://github.com/oladeeayo/open-matchday, football-data.co.uk (əsas və əlavə liqalar), openfootball (https://github.com/openfootball/football.json), international_results (https://github.com/martj42/international_results, milli komandalar) ESPN (qitə kubokları, daxili kuboklar və onlarla liqa) Eyni oyun bir neçə mənbədə varsa statistika üçün əvvəlcə football-data.co.uk, sonra Open Matchday, sonra openfootball, sonra ESPN götürülür. Künc, zərbə və qapıya dəqiq zərbə statistikası football-data.co.uk əsas liqalarında, Open Matchday-də və ESPN-in yüklədiyi oyunlarda var. Statistikası olmayan oyunlar müvafiq statistik filtrdə uyğun sayılmır.')
        st.write(f'Əlavə liqa faylları (football-data.co.uk/new): {len(list(FDX_DIR.glob("*.csv"))) if FDX_DIR.exists() else 0}. openfootball faylları: {len(list(OF_DIR.glob("*.json"))) if OF_DIR.exists() else 0}.')
        if FD_DIR.exists() and any(FD_DIR.glob('*.csv')):
            st.write(f'football-data.co.uk faylları: {len(list(FD_DIR.glob("*.csv")))}.')
        else:
            st.write('football-data.co.uk hələ yüklənməyib — yuxarıdakı "Məlumatı yenilə" düyməsinə bas.')
        if (ESPN_DIR / 'results.csv').exists():
            st.write('ESPN fayllarından oxunan nəticə sayı: ' + str(len(read_csv_safe(ESPN_DIR / 'results.csv'))) + '.')
        else:
            st.write('ESPN hələ yüklənməyib — yuxarıdakı "Məlumatı yenilə" düyməsinə bas.')
        if fd_only_teams:
            st.write(f'Yalnız football-data.co.uk-də tapılan komandalar: {len(fd_only_teams)}. Əgər bunların arasında Open Matchday-də başqa cür yazılan komanda varsa, app.py-dakı ALIASES siyahısına əlavə et.')
            st.code('\n'.join(fd_only_teams))
