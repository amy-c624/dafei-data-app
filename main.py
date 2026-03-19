import streamlit as st
import pandas as pd
import numpy as np

# --- 0. 密碼驗證 (維持原樣) ---
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
    # 1. 假期定義
    def get_holiday_type(date):
        if pd.isna(date): return "未知"
        d_str = date.strftime('%Y-%m-%d')
        # ... (此處保留您的假日清單) ...
        return "假日" if (date.weekday() >= 5) else "平日" # 簡化示範

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

            # --- [A] 分類邏輯 ---
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

            # --- [核心修正：142人次 Bug 預防] ---
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
                    res_att_val, res_watch_val = qty, qty # 保留原始數量

            # --- [B] 營收邏輯 ---
            if spec in ['商品兌換券', '票券核銷']: res_rev = "無視"
            elif any(x in spec for x in ['門票分潤', '線上票券']): res_rev = "平台收入"
            elif spec == '團購兌換券': res_rev = "預售票收入"
            elif spec == "券差額" or "活動服務費" in spec: res_rev = "票務收入"
            elif spec == "券類溢收-商品": res_rev = "周邊商品"
            elif (pname != "" and pname != "nan") or ("票" in spec) or ("券" in spec) or (res_att_cat not in ["無視", "周邊商品", "電競館"]): res_rev = "票務收入"
            elif res_att_cat == "電競館": res_rev = "電競館收入"
            else: res_rev = "周邊商品"

            return pd.Series([res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val, rev, pname])

        df[['營收分類', '人次分類', '計算人次', '電競人次', '觀看總數', '含稅營收', '清單節目名稱']] = df.apply(classify, axis=1)
        df['統計用營收'] = df.apply(lambda x: 0 if x['營收分類'] == '無視' else x['含稅營收'], axis=1)
        return df

    # 3. 稼動率容量函數
    def calc_capacity(df_in, site, off_dt):
        days = df_in['交易日期'].dt.date.unique()
        cap_data = []
        for d in days:
            if site == "高雄店" and d in off_dt: continue
            start_h, end_h = (11, 21) if site == "台北店" else (9, 17)
            time_slots = pd.date_range(f"{d} {start_h}:30", f"{d} {end_h}:00", freq='15min')
            is_holiday = get_holiday_type(d) == "假日"
            for ts in time_slots:
                cap = 40 if (site == "台北店" and is_holiday and ts.hour == 21 and ts.minute == 0) else 20
                cap_data.append({'時段小時': ts.hour, '假期': get_holiday_type(d), '容量分母': cap})
        return pd.DataFrame(cap_data)

    uploaded_file = st.file_uploader("1. 上傳原始檔", type=['csv', 'xlsx'])

    if uploaded_file:
        df_raw = pd.read_csv(uploaded_file, dtype=str) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, dtype=str)
        processed = process_data(df_raw)
        
        # --- 側邊欄設定 ---
        st.sidebar.header("📊 數據設定")
        sel_site = st.sidebar.selectbox("門店據點", ["台北店", "高雄店"])
        off_days = st.sidebar.date_input("高雄公休日", value=[])
        
        # --- [重點：手動無視標籤覆蓋邏輯] ---
        unique_films = sorted([f for f in processed['清單節目名稱'].unique() if f != "" and f != "nan"])
        with st.sidebar.form("film_tags"):
            st.write("🎬 影片分類標籤 (輸入「無視」將人次歸零並挪至無視類別)")
            tag_map = {f: st.text_input(f, value="未分類", key=f) for f in unique_films}
            submitted = st.form_submit_button("更新標籤統計")
        
        processed['影片類別'] = processed['清單節目名稱'].map(tag_map)
        
        # 執行「做法 B」挪動邏輯
        if submitted:
            # 找出所有被標記為「無視」的影片
            ignore_films = [film for film, tag in tag_map.items() if tag == "無視"]
            # 針對這些影片，強制改寫分類與人次
            mask = processed['清單節目名稱'].isin(ignore_films)
            processed.loc[mask, '人次分類'] = "無視"
            processed.loc[mask, '計算人次'] = processed.loc[mask, '觀看總數'] # 歸位為單次人次，由無視類別承接

        sel_months = st.sidebar.multiselect("選擇月份", sorted(processed['月份'].unique()), default=processed['月份'].unique())
        sel_holiday = st.sidebar.multiselect("日期類型", ["平日", "假日"], default=["平日", "假日"])
        
        f_df = processed[(processed['月份'].isin(sel_months)) & (processed['假期'].isin(sel_holiday))].copy()
        f_df_filtered = f_df[~f_df['人次分類'].isin(['無視', 'VIP'])]

        # --- 看板呈現 ---
        st.header(f"📈 {sel_site} 數據看板")
        c1, c2, c3 = st.columns(3)
        c1.metric("總計營收", f"{f_df['統計用營收'].sum():,.0f}")
        c2.metric("i-Ride 人次 (扣除無視/VIP)", f"{f_df_filtered['計算人次'].sum():,.0f}")
        c3.metric("電競館人次", f"{f_df['電競人次'].sum():,.0f}")
        
        st.download_button("💾 下載本次分析明細 (CSV)", f_df.to_csv(index=False).encode('utf-8-sig'), "data.csv")

        st.divider()
        t1, t2 = st.columns(2)
        with t1:
            st.subheader("💰 營收分類合計")
            rev_t = f_df.groupby('營收分類')['含稅營收'].sum().reset_index()
            st.table(rev_t.style.format({'含稅營收': '{:,.0f}'}))
        
        with t2:
            st.subheader("👥 人次分類合計")
            # 這裡顯示的「無視」類別會包含您手動標記的那 142 人(或其他手動無視影片)
            att_t = f_df.groupby('人次分類')[['計算人次', '觀看總數']].sum().reset_index()
            st.table(att_t.style.format({'計算人次': '{:,.0f}', '觀看總數': '{:,.0f}'}))

        # 稼動率
        st.divider()
        st.subheader("⏰ 時段稼動率分析")
        cap_df = calc_capacity(f_df, sel_site, off_days)
        if not cap_df.empty:
            cg = cap_df.groupby(['時段小時', '假期'])['容量分母'].sum().reset_index()
            # 稼動率分子排除手動無視後的觀看總數
            ag = f_df[f_df['人次分類'] != '無視'].groupby(['時段小時', '假期'])['觀看總數'].sum().reset_index()
            mg = pd.merge(cg, ag, on=['時段小時', '假期'], how='left').fillna(0)
            mg['稼動率'] = (mg['觀看總數'] / mg['容量分母'] * 100).map('{:.2f}%'.format)
            st.table(mg.pivot(index='時段小時', columns='假期', values='稼動率').fillna("-"))
