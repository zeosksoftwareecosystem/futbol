from pathlib import Path
import zipfile, io, re, unicodedata, requests, shutil, tempfile
from datetime import datetime
from collections import Counter
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
    'HC': 'home_corners', 'AC': 'away_corners', 'HY': 'home_yellow', 'AY': 'away_yellow',
}
FD_KEEP = ['date', 'time', 'home', 'away', 'league', 'ft_home', 'ft_away', 'ht_home', 'ht_away',
           'home_corners', 'away_corners', 'home_yellow', 'away_yellow']

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


def team_key(name):
    s = unicodedata.normalize('NFKD', str(name)).encode('ascii', 'ignore').decode().lower()
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
.block-container { padding-top: 1.4rem; max-width: 1180px; }
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

@media (max-width: 700px) { .stats { grid-template-columns: 1fr; } .hero h1 { font-size: 22px; } }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)
st.markdown(
    '<div class="hero"><h1>⚽ Futbol Filtri</h1>'
    '<p>Hər komandanın son oyunlarını yoxlayır və bütün seçilmiş şərtlərə uyğun gələn matçları tapır.</p>'
    '<div class="tags"><span>Open Matchday</span><span>football-data.co.uk</span><span>API açarı lazım deyil</span></div></div>',
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
            df = df[[c for c in FD_KEEP if c in df.columns]]
            (fix if f.name == 'fixtures.csv' else res).append(df)
    return (pd.concat(fix, ignore_index=True) if fix else pd.DataFrame(),
            pd.concat(res, ignore_index=True) if res else pd.DataFrame())


SRC_LABELS = {'FD': 'football-data.co.uk', 'OM': 'Open Matchday', 'FD+OM': 'football-data.co.uk + Open Matchday'}


def src_label(code):
    return SRC_LABELS.get(str(code), '')


def add_keys(df, src):
    if df.empty:
        return df
    df = df.copy()
    df['src'] = src
    df['date'] = pd.to_datetime(df.get('date'), errors='coerce').dt.normalize()
    df['home_k'] = df['home'].map(team_key)
    df['away_k'] = df['away'].map(team_key)
    return df


def _tokens_match(short, long_):
    used = set()
    for t in short:
        hit = next((j for j, u in enumerate(long_) if j not in used and (u == t or (len(t) >= 3 and u.startswith(t)))), None)
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
    if len(ta) > len(tb):
        ta, tb = tb, ta
    return _tokens_match(ta, tb)


def learn_key_map(fd, om):
    """Eyni gün oynanan və hər iki komandası uyğun gələn oyunlardan football-data adlarını Open Matchday adlarına çevirən xəritə öyrənir."""
    if fd.empty or om.empty:
        return {}
    m = fd[['date', 'home_k', 'away_k']].dropna().drop_duplicates().merge(
        om[['date', 'home_k', 'away_k']].dropna().drop_duplicates(), on='date', suffixes=('', '_om'))
    votes = Counter()
    for h, a, ho, ao in zip(m['home_k'], m['away_k'], m['home_k_om'], m['away_k_om']):
        if h == ho and a == ao:
            continue
        if names_compatible(h, ho) and names_compatible(a, ao):
            if h != ho:
                votes[(h, ho)] += 1
            if a != ao:
                votes[(a, ao)] += 1
    best = {}
    for (k, target), n in votes.items():
        if k not in best or n > best[k][1]:
            best[k] = (target, n)
    return {k: v[0] for k, v in best.items()}


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


@st.cache_data(show_spinner=False)
def load_data():
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
    om_fix = add_keys(pd.concat(fixtures, ignore_index=True) if fixtures else pd.DataFrame(), 'OM')
    om_res = add_keys(pd.concat(results, ignore_index=True) if results else pd.DataFrame(), 'OM')
    fd_fix, fd_res = load_fd()
    fd_fix, fd_res = add_keys(fd_fix, 'FD'), add_keys(fd_res, 'FD')
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
    for df_ in (fix, res):
        if not df_.empty and 'league' in df_.columns:
            df_['league'] = df_['league'].map(pretty_league)
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
        st.session_state['refresh_msgs'] = msgs
        st.rerun()
    st.caption('Yeniləmə internet tələb edir. Əvvəl yüklənmiş məlumatlar internet olmadan da analiz edilə bilər.')

fixtures, results, fd_only_teams = load_data()
if fixtures.empty:
    st.error('Oyun cədvəlləri tapılmadı. ZIP-i tam çıxartdığını yoxla və ya sol paneldən yenilə.')
    st.stop()

fixtures['date'] = pd.to_datetime(fixtures.get('date'), errors='coerce')
if not results.empty:
    results['date'] = pd.to_datetime(results.get('date'), errors='coerce')
for c in ['ft_home', 'ft_away', 'ht_home', 'ht_away', 'home_corners', 'away_corners', 'home_yellow', 'away_yellow']:
    if c in results.columns:
        results[c] = pd.to_numeric(results[c], errors='coerce')
results = results.dropna(subset=['date', 'home', 'away', 'ft_home', 'ft_away']).copy()

today = pd.Timestamp.now().date()
with st.container(border=True):
    st.markdown('<div class="sec">1 · Tarix və oyun sayı</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        date_from = st.date_input('Başlanğıc tarixi', value=today)
    with c2:
        date_to = st.date_input('Son tarix', value=today)
    with c3:
        n_games = st.number_input('Hər komandanın son neçə oyunu?', min_value=1, max_value=50, value=2, step=1)
    league_options = sorted({str(x) for x in pd.concat([fixtures['league'], results['league']]).dropna() if str(x).strip()})
    # Liqa seçimi: cədvəldə hər liqanın qarşısında quş (checkbox). İlk dəfə hamısı seçilmiş olur.
    known = st.session_state.get('lg_known', set())
    st.session_state.setdefault('lg_sel', set())
    st.session_state['lg_sel'] = (st.session_state['lg_sel'] & set(league_options)) | (set(league_options) - known)
    st.session_state['lg_known'] = set(league_options)
    st.session_state.setdefault('lg_ver', 0)
    with st.expander(f'🏆 Liqalar — {len(league_options)} liqa var (açıb seç)', expanded=False):
        lg_query = st.text_input('🔍 Liqa və ya ölkə axtar', placeholder='məs: almaniya, england, fin, champions, kubok ...', key='lg_query')
        q_tokens = norm_search(lg_query).split()
        visible = [l for l in league_options if all(t in league_search_blob(l) for t in q_tokens)]
        b1, b2, _ = st.columns([1.2, 1.2, 2.6])
        if b1.button('✅ Göstərilənləri seç' if q_tokens else '✅ Hamısını seç', use_container_width=True):
            st.session_state['lg_sel'] = st.session_state['lg_sel'] | set(visible)
            st.session_state['lg_ver'] += 1
        if b2.button('⬜ Göstərilənləri təmizlə' if q_tokens else '⬜ Təmizlə', use_container_width=True):
            st.session_state['lg_sel'] = st.session_state['lg_sel'] - set(visible)
            st.session_state['lg_ver'] += 1
        if visible:
            lg_df = pd.DataFrame({'Seç': [l in st.session_state['lg_sel'] for l in visible], 'Liqa': visible})
            lg_edit = st.data_editor(
                lg_df, hide_index=True, disabled=['Liqa'], height=340, use_container_width=True,
                column_config={'Seç': st.column_config.CheckboxColumn('Seç', width='small'),
                               'Liqa': st.column_config.TextColumn('Liqa', width='large')},
                key=f"lg_editor_{st.session_state['lg_ver']}_{norm_search(lg_query).strip()}")
            chosen = set(lg_edit.loc[lg_edit['Seç'], 'Liqa'])
            st.session_state['lg_sel'] = (st.session_state['lg_sel'] - set(visible)) | chosen
        else:
            st.info('Belə liqa tapılmadı. Başqa söz yaz (məs: ölkə adı).')
    sel_leagues = st.session_state['lg_sel']
    st.caption(f'Seçilmiş liqa: {len(sel_leagues)} / {len(league_options)}')

with st.container(border=True):
    st.markdown('<div class="sec">2 · Filtrlər</div>', unsafe_allow_html=True)
    cols = st.columns(3)
    with cols[0]:
        st.markdown('**⚽ Qol filtrləri**')
        btts = st.checkbox('BTTS — hər iki komanda qol vurub')
        over25 = st.checkbox('Matç 2.5 üst')
        over35 = st.checkbox('Matç 3.5 üst')
        over45 = st.checkbox('Matç 4.5 üst')
    with cols[1]:
        st.markdown('**⏱️ 1-ci hissə**')
        ht05 = st.checkbox('1-ci hissə 0.5 üst')
        ht15 = st.checkbox('1-ci hissə 1.5 üst')
    with cols[2]:
        st.markdown('**📊 Statistika**')
        corners_on = st.checkbox('Künc zərbələri minimumu')
        min_corners = st.number_input('Matç üzrə minimum ümumi künc', min_value=0, max_value=30, value=9, disabled=not corners_on)
        cards_on = st.checkbox('Sarı vərəqə minimumu')
        min_cards = st.number_input('Matç üzrə minimum sarı vərəqə', min_value=0, max_value=20, value=3, disabled=not cards_on)
    st.markdown('<div class="rule">Hər komandanın seçilən son oyunlarının <b>HAMISI</b> bütün şərtlərə uyğun olmalıdır.</div>', unsafe_allow_html=True)

criteria_selected = any([btts, ht05, ht15, over25, over35, over45, corners_on, cards_on])
if not criteria_selected:
    st.info('Ən azı bir filtr seç. Tarixə uyğun oyunlar aşağıda görünür, analiz üçün isə filtr lazımdır.')

def match_pass(row):
    checks = []
    hg, ag = row.get('ft_home'), row.get('ft_away')
    if pd.isna(hg) or pd.isna(ag):
        return False
    if btts:
        checks.append(hg > 0 and ag > 0)
    ht_h, ht_a = row.get('ht_home'), row.get('ht_away')
    if ht05:
        checks.append(pd.notna(ht_h) and pd.notna(ht_a) and ht_h + ht_a >= 1)
    if ht15:
        checks.append(pd.notna(ht_h) and pd.notna(ht_a) and ht_h + ht_a >= 2)
    total = hg + ag
    if over25:
        checks.append(total >= 3)
    if over35:
        checks.append(total >= 4)
    if over45:
        checks.append(total >= 5)
    hc, ac = row.get('home_corners'), row.get('away_corners')
    if corners_on:
        checks.append(pd.notna(hc) and pd.notna(ac) and hc + ac >= min_corners)
    hy, ay = row.get('home_yellow'), row.get('away_yellow')
    if cards_on:
        checks.append(pd.notna(hy) and pd.notna(ay) and hy + ay >= min_cards)
    return all(checks) if checks else True

def team_last(team_k, date):
    # Komandanın əvvəlki oyunlarını bütün yarışlardan götür (liqa və kubok). Komanda ad açarı ilə axtarılır.
    hist = results[
        (results['date'] < date) &
        ((results['home_k'] == team_k) | (results['away_k'] == team_k))
    ].sort_values('date', ascending=False).head(int(n_games))
    if len(hist) < int(n_games):
        return None
    return hist

if st.button('🔎 Oyunları analiz et', type='primary', use_container_width=True):
    if date_from > date_to:
        st.error('Başlanğıc tarixi son tarixdən böyük ola bilməz.')
        st.stop()
    if not criteria_selected:
        st.warning('Zəhmət olmasa ən azı bir filtr seç.')
        st.stop()
    today = pd.Timestamp.now().date()
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
    day_games['_source_priority'] = day_games.apply(lambda r: 1 if r['date'].date() >= today else 0, axis=1)
    day_games = day_games.sort_values('_source_priority', ascending=False)
    day_games = day_games.drop_duplicates(subset=['date', 'home_k', 'away_k']).drop(columns=['_source_priority']).copy()
    if day_games.empty:
        st.warning('Bu tarix aralığında bazada oyun tapılmadı. Məlumatı yeniləməyi yoxla.')
        st.stop()

    passed, skipped = [], 0
    progress = st.progress(0)
    for i, (_, game) in enumerate(day_games.iterrows()):
        league, date, home, away = game['league'], game['date'], game['home'], game['away']
        hhist = team_last(game['home_k'], date)
        ahist = team_last(game['away_k'], date)
        if hhist is None or ahist is None:
            skipped += 1
            progress.progress((i + 1) / len(day_games))
            continue
        if all(match_pass(r) for _, r in hhist.iterrows()) and all(match_pass(r) for _, r in ahist.iterrows()):
            passed.append({
                'Tarix': date.strftime('%Y-%m-%d'),
                'Saat': str(game.get('time', '')),
                'Çempionat': league,
                'Mənbə': src_label(game.get('src', '')),
                'Ev sahibi': home,
                'Qonaq': away,
                'Son oyun sayı': int(n_games),
                'Ev sahibinin əvvəlki nəticələri': hhist.sort_values('date', ascending=False).to_dict('records'),
                'Qonağın əvvəlki nəticələri': ahist.sort_values('date', ascending=False).to_dict('records')
            })
        progress.progress((i + 1) / len(day_games))
    progress.empty()
    st.markdown(
        f'<div class="stats">'
        f'<div class="stat"><div class="n">{len(day_games)}</div><div class="l">Yoxlanılan oyun</div></div>'
        f'<div class="stat good"><div class="n">{len(passed)}</div><div class="l">Uyğun oyun</div></div>'
        f'<div class="stat"><div class="n">{skipped}</div><div class="l">Tarixçəsi çatmayan oyun</div></div>'
        f'</div>',
        unsafe_allow_html=True
    )
    st.caption('Komandaların əvvəlki oyunları liqa və kubok daxil olmaqla bütün mövcud nəticələrdən, hədəf oyunun tarixindən əvvəl axtarılır.')

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
            with st.expander(title, expanded=False):
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
                            hyc, ayc = old_match.get('home_yellow'), old_match.get('away_yellow')
                            if pd.notna(hyc) and pd.notna(ayc):
                                chips += f'<span class="chip y">Sarı {int(hyc + ayc)}</span>'
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
        out = out.drop(columns=['Ev sahibinin əvvəlki nəticələri', 'Qonağın əvvəlki nəticələri'])
        st.download_button('⬇️ Nəticələri CSV kimi yüklə', out.to_csv(index=False).encode('utf-8-sig'), file_name='futbol_filtri_neticeleri.csv', mime='text/csv')
    else:
        st.info('Seçilən şərtlərə uyğun oyun tapılmadı. Tarix aralığını genişləndir və ya filtrləri dəyiş.')

with st.expander('Məlumat bazası haqqında'):
    st.write(f'Çempionat qovluqları: {len(list(DATA_DIR.iterdir())) if DATA_DIR.exists() else 0}. Qarşıdakı oyun sətri: {len(fixtures)}. Tarixi nəticə sətri: {len(results)}. Siyahıdakı liqa sayı: {len(league_options)}.')
    st.write('Mənbələr: Open Matchday — https://github.com/oladeeayo/open-matchday və football-data.co.uk. Eyni oyun iki mənbədə varsa statistika üçün əvvəlcə football-data.co.uk götürülür, çatışmayanı Open Matchday doldurur. Statistikası olmayan oyunlar müvafiq statistik filtrdə uyğun sayılmır.')
    if FD_DIR.exists() and any(FD_DIR.glob('*.csv')):
        st.write(f'football-data.co.uk faylları: {len(list(FD_DIR.glob("*.csv")))}.')
    else:
        st.write('football-data.co.uk hələ yüklənməyib — sol paneldən "Məlumatı yenilə" düyməsinə bas.')
    if fd_only_teams:
        st.write(f'Yalnız football-data.co.uk-də tapılan komandalar: {len(fd_only_teams)}. Əgər bunların arasında Open Matchday-də başqa cür yazılan komanda varsa, app.py-dakı ALIASES siyahısına əlavə et.')
        st.code('\n'.join(fd_only_teams))
