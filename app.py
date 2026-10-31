import streamlit as st
import requests
import pandas as pd
from datetime import datetime, date
import time

# --- GÜVƏNİLİR HEADERS VƏ KONFİQURASİYA ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.sofascore.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9"
}

# --- 1. MƏLUMAT ÇƏKMƏ VƏ API MEXANİZMİ ---

@st.cache_data(ttl=60)
def fetch_scheduled_matches(date_str: str):
    """
    Seçilmiş tarix üçün bütün futbol oyunlarını SofaScore API-dən çəkir.
    Səhifələmə məhdudiyyəti olmadan həmin günün bütün matçlarını gətirir.
    """
    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-date/{date_str}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=12)
        if response.status_code == 200:
            return response.json().get("events", [])
        elif response.status_code == 429:
            st.error("SofaScore Rate Limit (429): Həddindən artıq sorğu göndərildi. Zəhmət olmasa 1-2 dəqiqə gözləyin.")
            return []
        else:
            return []
    except Exception as e:
        st.error(f"Şəbəkə xətası baş verdi: {e}")
        return []

@st.cache_data(ttl=30)
def fetch_match_statistics(event_id: int):
    """
    Konkret bir matçın detallı statistikalarını (xG, Zərbələr, Künclər və s.) çəkir.
    """
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/statistics"
    try:
        response = requests.get(url, headers=HEADERS, timeout=8)
        if response.status_code == 200:
            return response.json().get("statistics", [])
        return []
    except:
        return []

def parse_statistics(stats_data):
    """
    API-dən gələn statistik məlumatları təmizləyir və struktura salır.
    Əgər göstərici yoxdursa, 'N/A' və ya 0 kimi idarə edir.
    """
    parsed = {
        "xg_home": None, "xg_away": None,
        "shots_home": 0, "shots_away": 0,
        "shots_on_target_home": 0, "shots_on_target_away": 0,
        "corners_home": 0, "corners_away": 0,
        "attacks_home": 0, "attacks_away": 0,
        "possession_home": 50, "possession_away": 50,
        "red_cards_home": 0, "red_cards_away": 0
    }
    
    if not stats_data:
        return parsed
        
    try:
        for period in stats_data:
            if period.get("period") == "ALL":
                for group in period.get("groups", []):
                    for item in group.get("statisticsItems", []):
                        name = item.get("name")
                        h_val = item.get("home")
                        a_val = item.get("away")
                        
                        if name == "Expected goals":
                            parsed["xg_home"] = float(h_val) if h_val is not None else 0.0
                            parsed["xg_away"] = float(a_val) if a_val is not None else 0.0
                        elif name == "Total shots":
                            parsed["shots_home"] = int(h_val or 0)
                            parsed["shots_away"] = int(a_val or 0)
                        elif name == "Shots on target":
                            parsed["shots_on_target_home"] = int(h_val or 0)
                            parsed["shots_on_target_away"] = int(a_val or 0)
                        elif name == "Corner kicks":
                            parsed["corners_home"] = int(h_val or 0)
                            parsed["corners_away"] = int(a_val or 0)
                        elif name == "Dangerous attacks":
                            parsed["attacks_home"] = int(h_val or 0)
                            parsed["attacks_away"] = int(a_val or 0)
                        elif name == "Ball possession":
                            parsed["possession_home"] = int(str(h_val).replace('%','') if h_val else 50)
                            parsed["possession_away"] = int(str(a_val).replace('%','') if a_val else 50)
    except Exception:
        pass
        
    return parsed

# --- 2. ZAMAN MÖHÜRÜ İLƏ SNAPSHOT VƏ DƏYİŞİKLİK ANALİZİ ---

