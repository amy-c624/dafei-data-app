import streamlit as st
import pandas as pd
import numpy as np
import io

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

st.set_page_config(page_title="i-Ride 營運智慧分析系統", layout="wide")
HIGHLIGHT_COLOR = "rgba(0, 123, 255, 0.4)" 

if check_password():
    # 1. 假期定義
    def get_holiday_type(date):
        if pd.isna(date): return "未知"
        d_str = date.strftime('%Y-%m-%d')
        holidays = ['2025-01-01', '2025-01-28', '2025-01-29', '2025-01-30', '2025-02-28', '2025-04-04', '2025-04-05', '2025-05-01', '2025-05-31', '2025-10-06', '2025-10-10']
        return "假日" if (d_str in holidays or date.weekday() >= 5) else "平日"

    def is_national_holiday(date):
        d_str = date.strftime('%Y-%m-%d')
        return d_str in ['2025-01-01','2025-01-28','2025-01-29','2025-01-30','2025-02-28','2025-04-04','2025-04-05','2025-05-01','2025-05-31','2025-10-06','2025-10-10']

    # 2. 核心處理函數 (對齊 34,516 邏輯)
    def process_data(df):
        df['交易日期'] = pd.to_datetime(df['交易日期'], errors='coerce')
        df = df.dropna(subset=['交易日期']).copy()
        df['月份'] = df['交易日期'].dt.strftime('%Y/%m月')
        df['假期'] = df['交易日期'].apply(get_holiday_type)
        df['時段小時'] = pd.to_datetime(df['場次時間'], format='%H:%M', errors='coerce').dt.hour

        def classify(row):
            pname = str(row.get('節目名稱', '')).strip() # strip() 解決隱形空格問題
            spec = str(row.get('品名規格', '')).strip()
            cid = str(row.get('會員卡號', row.get('客戶編號', ''))).strip().upper()
            qty = pd.to_numeric(row.get('交易數量', 0), errors='coerce') or 0
            rev = pd.to_numeric(row.get('原幣含稅金額', 0), errors='coerce') or 0
            
            res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val = "周邊商品", "無視", 0, 0, 0

            # --- A. 人次分類 ---
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

            # --- B. 數值邏輯 (嚴格：沒節目不計人次) ---
            if pname != "" and pname != "nan":
                res_watch_val = qty
                n_films = 2 if ('+' in pname or '＋' in pname) else 1
                res_att_val = n_films * qty
            else:
                if any(k in spec for k in ['LED','VR','4D','飛行','賽艇','賽車','僵屍','殭屍']): 
                    res_att_cat = "電競館"
                    res_esports_val = qty
                if res_att_cat != "電競館": res_att_val, res_watch_val = 0, 0

            # --- C. 營收分類 ---
            if spec in ['商品兌換券', '票券核銷']: res_rev = "無視"
            elif any(x in spec for x in ['分潤', '線上票']): res_rev = "平台收入"
            elif (pname != "" and pname != "nan") or ("票" in spec) or ("券" in spec): res_rev = "票務收入"
            elif res_att_cat == "電競館": res_rev = "電競館收入"
            else: res_rev = "周邊商品"

            return pd.Series([res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val, rev, pname])

        df[['營收分類', '人次分類', '計算人次', '電競人次', '觀看總數', '含稅營收', '清單節目名稱']] = df.apply(classify, axis=1)
        df['統計用營收'] = df.apply(lambda x: 0 if x['營收分類'] == '無視' else x['含稅營收'], axis=1)
        return df

    # 3. UI 介面
    uploaded_file = st.file_uploader("1. 上傳原始檔", type=['csv', 'xlsx'])
    if uploaded_file:
        df_raw = pd.read_csv(uploaded_file, dtype=str) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, dtype=str)
        processed = process_data(df_raw)
        
        # 側邊欄：篩選與標籤
        st.sidebar.header("⚙️ 篩選與設定")
        sel_site = st.sidebar.selectbox("據點", ["台北店", "高雄店"])
        off_days = st.sidebar.date_input("高雄公休日", value=[])
        sel_months = st.sidebar.multiselect("月份", sorted(processed['月份'].unique()), default=processed['月份'].unique())
        sel_holiday = st.sidebar.multiselect("日期類型", ["平日", "假日"], default=["平日", "假日"])
        
        # 影片類別標籤
        unique_films = sorted([f for f in processed['清單節目名稱'].unique() if f != "" and f != "nan"])
        with st.sidebar.form("tagging"):
            film_map = {f: st.text_input(f, value="未分類") for f in unique_films}
            st.form_submit_button("🔘 更新類別")
        processed['標籤'] = processed['清單節目名稱'].map(film_map)

        # 套用篩選
        f_df = processed[(processed['月份'].isin(sel_months)) & (processed['假期'].isin(sel_holiday))].copy()
        f_df_filtered = f_df[~f_df['人次分類'].isin(['無視', 'VIP'])]

        # 指標卡
        st.header(f"📊 {sel_site} 分析報表")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("總計營收", f"{f_df['統計用營收'].sum():,.0f}")
        c2.metric("i-Ride 人次 (去VIP)", f"{f_df_filtered['計算人次'].sum():,.0f}")
        c3.metric("電競館人次", f"{f_df['電競人次'].sum():,.0f}")
        
        # 下載功能
        csv_data = f_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("💾 下載分析明細 (CSV)", csv_data, "report.csv", "text/csv")

        # 表格樣式
        def style_total(x, t_len):
            is_tot = (x.name == t_len-1) or any("合計" in str(v) for v in x.values)
            return [f'background-color: {HIGHLIGHT_COLOR}; font-weight: bold' if is_tot else '' for _ in x]

        st.divider()
        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("💰 營收分類合計")
            rt = f_df.groupby('營收分類')['含稅營收'].sum().reset_index()
            rf = pd.concat([rt, pd.DataFrame([{'營收分類':'合計(不含無視)','含稅營收':f_df['統計用營收'].sum()}])]).reset_index(drop=True)
            # 修正點：只對數字欄位進行格式化
            st.table(rf.style.format({'含稅營收':'{:,.0f}'}).apply(style_total, t_len=len(rf), axis=1))

        with col_r:
            st.subheader("👥 人次分類合計")
            at = f_df.groupby('人次分類')[['計算人次', '觀看總數', '電競人次']].sum().reset_index()
            af = pd.concat([at, pd.DataFrame([{
                '人次分類': '合計(去無視/VIP)', 
                '計算人次': f_df_filtered['計算人次'].sum(), 
                '觀看總數': f_df_filtered['觀看總數'].sum(), 
                '電競人次': f_df['電競人次'].sum()
            }])]).reset_index(drop=True)
            # 修正點：subset 指定數字欄位，避免 ValueError
            st.table(af.style.format({'計算人次':'{:,.0f}', '觀看總數':'{:,.0f}', '電競人次':'{:,.0f}'}).apply(style_total, t_len=len(af), axis=1))

        st.divider()
        st.subheader("🎬 影片類別細項統計 (排除無視/VIP)")
        fs = f_df_filtered[f_df_filtered['清單節目名稱'] != ""].groupby(['標籤','清單節目名稱']).agg({'計算人次':'sum'}).reset_index()
        st.table(fs.style.format({'計算人次':'{:,.0f}'}).apply(style_total, t_len=len(fs), axis=1))

        # 稼動率表格
        st.divider()
        st.subheader("⏰ 時段稼動率分析")
        def calc_cap(df_in, site, off_dt):
            dts = df_in['交易日期'].dt.date.unique()
            res = []
            for d in dts:
                if site == "高雄店" and d in off_dt and not is_national_holiday(d): continue
                rng = pd.date_range(f"{d} 11:30", f"{d} 20:45", freq='15min') if site=="台北店" else pd.date_range(f"{d} 09:30", f"{d} 16:45", freq='15min')
                is_h = True if (site=="台北店" and get_holiday_type(d)=="假日") else False
                for s in rng:
                    cap = 40 if (site=="台北店" and s.hour==20 and s.minute==45 and is_h) else 20
                    res.append({'時段小時': s.hour, '容量': cap, '假期': get_holiday_type(d)})
            return pd.DataFrame(res)

        cp = calc_cap(f_df, sel_site, off_days)
        if not cp.empty:
            cg = cp.groupby(['時段小時','假期'])['容量'].sum().reset_index()
            ag = f_df[f_df['人次分類'] != '無視'].groupby(['時段小時','假期'])['觀看總數'].sum().reset_index()
            mg = pd.merge(cg, ag, on=['時段小時','假期'], how='left').fillna(0)
            mg['稼動率'] = (mg['觀看總數']/mg['容量']*100).map('{:.2f}%'.format)
            pv = mg.pivot(index='時段小時', columns='假期', values='稼動率').fillna("-")
            pv.index = [f"{h:02d}:00-{h+1:02d}:00" for h in pv.index]
            st.table(pv)
