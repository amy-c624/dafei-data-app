import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

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
    # 1. 假期定義邏輯
    def get_holiday_type(date):
        if pd.isna(date): return "未知"
        d_str = date.strftime('%Y-%m-%d')
        holidays = ['2025-01-01', '2025-01-25', '2025-01-28', '2025-01-29', '2025-01-30', '2025-02-28', '2025-04-04', '2025-04-05', '2025-05-01', '2025-05-31', '2025-10-06', '2025-10-10']
        return "假日" if (d_str in holidays or date.weekday() >= 5) else "平日"

    def is_national_holiday(date):
        d_str = date.strftime('%Y-%m-%d')
        national_days = ['2025-01-01','2025-01-28','2025-01-29','2025-01-30','2025-02-28','2025-04-04','2025-04-05','2025-05-01','2025-05-31','2025-10-06','2025-10-10']
        return d_str in national_days

    # 2. 核心數據處理 (修正 142 人次差異點)
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

            # --- 人次分類邏輯 (確保不漏掉任何關鍵字) ---
            if cid.startswith('P') and spec == "成人票": res_att_cat = "親子卡"
            elif cid == 'Z00054' and spec == "VIP貴賓券核銷": res_att_cat = "校園優惠票"
            elif any(x in spec for x in ['股東券', '股東票']): res_att_cat = "股東"
            elif '貴賓體驗' in spec: res_att_cat = "VVIP"
            elif 'VIP' in spec: res_att_cat = "VIP"
            elif '團購' in spec: res_att_cat = "團購券"
            elif '平台' in spec: res_att_cat = "平台"
            elif any(x in spec for x in ['企業', '團體']): res_att_cat = "團體"
            elif any(x in spec for x in ['市民', '愛心', '學生', '優惠', '成人']): res_att_cat = "散客"
            
            # 【注意】修正 142 點落差：若規格包含「券類溢收」或「券差額」，我們仍需檢查是否有觀看行為
            if any(x in spec for x in ['免費票', '員工票', '票券核銷', '商品兌換券']): 
                res_att_cat = "無視"

            # --- 計算人次與觀看總數 ---
            if pname != "" and pname != "nan":
                res_watch_val = qty
                n_films = 2 if ('+' in pname or '＋' in pname) else 1
                res_att_val = n_films * qty
            else:
                # 電競館關鍵字判定
                if any(k in spec for k in ['LED','VR','4D','飛行','賽艇','賽車','僵屍','殭屍']): 
                    res_att_cat = "電競館"
                    res_esports_val = qty
                if res_att_cat != "電競館": res_att_val, res_watch_val = 0, 0

            # --- 營收分類邏輯 ---
            if spec in ['商品兌換券', '票券核銷']: res_rev = "無視"
            elif any(x in spec for x in ['分潤', '線上票']): res_rev = "平台收入"
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
        df_raw = pd.read_csv(uploaded_file, dtype=str) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, dtype=str)
        processed = process_data(df_raw)
        
        # 側邊欄設定
        st.sidebar.header("🏢 營運與標籤設定")
        with st.sidebar.form("config_form"):
            sel_site = st.selectbox("選擇據點", ["台北店", "高雄店"])
            off_days_list = st.date_input("高雄公休日 (僅高雄店生效)", value=[])
            st.form_submit_button("🔘 更新據點設定")

        unique_films = sorted([f for f in processed['清單節目名稱'].unique() if f != "" and f != "nan"])
        with st.sidebar.form("film_labeling"):
            film_tag_map = {f: st.text_input(f, value="未分類", key=f"k_{f}") for f in unique_films}
            st.form_submit_button("🔘 更新影片標籤")

        processed['節目類別標籤'] = processed['清單節目名稱'].map(film_tag_map)
        processed.loc[processed['節目類別標籤'] == '無視', ['計算人次', '觀看總數']] = 0
        
        sel_months = st.sidebar.multiselect("月份", sorted(processed['月份'].unique()), default=processed['月份'].unique())
        sel_holiday = st.sidebar.multiselect("日期類型", ["平日", "假日"], default=["平日", "假日"])
        
        f_df = processed[(processed['月份'].isin(sel_months)) & (processed['假期'].isin(sel_holiday))].copy()
        
        # 定義統計群組
        f_df_util = f_df[f_df['人次分類'] != '無視']
        f_df_filtered = f_df[~f_df['人次分類'].isin(['無視', 'VIP'])]

        # Capacity 分母邏輯
        def calc_capacity(df_scope, site, off_dates):
            unique_dates = df_scope['交易日期'].dt.date.unique()
            res = []
            for d in unique_dates:
                if site == "高雄店" and d in off_dates and not is_national_holiday(d): continue
                # 決定時段範圍
                rng = pd.date_range(f"{d} 11:30", f"{d} 20:45", freq='15min') if site == "台北店" else pd.date_range(f"{d} 09:30", f"{d} 16:45", freq='15min')
                is_h = True if (site=="台北店" and get_holiday_type(d)=="假日") else False
                for s in rng:
                    # 台北假日 20:45 與 21:00 併場邏輯
                    cap = 40 if (site=="台北店" and s.hour==20 and s.minute==45 and is_h) else 20
                    res.append({'時段小時': s.hour, '容量': cap, '假期': get_holiday_type(d)})
            return pd.DataFrame(res)

        cap_df = calc_capacity(f_df, sel_site, off_days_list)

        # 頂部指標
        st.header(f"📊 {sel_site} 營運分析報告")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("總計營收", f"{f_df['統計用營收'].sum():,.0f}")
        c2.metric("i-Ride 人次 (去VIP)", f"{f_df_filtered['計算人次'].sum():,.0f}")
        c3.metric("總觀看人次 (含VIP)", f"{f_df_util['觀看總數'].sum():,.0f}")
        c_sum = cap_df['容量'].sum() if not cap_df.empty else 0
        c4.metric("平均稼動率", f"{(f_df_util['觀看總數'].sum()/c_sum*100):.2f}%" if c_sum > 0 else "0%")

        def apply_style(x, total_len):
            is_tot = (x.name == total_len - 1) or any("小計" in str(v) or "合計" in str(v) for v in x.values)
            return [f'background-color: {HIGHLIGHT_COLOR}; font-weight: bold' if is_tot else '' for _ in x]

        # 營收與人次表
        st.divider()
        t1, t2 = st.columns(2)
        with t1:
            st.subheader("💰 營收分類合計")
            rev_t = f_df.groupby('營營收分類')['含稅營收'].sum().reset_index() if '營營收分類' in f_df else f_df.groupby('營收分類')['含稅營收'].sum().reset_index()
            rev_f = pd.concat([rev_t, pd.DataFrame([{'營收分類': '合計(不含無視)', '含稅營收': f_df['統計用營收'].sum()}])]).reset_index(drop=True)
            st.table(rev_f.style.format({'含稅營收': '{:,.0f}'}).apply(apply_style, total_len=len(rev_f), axis=1))
        with t2:
            st.subheader("👥 人次分類合計")
            att_t = f_df.groupby('人次分類')[['計算人次', '觀看總數', '電競人次']].sum().reset_index()
            att_f = pd.concat([att_t, pd.DataFrame([{
                '人次分類': '合計(不含無視、VIP)', '計算人次': f_df_filtered['計算人次'].sum(), 
                '觀看總數': f_df_filtered['觀看總數'].sum(), '電競人次': f_df['電競人次'].sum()
            }])]).reset_index(drop=True)
            st.table(att_f.style.format({'計算人次': '{:,.0f}', '觀看總數': '{:,.0f}', '電競人次': '{:,.0f}'}).apply(apply_style, total_len=len(att_f), axis=1))

        # 影片統計表
        st.divider()
        st.subheader("🎬 影片組合統計 (排除無視/VIP)")
        f_s = f_df_filtered[f_df_filtered['清單節目名稱'] != ""].groupby(['節目類別標籤', '清單節目名稱']).agg({'計算人次': 'sum', '觀看總數': 'sum'}).reset_index()
        f_cat = f_s.groupby('節目類別標籤').agg({'計算人次': 'sum', '觀看總數': 'sum'}).reset_index()
        f_cat['清單節目名稱'] = "--- 類別小計 ---"
        f_fin = pd.concat([f_s, f_cat]).sort_values(['節目類別標籤', '清單節目名稱'], ascending=[True, False]).reset_index(drop=True)
        st.table(f_fin.style.format({'計算人次': '{:,.0f}', '觀看總數': '{:,.0f}'}).apply(apply_style, total_len=len(f_fin), axis=1))

        # 稼動率表
        st.divider()
        st.subheader("⏰ 時段別稼動率分析")
        if not cap_df.empty:
            c_g = cap_df.groupby(['時段小時', '假期'])['容量'].sum().reset_index()
            a_g = f_df_util.groupby(['時段小時', '假期'])['觀看總數'].sum().reset_index()
            m_g = pd.merge(c_g, a_g, on=['時段小時', '假期'], how='left').fillna(0)
            m_g['稼動率'] = (m_g['觀看總數'] / m_g['容量'] * 100).map('{:.2f}%'.format)
            piv = m_g.pivot(index='時段小時', columns='假期', values='稼動率').fillna("-")
            piv.index = [f"{h:02d}:00-{h+1:02d}:00" for h in piv.index]
            piv.index.name = "營業時間區段"
            st.table(piv)
