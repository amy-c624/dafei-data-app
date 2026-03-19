import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date

# --- 0. 驗證設定 ---
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

st.set_page_config(page_title="i-Ride 營運戰略系統 (YoY版)", layout="wide")
HIGHLIGHT_COLOR = "background-color: rgba(0, 123, 255, 0.4); font-weight: bold"

if check_password():
    # 1. 假期定義 (建議在此擴展 2024-2026 完整清單)
    def get_holiday_type(date_val):
        if pd.isna(date_val): return "未知"
        holidays = ['2025-01-01', '2025-01-27', '2025-01-28', '2025-01-29', '2025-01-30', '2025-01-31', '2026-01-01']
        return "假日" if (date_val.strftime('%Y-%m-%d') in holidays or date_val.weekday() >= 5) else "平日"

    # 2. 核心分類引擎 (合併檔期判斷)
    def process_data(dfs, campaign_list):
        df = pd.concat(dfs, ignore_index=True)
        df['交易日期'] = pd.to_datetime(df['交易日期'], errors='coerce')
        df = df.dropna(subset=['交易日期']).copy()
        df['月份'] = df['交易日期'].dt.strftime('%Y/%m月')
        df['假期'] = df['交易日期'].apply(get_holiday_type)
        df['時段小時'] = pd.to_datetime(df['場次時間'], format='%H:%M', errors='coerce').dt.hour
        df['分鐘'] = pd.to_datetime(df['場次時間'], format='%H:%M', errors='coerce').dt.minute

        def deep_classify(row):
            pname = str(row.get('節目名稱', '')).strip()
            spec = str(row.get('品名規格', '')).strip()
            cid = str(row.get('會員卡號', row.get('客戶編號', ''))).strip().upper()
            qty = pd.to_numeric(row.get('交易數量', 0), errors='coerce') or 0
            rev = pd.to_numeric(row.get('原幣含稅金額', 0), errors='coerce') or 0
            tx_date = row['交易日期'].date()
            
            # [A] 檔期匹配
            cur_camp = "一般"
            for camp in campaign_list:
                if camp['start'] <= tx_date <= camp['end']:
                    if camp['key'] in pname or camp['key'] in spec:
                        cur_camp = camp['name']
                        break

            # [B] 人次分類 (原始邏輯)
            res_att_cat = "不計人次"
            if cid.startswith('P') and spec == "成人票": res_att_cat = "親子卡"
            elif cid == 'Z00054' and spec == "VIP貴賓券核銷": res_att_cat = "校園票"
            elif any(x in spec for x in ['股東券', '股東票']): res_att_cat = "股東"
            elif 'VIP貴賓券核銷' in spec: res_att_cat = "VIP"
            elif any(x in spec for x in ['市民票', '愛心票', '學生票', '成人票']): res_att_cat = "散客"
            if any(x in spec for x in ['免費票', '員工票', '券差額', '商品兌換券', '票券核銷', '活動服務費']): res_att_cat = "無視"

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

            # [D] 營收細分 (檔期連動)
            res_rev = "一般周邊"
            if spec in ['商品兌換券', '票券核銷']: res_rev = "無視"
            elif any(x in spec for x in ['門票分潤', '線上票券']): res_rev = "平台收入"
            elif (pname != "" and pname != "nan") or "票" in spec or "券" in spec:
                res_rev = f"{cur_camp}票務" if cur_camp != "一般" else "一般票務"
            else:
                res_rev = f"{cur_camp}周邊" if cur_camp != "一般" else "一般周邊"
            
            if res_att_cat == "電競館": res_rev = "電競館收入"

            return pd.Series([cur_camp, res_rev, res_att_cat, res_att_val, res_watch_val, res_esports_val, rev, pname])

        df[['所屬檔期', '營收分類', '人次分類', '計算人次', '觀看總數', '電競人次', '含稅營收', '清單節目名稱']] = df.apply(deep_classify, axis=1)
        df['統計用營收'] = df.apply(lambda x: 0 if x['營收分類'] == '無視' else x['含稅營收'], axis=1)
        return df

    # 3. 稼動率區段 (原始 15min 邏輯)
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

    # --- 4. UI 介面 ---
    uploaded_files = st.file_uploader("1. 批次上傳數據 (可多選 2024-2026 報表)", type=['csv', 'xlsx'], accept_multiple_files=True)

    if uploaded_files:
        dfs = [pd.read_csv(f, dtype=str) if f.name.endswith('.csv') else pd.read_excel(f, dtype=str) for f in uploaded_files]
        raw_combined = pd.concat(dfs, ignore_index=True) # 預覽用
        
        with st.sidebar.form("strategic_form"):
            st.header("🎯 檔期與據點配置")
            sel_site = st.selectbox("營運據點", ["i-Ride TAIPEI", "i-Ride KAOHSIUNG"])
            
            # 公休日多選
            all_dates = pd.to_datetime(raw_combined['交易日期'], errors='coerce').dropna().dt.date.unique()
            all_dates = sorted(all_dates)
            date_options = {d: f"{d} ({d.strftime('%a')})" for d in all_dates}
            off_days = st.multiselect("選擇公休日 (不計分母)", options=all_dates, format_func=lambda x: date_options[x])

            # 動態檔期配置
            st.divider()
            num_camps = st.number_input("定義檔期數量", min_value=1, max_value=3, value=1)
            campaigns = []
            for i in range(int(num_camps)):
                c_name = st.text_input(f"檔期{i+1}名稱", value=f"主題{i+1}", key=f"cn{i}")
                c_dates = st.date_input(f"檔期{i+1}期間", value=[date(2026,1,1), date(2026,3,18)], key=f"cd{i}")
                c_key = st.text_input(f"檔期{i+1}關鍵字", value=c_name, key=f"ck{i}")
                if len(c_dates) == 2:
                    campaigns.append({'name': c_name, 'start': c_dates[0], 'end': c_dates[1], 'key': c_key})

            # 影片標籤
            st.divider()
            st.write("🎬 影片分類標籤")
            u_films = sorted([str(f) for f in raw_combined['節目名稱'].unique() if str(f) not in ["", "nan", "NaN"]])
            tag_map = {f: st.text_input(f, value="未分類", key=f"tag_{f}") for f in u_films}
            
            submitted = st.form_submit_button("🔥 啟動全戰略分析")

        # --- 數據計算處理 ---
        processed = process_data(dfs, campaigns)
        processed['影片類別'] = processed['清單節目名稱'].map(tag_map)
        
        # 手動無視與標籤更新觸發
        ign_mask = processed['影片類別'] == "無視"
        processed.loc[ign_mask, ['計算人次', '觀看總數']] = 0
        processed.loc[ign_mask, '人次分類'] = "無視"

        # --- 分檔期呈現 YoY ---
        for camp in campaigns:
            st.header(f"📌 檔期專報：{camp['name']}")
            
            # 定義今年與去年區間
            start_ly, end_ly = camp['start'].replace(year=camp['start'].year-1), camp['end'].replace(year=camp['end'].year-1)
            
            this_year = processed[(processed['交易日期'].dt.date >= camp['start']) & (processed['交易日期'].dt.date <= camp['end']) & (~processed['交易日期'].dt.date.isin(off_days))]
            last_year = processed[(processed['交易日期'].dt.date >= start_ly) & (processed['交易日期'].dt.date <= end_ly)]
            
            valid_ty = this_year[~this_year['人次分類'].isin(['無視','VIP','不計人次'])]
            valid_ly = last_year[~last_year['人次分類'].isin(['無視','VIP','不計人次'])]

            # 指標卡
            c1, c2, c3 = st.columns(3)
            c1.metric(f"{camp['name']} 人次", f"{valid_ty['計算人次'].sum():,.0f}", delta=f"{valid_ty['計算人次'].sum()-valid_ly['計算人次'].sum():,.0f} YoY")
            
            total_yr_valid = processed[(processed['交易日期'].dt.year == camp['start'].year) & (~processed['人次分類'].isin(['無視','VIP','不計人次']))]['計算人次'].sum()
            share = (valid_ty['計算人次'].sum() / total_yr_valid * 100) if total_yr_valid > 0 else 0
            c2.metric("檔期人次佔比", f"{share:.2f}%")
            c3.metric("檔期票務營收", f"{this_year[this_year['營收分類'].str.contains('票務')]['統計用營收'].sum():,.0f}")

            # YoY 表格
            st.subheader("📊 檔期同期對照表")
            comp_data = {
                '項目': ['有效人次', '票務營收 (不含無視)', '周邊營收 (不含無視)'],
                '今年數據': [
                    valid_ty['計算人次'].sum(),
                    this_year[this_year['營收分類'].str.contains('票務')]['統計用營收'].sum(),
                    this_year[this_year['營收分類'].str.contains('周邊')]['統計用營收'].sum()
                ],
                '去年同期': [
                    valid_ly['計算人次'].sum(),
                    last_year[last_year['營收分類'].str.contains('票務')]['統計用營收'].sum(),
                    last_year[last_year['營收分類'].str.contains('周邊')]['統計用營收'].sum()
                ]
            }
            cdf = pd.DataFrame(comp_data)
            cdf['成長率'] = ((cdf['今年數據'] - cdf['去年同期']) / cdf['去年同期'] * 100).map(lambda x: f"{x:.2f}%" if not np.isinf(x) else "N/A")
            st.table(cdf.style.format({'今年數據': '{:,.0f}', '去年同期': '{:,.0f}'}).apply(lambda x: [HIGHLIGHT_COLOR if x.name == 0 else "" for _ in x], axis=1))

        # --- 原始基礎報表回歸 (全區間) ---
        st.divider()
        st.header("📋 全區間基礎分類統計")
        # 僅看篩選月份後的資料 (如果需要的話)
        t1, t2 = st.columns(2)
        with t1:
            st.subheader("💰 營收類別合計 (全上傳區間)")
            rev_f = processed.groupby('營收分類')['含稅營收'].sum().reset_index()
            rev_f = pd.concat([rev_f, pd.DataFrame([{'營收分類':'合計(不含無視)','含稅營收':processed['統計用營收'].sum()}])]).reset_index(drop=True)
            st.table(rev_f.style.format({'含稅營收': '{:,.0f}'}).apply(lambda x: [HIGHLIGHT_COLOR if x.name == len(rev_f)-1 else "" for _ in x], axis=1))
        with t2:
            st.subheader("👥 人次類別合計 (全上傳區間)")
            att_f = processed[processed['人次分類'] != "不計人次"].groupby('人次分類')[['計算人次', '觀看總數']].sum().reset_index()
            v_all = processed[~processed['人次分類'].isin(['無視','VIP','不計人次'])]
            att_f = pd.concat([att_f, pd.DataFrame([{'人次分類':'合計(不含無視)','計算人次':v_all['計算人次'].sum(),'觀看總數':v_all['觀看總數'].sum()}])]).reset_index(drop=True)
            st.table(att_f.style.format({'計算人次': '{:,.0f}','觀看總數': '{:,.0f}'}).apply(lambda x: [HIGHLIGHT_COLOR if x.name == len(att_f)-1 else "" for _ in x], axis=1))

        # --- 影片觀看分析 (交易數量 + 類別合計) ---
        st.divider()
        st.subheader("🎬 影片觀看分析 (以交易數量計)")
        f_stats = processed[processed['清單節目名稱'] != ""].groupby(['影片類別', '清單節目名稱'])['觀看總數'].sum().reset_index()
        f_list = []
        for cat, group in f_stats.groupby('影片類別'):
            f_list.append(group)
            f_list.append(pd.DataFrame([{'影片類別': cat, '清單節目名稱': f'【{cat} 合計】', '觀看總數': group['觀看總數'].sum()}]))
        if f_list:
            full_f_df = pd.concat(f_list).reset_index(drop=True)
            st.table(full_f_df.style.format({'觀看總數': '{:,.0f}'}).apply(lambda x: [HIGHLIGHT_COLOR if "合計" in str(x['清單節目名稱']) else "" for _ in x], axis=1))

        # --- 稼動率分析回歸 ---
        st.divider()
        st.subheader("⏰ 時段稼動率分析")
        processed['區段'] = processed.apply(lambda x: get_slot_info(sel_site, x['假期'], x['時段小時'], x['分鐘']), axis=1)
        active_days = processed[~processed['交易日期'].dt.date.isin(off_days)].groupby(['交易日期', '假期']).size().reset_index()
        d_counts = active_days['假期'].value_counts().to_dict()
        
        slots_cfg = [("11:30-12:00", 2)] + [(f"{h:02d}:00-{(h+1):02d}:00", 4) for h in range(12, 20)] + [("20:00-21:00", 0)] if sel_site == "i-Ride TAIPEI" else \
                    [("09:30-10:00", 2)] + [(f"{h:02d}:00-{(h+1):02d}:00", 4) for h in range(10, 16)] + [("16:00-17:00", 4)]
        
        occ_rows = []
        for sn, sq in slots_cfg:
            for ht in ["平日", "假日"]:
                dn = d_counts.get(ht, 0)
                if dn == 0: continue
                aq = sq
                if sel_site == "i-Ride TAIPEI" and sn == "20:00-21:00": aq = 5 if ht == "假日" else 4
                denom = 20 * aq * dn
                num = processed[(processed['區段'] == sn) & (processed['假期'] == ht) & (~processed['人次分類'].isin(['無視','VIP','不計人次'])) & (~processed['交易日期'].dt.date.isin(off_days))]['觀看總數'].sum()
                occ_rows.append({'時段': sn, '類型': ht, '稼動率': f"{(num/denom*100):.2f}%" if denom > 0 else "0.00%"})
        if occ_rows:
            st.table(pd.DataFrame(occ_rows).pivot(index='時段', columns='類型', values='稼動率').fillna("-"))
