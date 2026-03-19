import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date

# --- 0. 授權驗證 ---
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

st.set_page_config(page_title="i-Ride 營運戰略分析系統", layout="wide")
HIGHLIGHT_COLOR = "background-color: rgba(0, 123, 255, 0.4); font-weight: bold"

if check_password():
    # --- 1. 假期與時段定義 ---
    def get_holiday_type(date_val):
        if pd.isna(date_val): return "未知"
        holidays = ['2025-01-01', '2025-01-27', '2025-01-28', '2025-01-29', '2025-01-30', '2025-01-31', '2026-01-01']
        return "假日" if (date_val.strftime('%Y-%m-%d') in holidays or date_val.weekday() >= 5) else "平日"

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

    # --- 2. 核心處理引擎 (雙關鍵字 + 檔期) ---
    def process_full_data(dfs, campaign_list):
        df = pd.concat(dfs, ignore_index=True)
        df['交易日期'] = pd.to_datetime(df['交易日期'], errors='coerce')
        df = df.dropna(subset=['交易日期']).copy()
        df['月份'] = df['交易日期'].dt.strftime('%Y/%m月')
        df['假期'] = df['交易日期'].apply(get_holiday_type)
        df['時段小時'] = pd.to_datetime(df['場次時間'], format='%H:%M', errors='coerce').dt.hour
        df['分鐘'] = pd.to_datetime(df['場次時間'], format='%H:%M', errors='coerce').dt.minute

        def classify_row(row):
            pname = str(row.get('節目名稱', '')).strip()
            spec = str(row.get('品名規格', '')).strip()
            cid = str(row.get('會員卡號', row.get('客戶編號', ''))).strip().upper()
            qty = pd.to_numeric(row.get('交易數量', 0), errors='coerce') or 0
            rev = pd.to_numeric(row.get('原幣含稅金額', 0), errors='coerce') or 0
            tx_date = row['交易日期'].date()
            
            # [A] 檔期判定
            att_camp, rev_camp = "一般", "一般"
            for camp in campaign_list:
                if camp['start'] <= tx_date <= camp['end']:
                    if camp['att_key'] and camp['att_key'] in pname: att_camp = camp['name']
                    if camp['rev_key'] and camp['rev_key'] in spec: rev_camp = camp['name']

            # [B] 人次分類邏輯
            res_att_cat = "不計人次"
            if cid.startswith('P') and spec == "成人票": res_att_cat = "親子卡"
            elif cid == 'Z00054' and spec == "VIP貴賓券核銷": res_att_cat = "校園票"
            elif any(x in spec for x in ['股東券', '股東票']): res_att_cat = "股東"
            elif any(x in spec for x in ['市民票', '愛心票', '學生票', '成人票']): res_att_cat = "散客"
            if any(x in spec for x in ['免費票', '員工票', '商品兌換券', '票券核銷']): res_att_cat = "無視"

            # [C] 數值計算
            res_att_val, res_watch_val, res_esports_val = 0, 0, 0
            if pname != "" and pname != "nan":
                res_watch_val = qty
                n_films = 2 if ('+' in pname or '＋' in pname) else 1
                res_att_val = n_films * qty
                if res_att_cat == "不計人次": res_att_cat = "無視"
            else:
                if any(k in spec for k in ['VR','體感','賽車','僵屍','LED']):
                    res_att_cat, res_esports_val, res_att_val = "電競館", qty, qty

            # [D] 營收細分 (連動雙關鍵字)
            res_rev = "一般周邊"
            if spec in ['商品兌換券', '票券核銷']: res_rev = "無視"
            elif any(x in spec for x in ['門票分潤', '線上票券']): res_rev = "平台收入"
            elif (pname != "" and pname != "nan") or "票" in spec or "券" in spec:
                res_rev = f"{att_camp}票務" if att_camp != "一般" else "一般票務"
            else:
                res_rev = f"{rev_camp}周邊" if rev_camp != "一般" else "一般周邊"
            
            if res_att_cat == "電競館": res_rev = "電競館收入"

            return pd.Series([att_camp, rev_camp, res_rev, res_att_cat, res_att_val, res_watch_val, res_esports_val, rev, pname])

        cols = ['人次檔期', '營收檔期', '營收分類', '人次分類', '計算人次', '觀看總數', '電競人次', '含稅營收', '清單節目名稱']
        df[cols] = df.apply(classify_row, axis=1)
        df['統計用營收'] = df.apply(lambda x: 0 if x['營收分類'] == '無視' else x['含稅營收'], axis=1)
        return df

    # --- 3. 側邊欄配置 ---
    with st.sidebar:
        st.header("⚙️ 營運戰略設定")
        files = st.file_uploader("批次上傳報表 (可多選)", type=['csv', 'xlsx'], accept_multiple_files=True)
        sel_site = st.selectbox("據點", ["i-Ride TAIPEI", "i-Ride KAOHSIUNG"])
        
        # 公休日 (含星期顯示)
        if files:
            all_df_raw = pd.concat([pd.read_csv(f, dtype=str) if f.name.endswith('.csv') else pd.read_excel(f, dtype=str) for f in files])
            all_dates = sorted(pd.to_datetime(all_df_raw['交易日期'], errors='coerce').dropna().dt.date.unique())
            date_fmt = {d: f"{d} ({d.strftime('%a')})" for d in all_dates}
            off_days = st.multiselect("公休日 (不計分母)", options=all_dates, format_func=lambda x: date_fmt[x])
        
        # 檔期配置 (動態欄位)
        st.divider()
        num_camps = st.number_input("定義檔期數量", 1, 3, 1)
        campaigns = []
        for i in range(int(num_camps)):
            with st.expander(f"主題 {i+1} 設定", expanded=True):
                c_name = st.text_input("名稱", f"主題{i+1}", key=f"n{i}")
                c_dates = st.date_input("區間", [date(2026,1,1), date(2026,3,18)], key=f"d{i}")
                c_att_k = st.text_input("人次關鍵字 (節目名)", c_name, key=f"ak{i}")
                c_rev_k = st.text_input("營收關鍵字 (品名規格)", c_name, key=f"rk{i}")
                if len(c_dates) == 2:
                    campaigns.append({'name': c_name, 'start': c_dates[0], 'end': c_dates[1], 'att_key': c_att_k, 'rev_key': c_rev_k})

        # 影片無視標籤
        st.divider()
        st.write("🎬 影片無視設定")
        if files:
            unique_films = sorted([str(f) for f in all_df_raw['節目名稱'].unique() if str(f) not in ["", "nan"]])
            tag_map = {f: st.selectbox(f, ["計入", "無視"], key=f"tag_{f}") for f in unique_films}

    # --- 4. 數據渲染與分頁 ---
    if files:
        processed = process_full_data([pd.read_csv(f, dtype=str) if f.name.endswith('.csv') else pd.read_excel(f, dtype=str) for f in files], campaigns)
        
        # 標籤無視邏輯
        processed['影片標籤'] = processed['清單節目名稱'].map(tag_map)
        processed.loc[processed['影片標籤'] == "無視", ['計算人次', '觀看總數']] = 0
        processed.loc[processed['影片標籤'] == "無視", '人次分類'] = "無視"

        tab1, tab2, tab3 = st.tabs(["🚀 By 檔期分析 (YoY)", "📅 By 月份分析", "📋 營運細項與稼動率"])

        # --- Tab 1: 檔期戰略 ---
        with tab1:
            for camp in campaigns:
                st.header(f"📌 檔期：{camp['name']}")
                ly_s, ly_e = camp['start'].replace(year=camp['start'].year-1), camp['end'].replace(year=camp['end'].year-1)
                st.info(f"📅 **比較區間對位**：本期 `{camp['start']} ~ {camp['end']}` | 去年同期 `{ly_s} ~ {ly_e}`")
                
                curr_d = processed[(processed['交易日期'].dt.date >= camp['start']) & (processed['交易日期'].dt.date <= camp['end']) & (~processed['交易日期'].dt.date.isin(off_days))]
                prev_d = processed[(processed['交易日期'].dt.date >= ly_s) & (processed['交易日期'].dt.date <= ly_e)]
                
                v_curr = curr_d[~curr_d['人次分類'].isin(['無視','VIP','不計人次'])]
                v_prev = prev_d[~prev_d['人次分類'].isin(['無視','VIP','不計人次'])]

                c1, c2, c3 = st.columns(3)
                c1.metric("有效人次 (本期)", f"{v_curr['計算人次'].sum():,.0f}", delta=f"{v_curr['計算人次'].sum()-v_prev['計算人次'].sum():,.0f} YoY")
                
                yr_tot = processed[(processed['交易日期'].dt.year == camp['start'].year) & (~processed['人次分類'].isin(['無視','VIP','不計人次']))]['計算人次'].sum()
                c2.metric("檔期人次佔比 (全年度)", f"{(v_curr['計算人次'].sum()/yr_tot*100):.2f}%" if yr_tot > 0 else "0%")
                c3.metric("票務營收 (不含無視)", f"{curr_d[curr_d['營收分類'].str.contains('票務')]['統計用營收'].sum():,.0f}")

                # YoY 表格
                comp_df = pd.DataFrame({
                    '項目': ['有效人次 (合計)', '票務收入 (含稅)', '周邊收入 (含稅)'],
                    '今年數據': [v_curr['計算人次'].sum(), curr_d[curr_d['營收分類'].str.contains('票務')]['統計用營收'].sum(), curr_d[curr_d['營收分類'].str.contains('周邊')]['統計用營收'].sum()],
                    '去年同期': [v_prev['計算人次'].sum(), prev_d[prev_d['營收分類'].str.contains('票務')]['統計用營收'].sum(), prev_d[prev_d['營收分類'].str.contains('周邊')]['統計用營收'].sum()]
                })
                comp_df['成長率 %'] = ((comp_df['今年數據'] - comp_df['去年同期']) / comp_df['去年同期'] * 100).map(lambda x: f"{x:.2f}%" if not np.isinf(x) else "N/A")
                st.table(comp_df.style.format({'今年數據': '{:,.0f}', '去年同期': '{:,.0f}'}).apply(lambda x: [HIGHLIGHT_COLOR if x.name == 0 else "" for _ in x], axis=1))
                st.divider()

        # --- Tab 2: 月份分析 ---
        with tab2:
            st.subheader("📅 月份營運趨勢")
            m_sum = processed.groupby('月份').agg({'統計用營收': 'sum', '計算人次': 'sum'}).reset_index()
            st.table(m_sum.style.format({'統計用營收': '{:,.0f}', '計算人次': '{:,.0f}'}))

        # --- Tab 3: 營運細項 (包含全分類合計與稼動率) ---
        with tab3:
            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader("💰 營收分類合計(全區間)")
                rev_all = processed.groupby('營收分類')['含稅營收'].sum().reset_index()
                rev_all = pd.concat([rev_all, pd.DataFrame([{'營收分類':'合計(不含無視)','含稅營收':processed['統計用營收'].sum()}])]).reset_index(drop=True)
                st.table(rev_all.style.format({'含稅營收': '{:,.0f}'}))
            with col_b:
                st.subheader("👥 人次分類合計(全區間)")
                att_all = processed[processed['人次分類'] != "不計人次"].groupby('人次分類')[['計算人次', '觀看總數']].sum().reset_index()
                st.table(att_all.style.format({'計算人次': '{:,.0f}', '觀看總數': '{:,.0f}'}))

            st.divider()
            st.subheader("⏰ 時段稼動率 (依篩選條件與公休日)")
            processed['區段'] = processed.apply(lambda x: get_slot_info(sel_site, x['假期'], x['時段小時'], x['分鐘']), axis=1)
            active_days = processed[~processed['交易日期'].dt.date.isin(off_days)].groupby(['交易日期', '假期']).size().reset_index()
            d_counts = active_days['假期'].value_counts().to_dict()
            
            slots = [("11:30-12:00", 2)] + [(f"{h:02d}:00-{(h+1):02d}:00", 4) for h in range(12, 20)] + [("20:00-21:00", 0)] if sel_site == "i-Ride TAIPEI" else \
                    [("09:30-10:00", 2)] + [(f"{h:02d}:00-{(h+1):02d}:00", 4) for h in range(10, 16)] + [("16:00-17:00", 4)]
            
            occ_data = []
            for sn, sq in slots:
                for ht in ["平日", "假日"]:
                    dn = d_counts.get(ht, 0)
                    if dn == 0: continue
                    aq = sq
                    if sel_site == "i-Ride TAIPEI" and sn == "20:00-21:00": aq = 5 if ht == "假日" else 4
                    denom = 20 * aq * dn
                    num = processed[(processed['區段'] == sn) & (processed['假期'] == ht) & (~processed['人次分類'].isin(['無視','VIP','不計人次'])) & (~processed['交易日期'].dt.date.isin(off_days))]['觀看總數'].sum()
                    occ_data.append({'時段': sn, '類型': ht, '稼動率': f"{(num/denom*100):.2f}%" if denom > 0 else "0.00%"})
            if occ_data:
                st.table(pd.DataFrame(occ_data).pivot(index='時段', columns='類型', values='稼動率').fillna("-"))
