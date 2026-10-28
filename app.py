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
.block-container { padding-top: 3.6rem; padding-bottom: 6rem; max-width: 1180px; }
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
div.st-key-coupon_float_button button {
  min-height: 52px !important; border-radius: 15px !important; white-space: nowrap !important;
  background: #1f2937 !important; color: #f9fafb !important; border: 1.5px solid #16a34a !important; font-weight: 700 !important;
}
div.st-key-coupon_float_button button p, div.st-key-coupon_float_button button span { color: #f9fafb !important; }
div.st-key-analyze_button button, div.st-key-analyze_button button p { color: #fff !important; }
div.st-key-coupon_float_panel {
  position: fixed !important; left: 12px !important; bottom: 84px !important;
  z-index: 100001 !important; width: min(420px, calc(100vw - 24px)) !important;
  max-height: 65vh !important; overflow-y: auto !important;
  padding: 12px !important; border: 1px solid rgba(128,128,128,.4) !important;
  border-radius: 16px !important; background: #111827 !important; color: #f9fafb !important;
  box-shadow: 0 10px 35px rgba(0,0,0,.45) !important;
}
div.st-key-coupon_float_panel *:not(button):not(button *) { color: #f9fafb !important; }
div.st-key-coupon_float_panel [data-testid="stCaptionContainer"], div.st-key-coupon_float_panel [data-testid="stCaptionContainer"] * { color: #9ca3af !important; }
div.st-key-coupon_float_panel button { background: #1f2937 !important; color: #f9fafb !important; border: 1px solid rgba(255,255,255,.18) !important; }
div.st-key-coupon_float_panel button p { color: #f9fafb !important; }
@media (max-width: 600px) {
  /* Mobil: iki düymə eyni sətirdə, bir-birinə girmir; Streamlit "Manage app" nişanının üstündə. */
  div.st-key-coupon_float_button { left: 10px !important; right: auto !important; bottom: 105px !important; width: 148px !important; }
  div.st-key-coupon_float_button button { width: 100% !important; min-width: 0 !important; padding: 0 8px !important; font-size: 13px !important; }
  div.st-key-analyze_button { left: 166px !important; right: 10px !important; bottom: 105px !important; transform: none !important; width: auto !important; max-width: none !important; }
  div.st-key-analyze_button button { width: 100% !important; min-width: 0 !important; padding: 0 8px !important; font-size: 13px !important; }
  div.st-key-coupon_float_panel { left: 8px !important; bottom: 120px !important; width: calc(100vw - 16px) !important; max-height: 60vh !important; }
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
  .block-container { padding: 3.4rem .65rem 6.5rem !important; max-width: 100% !important; }
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
  div.st-key-analyze_button { bottom: calc(105px + env(safe-area-inset-bottom)) !important; width: auto !important; max-width: none !important; }
  div.st-key-analyze_button button { width: 100% !important; min-height: 48px !important; font-size: 15px !important; border-radius: 13px !important; }
  /* Mobil: tarix oxları, tarix seçicisi və sağ ox həmişə bir sətirdə qalsın. */
  [class*="st-key-start_date_row"] [data-testid="stHorizontalBlock"],
  [class*="st-key-end_date_row"] [data-testid="stHorizontalBlock"] {
    display: flex !important; flex-direction: row !important; flex-wrap: nowrap !important;
    align-items: center !important; gap: 3px !important; width: 100% !important;
  }
  [class*="st-key-start_date_row"] [data-testid="stColumn"],
  [class*="st-key-start_date_row"] [data-testid="column"],
  [class*="st-key-end_date_row"] [data-testid="stColumn"],
  [class*="st-key-end_date_row"] [data-testid="column"] {
    min-width: 0 !important; flex-shrink: 1 !important;
  }
  [class*="st-key-start_date_row"] [data-testid="stColumn"]:first-child,
  [class*="st-key-start_date_row"] [data-testid="column"]:first-child,
  [class*="st-key-start_date_row"] [data-testid="stColumn"]:last-child,
  [class*="st-key-start_date_row"] [data-testid="column"]:last-child,
  [class*="st-key-end_date_row"] [data-testid="stColumn"]:first-child,
  [class*="st-key-end_date_row"] [data-testid="column"]:first-child,
  [class*="st-key-end_date_row"] [data-testid="stColumn"]:last-child,
  [class*="st-key-end_date_row"] [data-testid="column"]:last-child { flex: 0 0 1.8rem !important; }
  [class*="st-key-start_date_row"] [data-testid="stColumn"]:nth-child(2),
  [class*="st-key-start_date_row"] [data-testid="column"]:nth-child(2),
  [class*="st-key-end_date_row"] [data-testid="stColumn"]:nth-child(2),
  [class*="st-key-end_date_row"] [data-testid="column"]:nth-child(2) { flex: 1 1 0 !important; }
  [class*="st-key-start_date_row"] button, [class*="st-key-end_date_row"] button {
    min-width: 1.8rem !important; width: 1.8rem !important; height: 2.25rem !important;
    min-height: 2.25rem !important; padding: 0 !important; font-size: .85rem !important;
  }
  [class*="st-key-start_date_row"] [data-testid="stDateInput"],
  [class*="st-key-end_date_row"] [data-testid="stDateInput"] { min-width: 0 !important; width: 100% !important; }
  [class*="st-key-start_date_row"] [data-testid="stDateInput"] input,
  [class*="st-key-end_date_row"] [data-testid="stDateInput"] input { min-width: 0 !important; width: 100% !important; font-size: .78rem !important; padding: 0 .2rem !important; }
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


def refresh_espn(days_back=None):
    """days_back verilsə (sürətli rejim): yalnız son N günün oyunları yenilənir, statistikası gəlməyən oyunun cəhd sayı artmır."""
    quick = days_back is not None
    ESPN_DIR.mkdir(exist_ok=True)
    old_res_path = ESPN_DIR / 'results.csv'
    first = not old_res_path.exists()
    today_ = datetime.utcnow().date()
    start = today_ - timedelta(days=days_back if (quick and not first) else (ESPN_DAYS_BACK_FIRST if first else ESPN_DAYS_BACK))
    end = today_ + timedelta(days=(2 if quick and not first else ESPN_DAYS_AHEAD))
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
                if st_ or not quick:
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
            hh_, ha_ = _espn_ht(h), _espn_ht(a)
            out.append({'home': h['team']['displayName'], 'away': a['team']['displayName'], 'hs': int(hs), 'as': int(as_),
                        'ht_h': int(hh_) if pd.notna(hh_) else None, 'ht_a': int(ha_) if pd.notna(ha_) else None,
                        'id': str(ev.get('id', '')), 'slug': slug,
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
LAST_QUICK_FILE = ROOT / 'last_quick_refresh.txt'
AUTO_REFRESH_HOUR = 7   # Bakı vaxtı ilə hər səhər: tam yeniləmə
AUTO_QUICK_MINUTES = 30  # gün ərzində: yalnız ESPN (son 3 gün) + yeni bitmiş oyunların statistikası


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
                elif not _state['running'] and _rf_time.time() - _state.get('quick_last', 0) >= AUTO_QUICK_MINUTES * 60:
                    _state['quick_last'] = _rf_time.time()
                    refresh_espn(days_back=3)
                    LAST_QUICK_FILE.write_text(pd.Timestamp.now(tz='Asia/Baku').isoformat(), encoding='utf-8')
            except Exception:
                _state['quick_last'] = _rf_time.time()
            _rf_time.sleep(60)
    _rf_threading.Thread(target=loop, daemon=True).start()
    return True


_scheduler_start(_refresh_state())
def _open_pct():
    st.session_state['view_page'] = 'pct'


def _close_pct():
    st.session_state['view_page'] = 'main'


if st.session_state.get('view_page') != 'pct':
    st.button('📈 Faiz səhifəsi — günün oyunları faizlə', key='pct_nav', use_container_width=True, on_click=_open_pct)
_rs0 = _refresh_state()
with st.container(border=True, key='db_panel'):
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
    st.caption(f'🕖 Tam yeniləmə: hər gün {AUTO_REFRESH_HOUR:02d}:00 (Bakı), gün ərzində hər {AUTO_QUICK_MINUTES} dəq. sürətli (ESPN). Sonuncu tam yeniləmə: '
               + (_lr.strftime('%Y-%m-%d %H:%M') if _lr is not None else 'məlum deyil'))
    st.caption('Yeniləmə internet tələb edir. Əvvəl yüklənmiş məlumatlar internet olmadan da analiz edilə bilər.')
    import os as _os
    def _has_key(nm):
        try:
            v = st.secrets.get(nm, '')
        except Exception:
            v = ''
        return bool(str(v or _os.environ.get(nm, '')).strip())
    try:
        _u = json.loads((ROOT / 'apif_cache.json').read_text(encoding='utf-8')).get('used', {})
        _used = int(_u.get('n', 0)) if _u.get('day') == baku_today().isoformat() else 0
    except Exception:
        _used = 0
    st.caption('🔌 Canlı mənbələr (faiz səhifəsində hesab, 1-ci hissə, statistika üçün; bazanın yenilənməsinə aid deyil): '
               f"API-Football {'✓ açar var · bu gün ' + str(_used) + ' sorğu' if _has_key('APIFOOTBALL_KEY') else '✗ açar yoxdur'} · "
               f"football-data.org {'✓ açar var' if _has_key('FOOTBALLDATA_KEY') else '✗ açar yoxdur'}")

fixtures, results, fd_only_teams = load_data()



if fixtures.empty:
    st.error('Oyun cədvəlləri tapılmadı. ZIP-i tam çıxartdığını yoxla və ya yuxarıdakı "Məlumatı yenilə" düyməsindən yenilə.')
    st.stop()

# ======================= FAİZ SƏHİFƏSİ (2-ci səhifə) =======================
# Seçilmiş günün oyunları: hər komandanın son N oyununda filtrlərin neçə dəfə tutduğu (8/10 = 80%).
# Filtrlər "➕" ilə əlavə olunur, nəticə avtomatik yenilənir. Məlumatı kəsik oyunlar siyahının sonunda qalır.
_PCT_BASE = 100000
_PCT_STAT = ['Matç künc ≥', 'Klub künc ≥', 'Matç zərbə ≥', 'Klub zərbə ≥', 'Matç dəqiq zərbə ≥', 'Klub dəqiq zərbə ≥']
_PCT_DEF = (9, 4, 22, 11, 8, 4)


def _pct_num(df, col):
    return pd.to_numeric(df[col], errors='coerce') if col in df.columns else pd.Series(np.nan, index=df.index)


def _pct_atleast(d, ch, ca, mode, thr):
    a, b = _pct_num(d, ch), _pct_num(d, ca)
    has = a.notna() & b.notna()
    if mode == 'Klub':
        return a >= thr, b >= thr, has
    p = (a + b) >= thr
    return p, p, has


def _pct_catalog(thr):
    """Filtr adı -> funksiya. Funksiya (ev baxışı ödənir, qonaq baxışı ödənir, məlumat var) qaytarır."""
    cat = {}

    def ft(d):
        hg, ag = _pct_num(d, 'ft_home'), _pct_num(d, 'ft_away')
        return hg, ag, hg.notna() & ag.notna()

    def ht(d):
        a, b = _pct_num(d, 'ht_home'), _pct_num(d, 'ht_away')
        return a, b, a.notna() & b.notna()

    def same(fn):
        def inner(d):
            p, has = fn(d)
            return p, p, has
        return inner

    for L in (1.5, 2.5, 3.5, 4.5):
        cat[f'Matç {L} üst'] = (lambda thr: lambda d: _pct_atleast(d, 'ft_home', 'ft_away', 'Oyunda', thr))(int(L) + 1)
    for L in (1.5, 2.5, 3.5):
        cat[f'Matç {L} alt'] = (lambda lim: same(lambda d: (lambda hg, ag, has: (hg + ag <= lim, has))(*ft(d))))(int(L))
    cat['BTTS (hər ikisi qol vurur)'] = same(lambda d: (lambda hg, ag, has: ((hg > 0) & (ag > 0), has))(*ft(d)))
    cat['BTTS yox'] = same(lambda d: (lambda hg, ag, has: (~((hg > 0) & (ag > 0)), has))(*ft(d)))
    for L in (0.5, 1.5, 2.5):
        cat[f'Klub {L} üst'] = (lambda thr: lambda d: _pct_atleast(d, 'ft_home', 'ft_away', 'Klub', thr))(int(L) + 1)
    for L in (0.5, 1.5):
        cat[f'1-ci hissə {L} üst'] = (lambda thr: lambda d: _pct_atleast(d, 'ht_home', 'ht_away', 'Oyunda', thr))(int(L) + 1)
    cat['1-ci hissə 0.5 alt (qol yoxdur)'] = same(lambda d: (lambda a, b, has: (a + b == 0, has))(*ht(d)))
    cat['1-ci hissə 1.5 alt'] = same(lambda d: (lambda a, b, has: (a + b <= 1, has))(*ht(d)))
    cat['1-ci hissə heç-heçə'] = same(lambda d: (lambda a, b, has: (a == b, has))(*ht(d)))
    for L in (0.5, 1.5):
        cat[f'Klub 1-ci hissə {L} üst'] = (lambda thr: lambda d: _pct_atleast(d, 'ht_home', 'ht_away', 'Klub', thr))(int(L) + 1)
    cols = {'künc': ('home_corners', 'away_corners'), 'dəqiq zərbə': ('home_target', 'away_target'), 'zərbə': ('home_shots', 'away_shots')}
    for nm, t in zip(_PCT_STAT, thr):
        key = 'künc' if 'künc' in nm else ('dəqiq zərbə' if 'dəqiq' in nm else 'zərbə')
        ch, ca = cols[key]
        cat[nm] = (lambda ch_, ca_, mode_, t_: lambda d: _pct_atleast(d, ch_, ca_, mode_, t_))(ch, ca, 'Klub' if nm.startswith('Klub') else 'Oyunda', t)
    # Siyahı sırası: əvvəl ən çox işlənənlər, sonra qalanları
    first = ['1-ci hissə 0.5 üst', '1-ci hissə 1.5 üst', 'Matç 2.5 üst', 'Matç 3.5 üst', 'BTTS (hər ikisi qol vurur)']
    return {**{k: cat[k] for k in first if k in cat}, **{k: v for k, v in cat.items() if k not in first}}


def _pct_label(nm, thr):
    return f'{nm} {thr[_PCT_STAT.index(nm)]}' if nm in _PCT_STAT else nm


@st.cache_data(show_spinner='Faizlər hesablanır...', max_entries=12)
def _pct_history(_res, names, thr, sig):
    cat = _pct_catalog(thr)
    ok_h = pd.Series(True, index=_res.index)
    ok_a = pd.Series(True, index=_res.index)
    has_all = pd.Series(True, index=_res.index)
    for nm in names:
        p_h, p_a, hs = cat[nm](_res)
        ok_h &= p_h.fillna(False)
        ok_a &= p_a.fillna(False)
        has_all &= hs
    # Yalnız lazımi statistikası olan oyunlar sayılır: "son N oyun" = statistikası olan son N oyun.
    m = has_all.values
    hk, ak = _res['home_k'].values[m], _res['away_k'].values[m]
    teams = np.concatenate([hk, ak])
    codes, uniques = pd.factorize(teams)
    day = pd.to_datetime(_res['date']).values.astype('datetime64[D]').astype('int64')[m]
    days = np.concatenate([day, day])
    hit = np.concatenate([ok_h.values[m], ok_a.values[m]]).astype(np.int64)
    key = codes.astype(np.int64) * _PCT_BASE + days
    order = np.argsort(key, kind='stable')
    return {'key': key[order], 'cs_hit': np.concatenate([[0], np.cumsum(hit[order])]),
            'code_of': {t: i for i, t in enumerate(uniques)}}


def _pct_for(H, team_arr, day_arr, n):
    """Hər komanda üçün: son n oyunda tutan say, statistikası olan oyun sayı, faiz."""
    codes = np.fromiter((H['code_of'].get(t, -1) for t in team_arr), dtype=np.int64, count=len(team_arr))
    hi = np.searchsorted(H['key'], codes * _PCT_BASE + day_arr, side='left')
    lo = np.searchsorted(H['key'], codes * _PCT_BASE, side='left')
    k = np.minimum(hi - lo, n)
    start = hi - k
    hits = H['cs_hit'][hi] - H['cs_hit'][start]
    den = np.where(codes < 0, 0, k)
    pct = np.where(den > 0, hits / np.maximum(den, 1) * 100, np.nan)
    return hits, den, pct


# ---- API-Football (api-sports.io): hesab + 1-ci hissə + künc/zərbə (ESPN-in çatışmayanını tamamlayır) ----
# Açar: Streamlit Secrets-də  APIFOOTBALL_KEY = "..."  (və ya mühit dəyişəni). Kodun içinə yazılmır ki, GitHub-da görünməsin.
APIF_BASE = 'https://v3.football.api-sports.io'
APIF_DAILY_CAP = 90          # pulsuz plan: gündə 100 sorğu; bunu keçməsin
APIF_STATS_PER_RUN = 25      # bir səhifə yüklənməsində ən çox neçə oyunun statistikası çəkilsin
APIF_FILE = ROOT / 'apif_cache.json'
_apif_lock = _rf_threading.Lock()


def _apif_key():
    try:
        k = st.secrets.get('APIFOOTBALL_KEY', '')
    except Exception:
        k = ''
    import os
    return str(k or os.environ.get('APIFOOTBALL_KEY', '')).strip()


def _apif_load():
    try:
        return json.loads(APIF_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _apif_save(c):
    try:
        APIF_FILE.write_text(json.dumps(c), encoding='utf-8')
    except Exception:
        pass


def _apif_get(path, params):
    """Sorğu göndərir, gündəlik limiti sayır. Qaytarır (response_list, xəta_mətni_və_ya_None)."""
    key = _apif_key()
    if not key:
        return [], 'açar yoxdur'
    today = baku_today().isoformat()
    with _apif_lock:
        c = _apif_load()
        used = c.get('used', {})
        if used.get('day') != today:
            used = {'day': today, 'n': 0}
        if used['n'] >= APIF_DAILY_CAP:
            return [], f'gündəlik limit ({APIF_DAILY_CAP}) dolub'
        used['n'] += 1
        c['used'] = used
        _apif_save(c)
    try:
        r = requests.get(f'{APIF_BASE}/{path}', params=params, headers={'x-apisports-key': key}, timeout=15)
        if r.status_code != 200:
            return [], f'HTTP {r.status_code}'
        j = r.json()
    except (requests.RequestException, ValueError) as e:
        return [], type(e).__name__
    errs = j.get('errors')
    if errs:
        return [], (' · '.join(str(v) for v in errs.values()) if isinstance(errs, dict) else str(errs))[:200]
    return j.get('response') or [], None


_APIF_FINISHED = {'FT', 'AET', 'PEN'}
_APIF_LIVE = {'1H', 'HT', '2H', 'ET', 'BT', 'P', 'LIVE', 'INT'}


@st.cache_data(ttl=300, show_spinner=False)
def _apif_day(date_str):
    """Bir günün bütün oyunları (1 sorğu). Qaytarır (sətirlər, xəta)."""
    resp, err = _apif_get('fixtures', {'date': date_str, 'timezone': 'Asia/Baku'})
    rows = []
    for it in resp:
        try:
            fx, tm, gl, sc = it['fixture'], it['teams'], it.get('goals') or {}, it.get('score') or {}
            sh = (fx.get('status') or {}).get('short', '')
            if sh not in _APIF_FINISHED and sh not in _APIF_LIVE:
                continue
            hs, as_ = gl.get('home'), gl.get('away')
            if hs is None or as_ is None:
                continue
            ht = sc.get('halftime') or {}
            rows.append({'home': tm['home']['name'], 'away': tm['away']['name'],
                         'home_k': team_key(tm['home']['name']), 'away_k': team_key(tm['away']['name']),
                         'hs': int(hs), 'as': int(as_),
                         'ht_h': ht.get('home'), 'ht_a': ht.get('away'),
                         'live': sh in _APIF_LIVE, 'finished': sh in _APIF_FINISHED,
                         'date': pd.to_datetime(fx['date'], utc=True).tz_localize(None).normalize(),
                         'fid': int(fx['id']), 'home_id': tm['home']['id']})
        except (KeyError, TypeError, ValueError):
            continue
    return rows, err


def _apif_stats_parse(resp, home_id):
    out = {}
    for t in resp:
        side = 'home' if (t.get('team') or {}).get('id') == home_id else 'away'
        for it in t.get('statistics') or []:
            typ, v = str(it.get('type', '')).lower(), it.get('value')
            v = 0 if v is None else pd.to_numeric(v, errors='coerce')
            if pd.isna(v):
                continue
            if typ == 'corner kicks':
                out[f'{side}_corners'] = int(v)
            elif typ == 'total shots':
                out[f'{side}_shots'] = int(v)
            elif typ == 'shots on goal':
                out[f'{side}_target'] = int(v)
    for a_, b_ in (('home_corners', 'away_corners'), ('home_shots', 'away_shots'), ('home_target', 'away_target')):
        if not (a_ in out and b_ in out):
            out.pop(a_, None)
            out.pop(b_, None)
    return out


def _apif_stats(fid, home_id):
    """Bitmiş oyunun statistikası; nəticə diskdə saxlanır ki, eyni oyun üçün sorğu təkrar getməsin."""
    with _apif_lock:
        c = _apif_load()
        hit = c.get('stats', {}).get(str(fid))
    if hit is not None:
        return hit
    resp, err = _apif_get('fixtures/statistics', {'fixture': fid})
    if err:
        return {}
    out = _apif_stats_parse(resp, home_id)
    with _apif_lock:
        c = _apif_load()
        c.setdefault('stats', {})[str(fid)] = out
        _apif_save(c)
    return out


# ---- football-data.org (v4): hesab + 1-ci hissə (künc/zərbə vermir). Açar: Secrets-də FOOTBALLDATA_KEY ----
FDORG_BASE = 'https://api.football-data.org/v4'


def _fdorg_key():
    try:
        k = st.secrets.get('FOOTBALLDATA_KEY', '')
    except Exception:
        k = ''
    import os
    return str(k or os.environ.get('FOOTBALLDATA_KEY', '')).strip()


@st.cache_data(ttl=300, show_spinner=False)
def _fdorg_day(date_str):
    """Bir günün oyunları (1 sorğu; pulsuz plan dəqiqədə 10). Qaytarır (sətirlər, xəta)."""
    key = _fdorg_key()
    if not key:
        return [], 'açar yoxdur'
    try:
        r = requests.get(f'{FDORG_BASE}/matches', params={'dateFrom': date_str, 'dateTo': date_str},
                         headers={'X-Auth-Token': key}, timeout=15)
        if r.status_code != 200:
            return [], f'HTTP {r.status_code}'
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        return [], type(e).__name__
    rows = []
    for m in data.get('matches', []) or []:
        try:
            stt = m.get('status', '')
            if stt not in ('FINISHED', 'IN_PLAY', 'PAUSED'):
                continue
            sc = m.get('score') or {}
            ft, ht = sc.get('fullTime') or {}, sc.get('halfTime') or {}
            if ft.get('home') is None or ft.get('away') is None:
                continue
            hn, an = m['homeTeam']['name'], m['awayTeam']['name']
            rows.append({'home': hn, 'away': an, 'home_k': team_key(hn), 'away_k': team_key(an),
                         'hs': int(ft['home']), 'as': int(ft['away']),
                         'ht_h': ht.get('home'), 'ht_a': ht.get('away'),
                         'live': stt != 'FINISHED', 'finished': stt == 'FINISHED',
                         'date': pd.to_datetime(m['utcDate'], utc=True).tz_localize(None).normalize()})
        except (KeyError, TypeError, ValueError):
            continue
    return rows, None


@st.cache_data(ttl=600, show_spinner=False)
def _live_stats_cached(pairs):
    """[(slug, id), ...] -> {id: {home_corners:..}}; bu gün bitmiş oyunların künc/zərbəsi (yeniləmə gözlənilmədən)."""
    from concurrent.futures import ThreadPoolExecutor as _TP
    pairs = list(pairs)
    if not pairs:
        return {}
    with _TP(max_workers=16) as ex:
        got = list(ex.map(lambda t: _espn_stats(t[0], t[1]), pairs))
    return {i: st_ for (_, i), st_ in zip(pairs, got) if st_}


def _pct_overlay_live(g, need_stats=False):
    """Bazada hesabı/yarımvaxtı olmayan (hələ yenilənməmiş) oyunlara canlı ESPN məlumatını əlavə edir."""
    try:
        live = fetch_live_scores()
    except Exception:
        return g
    apif_rows, apif_err = [], None
    # Pulsuz plan yalnız dünən/bu gün/sabah tarixlərinə icazə verir; kənar tarixdə sorğu göndərib limiti əbəs yerə xərcləmirik
    if _apif_key() and not g.empty and abs((pd.Timestamp(g['date'].iloc[0]).date() - baku_today()).days) <= 1:
        apif_rows, apif_err = _apif_day(pd.Timestamp(g['date'].iloc[0]).strftime('%Y-%m-%d'))
    st.session_state['_apif_err'] = apif_err
    fd_rows, fd_err = [], None
    if _fdorg_key() and not g.empty:
        fd_rows, fd_err = _fdorg_day(pd.Timestamp(g['date'].iloc[0]).strftime('%Y-%m-%d'))
    st.session_state['_fd_err'] = fd_err
    if (not live and not apif_rows and not fd_rows) or g.empty:
        return g
    live = list(live or [])
    g = g.copy()
    idx = {}
    for r in live:
        idx.setdefault((r['home_k'], r['away_k']), []).append(r)
    aidx, fidx = {}, {}
    for r in fd_rows:
        fidx.setdefault((r['home_k'], r['away_k']), []).append(r)
    for r in apif_rows:
        aidx.setdefault((r['home_k'], r['away_k']), []).append(r)
    for c in ('ft_home', 'ft_away', 'ht_home', 'ht_away', 'home_corners', 'away_corners',
              'home_shots', 'away_shots', 'home_target', 'away_target'):
        if c not in g.columns:
            g[c] = np.nan
    pend, apend = [], []
    for i in g.index:
        hk, ak, dt = g.at[i, 'home_k'], g.at[i, 'away_k'], pd.Timestamp(g.at[i, 'date'])
        def _find(ix, rows):
            c_ = ix.get((hk, ak))
            if not c_:
                c_ = [r for r in rows if names_compatible(r['home_k'], hk) and names_compatible(r['away_k'], ak)]
            return [r for r in (c_ or []) if abs((r['date'] - dt.normalize()).days) <= 1]
        e_c, a_c, f_c = _find(idx, live), _find(aidx, apif_rows), _find(fidx, fd_rows)
        # Əvvəl ESPN, çatışmayanı API-Football, sonra football-data.org tamamlayır
        for r in e_c + a_c + f_c:
            if pd.isna(g.at[i, 'ft_home']) or pd.isna(g.at[i, 'ft_away']):
                g.at[i, 'ft_home'], g.at[i, 'ft_away'] = r['hs'], r['as']
            if (pd.isna(g.at[i, 'ht_home']) or pd.isna(g.at[i, 'ht_away'])) and r.get('ht_h') is not None and r.get('ht_a') is not None:
                g.at[i, 'ht_home'], g.at[i, 'ht_away'] = r['ht_h'], r['ht_a']
        if need_stats and pd.isna(g.at[i, 'home_corners']):
            if e_c and not e_c[0]['live'] and e_c[0].get('id'):
                pend.append((i, e_c[0]['slug'], e_c[0]['id']))
            if a_c and a_c[0]['finished']:
                apend.append((i, a_c[0]['fid'], a_c[0]['home_id']))
    if pend:
        st_map = _live_stats_cached(tuple(sorted({(sl, ev) for _, sl, ev in pend})))
        for i, _, ev in pend:
            for k, v in (st_map.get(ev) or {}).items():
                if k in g.columns:
                    g.at[i, k] = v
    # ESPN statistikası gətirməyən bitmiş oyunlar üçün API-Football (sorğu sayı məhduddur, nəticə diskdə saxlanır)
    left = [t for t in apend if pd.isna(g.at[t[0], 'home_corners'])][:APIF_STATS_PER_RUN]
    if left:
        with ThreadPoolExecutor(max_workers=6) as ex:
            got = list(ex.map(lambda t: _apif_stats(t[1], t[2]), left))
        for (i, _, _), st_ in zip(left, got):
            for k, v in (st_ or {}).items():
                if k in g.columns and pd.isna(g.at[i, k]):
                    g.at[i, k] = v
    return g


def _pct_games(d, need_stats=False):
    d = pd.Timestamp(d).normalize()
    base = ['date', 'time', 'home', 'away', 'league', 'home_k', 'away_k']
    extra = ['ft_home', 'ft_away', 'ht_home', 'ht_away', 'home_corners', 'away_corners',
             'home_shots', 'away_shots', 'home_target', 'away_target']
    rs = results[results['date'].dt.normalize() == d]
    fx = fixtures[fixtures['date'].dt.normalize() == d]
    parts = []
    for df in (rs, fx):
        if df.empty:
            continue
        df = df.copy()
        for c in base + extra:
            if c not in df.columns:
                df[c] = np.nan
        parts.append(df[base + extra])
    if not parts:
        return pd.DataFrame(columns=base + extra)
    g = pd.concat(parts, ignore_index=True).dropna(subset=['home', 'away', 'home_k', 'away_k'])
    g = g.drop_duplicates(subset=['home_k', 'away_k'], keep='first').reset_index(drop=True)
    return _pct_overlay_live(g, need_stats)


def _pct_shift(days):
    if days == 0:
        st.session_state['p_date'] = baku_today()
    else:
        st.session_state['p_date'] = st.session_state['p_date'] + timedelta(days=days)


def _pct_add():
    nm = st.session_state.get('p_add_sel')
    lst = st.session_state.setdefault('p_flt', [])
    if nm and nm not in lst:
        lst.append(nm)


def _pct_add_named(nm):
    lst = st.session_state.setdefault('p_flt', [])
    if nm not in lst:
        lst.append(nm)


def _pct_remove(nm):
    st.session_state['p_flt'] = [x for x in st.session_state.get('p_flt', []) if x != nm]


def _pct_score(a, b):
    return [f'{int(x)}–{int(y)}' if pd.notna(x) and pd.notna(y) else '' for x, y in zip(a, b)]


def _pct_stat_txt(a, b):
    """Ev-Qonaq (cəm) formatı: 7-5 (12). Məlumat yoxdursa boş."""
    return [f'{int(x)}-{int(y)} ({int(x) + int(y)})' if pd.notna(x) and pd.notna(y) else '' for x, y in zip(a, b)]


# Filtr adı -> (sütun adı, ev sütunu, qonaq sütunu)
_PCT_STAT_COLS = {'künc': ('Künc', 'home_corners', 'away_corners'),
                  'dəqiq zərbə': ('Dəqiq zərbə', 'home_target', 'away_target'),
                  'zərbə': ('Zərbə', 'home_shots', 'away_shots')}


def render_pct_page():
    st.markdown("""<style>
    .st-key-db_panel { display: none !important; }
    .st-key-pct_datenav [data-testid="stHorizontalBlock"], .st-key-pct_addrow [data-testid="stHorizontalBlock"], [class*="st-key-pct_fl_"] [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: nowrap !important; gap: .4rem !important; align-items: center !important; }
    .st-key-pct_datenav [data-testid="stColumn"], .st-key-pct_datenav [data-testid="column"] { min-width: 0 !important; width: auto !important; flex: 1 1 0 !important; }
    .st-key-pct_datenav [data-testid="stColumn"]:nth-child(2), .st-key-pct_datenav [data-testid="column"]:nth-child(2) { flex: 4 1 0 !important; }
    .st-key-pct_addrow [data-testid="stColumn"], .st-key-pct_addrow [data-testid="column"], [class*="st-key-pct_fl_"] [data-testid="stColumn"], [class*="st-key-pct_fl_"] [data-testid="column"] { min-width: 0 !important; width: auto !important; }
    .st-key-pct_addrow [data-testid="stColumn"]:nth-child(1), .st-key-pct_addrow [data-testid="column"]:nth-child(1), [class*="st-key-pct_fl_"] [data-testid="stColumn"]:nth-child(1), [class*="st-key-pct_fl_"] [data-testid="column"]:nth-child(1) { flex: 1 1 0 !important; }
    .st-key-pct_addrow [data-testid="stColumn"]:nth-child(2), .st-key-pct_addrow [data-testid="column"]:nth-child(2), [class*="st-key-pct_fl_"] [data-testid="stColumn"]:nth-child(2), [class*="st-key-pct_fl_"] [data-testid="column"]:nth-child(2) { flex: 0 0 3rem !important; }
    [class*="st-key-pct_thr_"] [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: nowrap !important; gap: .4rem !important; align-items: flex-end !important; }
    [class*="st-key-pct_thr_"] [data-testid="stColumn"], [class*="st-key-pct_thr_"] [data-testid="column"] { min-width: 0 !important; width: auto !important; }
    [class*="st-key-pct_thr_"] [data-testid="stColumn"]:nth-child(1), [class*="st-key-pct_thr_"] [data-testid="column"]:nth-child(1) { flex: 3 1 0 !important; }
    [class*="st-key-pct_thr_"] [data-testid="stColumn"]:nth-child(2), [class*="st-key-pct_thr_"] [data-testid="column"]:nth-child(2) { flex: 2 1 0 !important; }
    .st-key-pct_datenav button { min-height: 2.6rem; font-weight: 700; }
    [data-testid="stMainBlockContainer"], .block-container { padding-bottom: 8rem !important; }
    </style>""", unsafe_allow_html=True)
    st.button('← Ana səhifə', key='pct_back', on_click=_close_pct)
    st.markdown('<div class="hero"><h1>📈 Günün oyunları — faiz</h1>'
                '<p>Filtr əlavə et: hər komandanın son N oyununda filtrlərin neçə dəfə tutduğu faizlə göstərilir (məsələn 10 oyundan 8 → 80%). '
                'Ən yüksək faizli oyun siyahının başındadır, məlumatı kəsik oyunlar sonda qalır.</p></div>', unsafe_allow_html=True)
    st.session_state.setdefault('p_date', baku_today())
    with st.container(border=True):
        with st.container(key='pct_datenav'):
            c1, c2, c3 = st.columns([1, 4, 1])
            c1.button('◀', key='p_prev', on_click=_pct_shift, args=(-1,), use_container_width=True, help='Əvvəlki gün')
            c2.date_input('Tarix', key='p_date', label_visibility='collapsed')
            c3.button('▶', key='p_next', on_click=_pct_shift, args=(1,), use_container_width=True, help='Növbəti gün')
        st.button('📅 Bu gün', key='p_today', on_click=_pct_shift, args=(0,), use_container_width=True)
        st.caption('🕒 Tarix və saatlar Bakı vaxtı ilədir (UTC+4).')

    with st.container(border=True):
        st.markdown('<div class="sec">Filtrlər</div>', unsafe_allow_html=True)
        n = st.number_input('Hər komandanın son neçə oyununa baxılsın?', min_value=1, max_value=100, value=10, step=1, key='p_n')
        # Hədlər aşağıdakı qutuda dəyişdirilir; burada session_state-dən oxunur (qutu açılanda "➕" düyməsi aşağı itməsin deyə ən sonda göstərilir)
        thr = tuple(int(st.session_state.get(f'p_thr_{i}', d)) for i, d in enumerate(_PCT_DEF))
        cat = _pct_catalog(thr)
        chosen = [x for x in st.session_state.get('p_flt', []) if x in cat]
        st.session_state['p_flt'] = chosen
        free = [x for x in cat if x not in chosen]
        if free:
            with st.container(key='pct_addrow'):
                a1, a2 = st.columns([1, 1])
                a1.selectbox('Filtr seç', free, key='p_add_sel', label_visibility='collapsed', format_func=lambda x: _pct_label(x, thr))
                a2.button('➕', key='p_add_btn', on_click=_pct_add, use_container_width=True, help='Seçilmiş filtri əlavə et')
        if not chosen:
            st.caption('Siyahıdan filtr seç və ➕ düyməsinə bas. Bir neçə filtr əlavə etsən, hamısı eyni oyunda tutmalıdır.')
        for i, nm in enumerate(chosen):
            with st.container(key=f'pct_fl_{i}'):
                r1, r2 = st.columns([1, 1])
                r1.markdown(f'**{_pct_label(nm, thr)}**')
                r2.button('✖', key=f'p_rm_{i}', on_click=_pct_remove, args=(nm,), use_container_width=True, help='Filtri sil')
        with st.expander('Künc / zərbə hədləri', expanded=False):
            st.caption('Matç: iki komandanın cəmi. Klub: hər klubun öz göstəricisi.')
            for i, (nm, d) in enumerate(zip(_PCT_STAT, _PCT_DEF)):
                with st.container(key=f'pct_thr_{i}'):
                    _a, _b = st.columns([3, 2])
                    _a.number_input(nm, 0, 60, d, key=f'p_thr_{i}')
                    _b.button('＋ Filtr', key=f'p_thradd_{i}', on_click=_pct_add_named, args=(nm,), use_container_width=True,
                              help='Bu həddi filtr kimi əlavə et')

    g = _pct_games(st.session_state['p_date'], need_stats=any(x in _PCT_STAT for x in chosen))
    if g.empty:
        st.info('Bu tarixdə bazada oyun yoxdur. Başqa gün seç və ya əsas səhifədən məlumatı yenilə.')
        return
    leagues = sorted(g['league'].dropna().astype(str).unique())
    with st.expander(f'🏆 Liqa seçimi ({len(leagues)} liqa, boş = hamısı)', expanded=False):
        sel = st.multiselect('Liqalar', leagues, key='p_leagues')
    if sel:
        g = g[g['league'].astype(str).isin(sel)].reset_index(drop=True)

    tm = g['time'].astype(str).replace({'nan': '', 'NaT': '', 'None': ''})
    if not chosen:
        st.caption(f'Bu gün {len(g)} oyun var. Faizi görmək üçün yuxarıdan ən azı bir filtr əlavə et.')
        show = pd.DataFrame({'Saat': tm, 'Liqa': g['league'], 'Ev sahibi': g['home'], 'Qonaq': g['away'],
                             '1-ci hissə': _pct_score(g['ht_home'], g['ht_away']),
                             'Hesab': _pct_score(g['ft_home'], g['ft_away'])}).sort_values('Saat')
        st.dataframe(show, hide_index=True, use_container_width=True, height=40 + 35 * len(show))
        return

    H = _pct_history(results, tuple(chosen), thr, (len(results), str(results['date'].max())))
    day = np.full(len(g), pd.Timestamp(st.session_state['p_date']).normalize().to_datetime64().astype('datetime64[D]').astype('int64'))
    hh, hd, hp = _pct_for(H, g['home_k'].values, day, int(n))
    ah, ad, ap = _pct_for(H, g['away_k'].values, day, int(n))
    cnt = (~np.isnan(hp)).astype(int) + (~np.isnan(ap)).astype(int)
    tot = np.nan_to_num(hp) + np.nan_to_num(ap)
    avg = np.where(cnt > 0, tot / np.maximum(cnt, 1), np.nan)
    complete = (hd >= int(n)) & (ad >= int(n))
    fmt = lambda h, d, p: [f'{a}/{b} ({q:.0f}%)' if b else '—' for a, b, q in zip(h, d, p)]
    out = pd.DataFrame({
        'Saat': tm, 'Ev sahibi': g['home'], 'Qonaq': g['away'],
        '1-c