def update_snapshots_and_calculate_deltas(match_id, current_stats):
    """
    Zaman möhürü (timestamp) ilə statistik snapshot-ları saxlayır.
    Son 5 və 10 dəqiqədəki REAL statistik artımı hesablayır.
    """
    now = time.time()
    
    if "match_snapshots" not in st.session_state:
        st.session_state.match_snapshots = {}
        
    if match_id not in st.session_state.match_snapshots:
        st.session_state.match_snapshots[match_id] = []
        
    history = st.session_state.match_snapshots[match_id]
    history.append({"time": now, "stats": current_stats})
    
    # 15 dəqiqədən köhnə snapshot-ları sil
    st.session_state.match_snapshots[match_id] = [h for h in history if now - h["time"] <= 900]
    history = st.session_state.match_snapshots[match_id]
    
    # 5 dəqiqə (300s) və 10 dəqiqə (600s) əvvəlki ən yaxın snapshot-ı tap
    snap_5min = min(history, key=lambda x: abs((now - 300) - x["time"]), default=history[0])
    snap_10min = min(history, key=lambda x: abs((now - 600) - x["time"]), default=history[0])
    
    curr_shots = current_stats["shots_home"] + current_stats["shots_away"]
    curr_corners = current_stats["corners_home"] + current_stats["corners_away"]
    curr_attacks = current_stats["attacks_home"] + current_stats["attacks_away"]
    
    # 5 dəqiqəlik dəyişikliklər
    delta_5 = {
        "shots": max(0, curr_shots - (snap_5min["stats"]["shots_home"] + snap_5min["stats"]["shots_away"])),
        "corners": max(0, curr_corners - (snap_5min["stats"]["corners_home"] + snap_5min["stats"]["corners_away"])),
        "attacks": max(0, curr_attacks - (snap_5min["stats"]["attacks_home"] + snap_5min["stats"]["attacks_away"]))
    }
    
    # 10 dəqiqəlik dəyişikliklər
    delta_10 = {
        "shots": max(0, curr_shots - (snap_10min["stats"]["shots_home"] + snap_10min["stats"]["shots_away"])),
        "corners": max(0, curr_corners - (snap_10min["stats"]["corners_home"] + snap_10min["stats"]["corners_away"])),
        "attacks": max(0, curr_attacks - (snap_10min["stats"]["attacks_home"] + snap_10min["stats"]["attacks_away"]))
    }
    
    return delta_5, delta_10

# --- 3. TƏZYİQ REYTİNQİ HESABLAMASI ---

def calculate_pressure_scores(stats, delta_5):
    """
    Qol Təzyiqi: xG, qapıya dəqiq zərbələr və son 5 dəqiqəlik zərbə intensivliyi.
    Künc Təzyiqi: künclər, təhlükəli hücumlar və son 5 dəqiqəlik artım.
    0 - 100 aralığında bal qaytarır.
    """
    try:
        xg_sum = (stats["xg_home"] or 0) + (stats["xg_away"] or 0)
        total_ontarget = stats["shots_on_target_home"] + stats["shots_on_target_away"]
        
        # Qol təzyiqi balı (0-100)
        goal_score = int((xg_sum * 30) + (total_ontarget * 7) + (delta_5["shots"] * 12))
        goal_score = max(0, min(100, goal_score))
        
        # Künc təzyiqi balı (0-100)
        total_corners = stats["corners_home"] + stats["corners_away"]
        corner_score = int((total_corners * 8) + (delta_5["attacks"] * 2.5) + (delta_5["corners"] * 15))
        corner_score = max(0, min(100, corner_score))
        
        return goal_score, corner_score
    except:
        return 0, 0

# --- 4. STREAMLIT İNTERFEYS MODULU ---

