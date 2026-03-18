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

st.set_page_config(page_title="i-Ride 營收數據分析系統", layout="wide")

HIGHLIGHT_COLOR = "rgba(0, 123, 255, 0.4)" 

if check_password():
    # 1. 假期定義
    def get_holiday_type(date):
        if pd.isna(date): return "未知"
        d_str = date.strftime('%Y-%m-%d')
        holidays_2025 = ['2025-01-01', '2025-01-25', '2025-01-26', '2025-01-27', '2025-01-28', '2025-01-29', '2025-01-30', '2025-01-31', '2025-02-01', '2025-02-02', '2025-02-28', '2025-03-01', '2025-03-02', '2025-04-03', '2025-04-04', '2025-04-05', '2025-04-06', '2025-05-01', '2025-05-30', '2025-05-31', '2025-06-01', '2025-09-27', '2025-09-28', '2025-09-29', '2025-10-04', '2025-10-05', '2025-10-06', '2025-10-10', '2025-10-11', '2025-10-12', '2025-10-24', '2025-10-25', '2025-10-26', '2025-12-25']
        holidays_2026 = ['2026-01-01', '2026-02-14', '2026-02-15', '2026-02-16', '2026-02-17', '2026-02-18', '2026-02-19', '2026-02-20', '2026-02-21', '2026-02-22', '2026-02-27', '2026-02-28', '2026-03-01', '2026-04-03', '2026-04-04', '2026-04-05', '2026-04-06', '2026-05-01', '2026-05-02', '2026-05-03', '2026-06-19', '2026-06-20', '2026-06-21', '2026-09-25', '2026-09-26', '2026-09-27', '2026-09-28', '2026-10-09', '2026-10-10', '2026-10-11', '2026-10-24', '2026-10-25', '2026-10-26', '2026-12-25', '2026-12-26', '2026-12-27']
        all_holidays = holidays_2025 + holidays_2026
        return "假日" if (d_str in all_holidays or date.weekday() >= 5) else "平日"

    # 2. 核心處理函數
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

            # 人次分類
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

            # 初始計算
            if pname != "" and pname != "nan":
                res_watch_val = qty
                n_films = 2 if ('+' in pname or '＋' in pname) else 1
                res_att_val = n_films * qty
            else:
                esports_k = ['LED體感','VR','4D劇院','飛行模擬器','極速賽艇','體感賽車','僵屍籠','殭屍籠']
                if any(k in spec for k in esports_k): 
                    res_att_cat = "電競館"
                    res_esports_val = qty
                if res_att_cat != "電競館":
                    res_att_val, res_watch_val = 0, 0

            # 營收分類
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

    # --- 介面呈現 ---
    uploaded_file = st.file_uploader("1. 上傳原始檔 (CSV 或 Excel)", type=['csv', 'xlsx'])

    if uploaded_file:
        df_raw = pd.read_csv(uploaded_file, dtype={'會員卡號': str, '客戶編號': str}) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, dtype={'會員卡號': str, '客戶編號': str})
        processed = process_data(df_raw)
        
        # --- [優化 1] 影片類別批次輸入表單 ---
        st.sidebar.header("🎬 影片類別定義")
        unique_films = sorted([f for f in processed['清單節目名稱'].unique() if f != "" and f != "nan"])
        
        film_tag_map = {}
        # 使用 st.sidebar.form 確保填寫過程中不重跑
        with st.sidebar.form("film_labeling_form"):
            st.write("請輸入影片對應標籤：")
            st.caption("💡 標籤填寫「無視」將自動將該片人次歸零。")
            for film in unique_films:
                film_tag_map[film] = st.text_input(f"{film}", value="未分類影片", key=f"inp_{film}")
            
            submit_labels = st.form_submit_button("💾 儲存並更新分析資料")

        # --- [優化 2] 邏輯聯動：無視影片則人次倍率歸零 ---
        processed['節目類別標籤'] = processed['清單節目名稱'].map(film_tag_map)
        
        # 如果標籤是「無視」，強行將人次數據歸零
        processed.loc[processed['節目類別標籤'] == '無視', ['計算人次', '觀看總數']] = 0
        
        # 篩選器
        st.sidebar.header("📅 數據篩選")
        all_months = sorted(processed['月份'].unique())
        sel_months = st.sidebar.multiselect("選擇月份", all_months, default=all_months)
        sel_holiday = st.sidebar.multiselect("日期類型", ["平日", "假日"], default=["平日", "假日"])
        
        f_df = processed[(processed['月份'].isin(sel_months)) & (processed['假期'].isin(sel_holiday))].copy()
        f_df_filtered = f_df[~f_df['人次分類'].isin(['無視', 'VIP'])]

        st.header(f"📊 營收統計分析")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("總計營收", f"{f_df['統計用營收'].sum():,.0f}")
        c2.metric("i-Ride 人次", f"{f_df_filtered['計算人次'].sum():,.0f}")
        c3.metric("影片觀看總數", f"{f_df_filtered['觀看總數'].sum():,.0f}")
        c4.metric("電競館人次", f"{f_df['電競人次'].sum():,.0f}")

        def apply_style(x, df_len):
            return [f'background-color: {HIGHLIGHT_COLOR}; font-weight: bold' if x.name == df_len-1 else '' for _ in x]

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
                '人次分類': '合計(不含無視、VIP)', 
                '計算人次': f_df_filtered['計算人次'].sum(), 
                '觀看總數': f_df_filtered['觀看總數'].sum(), 
                '電競人次': f_df_filtered['電競人次'].sum()
            }])]).reset_index(drop=True)
            st.table(att_final.style.format({'計算人次': '{:,.0f}', '觀看總數': '{:,.0f}', '電競人次': '{:,.0f}'}).apply(apply_style, df_len=len(att_final), axis=1))

        # 影片組合類別統計
        st.divider()
        st.subheader("🎬 影片組合與類別人次統計 (已排除無視/VIP)")
        film_stats = f_df_filtered[f_df_filtered['清單節目名稱'] != ""].groupby(['節目類別標籤', '清單節目名稱']).agg({
            '計算人次': 'sum',
            '觀看總數': 'sum'
        }).reset_index()
        
        film_cat_summary = film_stats.groupby('節目類別標籤').agg({'計算人次': 'sum', '觀看總數': 'sum'}).reset_index()
        film_cat_summary['清單節目名稱'] = "--- 類別小計 ---"
        combined_film_table = pd.concat([film_stats, film_cat_summary]).sort_values(['節目類別標籤', '清單節目名稱'], ascending=[True, False])
        
        st.dataframe(combined_film_table, use_container_width=True)

        st.divider()
        st.subheader("📄 數據明細")
        st.dataframe(f_df)
