import io, zipfile, requests, re
from datetime import date, timedelta
import pandas as pd
import streamlit as st

REPO_ZIP = 'https://codeload.github.com/oladeeayo/open-matchday/zip/refs/heads/master'
REPO_PAGE = 'https://github.com/oladeeayo/open-matchday'

st.set_page_config(page_title='Futbol Filtri', page_icon='⚽', layout='wide')

# Optional password gate: set APP_PASSWORD in Streamlit Community Cloud Secrets.
def password_gate():
    try:
        expected = st.secrets.get('APP_PASSWORD', '')
    except Exception:
        expected = ''
    if not expected:
        st.warning('Şəxsi istifadə üçün qoruma: Streamlit Secrets bölməsində APP_PASSWORD təyin et. Əks halda linki bilənlər tətbiqi aça bilər.')
        return True
    if st.session_state.get('authenticated'):
        return True
    st.title('🔐 Şəxsi futbol filtri')
    entered = st.text_input('Şifrə', type='password')
    if st.button('Daxil ol', use_container_width=True):
        if entered == expected:
            st.session_state['authenticated'] = True
            st.rerun()
        else:
            st.error('Şifrə yanlışdır.')
    return False

@st.cache_data(ttl=21600, show_spinner=False)
def download_and_read_data():
    response = requests.get(REPO_ZIP, timeout=90)
    response.raise_for_status()
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    results, fixtures = {}, []
    for name in archive.namelist():
        if '/data/' not in name or not name.lower().endswith('.csv'):
            continue
        match = re.search(r'/data/([^/]+)/([^/]+\.csv)$', name)
        if not match:
            continue
        league, filename = match.group(1), match.group(2)
        try:
            with archive.open(name) as f:
                df = pd.read_csv(f)
        except Exception:
            continue
        if filename.startswith('results_') and {'date','home','away','ft_home','ft_away'}.issubset(df.columns):
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df = df.dropna(subset=['date','ft_home','ft_away'])
            results[league] = df
        elif filename.startswith('fixtures_') and {'date','home','away'}.issubset(df.columns):
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df = df.dropna(subset=['date'])
            df['league_key'] = league
            fixtures.append(df)
    all_fixtures = pd.concat(fixtures, ignore_index=True) if fixtures else pd.DataFrame()
    if not all_fixtures.empty:
        all_fixtures = all_fixtures.sort_values(['date','time'] if 'time' in all_fixtures.columns else ['date'])
    return results, all_fixtures

def has_col(row, col):
    return col in row.index and pd.notna(row[col])

def match_passes(row, filters, thresholds):
    fh = float(row['ft_home']); fa = float(row['ft_away'])
    goals = fh + fa
    if filters['BTTS'] and not (fh > 0 and fa > 0): return False
    if filters['Matç 2.5+'] and not goals >= 3: return False
    if filters['Matç 3.5+'] and not goals >= 4: return False
    if filters['Matç 4.5+'] and not goals >= 5: return False
    if filters['1-ci hissə 0.5+']:
        if not (has_col(row,'ht_home') and has_col(row,'ht_away')) or float(row['ht_home']) + float(row['ht_away']) < 1: return False
    if filters['1-ci hissə 1.5+']:
        if not (has_col(row,'ht_home') and has_col(row,'ht_away')) or float(row['ht_home']) + float(row['ht_away']) < 2: return False
    if filters['Künc zərbələri']:
        if not (has_col(row,'home_corners') and has_col(row,'away_corners')) or float(row['home_corners']) + float(row['away_corners']) < thresholds['corners']: return False
    if filters['Sarı vərəqələr']:
        if not (has_col(row,'home_yellow') and has_col(row,'away_yellow')) or float(row['home_yellow']) + float(row['away_yellow']) < thresholds['yellow']: return False
    return True

def score_label(row):
    return f"{int(float(row['ft_home']))}-{int(float(row['ft_away']))}"

def last_team_matches(results_df, team, before_date, count):
    df = results_df[(results_df['date'] < before_date) & ((results_df['home'].astype(str) == str(team)) | (results_df['away'].astype(str) == str(team)))].copy()
    return df.sort_values('date', ascending=False).head(count)

if not password_gate():
    st.stop()

st.title('⚽ Futbol Filtri')
st.caption('Yerli analiz · API açarı tələb etmir · Open Matchday məlumat bazası')
with st.sidebar:
    st.header('Filtrlər')
    today = date.today()
    date_from = st.date_input('Başlanğıc tarix', value=today)
    date_to = st.date_input('Son tarix', value=today + timedelta(days=1))
    n_matches = st.selectbox('Hər komandanın son neçə oyunu?', [2,3,4,5,6,8,10], index=0)
    st.markdown('**Qol şərtləri**')
    filter_btts = st.checkbox('BTTS — hər iki komanda qol vurub')
    filter_o25 = st.checkbox('Matç 2.5 üst', value=True)
    filter_o35 = st.checkbox('Matç 3.5 üst')
    filter_o45 = st.checkbox('Matç 4.5 üst')
    filter_ht05 = st.checkbox('1-ci hissə 0.5 üst')
    filter_ht15 = st.checkbox('1-ci hissə 1.5 üst')
    st.markdown('**Statistika**')
    filter_corners = st.checkbox('Künc zərbələri minimumu')
    corners_min = st.number_input('Künc minimumu', min_value=0, max_value=30, value=9, disabled=not filter_corners)
    filter_yellow = st.checkbox('Sarı vərəqə minimumu')
    yellow_min = st.number_input('Sarı vərəqə minimumu', min_value=0, max_value=20, value=3, disabled=not filter_yellow)
    st.caption('Ofsayd məlumatı bu mənbənin CSV-lərində yoxdur.')
    run_scan = st.button('🔎 Oyunları analiz et', type='primary', use_container_width=True)
    update = st.button('🔄 Məlumatları yenilə', use_container_width=True)

