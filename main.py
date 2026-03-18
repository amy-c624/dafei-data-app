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
    else:
        return True

st.set_page_config(page_title="i-Ride 營運據點分析系統", layout="wide")

HIGHLIGHT_COLOR = "rgba(0, 123, 255, 0.4)" 

if check_password():
    # 1. 假期定義 (2025-2026 最新版)
    def get_holiday_type(date):
        if pd.isna(date): return "未知"
        d_str = date.strftime('%Y-%m-%d')
        holidays_2025 = ['2025-01-01', '2025-01-25', '2025-01-26', '2025-01-27', '2025-01-28', '2025-01-29', '2025-01-30', '2025-01-31', '2025-02-01', '2025-02-02', '2025-02-28', '2025-03-01', '2025-03-02', '2025-04-03', '2025-04-04', '2025-04-05', '2025-04-06', '2025-05-01', '2025-05-30', '2025-05-31', '2025-06-01', '2025-09-27', '2025-09-28', '2025-09-29', '2025-10-04', '2025-10-05', '2025-10-06', '2025-10-10', '2025-10-11', '2025-10-12', '2025-10-24', '2025-10-25', '2025-10-26', '2025-12-25']
        holidays_2026 = ['2026-01-01', '2026-02-14', '2026-02-15', '2026-02-16', '2026-02-17', '2026-02-18', '2026-02-19', '2026-02-20', '2026-02-21', '2026-02-22', '2026-02-27', '2026-02-28', '2026-03-01', '2026-04-03', '2026-04-04', '2026-04-05', '2026-04-06', '2026-05-01', '2026-05-02', '2026-05-03', '2026-06-19', '2026-06-20', '2026-06-21', '2026-09-25', '2026-09-26', '2026-09-27', '2026-09-28', '2026-10-09', '2026-10-10', '2026-10-11', '2026-10-24', '2026-10-25', '2026-10-26', '2026-12-25', '2026-12-26', '2026-12-27']
        all_holidays = holidays_2025 + holidays_2026
        return "假日" if (d_str in all_holidays or date.weekday() >= 5) else "平日"

    # 2. 處理函數
    def process_data(df):
        df['交易日期'] = pd.to_datetime(df['交易日期'], errors='coerce')
        df = df.dropna(subset=['交易日期']).copy()
        df['月份'] = df['交易日期'].dt.strftime('%Y/%m月')
        df['假期'] = df['交易日期'].apply(get_holiday_type)

        def classify(row):
            pname = str(row.get('節目名稱', '')).strip()
            spec = str(row.get('品名規格', '')).strip()
            cid = str(row.get('會員卡號', row.get('客戶編號', ''))).strip().upper()
            qty = pd.to_numeric(row.get('交易數量', 0), errors='coerce') or 0
            rev = pd.to_numeric(row.get('原幣含稅金額', 0), errors='coerce') or 0
            
            res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val = "周邊商品", "無視", 0, 0, 0

            # 人次判定邏輯
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

            # 計算人次與觀看總數
            if pname != "" and pname != "nan":
                res_watch_val = qty
                n_films = 2 if ('+' in pname or '＋' in pname) else 1
                res_att_val = n_films * qty
            else:
                if any(k in spec for k in ['LED體感','VR','4D劇院','飛行模擬器','極速賽艇','體感賽車','僵屍籠']): 
                    res_att_cat = "電競館"
                    res_esports_val = qty
                if res_att_cat != "電競館": res_att_val, res_watch_val = 0, 0

            # 營收判定
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

    # --- 3. 介面呈現 ---
    uploaded_file = st.file_uploader("1. 上傳原始檔 (CSV 或 Excel)", type=['csv', 'xlsx'])

    if uploaded_file:
        df_raw = pd.read_csv(uploaded_file, dtype={'會員卡號': str, '客戶編號': str}) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, dtype={'會員卡號': str, '客戶編號': str})
        processed = process_data(df_raw)
        
        # 側邊欄：據點與稼動率參數
        st.sidebar.header("🏢 據點與稼動率設定")
        site = st.sidebar.selectbox("選擇營運據點", ["台北店", "高雄店"])
        
        site_params = {"台北店": (20, 33), "高雄店": (20, 24)}
        seats = st.sidebar.number_input("每場座位數", value=site_params[site][0])
        sessions_per_day = st.sidebar.number_input("每日總場次數", value=site_params[site][1])

        st.sidebar.divider()
        st.sidebar.header("🎬 影片類別定義")
        unique_films = sorted([f for f in processed['清單節目名稱'].unique() if f != "" and f != "nan"])
        
        with st.sidebar.form("film_labeling_form"):
            film_tag_map = {}
            for film in unique_films:
                film_tag_map[film] = st.text_input(f"{film}", value="未分類影片", key=f"inp_{film}")
            submit_labels = st.form_submit_button("💾 儲存並更新分析資料")

        processed['節目類別標籤'] = processed['清單節目名稱'].map(film_tag_map)
        processed.loc[processed['節目類別標籤'] == '無視', ['計算人次', '觀看總數']] = 0
        
        # 篩選器
        st.sidebar.header("📅 數據篩選")
        all_months = sorted(processed['月份'].unique())
        sel_months = st.sidebar.multiselect("選擇月份", all_months, default=all_months)
        sel_holiday = st.sidebar.multiselect("日期類型", ["平日", "假日"], default=["平日", "假日"])
        
        # 套用篩選
        f_df = processed[(processed['月份'].isin(sel_months)) & (processed['假期'].isin(sel_holiday))].copy()
        # 排除無視與 VIP 的計算 DataFrame (用於核心指標)
        f_df_filtered = f_df[~f_df['人次分類'].isin(['無視', 'VIP'])]

        # --- [關鍵更新] 稼動率動態計算 (隨篩選器變動) ---
        # 只抓篩選後結果中「實際有交易日期」的天數
        if not f_df.empty:
            active_days = f_df['交易日期'].dt.date.nunique()
            total_capacity = active_days * sessions_per_day * seats
            actual_watches = f_df_filtered['觀看總數'].sum()
            utilization_rate = (actual_watches / total_capacity) * 100 if total_capacity > 0 else 0
        else:
            active_days, actual_watches, utilization_rate = 0, 0, 0

        st.header(f"📊 {site} 營收與稼動率分析")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("總計營收", f"{f_df['統計用營收'].sum():,.0f}")
        c2.metric("i-Ride 人次", f"{f_df_filtered['計算人次'].sum():,.0f}")
        c3.metric("影片觀看總數", f"{actual_watches:,.0f}")
        c4.metric("電競館人次", f"{f_df['電競人次'].sum():,.0f}")
        c5.metric("核心稼動率", f"{utilization_rate:.2f}%", help=f"依據篩選條件計算。計算分母天數：{active_days}天")

        def apply_style(x, df_len):
            # 偵測是否為合計列：最後一行 OR 清單節目名稱內含 "小計"
            is_total = x.name == df_len-1 or (hasattr(x, '清單節目名稱') and "小計" in str(x.清單節目名稱))
            return [f'background-color: {HIGHLIGHT_COLOR}; font-weight: bold' if is_total else '' for _ in x]

        t1, t2 = st.columns(2)
        with t1:
            st.subheader("💰 營收分類合計")
            rev_table = f_df.groupby('營收分類')['含稅營收'].sum().reset_index()
            rev_final = pd.concat([rev_table, pd.DataFrame([{'營收分類': '合計(不含無視)', '含稅營收': f_df['統計用營收'].sum()}])]).reset_index(drop=True)
            st.table(rev_final.style.format({'含稅營收': '{:,.0f}'}).apply(apply_style, df_len=len(rev_final), axis=1))
        
        with t2:
            st.subheader("👥 人次分類合計")
            att_table = f_df.groupby('人次分類')[['計算人次', '觀看總數', '電競人次']].sum().reset_index()
            att_final = pd.concat([att_table, pd.DataFrame([{
                '人次分類': '合計(不含無視、VIP)', '計算人次': f_df_filtered['計算人次'].sum(), 
                '觀看總數': f_df_filtered['觀看總數'].sum(), '電競人次': f_df['電競人次'].sum()
            }])]).reset_index(drop=True)
            st.table(att_final.style.format({'計算人次': '{:,.0f}', '觀看總數': '{:,.0f}', '電競人次': '{:,.0f}'}).apply(apply_style, df_len=len(att_final), axis=1))

        # 影片類別統計表 (含醒目顏色)
        st.divider()
        st.subheader("🎬 影片組合與類別人次統計 (已排除無視/VIP)")
        film_stats = f_df_filtered[f_df_filtered['清單節目名稱'] != ""].groupby(['節目類別標籤', '清單節目名稱']).agg({'計算人次': 'sum', '觀看總數': 'sum'}).reset_index()
        film_cat_summary = film_stats.groupby('節目類別標籤').agg({'計算人次': 'sum', '觀看總數': 'sum'}).reset_index()
        film_cat_summary['清單節目名稱'] = "--- 類別小計 ---"
        combined_film_table = pd.concat([film_stats, film_cat_summary]).sort_values(['節目類別標籤', '清單節目名稱'], ascending=[True, False]).reset_index(drop=True)
        
        st.table(combined_film_table.style.format({'計算人次': '{:,.0f}', '觀看總數': '{:,.0f}'}).apply(apply_style, df_len=len(combined_film_table), axis=1))

        st.divider()
        st.subheader("📄 數據明細")
        st.dataframe(f_df)
