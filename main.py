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
    # 1. 假期定義 (2025-2026)
    def get_holiday_type(date):
        if pd.isna(date): return "未知"
        d_str = date.strftime('%Y-%m-%d')
        holidays = [
            '2025-01-01', '2025-01-25', '2025-01-26', '2025-01-27', '2025-01-28', '2025-01-29', '2025-01-30', '2025-01-31', '2025-02-01', '2025-02-02', '2025-02-28', '2025-03-01', '2025-03-02', '2025-04-03', '2025-04-04', '2025-04-05', '2025-04-06', '2025-05-01', '2025-05-30', '2025-05-31', '2025-06-01', '2025-09-27', '2025-09-28', '2025-09-29', '2025-10-04', '2025-10-05', '2025-10-06', '2025-10-10', '2025-10-11', '2025-10-12', '2025-10-24', '2025-10-25', '2025-10-26', '2025-12-25',
            '2026-01-01', '2026-02-14', '2026-02-15', '2026-02-16', '2026-02-17', '2026-02-18', '2026-02-19', '2026-02-20', '2026-02-21', '2026-02-22', '2026-02-27', '2026-02-28', '2026-03-01', '2026-04-03', '2026-04-04', '2026-04-05', '2026-04-06', '2026-05-01', '2026-05-02', '2026-05-03', '2026-06-19', '2026-06-20', '2026-06-21', '2026-09-25', '2026-09-26', '2026-09-27', '2026-09-28', '2026-10-09', '2026-10-10', '2026-10-11', '2026-10-24', '2026-10-25', '2026-10-26', '2026-12-25', '2026-12-26', '2026-12-27'
        ]
        return "假日" if (d_str in holidays or date.weekday() >= 5) else "平日"

    def is_national_holiday(date):
        # 用於高雄公休日邏輯：檢查是否為國定假日
        d_str = date.strftime('%Y-%m-%d')
        national_days = ['2025-01-01','2025-01-28','2025-01-29','2025-01-30','2025-02-28','2025-04-04','2025-04-05','2025-05-01','2025-05-31','2025-10-06','2025-10-10'] # 簡略清單，實際可擴充
        return d_str in national_days

    # 2. 核心數據處理
    def process_data(df):
        df['交易日期'] = pd.to_datetime(df['交易日期'], errors='coerce')
        df = df.dropna(subset=['交易日期']).copy()
        df['月份'] = df['交易日期'].dt.strftime('%Y/%m月')
        df['假期'] = df['交易日期'].apply(get_holiday_type)
        df['時段'] = pd.to_datetime(df['場次時間'], format='%H:%M', errors='coerce').dt.hour

        def classify(row):
            pname = str(row.get('節目名稱', '')).strip()
            spec = str(row.get('品名規格', '')).strip()
            cid = str(row.get('會員卡號', row.get('客戶編號', ''))).strip().upper()
            qty = pd.to_numeric(row.get('交易數量', 0), errors='coerce') or 0
            rev = pd.to_numeric(row.get('原幣含稅金額', 0), errors='coerce') or 0
            
            res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val = "周邊商品", "無視", 0, 0, 0

            # 人次分類 (含 VIP)
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

            # 計算觀看總數
            if pname != "" and pname != "nan":
                res_watch_val = qty
                n_films = 2 if ('+' in pname or '＋' in pname) else 1
                res_att_val = n_films * qty
            else:
                if any(k in spec for k in ['LED體感','VR','4D劇院','飛行模擬器','極速賽艇','體感賽車']): 
                    res_att_cat = "電競館"
                    res_esports_val = qty
                if res_att_cat != "電競館": res_att_val, res_watch_val = 0, 0

            # 營收分類
            if spec in ['商品兌換券', '票券核銷']: res_rev = "無視"
            elif any(x in spec for x in ['門票分潤', '線上票券']): res_rev = "平台收入"
            elif (pname != "" and pname != "nan") or ("票" in spec) or (res_att_cat not in ["無視", "周邊商品", "電競館"]): res_rev = "票務收入"
            elif res_att_cat == "電競館": res_rev = "電競館收入"
            else: res_rev = "周邊商品"

            return pd.Series([res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val, rev, pname])

        df[['營收分類', '人次分類', '計算人次', '電競人次', '觀看總數', '含稅營收', '清單節目名稱']] = df.apply(classify, axis=1)
        df['統計用營收'] = df.apply(lambda x: 0 if x['營收分類'] == '無視' else x['含稅營收'], axis=1)
        return df

    # --- 3. 介面與表單 ---
    uploaded_file = st.file_uploader("1. 上傳原始檔", type=['csv', 'xlsx'])

    if uploaded_file:
        df_raw = pd.read_csv(uploaded_file, dtype={'會員卡號': str, '客戶編號': str}) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, dtype={'會員卡號': str, '客戶編號': str})
        processed = process_data(df_raw)

        # 側邊欄 A：營運據點表單
        st.sidebar.header("🏢 營運參數設定")
        with st.sidebar.form("site_config_form"):
            sel_site = st.selectbox("選擇據點", ["台北店", "高雄店"])
            off_days = st.date_input("高雄公休日選擇 (僅高雄有效)", value=[], help="選取的日期若非國定假日則不計入分母")
            st.caption("台北: 11:30-20:45 | 高雄: 09:30-16:45")
            update_site = st.form_submit_button("🔘 更新營運設定")

        # 側邊欄 B：影片標籤表單
        st.sidebar.header("🎬 影片類別定義")
        unique_films = sorted([f for f in processed['清單節目名稱'].unique() if f != "" and f != "nan"])
        with st.sidebar.form("film_labeling_form"):
            film_tag_map = {}
            for film in unique_films:
                film_tag_map[film] = st.text_input(f"{film}", value="未分類影片", key=f"inp_{film}")
            update_labels = st.form_submit_button("🔘 更新影片標籤")

        processed['節目類別標籤'] = processed['清單節目名稱'].map(film_tag_map)
        processed.loc[processed['節目類別標籤'] == '無視', ['計算人次', '觀看總數']] = 0

        # 篩選器
        st.sidebar.header("📅 數據篩選")
        sel_months = st.sidebar.multiselect("選擇月份", sorted(processed['月份'].unique()), default=processed['月份'].unique())
        sel_holiday = st.sidebar.multiselect("日期類型", ["平日", "假日"], default=["平日", "假日"])
        
        f_df = processed[(processed['月份'].isin(sel_months)) & (processed['假期'].isin(sel_holiday))].copy()
        # 稼動率分子：包含 VIP 但排除無視
        f_df_util = f_df[f_df['人次分類'] != '無視']
        # 一般人次統計：排除無視與 VIP
        f_df_filtered = f_df[~f_df['人次分類'].isin(['無視', 'VIP'])]

        # --- [關鍵邏輯] 分母 Capacity 計算 ---
        def calc_capacity(df_scope, site, off_dates):
            unique_dates = df_scope['交易日期'].dt.date.unique()
            total_cap = 0
            hourly_cap_detail = []

            for d in unique_dates:
                # 高雄公休判斷
                if site == "高雄店" and d in off_dates and not is_national_holiday(d):
                    continue
                
                # 產生該日場次
                if site == "台北店":
                    # 11:30 - 20:45, 每15分
                    slots = pd.date_range(start=f"{d} 11:30", end=f"{d} 20:45", freq='15min')
                    # 國定假日判定 (若為假日則包含21:00)
                    if get_holiday_type(d) == "假日":
                        is_special_night = True # 21:00 併入 20:00 區間
                    else: is_special_night = False
                else: # 高雄
                    slots = pd.date_range(start=f"{d} 09:30", end=f"{d} 16:45", freq='15min')
                    is_special_night = False

                for s in slots:
                    h = s.hour
                    cap = 20
                    # 台北 20:00 區間特殊處理
                    if site == "台北店" and h == 20 and s.minute == 45 and is_special_night:
                        cap = 40 # 20:45 與 21:00 併場
                    hourly_cap_detail.append({'日期': d, '時段': h, '容量': cap, '假期': get_holiday_type(d)})
            
            return pd.DataFrame(hourly_cap_detail)

        cap_df = calc_capacity(f_df, sel_site, off_days)
        
        # --- 呈現指標 ---
        st.header(f"📊 {sel_site} 綜合營運報表")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("總計營收", f"{f_df['統計用營營收'].sum() if '統計用營營收' in f_df else f_df['統計用營收'].sum():,.0f}")
        c2.metric("i-Ride 人次 (不含VIP)", f"{f_df_filtered['計算人次'].sum():,.0f}")
        c3.metric("總觀看人次 (含VIP)", f"{f_df_util['觀看總數'].sum():,.0f}")
        util_total = (f_df_util['觀看總數'].sum() / cap_df['容量'].sum() * 100) if not cap_df.empty else 0
        c4.metric("平均稼動率", f"{util_total:.2f}%")

        # --- 稼動率時段分析表 ---
        st.divider()
        st.subheader("⏰ 時段別稼動率分析 (按小時)")
        if not cap_df.empty:
            # 分母分組
            cap_grouped = cap_df.groupby(['時段', '假期'])['容量'].sum().reset_index()
            # 分子分組
            act_grouped = f_df_util.groupby(['時段', '假期'])['觀看總數'].sum().reset_index()
            # 合併
            util_table = pd.merge(cap_grouped, act_grouped, on=['時段', '假期'], how='left').fillna(0)
            util_table['稼動率'] = (util_table['觀看總數'] / util_table['容量'] * 100).map('{:.2f}%'.format)
            
            # 轉換為易讀格式 (Pivot)
            util_pivot = util_table.pivot(index='時段', columns='假期', values='稼動率').fillna("-")
            st.table(util_pivot)
        else:
            st.warning("目前篩選條件下無營業天數。")

        # --- 影片類別表與營收表 (略，同前版美化樣式) ---
        # ... [保留前述之 apply_style 與表格呈現代碼] ...
