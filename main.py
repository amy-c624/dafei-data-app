import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta

# --- 0. 密碼驗證 ---
def check_password():
    def password_entered():
        if st.session_state["password"] == "TEST":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    if "password_correct" not in st.session_state:
        st.text_input("請輸入授權密碼", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("密碼不正確", type="password", on_change=password_entered, key="password")
        return False
    else:
        return True

st.set_page_config(page_title="i-Ride 營運智慧分析系統", layout="wide")
HIGHLIGHT_COLOR = "rgba(0, 123, 255, 0.4)" 

if check_password():
    # 1. 假期定義
    def get_holiday_type(date):
        if pd.isna(date): return "未知"
        d_str = date.strftime('%Y-%m-%d')
        holidays = ['2025-01-01', '2025-01-25', '2025-01-28', '2025-01-29', '2025-01-30', '2025-02-28', '2025-04-04', '2025-04-05', '2025-05-01', '2025-05-31', '2025-10-06', '2025-10-10']
        return "假日" if (d_str in holidays or date.weekday() >= 5) else "平日"

    def is_national_holiday(date):
        d_str = date.strftime('%Y-%m-%d')
        national_days = ['2025-01-01','2025-01-28','2025-01-29','2025-01-30','2025-02-28','2025-04-04','2025-04-05','2025-05-01','2025-05-31','2025-10-06','2025-10-10']
        return d_str in national_days

    # 2. 核心處理函數
    def process_data(df):
        df['交易日期'] = pd.to_datetime(df['交易日期'], errors='coerce')
        df = df.dropna(subset=['交易日期']).copy()
        df['月份'] = df['交易日期'].dt.strftime('%Y/%m月')
        df['假期'] = df['交易日期'].apply(get_holiday_type)
        df['時段小時'] = pd.to_datetime(df['場次時間'], format='%H:%M', errors='coerce').dt.hour
        
        def classify(row):
            pname = str(row.get('節目名稱', '')).strip()
            spec = str(row.get('品名規格', '')).strip()
            cid = str(row.get('會員卡號', row.get('客戶編號', ''))).strip().upper()
            qty = pd.to_numeric(row.get('交易數量', 0), errors='coerce') or 0
            rev = pd.to_numeric(row.get('原幣含稅金額', 0), errors='coerce') or 0
            res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val = "周邊商品", "無視", 0, 0, 0

            if cid.startswith('P') and spec == "成人票": res_att_cat = "親子卡"
            elif cid == 'Z00054' and spec == "VIP貴賓券核銷": res_att_cat = "校園優惠票"
            elif any(x in spec for x in ['股東券', '股東票']): res_att_cat = "股東"
            elif '貴賓體驗通行證核銷' in spec: res_att_cat = "VVIP"
            elif 'VIP貴賓券核銷' in spec: res_att_cat = "VIP"
            elif any(x in spec for x in ['團購兌換券展延', '團購兌換券核銷']): res_att_cat = "團購券"
            elif '平台通路票' in spec: res_att_cat = "平台"
            elif any(x in spec for x in ['企業優惠票', '團體優惠票']): res_att_cat = "團體"
            elif any(x in spec for x in ['市民票', '愛心票', '學生票', '優惠套票', '成人票']): res_att_cat = "散客"
            if any(x in spec for x in ['免費票', '員工票', '券差額', '券類溢收-商品', '商品兌換券', '票券核銷', '活動服務費']): res_att_cat = "無視"

            if pname != "" and pname != "nan":
                res_watch_val = qty
                n_films = 2 if ('+' in pname or '＋' in pname) else 1
                res_att_val = n_films * qty
            else:
                if any(k in spec for k in ['LED體感','VR','4D劇院','飛行模擬器','極速賽艇','體感賽車','僵屍籠']): 
                    res_att_cat = "電競館"
                    res_esports_val = qty
                if res_att_cat != "電競館": res_att_val, res_watch_val = 0, 0

            if spec in ['商品兌換券', '票券核銷']: res_rev = "無視"
            elif any(x in spec for x in ['門票分潤', '線上票券']): res_rev = "平台收入"
            elif (pname != "" and pname != "nan") or ("票" in spec) or ("券" in spec) or (res_att_cat not in ["無視", "周邊商品", "電競館"]): res_rev = "票務收入"
            elif res_att_cat == "電競館": res_rev = "電競館收入"
            else: res_rev = "周邊商品"

            return pd.Series([res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val, rev, pname])

        df[['營收分類', '人次分類', '計算人次', '電競人次', '觀看總數', '含稅營收', '清單節目名稱']] = df.apply(classify, axis=1)
        df['統計用營收'] = df.apply(lambda x: 0 if x['營收分類'] == '無視' else x['含稅營收'], axis=1)
        return df

    # --- 3. 介面呈現 ---
    uploaded_file = st.file_uploader("1. 上傳原始檔", type=['csv', 'xlsx'])

    if uploaded_file:
        # 修正後的讀取邏輯
        if uploaded_file.name.endswith('.csv'):
            df_raw = pd.read_csv(uploaded_file, dtype={'會員卡號': str, '客戶編號': str})
        else:
            df_raw = pd.read_excel(uploaded_file, dtype={'會員卡號': str, '客戶編號': str})
            
        processed = process_data(df_raw)
        
        # 側邊欄 A
        st.sidebar.header("🏢 營運參數設定")
        with st.sidebar.form("site_config_form"):
            sel_site = st.selectbox("選擇據點", ["台北店", "高雄店"])
            off_days_list = st.date_input("高雄公休日選擇 (僅高雄有效)", value=[])
            st.form_submit_button("🔘 更新營運設定")

        # 側邊欄 B
        st.sidebar.header("🎬 影片類別定義")
        unique_films = sorted([f for f in processed['清單節目名稱'].unique() if f != "" and f != "nan"])
        with st.sidebar.form("film_labeling_form"):
            film_tag_map = {}
            for film in unique_films:
                film_tag_map[film] = st.text_input(f"{film}", value="未分類影片", key=f"inp_{film}")
            st.form_submit_button("🔘 更新影片標籤")

        processed['節目類別標籤'] = processed['清單節目名稱'].map(film_tag_map)
        processed.loc[processed['節目類別標籤'] == '無視', ['計算人
