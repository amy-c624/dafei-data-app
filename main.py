import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date

# --- 0. 驗證 ---
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
    # 1. 假期定義 (更新為 2026 範例)
    def get_holiday_type(date_val):
        if pd.isna(date_val): return "未知"
        d_str = date_val.strftime('%Y-%m-%d')
        # 國定假日清單 (可自行增加)
        holidays_list = ['2026-01-01', '2026-02-17', '2026-02-18'] 
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

            # --- [A] 人次分類 ---
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
                    res_att_cat, res_esports_val, res_att_val = "電競館", qty, qty

            # --- [C] 營收分類 ---
            if spec in ['商品兌換券', '票券核銷']: res_rev = "無視"
            elif any(x in spec for x in ['門票分潤', '線上票券']): res_rev = "平台收入"
            elif spec == '團購兌換券': res_rev = "預售票收入"
            elif (pname != "" and pname != "nan") or ("票" in spec) or ("券" in spec): res_rev = "票務"
            elif res_att_cat == "電競館": res_rev = "電競館收入"
            else: res_rev = "周邊商品"

            return pd.Series([res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val, rev, pname, spec])

        df[['營收分類', '人次分類', '計算人次', '電競人次', '觀看總數', '含稅營收', '清單節目名稱', '原始規格']] = df.apply(classify, axis=1)
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
        
        with st.sidebar:
            st.header("⚙️ 全域設定")
            sel_site = st.selectbox("營運據點", ["i-Ride TAIPEI", "i-Ride KAOHSIUNG"])
            all_dates = sorted(processed['交易日期'].dt.date.unique())
            sel_range = st.date_input("選擇分析區間", value=(all_dates[0], all_dates[-1]))
            sel_hols = st.multiselect("假日類型", ["平日", "假日"], default=["平日", "假日"])
            off_days = st.multiselect("公休日 (不計分母)", options=all_dates, format_func=lambda x: f"{x} ({x.strftime('%a')})")

        # --- 置頂：人工對位機制 ---
        unknown_mask = (processed['人次分類'] == "不計人次") & (processed['營收分類'] == "周邊商品")
        unknown_specs = processed[unknown_mask]['原始規格'].unique()
        manual_mapping = {}

        if len(unknown_specs) > 0:
            with st.expander("⚠️ 偵測到未分類品名規格 (請手動對位)", expanded=True):
                for spec in unknown_specs:
                    cols = st.columns([2, 2, 2, 2])
                    with cols[0]: st.markdown(f"**品名：**\n{spec}")
                    with cols[1]: m_att = st.selectbox("人次標籤", ["不計人次", "VIP", "VVIP", "平台", "股東票", "校園票", "散客", "無視", "團購券", "團體", "親子卡"], key=f"att_{spec}")
                    with cols[2]: m_rev = st.selectbox("營收標籤", ["周邊商品", "檔期商品", "票務", "平台", "無視", "預售票"], key=f"rev_{spec}")
                    with cols[3]:
                        if m_rev == "檔期商品":
                            m_key = st.text_input("檔期關鍵字", placeholder="例如：巨人", key=f"key_{spec}")
                            final_rev = f"{m_key}周邊商品" if m_key else "檔期周邊商品"
                        else: final_rev = m_rev
                    manual_mapping[spec] = {"att": m_att, "rev": final_rev}
                st.info("完成選取後，下方報表將自動即時更新。")

        # 套用覆寫
        for spec, mapping in manual_mapping.items():
            mask = processed['原始規格'] == spec
            processed.loc[mask, '人次分類'] = mapping['att']
            processed.loc[mask, '營收分類'] = mapping['rev']
            processed.loc[mask, '統計用營收'] = 0 if mapping['rev'] == "無視" else processed.loc[mask, '含稅營收']

        # --- 數據篩選 ---
        start_d, end_d = (sel_range[0], sel_range[1]) if isinstance(sel_range, tuple) and len(sel_range) == 2 else (all_dates[0], all_dates[-1])
        f_df = processed[
            (processed['交易日期'].dt.date >= start_d) & 
            (processed['交易日期'].dt.date <= end_d) & 
            (processed['假期'].isin(sel_hols)) &
            (~processed['交易日期'].dt.date.isin(off_days))
        ].copy()

        # --- 報表呈現 ---
        st.header(f"📊 {sel_site} 營運分析報表")
        f_df_filtered = f_df[~f_df['人次分類'].isin(['無視', 'VIP', '不計人次', 'VVIP'])]

        c1, c2, c3 = st.columns(3)
        c1.metric("總計營收 (去無視)", f"{f_df['統計用營收'].sum():,.0f}")
        c2.metric("i-Ride 有效人次", f"{f_df_filtered['計算人次'].sum():,.0f}")
        c3.metric("電競館人次", f"{f_df['電競人次'].sum():,.0f}")

        # 第一部分：合計
        st.divider()
        t1, t2 = st.columns(2)
        with t1:
            st.subheader("💰 營收分類合計")
            rev_t = f_df.groupby('營營收分類')['含稅營收'].sum().reset_index() if '營營收分類' in f_df.columns else f_df.groupby('營收分類')['含稅營收'].sum().reset_index()
            rev_f = pd.concat([rev_t, pd.DataFrame([{'營收分類':'合計(不含無視)','含稅營收':f_df['統計用營收'].sum()}])]).reset_index(drop=True)
            st.table(rev_f.style.format({'含稅營收': '{:,.0f}'}).apply(lambda x: [HIGHLIGHT_COLOR if x.name == len(rev_f)-1 else "" for _ in x], axis=1))
        with t2:
            st.subheader("👥 人次分類合計")
            att_t = f_df[f_df['人次分類'] != "不計人次"].groupby('人次分類')[['計算人次', '觀看總數']].sum().reset_index()
            att_f = pd.concat([att_t, pd.DataFrame([{'人次分類': '合計(不含無視)', '計算人次': f_df_filtered['計算人次'].sum(), '觀看總數': f_df_filtered['觀看總數'].sum()}])]).reset_index(drop=True)
            st.table(att_f.style.format({'計算人次': '{:,.0f}', '觀看總數': '{:,.0f}'}).apply(lambda x: [HIGHLIGHT_COLOR if x.name == len(att_f)-1 else "" for _ in x], axis=1))

        # 第二部分：稼動率 (重點更新區)
        st.divider()
        st.subheader("⏰ 時段稼動率分析")
        
        # 顯示假日日期文字
        hol_dates = f_df[f_df['假期'] == "假日"]['交易日期'].dt.strftime('%m/%d').unique()
        if len(hol_dates) > 0:
            st.write(f"📅 **本區間假日日期：** {', '.join(sorted(hol_dates))}")
        else:
            st.write("📅 **本區間無假日。**")

        f_df['區段'] = f_df.apply(lambda x: get_slot_info(sel_site, x['假期'], x['時段小時'], x['分鐘']), axis=1)
        active_days_df = f_df.groupby(['交易日期', '假期']).size().reset_index()
        day_counts = active_days_df['假期'].value_counts().to_dict()
        
        slots_cfg = [("11:30-12:00", 2)] + [(f"{h:02d}:00-{(h+1):02d}:00", 4) for h in range(12, 20)] + [("20:00-21:00", 0)] if sel_site == "i-Ride TAIPEI" else \
                    [("09:30-10:00", 2)] + [(f"{h:02d}:00-{(h+1):02d}:00", 4) for h in range(10, 16)] + [("16:00-17:00", 4)]

        occ_list = []
        for s_name, s_qty in slots_cfg:
            for h_type in sel_hols:
                d_num = day_counts.get(h_type, 0)
                if d_num == 0: continue
                act_qty = s_qty
                if sel_site == "i-Ride TAIPEI" and s_name == "20:00-21:00":
                    act_qty = 5 if h_type == "假日" else 4
                denom = 20 * act_qty * d_num
                num = f_df[(f_df['區段'] == s_name) & (f_df['假期'] == h_type) & (~f_df['人次分類'].isin(['無視','VIP','不計人次','VVIP']))]['觀看總數'].sum()
                rate = (num / denom * 100) if denom > 0 else 0
                occ_list.append({'時段': s_name, '類型': h_type, '稼動率值': rate, '稼動率': f"{rate:.2f}%"})

        if occ_list:
            occ_df = pd.DataFrame(occ_list)
            pivot_df = occ_df.pivot(index='時段', columns='類型', values='稼動率').fillna("-")
            
            # 計算平均值
            avg_row = {}
            for h_type in sel_hols:
                if h_type in pivot_df.columns:
                    mean_val = occ_df[occ_df['類型'] == h_type]['稼動率值'].mean()
                    avg_row[h_type] = f"平均: {mean_val:.2f}%"
            
            # 合併平均值到表格下方
            final_occ_df = pd.concat([pivot_df, pd.DataFrame(avg_row, index=['平均稼動率'])])
            
            st.table(final_occ_df.style.apply(lambda x: [HIGHLIGHT_COLOR if x.name == '平均稼動率' else "" for _ in x], axis=1))