def render_live_scanner():
    st.set_page_config(page_title="Canlı Oyun Analiz Skaneri", layout="wide")
    
    st.title("⚽ Canlı Oyunlar və Statistik Təzyiq Skaneri")
    st.markdown("---")
    
    # Filtrlər bloku
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        selected_date = st.date_input("Tarix Seçin", value=date.today())
    with col2:
        status_filter = st.selectbox("Oyun Statusu", ["Hamısı", "Canlı (In-Progress)", "Bitmiş", "Başlamamış"])
    with col3:
        min_goal_press = st.slider("Min. Qol Təzyiqi Balı", 0, 100, 0)
    with col4:
        min_corner_press = st.slider("Min. Künc Təzyiqi Balı", 0, 100, 0)
        
    search_button = st.button("🔍 Oyunları Skan Et", type="primary")
    
    if search_button or "scanned_data" in st.session_state:
        date_str = selected_date.strftime("%Y-%m-%d")
        
        if search_button:
            with st.spinner("Oyunlar və canlı statistikalar mənbədən toplanır..."):
                raw_events = fetch_scheduled_matches(date_str)
                
                if not raw_events:
                    st.warning("Seçilmiş tarix üçün məlumat tapılmadı və ya API cavab vermədi.")
                    return
                
                processed_rows = []
                leagues_set = set()
                failed_requests = 0
                
                for event in raw_events:
                    tournament = event.get("tournament", {})
                    league_name = tournament.get("name", "Naməlum Liqa")
                    category = tournament.get("category", {}).get("name", "Ümumi")
                    full_league = f"{category} - {league_name}"
                    leagues_set.add(full_league)
                    
                    status_info = event.get("status", {})
                    status_type = status_info.get("type", "")
                    
                    # Status Filtri
                    if status_filter == "Canlı (In-Progress)" and status_type != "inprogress":
                        continue
                    elif status_filter == "Bitmiş" and status_type != "finished" and status_type != "ended":
                        continue
                    elif status_filter == "Başlamamış" and status_type != "notstarted":
                        continue
                        
                    event_id = event.get("id")
                    home_team = event.get("homeTeam", {}).get("name", "Ev")
                    away_team = event.get("awayTeam", {}).get("name", "Qonaq")
                    
                    h_score = event.get("homeScore", {}).get("current", 0)
                    a_score = event.get("awayScore", {}).get("current", 0)
                    score_fmt = f"{h_score} - {a_score}"
                    
                    match_time = status_info.get("description", "-")
                    
                    # Statistikaları çək və emal et
                    raw_stats = fetch_match_statistics(event_id)
                    if not raw_stats:
                        failed_requests += 1
                    
                    stats = parse_statistics(raw_stats)
                    
                    # Snapshot və Deltalar
                    delta_5, delta_10 = update_snapshots_and_calculate_deltas(event_id, stats)
                    g_press, c_press = calculate_pressure_scores(stats, delta_5)
                    
                    # Reytinq filtrləri
                    if g_press < min_goal_press or c_press < min_corner_press:
                        continue
                    
                    # xG Formatlama
                    xg_str = f"{stats['xg_home']:.2f} / {stats['xg_away']:.2f}" if stats['xg_home'] is not None else "N/A"
                    
                    processed_rows.append({
                        "Saat/Dəq": match_time,
                        "Liqa": full_league,
                        "Ev Sahibi": home_team,
                        "Hesab": score_fmt,
                        "Qonaq": away_team,
                        "xG (E/Q)": xg_str,
                        "Zərbələr": f"{stats['shots_home']} - {stats['shots_away']}",
                        "Dəqiq Zərbələr": f"{stats['shots_on_target_home']} - {stats['shots_on_target_away']}",
                        "Künclər": f"{stats['corners_home']} - {stats['corners_away']}",
                        "Son 5 Dəq Təzyiq": f"Zərbə: +{delta_5['shots']} | Künc: +{delta_5['corners']}",
                        "Son 10 Dəq Təzyiq": f"Zərbə: +{delta_10['shots']} | Künc: +{delta_10['corners']}",
                        "Qol Təzyiqi Balı": g_press,
                        "Künc Təzyiqi Balı": c_press
                    })
                
                st.session_state.scanned_data = processed_rows
                st.session_state.stats_summary = {
                    "leagues_count": len(leagues_set),
                    "matches_count": len(processed_rows),
                    "failed_count": failed_requests
                }

        # Nəticələrin göstərilməsi
        summary = st.session_state.get("stats_summary", {})
        if summary:
            st.info(f"📊 Yoxlanılan Liqa Sayı: **{summary.get('leagues_count', 0)}** | "
                    f"Tapılan Matç Sayı: **{summary.get('matches_count', 0)}** | "
                    f"Statistikasız Sorğular: **{summary.get('failed_count', 0)}**")
            
        data = st.session_state.get("scanned_data", [])
        if data:
            df = pd.DataFrame(data)
            
            # Sütunlara görə sıralama üçün Streamlit Dataframe
            st.dataframe(
                df, 
                use_container_width=True, 
                hide_index=True
            )
        else:
            st.warning("Seçilmiş filtrlərə uyğun heç bir matç tapılmadı.")

if __name__ == "__main__":
    render_live_scanner()
