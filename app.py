from pathlib import Path
import zipfile, io, requests, shutil, tempfile
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / 'open-matchday' / 'data'
REPO_ZIP = 'https://github.com/oladeeayo/open-matchday/archive/refs/heads/master.zip'

st.set_page_config(page_title='Futbol Filtri v5', page_icon='⚽', layout='wide')
st.title('⚽ Futbol Filtri v5 — Yerli baza')
st.caption('Oyunları yerli CSV bazasında analiz edir. API açarı tələb etmir. Statistikası olmayan oyunlar seçilmiş statistik filtrləri keçmiş sayılmır.')

@st.cache_data(show_spinner=False)
def load_data():
    fixtures, results = [], []
    for f in DATA_DIR.glob('*/*.csv'):
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        league = f.parent.name
        df['league'] = league
        if f.name.startswith('fixtures_'):
            fixtures.append(df)
        elif f.name.startswith('results_'):
            results.append(df)
    return (pd.concat(fixtures, ignore_index=True) if fixtures else pd.DataFrame(),
            pd.concat(results, ignore_index=True) if results else pd.DataFrame())

def refresh_data():
    r = requests.get(REPO_ZIP, timeout=90, headers={'User-Agent':'FutbolFiltri/1.0'})
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
        dest = DATA_DIR
        if dest.exists(): shutil.rmtree(dest)
        shutil.copytree(source, dest)
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    load_data.clear()

with st.sidebar:
    st.header('Məlumat bazası')
    if st.button('🔄 GitHub-dan yenilə', use_container_width=True):
        with st.spinner('Məlumatlar yüklənir...'):
            try:
                refresh_data()
                st.success('Məlumat bazası yeniləndi.')
                st.rerun()
            except Exception as e:
                st.error(f'Yeniləmə alınmadı: {e}')
    st.caption('Yeniləmə internet tələb edir. İlkin ZIP-dəki məlumatlar internet olmadan da analiz edilə bilər.')

fixtures, results = load_data()
if fixtures.empty:
    st.error('Oyun cədvəlləri tapılmadı. ZIP-i tam çıxartdığını yoxla.')
    st.stop()

fixtures['date'] = pd.to_datetime(fixtures.get('date'), errors='coerce')
results['date'] = pd.to_datetime(results.get('date'), errors='coerce')
for c in ['ft_home','ft_away','ht_home','ht_away','home_corners','away_corners','home_yellow','away_yellow']:
    if c in results.columns: results[c] = pd.to_numeric(results[c], errors='coerce')
results = results.dropna(subset=['date','home','away','ft_home','ft_away']).copy()

st.subheader('Axtarış şərtləri')
c1,c2,c3 = st.columns(3)
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

c4,c5 = st.columns(2)
with c4: min_corners = st.number_input('Matç üzrə minimum ümumi künc', min_value=0, max_value=30, value=9, disabled=not corners_on)
with c5: min_cards = st.number_input('Matç üzrə minimum sarı vərəqə', min_value=0, max_value=20, value=3, disabled=not cards_on)

criteria_selected = any([btts,ht05,ht15,over25,over35,over45,corners_on,cards_on])
if not criteria_selected:
    st.info('Ən azı bir filtr seç. Tarixə uyğun oyunlar aşağıda görünür, analiz üçün isə filtr lazımdır.')


def match_pass(row):
    checks=[]
    hg,ag = row.get('ft_home'),row.get('ft_away')
    if pd.isna(hg) or pd.isna(ag): return False
    if btts: checks.append(hg > 0 and ag > 0)
    ht_h,ht_a = row.get('ht_home'),row.get('ht_away')
    if ht05: checks.append(pd.notna(ht_h) and pd.notna(ht_a) and ht_h+ht_a >= 1)
    if ht15: checks.append(pd.notna(ht_h) and pd.notna(ht_a) and ht_h+ht_a >= 2)
    total=hg+ag
    if over25: checks.append(total >= 3)
    if over35: checks.append(total >= 4)
    if over45: checks.append(total >= 5)
    hc,ac=row.get('home_corners'),row.get('away_corners')
    if corners_on: checks.append(pd.notna(hc) and pd.notna(ac) and hc+ac >= min_corners)
    hy,ay=row.get('home_yellow'),row.get('away_yellow')
    if cards_on: checks.append(pd.notna(hy) and pd.notna(ay) and hy+ay >= min_cards)
    return all(checks) if checks else True

