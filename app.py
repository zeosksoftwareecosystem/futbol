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
        out = out.drop(columns=['Ev sahibinin əvvəlki nəticələri', 'Qonağın əvvəlki nəticələri'])
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
    if not criteria_selected:
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
    st.write('Mənbələr: Open Matchday — https://github.com/oladeeayo/open-matchday, football-data.co.uk (əsas və əlavə liqalar), openfootball (https://github.com/openfootball/football.json), international_results (https://github.com/martj42/international_results, milli komandalar) və ESPN (qitə kubokları, daxili kuboklar və onlarla liqa; yarımvaxt, künc, zərbə və qapıya dəqiq zərbə ESPN-dən də çıxarılır). Eyni oyun bir neçə mənbədə varsa statistika üçün əvvəlcə football-data.co.uk, sonra Open Matchday, sonra openfootball, sonra ESPN götürülür. Künc, zərbə və qapıya dəqiq zərbə statistikası football-data.co.uk əsas liqalarında, Open Matchday-də və ESPN-in yüklədiyi oyunlarda var. Statistikası olmayan oyunlar müvafiq statistik filtrdə uyğun sayılmır.')
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
