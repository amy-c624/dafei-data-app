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

    # 2. 恢復最準確的人次與營收邏輯
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

            # 恢復：人次分類邏輯 (關鍵在於 spec 判定)
            if cid.startswith('P') and spec == "成人票": res_att_cat = "親子卡"
            elif cid == 'Z00054' and spec == "VIP貴賓券核銷": res_att_cat = "校園優惠票"
            elif any(x in spec for x in ['股東券', '股東票']): res_att_cat = "股東"
            elif '貴賓體驗通行證核銷' in spec: res_att_cat = "VVIP"
            elif 'VIP貴賓券核銷' in spec: res_att_cat = "VIP"
            elif any(x in spec for x in ['團購兌換券展延', '團購兌換券核銷']): res_att_cat = "團購券"
            elif '平台通路票' in spec: res_att_cat = "平台"
            elif any(x in spec for x in ['企業優惠票', '團體優惠票']): res_att_cat = "團體"
            elif any(x in spec for x in ['市民票', '愛心票', '學生票', '優惠套票', '成人票']): res_att_cat = "散客"
            
            # 過濾掉不計入人次的項目
            if any(x in spec for x in ['免費票', '員工票', '券差額', '券類溢收-商品', '商品兌換券', '票券核銷']): res_att_cat = "無視"

            # 計算觀看總數與計算人次
            if pname != "" and pname != "nan":
                res_watch_val = qty
                n_films = 2 if ('+' in pname or '＋' in pname) else 1
                res_att_val = n_films * qty
            else:
                # 電競館判定
                esports_keywords = ['LED體感','VR','4D劇院','飛行模擬器','極速賽艇','體感賽車','僵屍籠','殭屍籠']
                if any(k in spec for k in esports_keywords): 
                    res_att_cat = "電競館"
                    res_esports_val = qty
                if res_att_cat != "電競館": res_att_val, res_watch_val = 0, 0

            # 營收分類邏輯
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
        df_raw = pd.read_csv(uploaded_file, dtype=str) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, dtype=str)
        processed = process_data(df_raw)
        
        # 側邊欄 A：營運參數
        st.sidebar.header("🏢 營運參數設定")
        with st.sidebar.form("site_config_form"):
            sel_site = st.selectbox("選擇據點", ["台北店", "高雄店"])
            off_days_list = st.date_input("高雄公休日選擇 (僅高雄有效)", value=[])
            st.form_submit_button("🔘 更新營運設定")

        # 側邊欄 B：影片標籤 (這部分不影響人次分類)
        st.sidebar.header("🎬 影片類別定義")
        unique_films = sorted([f for f in processed['清單節目名稱'].unique() if f != "" and f != "nan"])
        with st.sidebar.form("film_labeling_form"):
            film_tag_map = {f: st.text_input(f, value="未分類", key=f"k_{f}") for f in unique_films}
            st.form_submit_button("🔘 更新影片標籤")

        processed['節目類別標籤'] = processed['清單節目名稱'].map(film_tag_map)
        processed.loc[processed['節目類別標籤'] == '無視', ['計算人次', '觀看總數']] = 0
        
        # 篩選
        sel_months = st.sidebar.multiselect("選擇月份", sorted(processed['月份'].unique()), default=processed['月份'].unique())
        sel_holiday = st.sidebar.multiselect("日期類型", ["平日", "假日"], default=["平日", "假日"])
        
        f_df = processed[(processed['月份'].isin(sel_months)) & (processed['假期'].isin(sel_holiday))].copy()
        
        # 恢復：稼動率分子 (含 VIP 但排除無視)
        f_df_util = f_df[f_df['人次分類'] != '無視']
        # 恢復：人次統計表分子 (排除無視、排除 VIP，確保 34516 這個數字正確)
        f_df_filtered = f_df[~f_df['人次分類'].isin(['無視', 'VIP'])]

        # 分母 Capacity 邏輯
        def calc_capacity(df_scope, site, off_dates):
            unique_dates = df_scope['交易日期'].dt.date.unique()
            hourly_cap_detail = []
            for d in unique_dates:
                if site == "高雄店" and d in off_dates and not is_national_holiday(d): continue
                if site == "台北店":
                    slots = pd.date_range(start=f"{d} 11:30", end=f"{d} 20:45", freq='15min')
                    is_special_night = True if get_holiday_type(d) == "假日" else False
                else:
                    slots = pd.date_range(start=f"{d} 09:30", end=f"{d} 16:45", freq='15min')
                    is_special_night = False
                for s in slots:
                    h = s.hour
                    cap = 20
                    if site == "台北店" and h == 20 and s.minute == 45 and is_special_night: cap = 40
                    hourly_cap_detail.append({'時段小時': h, '容量': cap, '假期': get_holiday_type(d)})
            return pd.DataFrame(hourly_cap_detail)

        cap_df = calc_capacity(f_df, sel_site, off_days_list)

        # 指標卡
        st.header(f"📊 {sel_site} 營運分析報告")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("總計營收", f"{f_df['統計用營收'].sum():,.0f}")
        c2.metric("i-Ride 人次 (去VIP)", f"{f_df_filtered['計算人次'].sum():,.0f}")
        c3.metric("總觀看人次 (含VIP)", f"{f_df_util['觀看總數'].sum():,.0f}")
        total_cap_sum = cap_df['容量'].sum() if not cap_df.empty else 0
        util_val = (f_df_util['觀看總數'].sum() / total_cap_sum * 100) if total_cap_sum > 0 else 0
        c4.metric("平均稼動率", f"{util_val:.2f}%")

        def apply_style(x, df_len):
            is_total = x.name == df_len-1 or any("小計" in str(v) or "合計" in str(v) for v in x.values)
            return [f'background-color: {HIGHLIGHT_COLOR}; font-weight: bold' if is_total else '' for _ in x]

        # 營收與人次表
        st.divider()
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

        # 影片統計表
        st.divider()
        st.subheader("🎬 影片組合與類別統計 (排除無視/VIP)")
        film_stats = f_df_filtered[f_df_filtered['清單節目名稱'] != ""].groupby(['節目類別標籤', '清單節目名稱']).agg({'計算人次': 'sum', '觀看總數': 'sum'}).reset_index()
        film_cat_summary = film_stats.groupby('節目類別標籤').agg({'計算人次': 'sum', '觀看總數': 'sum'}).reset_index()
        film_cat_summary['清單節目名稱'] = "--- 類別小計 ---"
        combined_film_table = pd.concat([film_stats, film_cat_summary]).sort_values(['節目類別標籤', '清單節目名稱'], ascending=[True, False]).reset_index(drop=True)
        st.table(combined_film_table.style.format({'計算人次': '{:,.0f}', '觀看總數': '{:,.0f}'}).apply(apply_style, df_len=len(combined_film_table), axis=1))

        # 稼動率時段表
        st.divider()
        st.subheader("⏰ 時段別稼動率分析")
        if not cap_df.empty:
            cap_grouped = cap_df.groupby(['時段小時', '假期'])['容量'].sum().reset_index()
            act_grouped = f_df_util.groupby(['時段小時', '假期'])['觀看總數'].sum().reset_index()
            util_table = pd.merge(cap_grouped, act_grouped, on=['時段小時', '假期'], how='left').fillna(0)
            util_table['稼動率'] = (util_table['觀看總數'] / util_table['容量'] * 100).map('{:.2f}%'.format)
            util_pivot = util_table.pivot(index='時段小時', columns='假期', values='稼動率').fillna("-")
            util_pivot.index = [f"{h:02d}:00-{h+1:02d}:00" for h in util_pivot.index]
            util_pivot.index.name = "營業時間區段"
            st.table(util_pivot)