def team_last(team, date, league):
    hist=results[(results['league']==league) & (results['date'] < date) & ((results['home']==team)|(results['away']==team))].sort_values('date', ascending=False).head(n_games)
    if len(hist)<n_games: return None
    return hist

if st.button('🔎 Oyunları analiz et', type='primary', use_container_width=True):
    if date_from > date_to:
        st.error('Başlanğıc tarixi son tarixdən böyük ola bilməz.')
        st.stop()
    if not criteria_selected:
        st.warning('Zəhmət olmasa ən azı bir filtr seç.')
        st.stop()
    # Target matches must include both scheduled fixtures AND completed results.
    # The source's fixtures CSV mostly contains upcoming games, so scanning fixtures
    # alone silently misses matches on past dates.
    fixture_targets = fixtures[(fixtures['date'].dt.date >= date_from) & (fixtures['date'].dt.date <= date_to)].copy()
    result_targets = results[(results['date'].dt.date >= date_from) & (results['date'].dt.date <= date_to)].copy()
    target_cols = ['date','time','home','away','league']
    for frame in (fixture_targets, result_targets):
        for col in target_cols:
            if col not in frame.columns:
                frame[col] = '' if col in ('time','league') else pd.NaT if col == 'date' else ''
    day_games = pd.concat([fixture_targets[target_cols], result_targets[target_cols]], ignore_index=True)
    day_games = day_games.dropna(subset=['date','home','away']).drop_duplicates(subset=['date','league','home','away']).copy()
    if day_games.empty:
        st.warning('Bu tarix aralığında bazada oyun tapılmadı. Bu mənbə keçmiş tarixlər üçün əsasən nəticələr cədvəlindən istifadə edir; GitHub-dan yeniləməyi yoxla.')
        st.stop()
    passed=[]; skipped=0
    progress=st.progress(0)
    for i,(_, game) in enumerate(day_games.iterrows()):
        league=game['league']; date=game['date']; home=game['home']; away=game['away']
        hhist=team_last(home,date,league); ahist=team_last(away,date,league)
        if hhist is None or ahist is None:
            skipped += 1; progress.progress((i+1)/len(day_games)); continue
        if all(match_pass(r) for _,r in hhist.iterrows()) and all(match_pass(r) for _,r in ahist.iterrows()):
            passed.append({'Tarix':date.strftime('%Y-%m-%d'),'Saat':str(game.get('time','')),'Çempionat':league,'Ev sahibi':home,'Qonaq':away,'Son oyun sayı':n_games,
                           'Ev sahibinin əvvəlki nəticələri':' | '.join(f"{r['home']} {int(r['ft_home'])}-{int(r['ft_away'])} {r['away']}" for _,r in hhist.sort_values('date').iterrows()),
                           'Qonağın əvvəlki nəticələri':' | '.join(f"{r['home']} {int(r['ft_home'])}-{int(r['ft_away'])} {r['away']}" for _,r in ahist.sort_values('date').iterrows())})
        progress.progress((i+1)/len(day_games))
    progress.empty()
    st.success(f'Yoxlanılan oyun: {len(day_games)} · Uyğun oyun: {len(passed)} · Tarixi çatmayan/az olan oyun: {skipped}')
    st.caption('Seçilmiş tarixdəki oyunlar həm qarşıdakı oyunlar, həm də artıq başa çatmış nəticələr cədvəlindən götürülür. Komandaların əvvəlki oyunları isə yalnız həmin oyunun tarixindən əvvəl axtarılır.')
    if passed:
        out=pd.DataFrame(passed)
        st.dataframe(out, use_container_width=True, hide_index=True)
        st.download_button('Nəticələri CSV kimi yüklə', out.to_csv(index=False).encode('utf-8-sig'), file_name='futbol_filtri_neticeleri.csv', mime='text/csv')
    else:
        st.info('Seçilən şərtlərə uyğun oyun tapılmadı. Tarix aralığını genişləndir və ya filtrləri dəyiş.')

with st.expander('Məlumat bazası haqqında'):
    st.write(f'Çempionat qovluqları: {len(list(DATA_DIR.iterdir()))}. Qarşıdakı oyun sətri: {len(fixtures)}. Tarixi nəticə sətri: {len(results)}.')
    st.write('Mənbə: Open Matchday — https://github.com/oladeeayo/open-matchday. Məlumatların əhatəsi və yenilənmə vaxtı mənbədən asılıdır; statistikası olmayan oyunlar müvafiq statistik filtrdə uyğun sayılmır.')
