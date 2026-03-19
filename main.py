import streamlit as st
import pandas as pd
import numpy as np

# --- [0-2 區塊維持您的穩定版邏輯，僅修正上述數值 Bug] ---

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

st.set_page_config(page_title="i-Ride 營收數據分析", layout="wide")
HIGHLIGHT_COLOR = "rgba(0, 123, 255, 0.4)" 

if check_password():
    def get_holiday_type(date):
        if pd.isna(date): return "未知"
        d_str = date.strftime('%Y-%m-%d')
        holidays_2025 = ['2025-01-01', '2025-01-25', '2025-01-26', '2025-01-27', '2025-01-28', '2025-01-29', '2025-01-30', '2025-01-31', '2025-02-01', '2025-02-02', '2025-02-28', '2025-03-01', '2025-03-02', '2025-04-03', '2025-04-04', '2025-04-05', '2025-04-06', '2025-05-01', '2025-05-30', '2025-05-31', '2025-06-01', '2025-09-27', '2025-09-28', '2025-09-29', '2025-10-04', '2025-10-05', '2025-10-06', '2025-10-10', '2025-10-11', '2025-10-12', '2025-10-24', '2025-10-25', '2025-10-26', '2025-12-25']
        all_holidays = holidays_2025 # 簡化示範
        return "假日" if (d_str in all_holidays or date.weekday() >= 5) else "平日"

    def process_data(df):
        df['交易日期'] = pd.to_datetime(df['交易日期'], errors='coerce')
        df = df.dropna(subset=['交易日期']).copy()
        df['月份'] = df['交易日期'].dt.strftime('%Y/%m月')
        df['假期'] = df['交易日期'].apply(get_holiday_type)
        # 額外新增：為稼動率準備時段
        df['時段小時'] = pd.to_datetime(df['場次時間'], format='%H:%M', errors='coerce').dt.hour

        def classify(row):
            pname = str(row.get('節目名稱', '')).strip()
            spec = str(row.get('品名規格', '')).strip()
            cid = str(row.get('會員卡號', row.get('客戶編號', ''))).strip().upper()
            qty = pd.to_numeric(row.get('交易數量', 0), errors='coerce') or 0
            rev = pd.to_numeric(row.get('原幣含稅金額', 0), errors='coerce') or 0
            
            res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val = "周邊商品", "無視", 0, 0, 0

            # --- [A] 分類邏輯 (維持原樣) ---
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

            # --- [核心修正：確保沒節目名稱也會算 qty] ---
            if pname != "" and pname != "nan":
                res_watch_val = qty
                n_films = 2 if ('+' in pname or '＋' in pname) else 1
                res_att_val = n_films * qty
            else:
                esports_k = ['LED體感','VR','4D劇院','飛行模擬器','極速賽艇','體感賽車','僵屍籠','殭屍籠']
                if any(k in spec for k in esports_k): 
                    res_att_cat = "電競館"
                    res_esports_val = qty
                    res_att_val = qty
                
                if res_att_cat != "電競館":
                    # 修正：若沒節目名但有分類，仍應計算數量，避免總數少算
                    res_att_val, res_watch_val = qty, qty

            # --- [B] 營收邏輯 (維持原樣) ---
            if spec in ['商品兌換券', '票券核銷']: res_rev = "無視"
            elif any(x in spec for x in ['門票分潤', '線上票券']): res_rev = "平台收入"
            elif spec == '團購兌換券': res_rev = "預售票收入"
            elif spec == "券差額" or "活動服務費" in spec: res_rev = "票務收入"
            elif spec == "券類溢收-商品": res_rev = "周邊商品"
            elif '巨人' in spec: res_rev = "巨人周邊商品"
            elif spec in ['妖怪森林公仔', '妖怪森林公仔-煞', '妖怪森林外傳', '妖怪森林盲盒']: res_rev = "妖怪周邊商品"
            elif (pname != "" and pname != "nan") or ("票" in spec) or ("券" in spec) or (res_att_cat not in ["無視", "周邊商品", "電競館"]): res_rev = "票務收入"
            elif res_att_cat == "電競館": res_rev = "電競館收入"
            else: res_rev = "周邊商品"

            return pd.Series([res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val, rev, pname])

        df[['營收分類', '人次分類', '計算人次', '電競人次', '觀看總數', '含稅營收', '清單節目名稱']] = df.apply(classify, axis=1)
        df['統計用營收'] = df.apply(lambda x: 0 if x['營收分類'] == '無視' else x['含稅營收'], axis=1)
        return df

    # --- 以下為額外新增的功能 --- (Line 105 起)

    def calc_capacity(df_in, site, off_dt):
        days = df_in['交易日期'].dt.date.unique()
        res = []
        for d in days:
            if site == "高雄店" and d in off_dt: continue
            start, end = (11, 21) if site=="台北店" else (9, 17)
            slots = pd.date_range(f"{d} {start}:30", f"{d} {end}:00", freq='15min')
            is_h = get_holiday_type(d) == "假日"
            for s in slots:
                cap = 40 if (site=="台北店" and is_h and s.hour==21 and s.minute==0) else 20
                res.append({'時段小時': s.hour, '假期': get_holiday_type(d), '容量': cap})
        return pd.DataFrame(res)

    uploaded_file = st.file_uploader("1. 上傳原始檔", type=['csv', 'xlsx'])
    if uploaded_file:
        df_raw = pd.read_csv(uploaded_file, dtype=str) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, dtype=str)
        processed = process_data(df_raw)
        
        # 側邊欄外掛
        st.sidebar.header("⚙️ 設定")
        sel_site = st.sidebar.selectbox("門店", ["台北店", "高雄店"])
        off_days = st.sidebar.date_input("公休日", value=[])
        sel_months = st.sidebar.multiselect("月份", sorted(processed['月份'].unique()), default=processed['月份'].unique())
        sel_holiday = st.sidebar.multiselect("類型", ["平日", "假日"], default=["平日", "假日"])
        
        f_df = processed[(processed['月份'].isin(sel_months)) & (processed['假期'].isin(sel_holiday))].copy()
        f_df_filtered = f_df[~f_df['人次分類'].isin(['無視', 'VIP'])]

        # 指標卡 (此時數值應已修正)
        st.header(f"📊 {sel_site} 分析報表")
        c1, c2, c3 = st.columns(3)
        c1.metric("總計營收", f"{f_df['統計用營收'].sum():,.0f}")
        c2.metric("i-Ride 人次 (去無視/VIP)", f"{f_df_filtered['計算人次'].sum():,.0f}")
        c3.metric("電競館人次", f"{f_df['電競人次'].sum():,.0f}")

        # 下載外掛
        st.download_button("💾 下載分析明細", f_df.to_csv(index=False).encode('utf-8-sig'), "data.csv")

        # 呈現表格 (省略樣式代碼以保持簡潔)
        st.subheader("👥 人次分類合計")
        st.table(f_df.groupby('人次分類')[['計算人次', '觀看總數']].sum())

        # 稼動率外掛
        st.divider()
        st.subheader("⏰ 時段稼動率")
        cp = calc_capacity(f_df, sel_site, off_days)
        if not cp.empty:
            cg = cp.groupby(['時段小時','假期'])['容量'].sum().reset_index()
            ag = f_df[f_df['人次分類'] != '無視'].groupby(['時段小時','假期'])['觀看總數'].sum().reset_index()
            mg = pd.merge(cg, ag, on=['時段小時','假期'], how='left').fillna(0)
            mg['稼動率'] = (mg['觀看總數']/mg['容量']*100).map('{:.2f}%'.format)
            st.table(mg.pivot(index='時段小時', columns='假期', values='稼動率'))