if 'data' not in st.session_state:
    st.session_state['data'] = None
if update:
    download_and_read_data.clear()
    st.session_state['data'] = None
    with st.spinner('GitHub-dan yenilənmiş məlumatlar endirilir...'):
        try:
            st.session_state['data'] = download_and_read_data()
            st.success('Məlumatlar yeniləndi.')
        except Exception as e:
            st.error(f'Məlumatları yeniləmək alınmadı: {e}')
if st.session_state['data'] is None:
    with st.spinner('Məlumat bazası yüklənir...'):
        try:
            st.session_state['data'] = download_and_read_data()
        except Exception as e:
            st.error(f'Məlumatları yükləmək alınmadı: {e}')
            st.info('Bir az sonra yenidən cəhd et. Mənbə: Open Matchday GitHub.')
            st.stop()

results, fixtures = st.session_state['data']
all_result_rows = sum(len(df) for df in results.values())
col1, col2, col3 = st.columns(3)
col1.metric('Çempionat məlumat faylları', len(results))
col2.metric('Tarixi nəticələr', f'{all_result_rows:,}')
col3.metric('Qarşıdakı oyunlar', f'{len(fixtures):,}')
st.caption(f'Məlumat mənbəyi: {REPO_PAGE} · CSV məlumatları yenilənənə qədər keşdə saxlanılır.')

if run_scan:
    if date_to < date_from:
        st.error('Son tarix başlanğıc tarixindən əvvəl ola bilməz.')
        st.stop()
    if not any([filter_btts,filter_o25,filter_o35,filter_o45,filter_ht05,filter_ht15,filter_corners,filter_yellow]):
        st.warning('Ən azı bir filtr seç.')
        st.stop()
    if fixtures.empty:
        st.warning('Mənbədə qarşıdakı oyun tapılmadı.')
        st.stop()
    selected = fixtures[(fixtures['date'].dt.date >= date_from) & (fixtures['date'].dt.date <= date_to)].copy()
    filters = {'BTTS':filter_btts,'Matç 2.5+':filter_o25,'Matç 3.5+':filter_o35,'Matç 4.5+':filter_o45,'1-ci hissə 0.5+':filter_ht05,'1-ci hissə 1.5+':filter_ht15,'Künc zərbələri':filter_corners,'Sarı vərəqələr':filter_yellow}
    thresholds = {'corners':corners_min,'yellow':yellow_min}
    found, insufficient = [], 0
    progress = st.progress(0)
    for idx, (_, fixture) in enumerate(selected.iterrows()):
        league = fixture['league_key']
        hist = results.get(league)
        if hist is None:
            insufficient += 1; continue
        home_hist = last_team_matches(hist, fixture['home'], fixture['date'], n_matches)
        away_hist = last_team_matches(hist, fixture['away'], fixture['date'], n_matches)
        if len(home_hist) < n_matches or len(away_hist) < n_matches:
            insufficient += 1; continue
        if all(match_passes(r, filters, thresholds) for _,r in home_hist.iterrows()) and all(match_passes(r, filters, thresholds) for _,r in away_hist.iterrows()):
            found.append({'Tarix':fixture['date'].strftime('%Y-%m-%d'),'Saat':fixture.get('time',''),'Çempionat':league,'Ev sahibi':fixture['home'],'Qonaq':fixture['away'],'Ev sahibinin son oyunları':' · '.join(f"{r['date'].strftime('%m-%d')} {score_label(r)}" for _,r in home_hist.iterrows()),'Qonağın son oyunları':' · '.join(f"{r['date'].strftime('%m-%d')} {score_label(r)}" for _,r in away_hist.iterrows())})
        progress.progress((idx+1)/max(1,len(selected)))
    st.subheader(f'Uyğun oyunlar: {len(found)}')
    st.caption(f'Tarix aralığında oyunlar: {len(selected)} · Kifayət qədər əvvəlki nəticəsi/statistikası olmayan oyunlar: {insufficient}')
    if found:
        output = pd.DataFrame(found)
        st.dataframe(output, use_container_width=True, hide_index=True)
        st.download_button('⬇️ CSV kimi yüklə', output.to_csv(index=False).encode('utf-8-sig'), file_name='uygun_futbol_oyunlari.csv', mime='text/csv', use_container_width=True)
    else:
        st.info('Bu şərtlərə uyğun oyun tapılmadı. Daha geniş tarix və ya daha az filtr seçib yenidən yoxla.')

st.divider()
st.caption('Qeyd: tarixçə hər çempionatın öz məlumat faylı üzrə yoxlanır. Bu mənbədə ofsayd göstəricisi yoxdur; statistikası olmayan matçlar seçilmiş statistik şərtini keçmiş sayılmır.')
