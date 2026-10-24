from pathlib import Path
import zipfile, io, re, unicodedata, requests, shutil, tempfile
from datetime import datetime
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


st.set_page_config(page_title='Futbol Filtri v6', page_icon='⚽', layout='wide')
st.title('⚽ Futbol Filtri v6 — Yerli baza')
st.caption('Oyunları yerli CSV bazasında analiz edir (Open Matchday + football-data.co.uk). API açarı tələb etmir. Statistikası olmayan oyunlar seçilmiş statistik filtrləri keçmiş sayılmır.')


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


def add_keys(df):
    if df.empty:
        return df
    df = df.copy()
    df['date'] = pd.to_datetime(df.get('date'), errors='coerce').dt.normalize()
    df['home_k'] = df['home'].map(team_key)
    df['away_k'] = df['away'].map(team_key)
    return df


def merge_sources(fd, om):
    """Eyni oyun (tarix + komanda) iki mənbədə varsa birləşdirir: statistika üçün əvvəlcə football-data.co.uk, boşluğu Open Matchday doldurur."""
    fd, om = add_keys(fd), add_keys(om)
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
    merged = both.groupby(['date', 'home_k', 'away_k'], as_index=False, sort=False).first()
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
    om_fix = pd.concat(fixtures, ignore_index=True) if fixtures else pd.DataFrame()
    om_res = pd.concat(results, ignore_index=True) if results else pd.DataFrame()
    fd_fix, fd_res = load_fd()
    fix, fix_only = merge_sources(fd_fix, om_fix)
    res, res_only = merge_sources(fd_res, om_res)
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

st.subheader('Axtarış şərtləri')
c1, c2, c3 = st.columns(3)
today = pd.Timestamp.now().date()
with c1:
    date_from = st.date_input('Başlanğıc tarixi', value=today)
with c2:
    date_to = st.date_input('Son tarix', value=today)
with c3:
    n_games = st.number_input('Hər komandanın son neçə oyununu yoxlayaq?', min_value=1, max_value=50, value=2, step=1)
st.markdown('**Hər komandanın seçilən son oyunlarının HAMISI şərtlərə uyğun olmalıdır.**')
cols = st.columns(4)
with cols[0]:
    btts = st.checkbox('BTTS — hər iki komanda qol vurub')
    ht05 = st.checkbox('1-ci hissə 0.5 üst')
with cols[1]:
    ht15 = st.checkbox('1-ci hissə 1.5 üst')
    over25 = st.checkbox('Matç 2.5 üst')
with cols[2]:
    over35 = st.checkbox('Matç 3.5 üst')
    over45 = st.checkbox('Matç 4.5 üst')
with cols[3]:
    corners_on = st.checkbox('Künc zərbələri minimumu')
    cards_on = st.checkbox('Sarı vərəqə minimumu')
c4, c5 = st.columns(2)
with c4:
    min_corners = st.number_input('Matç üzrə minimum ümumi künc', min_value=0, max_value=30, value=9, disabled=not corners_on)
with c5:
    min_cards = st.number_input('Matç üzrə minimum sarı vərəqə', min_value=0, max_value=20, value=3, disabled=not cards_on)

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
    target_cols = ['date', 'time', 'home', 'away', 'league', 'home_k', 'away_k']
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
                'Ev sahibi': home,
                'Qonaq': away,
                'Son oyun sayı': int(n_games),
                'Ev sahibinin əvvəlki nəticələri': hhist.sort_values('date', ascending=False).to_dict('records'),
                'Qonağın əvvəlki nəticələri': ahist.sort_values('date', ascending=False).to_dict('records')
            })
        progress.progress((i + 1) / len(day_games))
    progress.empty()
    st.success(f'Yoxlanılan oyun: {len(day_games)} · Uyğun oyun: {len(passed)} · Tarixi çatmayan/az olan oyun: {skipped}')
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
                st.caption(f"{league_text} · Hər komandanın son {item['Son oyun sayı']} oyunu")
                left, right = st.columns(2)
                for col, team_name, history_key in [
                    (left, item['Ev sahibi'], 'Ev sahibinin əvvəlki nəticələri'),
                    (right, item['Qonaq'], 'Qonağın əvvəlki nəticələri')
                ]:
                    with col:
                        st.markdown(f'**🏟️ {team_name}**')
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
                            st.markdown(
                                f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:8px 10px;margin:5px 0 7px 0;text-align:center;">'
                                f'<div style="color:#64748b;font-size:12px;">{date_text}{(" · " + old_time) if old_time else ""}</div>'
                                f'<div style="font-size:13px;overflow-wrap:anywhere;">{old_home}</div>'
                                f'<div style="font-size:19px;font-weight:700;">{score}</div>'
                                f'<div style="font-size:13px;overflow-wrap:anywhere;">{old_away}</div></div>',
                                unsafe_allow_html=True
                            )
        out = out.drop(columns=['Ev sahibinin əvvəlki nəticələri', 'Qonağın əvvəlki nəticələri'])
        st.download_button('⬇️ Nəticələri CSV kimi yüklə', out.to_csv(index=False).encode('utf-8-sig'), file_name='futbol_filtri_neticeleri.csv', mime='text/csv')
    else:
        st.info('Seçilən şərtlərə uyğun oyun tapılmadı. Tarix aralığını genişləndir və ya filtrləri dəyiş.')

with st.expander('Məlumat bazası haqqında'):
    st.write(f'Çempionat qovluqları: {len(list(DATA_DIR.iterdir())) if DATA_DIR.exists() else 0}. Qarşıdakı oyun sətri: {len(fixtures)}. Tarixi nəticə sətri: {len(results)}.')
    st.write('Mənbələr: Open Matchday — https://github.com/oladeeayo/open-matchday və football-data.co.uk. Eyni oyun iki mənbədə varsa statistika üçün əvvəlcə football-data.co.uk götürülür, çatışmayanı Open Matchday doldurur. Statistikası olmayan oyunlar müvafiq statistik filtrdə uyğun sayılmır.')
    if FD_DIR.exists() and any(FD_DIR.glob('*.csv')):
        st.write(f'football-data.co.uk faylları: {len(list(FD_DIR.glob("*.csv")))}.')
    else:
        st.write('football-data.co.uk hələ yüklənməyib — sol paneldən "Məlumatı yenilə" düyməsinə bas.')
    if fd_only_teams:
        st.write(f'Yalnız football-data.co.uk-də tapılan komandalar: {len(fd_only_teams)}. Əgər bunların arasında Open Matchday-də başqa cür yazılan komanda varsa, app.py-dakı ALIASES siyahısına əlavə et.')
        st.code('\n'.join(fd_only_teams))
