import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date

# --- 0. 驗證 (維持原樣) ---
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

st.set_page_config(page_title="i-Ride 營運決策系統", layout="wide")
HIGHLIGHT_COLOR = "background-color: rgba(0, 123, 255, 0.4); font-weight: bold"

if check_password():
    # 1. 假期定義 (2025-2026 國定假日範例)
    def get_holiday_type(date_val):
        if pd.isna(date_val): return "未知"
        d_str = date_val.strftime('%Y-%m-%d')
        # 您可以在此擴展假期清單
        holidays_list = ['2025-01-01', '2025-01-27', '2025-01-28', '2025-01-29', '2025-01-30', '2025-01-31', '2026-01-01']
        return "假日" if (d_str in holidays_list or date_val.weekday() >= 5) else "平日"

    # 2. 核心處理函數
    def process_data(df):
        df['交易日期'] = pd.to_datetime(df['交易日期'], errors='coerce')
        df = df.dropna(subset=['交易日期']).copy()
        df['月份'] = df['交易日期'].dt.strftime('%Y/%m月')
        df['假期'] = df['交易日期'].apply(get_holiday_type)
        df['時段小時'] = pd.to_datetime(df['場次時間'], format='%H:%M', errors='coerce').dt.hour
        df['分鐘'] = pd.to_datetime(df['場次時間'], format='%H:%M', errors='coerce').dt.minute

        def classify(row):
            pname = str(row.get('節目名稱', '')).strip()
            spec = str(row.get('品名規格', '')).strip()
            cid = str(row.get('會員卡號', row.get('客戶編號', ''))).strip().upper()
            qty = pd.to_numeric(row.get('交易數量', 0), errors='coerce') or 0
            rev = pd.to_numeric(row.get('原幣含稅金額', 0), errors='coerce') or 0
            res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val = "周邊商品", "不計人次", 0, 0, 0

            # --- [A] 人次分類判定 ---
            if cid.startswith('P') and spec == "成人票": res_att_cat = "親子卡"
            elif cid == 'Z00054' and spec == "VIP貴賓券核銷": res_att_cat = "校園票"
            elif any(x in spec for x in ['股東券', '股東票']): res_att_cat = "股東"
            elif '貴賓體驗通行證核銷' in spec: res_att_cat = "VVIP"
            elif 'VIP貴賓券核銷' in spec: res_att_cat = "VIP"
            elif any(x in spec for x in ['團購兌換券展延', '團購兌換券核銷']): res_att_cat = "團購券"
            elif '平台通路票' in spec: res_att_cat = "平台"
            elif any(x in spec for x in ['企業優惠票', '團體優惠票']): res_att_cat = "團體"
            elif any(x in spec for x in ['市民票', '愛心票', '學生票', '優惠套票', '成人票']): res_att_cat = "散客"
            if any(x in spec for x in ['免費票', '員工票', '券差額', '券類溢收-商品', '商品兌換券', '票券核銷', '活動服務費']): res_att_cat = "無視"

            # --- [B] 數值計算 ---
            if pname != "" and pname != "nan":
                res_watch_val = qty
                n_films = 2 if ('+' in pname or '＋' in pname) else 1
                res_att_val = n_films * qty
                if res_att_cat == "不計人次": res_att_cat = "無視"
            else:
                if any(k in spec for k in ['VR','體感','賽車','僵屍','LED']): 
                    res_att_cat = "電競館"
                    res_esports_val = qty
                    res_att_val = qty

            # --- [C] 營收分類 ---
            if spec in ['商品兌換券', '票券核銷']: res_rev = "無視"
            elif any(x in spec for x in ['門票分潤', '線上票券']): res_rev = "平台收入"
            elif spec == '團購兌換券': res_rev = "預售票收入"
            elif '巨人' in spec: res_rev = "巨人周邊商品"
            elif '妖怪' in spec: res_rev = "妖怪周邊商品"
            elif (pname != "" and pname != "nan") or ("票" in spec) or ("券" in spec): res_rev = "票務"
            elif res_att_cat == "電競館": res_rev = "電競館收入"
            else: res_rev = "周邊商品"

            return pd.Series([res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val, rev, pname])

        df[['營收分類', '人次分類', '計算人次', '電競人次', '觀看總數', '含稅營收', '清單節目名稱']] = df.apply(classify, axis=1)
        df['統計用營收'] = df.apply(lambda x: 0 if x['營收分類'] == '無視' else x['含稅營收'], axis=1)
        return df

    # 3. 稼動率區段
    def get_slot_info(site, holiday_type, hour, minute):
        try:
            h, m = int(hour), int(minute)
            if site == "i-Ride TAIPEI":
                if h == 11 and m >= 30: return "11:30-12:00"
                if 12 <= h < 20: return f"{h:02d}:00-{(h+1):02d}:00"
                if h == 20: return "20:00-21:00"
            else: # KAOHSIUNG
                if h == 9 and m >= 30: return "09:30-10:00"
                if 10 <= h < 16: return f"{h:02d}:00-{(h+1):02d}:00"
                if h == 16: return "16:00-17:00"
        except: pass
        return "不計入時段"

    uploaded_file = st.file_uploader("1. 上傳數據文件 (CSV/Excel)", type=['csv', 'xlsx'])

    if uploaded_file:
        df_raw = pd.read_csv(uploaded_file, dtype=str) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, dtype=str)
        processed = process_data(df_raw)
        
        # --- 側邊欄 Form ---
        with st.sidebar.form("setting_form"):
            st.header("⚙️ 營運設定")
            sel_site = st.selectbox("營運據點", ["i-Ride TAIPEI", "i-Ride KAOHSIUNG"])
            
            # --- 核心修改：日期起訖篩選 ---
            st.divider()
            st.write("📅 數據篩選區間")
            all_dates = sorted(processed['交易日期'].dt.date.unique())
            min_date, max_date = all_dates[0], all_dates[-1]
            
            # 使用 date_input 選擇起迄
            sel_range = st.date_input("選擇分析區間", value=(min_date, max_date), min_value=min_date, max_value=max_date)
            
            # 假日類型篩選 (保留)
            sel_hols = st.multiselect("假日類型篩選", ["平日", "假日"], default=["平日", "假日"])
            
            # 公休日選擇 (加入星期顯示)
            date_options = {d: f"{d} ({d.strftime('%a')})" for d in all_dates}
            off_days_keys = st.multiselect("選擇公休日 (不計分母)", options=all_dates, format_func=lambda x: date_options[x])
            
            st.divider()
            st.write("🎬 影片分類標籤")
            unique_f = sorted([f for f in processed['清單節目名稱'].unique() if f not in ["", "nan"]])
            tag_map = {f: st.text_input(f, value="未分類", key=f) for f in unique_f}
            
            submitted = st.form_submit_button("🔥 執行數據更新")

        # 執行標籤與日期篩選邏輯
        processed['影片類別'] = processed['清單節目名稱'].map(tag_map)
        
        # 確保區段有選好起迄才篩選
        if isinstance(sel_range, tuple) and len(sel_range) == 2:
            start_date, end_date = sel_range
        else:
            start_date, end_date = min_date, max_date

        if submitted:
            ign_mask = processed['影片類別'] == "無視"
            processed.loc[ign_mask, ['計算人次', '觀看總數']] = 0
            processed.loc[ign_mask, '人次分類'] = "無視"

        # 數據篩選 (加入日期篩選邏輯)
        f_df = processed[
            (processed['交易日期'].dt.date >= start_date) & 
            (processed['交易日期'].dt.date <= end_date) & 
            (processed['假期'].isin(sel_hols)) &
            (~processed['交易日期'].dt.date.isin(off_days_keys))
        ].copy()

        # --- 以下輸出報表維持原樣 ---
        st.header(f"📊 {sel_site} 營運分析報表")
        st.caption(f"分析區間：{start_date} 至 {end_date}")
        
        f_df_filtered = f_df[~f_df['人次分類'].isin(['無視', 'VIP', '不計人次'])]

        c1, c2, c3 = st.columns(3)
        c1.metric("總計營收 (去無視)", f"{f_df['統計用營收'].sum():,.0f}")
        c2.metric("i-Ride 有效人次", f"{f_df_filtered['計算人次'].sum():,.0f}")
        c3.metric("電競館人次", f"{f_df['電競人次'].sum():,.0f}")

        # 第一部分：合計表格
        st.divider()
        t1, t2 = st.columns(2)
        with t1:
            st.subheader("💰 營收分類合計")
            rev_t = f_df.groupby('營營收分類')['含稅營收'].sum().reset_index() if '營營收分類' in f_df.columns else f_df.groupby('營收分類')['含稅營收'].sum().reset_index()
            rev_f = pd.concat([rev_t, pd.DataFrame([{'營收分類':'合計(不含無視)','含稅營收':f_df['統計用營收'].sum()}])]).reset_index(drop=True)
            st.table(rev_f.style.format({'含稅營收': '{:,.0f}'}).apply(lambda x: [HIGHLIGHT_COLOR if x.name == len(rev_f)-1 else "" for _ in x], axis=1))
        
        with t2:
            st.subheader("👥 人次分類合計")
            att_data = f_df[f_df['人次分類'] != "不計人次"]
            att_t = att_data.groupby('人次分類')[['計算人次', '觀看總數']].sum().reset_index()
            att_f = pd.concat([att_t, pd.DataFrame([{
                '人次分類': '合計(不含無視)', 
                '計算人次': f_df_filtered['計算人次'].sum(), 
                '觀看總數': f_df_filtered['觀看總數'].sum()
            }])]).reset_index(drop=True)
            st.table(att_f.style.format({'計算人次': '{:,.0f}', '觀看總數': '{:,.0f}'}).apply(lambda x: [HIGHLIGHT_COLOR if x.name == len(att_f)-1 else "" for _ in x], axis=1))

        # 第二部分：影片細分
        st.divider()
        st.subheader("🎬 影片觀看分析")
        film_stats = f_df[f_df['清單節目名稱'] != ""].groupby(['影片類別', '清單節目名稱'])['觀看總數'].sum().reset_index()
        final_list = []
        for cat, group in film_stats.groupby('影片類別'):
            final_list.append(group)
            final_list.append(pd.DataFrame([{'影片類別': cat, '清單節目名稱': f'【{cat} 合計】', '觀看總數': group['觀看總數'].sum()}]))
        
        if final_list:
            full_df = pd.concat(final_list).reset_index(drop=True)
            st.table(full_df.style.format({'觀看總數': '{:,.0f}'}).apply(lambda x: [HIGHLIGHT_COLOR if "合計" in str(x['清單節目名稱']) else "" for _ in x], axis=1))

        # 第三部分：稼動率
        st.divider()
        st.subheader("⏰ 時段稼動率分析")
        f_df['區段'] = f_df.apply(lambda x: get_slot_info(sel_site, x['假期'], x['時段小時'], x['分鐘']), axis=1)
        active_days = f_df.groupby(['交易日期', '假期']).size().reset_index()
        day_counts = active_days['假期'].value_counts().to_dict()
        
        if sel_site == "i-Ride TAIPEI":
            slots_cfg = [("11:30-12:00", 2)] + [(f"{h:02d}:00-{(h+1):02d}:00", 4) for h in range(12, 20)] + [("20:00-21:00", 0)]
        else: # KAOHSIUNG
            slots_cfg = [("09:30-10:00", 2)] + [(f"{h:02d}:00-{(h+1):02d}:00", 4) for h in range(10, 16)] + [("16:00-17:00", 4)]

        occ_list = []
        for s_name, s_qty in slots_cfg:
            for h_type in sel_hols:
                d_num = day_counts.get(h_type, 0)
                if d_num == 0: continue
                actual_qty = s_qty
                if sel_site == "i-Ride TAIPEI" and s_name == "20:00-21:00":
                    actual_qty = 5 if h_type == "假日" else 4
                denom = 20 * actual_qty * d_num
                num = f_df[(f_df['區段'] == s_name) & (f_df['假期'] == h_type) & (~f_df['人次分類'].isin(['無視','VIP','不計人次']))]['觀看總數'].sum()
                rate = (num / denom * 100) if denom > 0 else 0
                occ_list.append({'時段': s_name, '類型': h_type, '稼動率': f"{rate:.2f}%"})

        if occ_list:
            st.table(pd.DataFrame(occ_list).pivot(index='時段', columns='類型', values='稼動率').fillna("-"))
