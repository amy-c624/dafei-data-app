import streamlit as st
import pandas as pd
import numpy as np

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
    else: return True

st.set_page_config(page_title="i-Ride 營收分析系統", layout="wide")
HIGHLIGHT_COLOR = "rgba(0, 123, 255, 0.4)" 

if check_password():
    # 1. 假期定義
    def get_holiday_type(date):
        if pd.isna(date): return "未知"
        d_str = date.strftime('%Y-%m-%d')
        # 簡化 2025 假期清單
        holidays = ['2025-01-01', '2025-01-28', '2025-01-29', '2025-01-30', '2025-02-28', '2025-04-04', '2025-04-05', '2025-05-01', '2025-05-31', '2025-10-06', '2025-10-10']
        return "假日" if (d_str in holidays or date.weekday() >= 5) else "平日"

    # 2. 核心數據處理
    def process_data(df):
        df['交易日期'] = pd.to_datetime(df['交易日期'], errors='coerce')
        df = df.dropna(subset=['交易日期']).copy()
        df['月份'] = df['交易日期'].dt.strftime('%Y/%m月')
        df['假期'] = df['交易日期'].apply(get_holiday_type)
        df['時段小時'] = pd.to_datetime(df['場次時間'], format='%H:%M', errors='coerce').dt.hour

        def classify(row):
            # [關鍵修正]：使用 strip() 確保含有空格的節目名稱也能被正確識別為有效或無效
            pname = str(row.get('節目名稱', '')).strip()
            spec = str(row.get('品名規格', '')).strip()
            cid = str(row.get('會員卡號', row.get('客戶編號', ''))).strip().upper()
            qty = pd.to_numeric(row.get('交易數量', 0), errors='coerce') or 0
            rev = pd.to_numeric(row.get('原幣含稅金額', 0), errors='coerce') or 0
            
            res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val = "周邊商品", "無視", 0, 0, 0

            # --- A. 人次分類 (完全依照您的穩定版) ---
            if cid.startswith('P') and spec == "成人票": res_att_cat = "親子卡"
            elif cid == 'Z00054' and spec == "VIP貴賓券核銷": res_att_cat = "校園優惠票"
            elif any(x in spec for x in ['股東券', '股東票']): res_att_cat = "股東"
            elif '貴賓體驗' in spec: res_att_cat = "VVIP"
            elif 'VIP' in spec: res_att_cat = "VIP"
            elif '團購' in spec: res_att_cat = "團購券"
            elif '平台' in spec: res_att_cat = "平台"
            elif any(x in spec for x in ['企業', '團體']): res_att_cat = "團體"
            elif any(x in spec for x in ['市民', '愛心', '學生', '優惠', '成人']): res_att_cat = "散客"
            
            if any(x in spec for x in ['免費票', '員工票', '券差額', '券類溢收', '商品兌換券', '票券核銷', '活動服務費']): 
                res_att_cat = "無視"

            # --- B. 數值邏輯 (嚴格執行：沒節目 = 0) ---
            # 這裡的 pname 已經經過 strip()，如果是空格也會變成 ""
            if pname != "" and pname != "nan":
                res_watch_val = qty
                n_films = 2 if ('+' in pname or '＋' in pname) else 1
                res_att_val = n_films * qty
            else:
                # 沒節目名稱時，檢查是否為電競館設備
                if any(k in spec for k in ['LED','VR','4D','飛行','賽艇','賽車','僵屍','殭屍']): 
                    res_att_cat = "電競館"
                    res_esports_val = qty
                # 若非電競館，則人次與觀看數強歸 0
                if res_att_cat != "電競館": res_att_val, res_watch_val = 0, 0

            # --- C. 營收分類 (依照您的穩定版) ---
            if spec in ['商品兌換券', '票券核銷']: res_rev = "無視"
            elif any(x in spec for x in ['分潤', '線上票']): res_rev = "平台收入"
            elif (pname != "" and pname != "nan") or ("票" in spec) or ("券" in spec): res_rev = "票務收入"
            elif res_att_cat == "電競館": res_rev = "電競館收入"
            else: res_rev = "周邊商品"

            return pd.Series([res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val, rev, pname])

        df[['營收分類', '人次分類', '計算人次', '電競人次', '觀看總數', '含稅營收', '清單節目名稱']] = df.apply(classify, axis=1)
        df['統計用營收'] = df.apply(lambda x: 0 if x['營收分類'] == '無視' else x['含稅營收'], axis=1)
        return df

    # 3. 介面呈現
    uploaded_file = st.file_uploader("1. 上傳原始檔", type=['csv', 'xlsx'])
    if uploaded_file:
        df_raw = pd.read_csv(uploaded_file, dtype=str) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, dtype=str)
        processed = process_data(df_raw)
        
        # 側邊欄：設定與標籤
        st.sidebar.header("🏢 設定")
        sel_site = st.sidebar.selectbox("據點", ["台北店", "高雄店"])
        off_days = st.sidebar.date_input("高雄公休日", value=[])
        
        # 影片標籤功能
        unique_films = sorted([f for f in processed['清單節目名稱'].unique() if f != "" and f != "nan"])
        with st.sidebar.form("tags"):
            film_map = {f: st.text_input(f, value="未分類") for f in unique_films}
            st.form_submit_button("🔘 更新標籤")
        processed['標籤'] = processed['清單節目名稱'].map(film_map)

        # 篩選器
        sel_months = st.sidebar.multiselect("月份", sorted(processed['月份'].unique()), default=processed['月份'].unique())
        f_df = processed[processed['月份'].isin(sel_months)].copy()
        f_df_filtered = f_df[~f_df['人次分類'].isin(['無視', 'VIP'])]

        # 指標顯示
        st.header(f"📊 {sel_site} 分析報告")
        c1, c2, c3 = st.columns(3)
        c1.metric("總計營收", f"{f_df['統計用營收'].sum():,.0f}")
        c2.metric("i-Ride 人次 (去VIP)", f"{f_df_filtered['計算人次'].sum():,.0f}")
        c3.metric("電競館人次", f"{f_df['電競人次'].sum():,.0f}")

        # 表格顯示邏輯
        def apply_style(x, t_len):
            is_tot = (x.name == t_len-1) or any("合計" in str(v) for v in x.values)
            return [f'background-color: {HIGHLIGHT_COLOR}; font-weight: bold' if is_tot else '' for _ in x]

        st.divider()
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("👥 人次分類合計")
            att_t = f_df.groupby('人次分類')[['計算人次', '觀看總數', '電競人次']].sum().reset_index()
            att_f = pd.concat([att_t, pd.DataFrame([{'人次分類': '合計(去無視/VIP)', '計算人次': f_df_filtered['計算人次'].sum(), '觀看總數': f_df_filtered['觀看總數'].sum(), '電競人次': f_df['電競人次'].sum()}])]).reset_index(drop=True)
            st.table(att_f.style.format('{:,.0f}', subset=['計算人次','觀看總數','電競人次']).apply(apply_style, t_len=len(att_f), axis=1))

        with col_b:
            st.subheader("🎬 影片類別統計")
            fs = f_df_filtered[f_df_filtered['清單節目名稱'] != ""].groupby(['標籤','清單節目名稱']).agg({'計算人次':'sum'}).reset_index()
            st.table(fs.style.format('{:,.0f}', subset=['計算人次']).apply(apply_style, t_len=len(fs), axis=1))
