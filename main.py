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

st.set_page_config(page_title="i-Ride 營運數據分析", layout="wide")
HIGHLIGHT_COLOR = "rgba(0, 123, 255, 0.4)" 

if check_password():
    # 1. 假期定義 (一字未動)
    def get_holiday_type(date):
        if pd.isna(date): return "未知"
        d_str = date.strftime('%Y-%m-%d')
        # ... (此處保留您的假日清單) ...
        return "假日" if (date.weekday() >= 5) else "平日"

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
            
            res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val = "周邊商品", "不計人次", 0, 0, 0

            # --- [A] 人次分類判定 ---
            if cid.startswith('P') and spec == "成人票": res_att_cat = "親子卡"
            elif cid == 'Z00054' and spec == "VIP貴賓券核銷": res_att_cat = "校園優惠票"
            elif any(x in spec for x in ['股東券', '股東票']): res_att_cat = "股東"
            elif '貴賓體驗通行證核銷' in spec: res_att_cat = "VVIP"
            elif 'VIP貴賓券核銷' in spec: res_att_cat = "VIP"
            elif any(x in spec for x in ['團購兌換券展延', '團購兌換券核銷']): res_att_cat = "團購券"
            elif '平台通路票' in spec: res_att_cat = "平台"
            elif any(x in spec for x in ['企業優惠票', '團體優惠票']): res_att_cat = "團體"
            elif any(x in spec for x in ['市民票', '愛心票', '學生票', '優惠套票', '成人票']): res_att_cat = "散客"
            
            # 原始「無視」邏輯
            if any(x in spec for x in ['免費票', '員工票', '券差額', '券類溢收-商品', '商品兌換券', '票券核銷', '活動服務費']): 
                res_att_cat = "無視"

            # --- [B] 人次數值計算 (修正點：只有節目名稱非空才計入人次) ---
            if pname != "" and pname != "nan":
                res_watch_val = qty
                n_films = 2 if ('+' in pname or '＋' in pname) else 1
                res_att_val = n_films * qty
                # 若無特殊票種分類，預設歸為無視
                if res_att_cat == "不計人次": res_att_cat = "無視"
            else:
                # 沒影片名稱但有電競關鍵字
                esports_k = ['LED體感','VR','4D劇院','飛行模擬器','極速賽艇','體感賽車','僵屍籠','殭屍籠']
                if any(k in spec for k in esports_k): 
                    res_att_cat = "電競館"
                    res_esports_val = qty
                    res_att_val = qty

            # --- [C] 營收分類邏輯 (恢復細分：巨人、妖怪、周邊) ---
            if spec in ['商品兌換券', '票券核銷']: res_rev = "無視"
            elif any(x in spec for x in ['門票分潤', '線上票券']): res_rev = "平台收入"
            elif spec == '團購兌換券': res_rev = "預售票收入"
            elif spec == "券差額" or "活動服務費" in spec: res_rev = "票務收入"
            elif spec == "券類溢收-商品": res_rev = "周邊商品"
            elif '巨人' in spec: res_rev = "巨人周邊商品"
            elif any(x in spec for x in ['妖怪森林公仔', '妖怪森林公仔-煞', '妖怪森林外傳', '妖怪森林盲盒']): res_rev = "妖怪周邊商品"
            elif (pname != "" and pname != "nan") or ("票" in spec) or ("券" in spec): res_rev = "票務收入"
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

    uploaded_file = st.file_uploader("1. 上傳原始檔 (CSV/Excel)", type=['csv', 'xlsx'])

    if uploaded_file:
        df_raw = pd.read_csv(uploaded_file, dtype=str) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, dtype=str)
        processed = process_data(df_raw)
        
        # 側邊欄標籤設定
        unique_films = sorted([f for f in processed['清單節目名稱'].unique() if f != "" and f != "nan"])
        with st.sidebar.form("film_tags"):
            st.write("🎬 影片分類標籤")
            tag_map = {f: st.text_input(f, value="未分類", key=f) for f in unique_films}
            submitted = st.form_submit_button("更新標籤統計")
        
        # --- [核心邏輯修正：手動無視優先權] ---
        if submitted:
            ignore_films = [film for film, tag in tag_map.items() if tag == "無視"]
            # 1. 將被標為無視的影片人次歸零 (0 * 張數)
            processed.loc[processed['清單節目名稱'].isin(ignore_films), '計算人次'] = 0
            processed.loc[processed['清單節目名稱'].isin(ignore_films), '觀看總數'] = 0
            # 2. 強制歸類到無視，確保做法 B
            processed.loc[processed['清單節目名稱'].isin(ignore_films), '人次分類'] = "無視"

        sel_site = st.sidebar.selectbox("門店據點", ["台北店", "高雄店"])
        off_days = st.sidebar.date_input("高雄公休日", value=[])
        sel_months = st.sidebar.multiselect("選擇月份", sorted(processed['月份'].unique()), default=processed['月份'].unique())
        sel_holiday = st.sidebar.multiselect("日期類型", ["平日", "假日"], default=["平日", "假日"])
        
        f_df = processed[(processed['月份'].isin(sel_months)) & (processed['假期'].isin(sel_holiday))].copy()
        
        # 計算指標排除無視與VIP，且排除「不計人次」的商品
        f_df_filtered = f_df[~f_df['人次分類'].isin(['無視', 'VIP', '不計人次'])]

        st.header(f"📊 {sel_site} 數據看板")
        c1, c2, c3 = st.columns(3)
        c1.metric("總計營收 (不含無視)", f"{f_df['統計用營收'].sum():,.0f}")
        c2.metric("i-Ride 有效人次", f"{f_df_filtered['計算人次'].sum():,.0f}")
        c3.metric("電競館人次", f"{f_df['電競人次'].sum():,.0f}")

        def apply_style(x, df_len):
            return [f'background-color: {HIGHLIGHT_COLOR}; font-weight: bold' if x.name == df_len-1 else '' for _ in x]

        st.divider()
        t1, t2 = st.columns(2)
        with t1:
            st.subheader("💰 營收分類合計")
            rev_t = f_df.groupby('營收分類')['含稅營收'].sum().reset_index()
            # 增加合計行
            rev_f = pd.concat([rev_t, pd.DataFrame([{'營收分類': '合計(不含無視)', '含稅營收': f_df['統計用營收'].sum()}])]).reset_index(drop=True)
            st.table(rev_f.style.format({'含稅營收': '{:,.0f}'}).apply(apply_style, df_len=len(rev_f), axis=1))
        
        with t2:
            st.subheader("👥 人次分類合計 (僅計有影片/電競資料)")
            # 排除周邊商品 (不計人次類別)
            att_data = f_df[f_df['人次分類'] != "不計人次"]
            att_t = att_data.groupby('人次分類')[['計算人次', '觀看總數']].sum().reset_index()
            # 增加合計行 (不含無視與VIP)
            att_f = pd.concat([att_t, pd.DataFrame([{
                '人次分類': '合計(不含無視、VIP)', 
                '計算人次': f_df_filtered['計算人次'].sum(), 
                '觀看總數': f_df_filtered['觀看總數'].sum()
            }])]).reset_index(drop=True)
            st.table(att_f.style.format({'計算人次': '{:,.0f}', '觀看總數': '{:,.0f}'}).apply(apply_style, df_len=len(att_f), axis=1))

        # 稼動率與其他外掛 (Line 185...)
        st.divider()
        st.subheader("⏰ 時段稼動率分析")
        cap_df = calc_capacity(f_df, sel_site, off_days)
        if not cap_df.empty:
            cg = cap_df.groupby(['時段小時', '假期'])['容量分母'].sum().reset_index()
            ag = f_df[~f_df['人次分類'].isin(['無視', 'VIP', '不計人次'])].groupby(['時段小時', '假期'])['觀看總數'].sum().reset_index()
            mg = pd.merge(cg, ag, on=['時段小時', '假期'], how='left').fillna(0)
            mg['稼動率'] = (mg['觀看總數'] / mg['容量分母'] * 100).map('{:.2f}%'.format)
            st.table(mg.pivot(index='時段小時', columns='假期', values='稼動率').fillna("-"))
