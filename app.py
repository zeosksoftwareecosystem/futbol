import streamlit as st
import pandas as pd
from datetime import date, timedelta
from live_scanner import scan_date_range, get_source_catalog
from engine.snapshots import init_db

st.set_page_config(page_title="Football Live Scanner", layout="wide")
init_db()
st.title("⚽ Football Live Scanner")
st.caption("Ayrıca qurulmuş modul · yalnız açıq/no-key mənbələr · çatışmayan statistika N/A göstərilir")

with st.sidebar:
    st.header("Axtarış")
    d1 = st.date_input("Başlanğıc tarix", value=date.today())
    d2 = st.date_input("Son tarix", value=date.today())
    status = st.multiselect("Oyun statusu", ["LIVE", "UPCOMING", "FINISHED"], default=["LIVE", "UPCOMING", "FINISHED"])
    leagues = st.text_input("Liqa filtri (istəyə görə)", placeholder="Premier League, La Liga...")
    min_goal = st.slider("Minimum qol təzyiqi", 0, 100, 0)
    min_corner = st.slider("Minimum künc təzyiqi", 0, 100, 0)
    run = st.button("🔎 OYUNLARI TAP VƏ ANALİZ ET", type="primary", use_container_width=True)

st.subheader("Mənbələr və əhatə")
for src in get_source_catalog():
    st.write(f"**{src['name']}** — {src['role']} · {src['status']}")

if run:
    if d2 < d1:
        st.error("Son tarix başlanğıc tarixdən əvvəl ola bilməz.")
    else:
        with st.spinner("Açıq mənbələr yoxlanılır..."):
            result = scan_date_range(d1.isoformat(), d2.isoformat())
        st.session_state["scan_result"] = result
        st.session_state["scan_filters"] = {"status": status, "league": leagues, "goal": min_goal, "corner": min_corner}

if "scan_result" in st.session_state:
    result = st.session_state["scan_result"]
    f = st.session_state.get("scan_filters", {})
    matches = result["matches"]
    stats = result["stats"]
    a,b,c,d = st.columns(4)
    a.metric("Tapılan oyun", len(matches))
    b.metric("Yoxlanmış liqa", stats["leagues_checked"])
    c.metric("Sorğu xətası", stats["request_errors"])
    d.metric("Statistika olan oyun", stats["matches_with_stats"])
    st.caption(f"Mənbə: {stats['source_note']}")
    df = pd.DataFrame(matches)
    if not df.empty:
        if f.get("status"):
            df = df[df["status"].isin(f["status"])]
        if f.get("league"):
            df = df[df["league"].str.contains(f["league"], case=False, na=False)]
        df = df[(df["goal_pressure"] >= f.get("goal",0)) & (df["corner_pressure"] >= f.get("corner",0))]
        preferred = ["kickoff","league","home","away","score","minute","xg","shots","sot","corners",
                     "last5_pressure","last10_pressure","goal_pressure","corner_pressure","status","source"]
        st.dataframe(df[[x for x in preferred if x in df.columns]], use_container_width=True, hide_index=True)
        with st.expander("Oyunlar üzrə xam statistikalar"):
            st.json(matches)
    else:
        st.info("Seçilmiş tarix aralığında açıq mənbələrdən oyun tapılmadı.")
    if result["warnings"]:
        with st.expander("Mənbə xəbərdarlıqları"):
            for w in result["warnings"]:
                st.warning(w)
else:
    st.info("Tarix aralığını seçin və analizi yalnız düyməyə basdıqdan sonra başladın.")
