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
    # 1. 假期定義
    def get_holiday_type(date_val):
        if pd.isna(date_val): return "未知"
        d_str = date_val.strftime('%Y-%m-%d')
        # 國定假日清單
        holidays_list = ['2025-01-01', '2025-01-27', '2025-01-28', '2025-01-29', '2025-01-30', '2025-01-31', '2026-01-01']
        return "假日" if (d_str in holidays_list or date_val.weekday() >= 5) else "平日"

    # 2. 核心分類邏輯
    def classify_row(row):
        pname = str(row.get('節目名稱', '')).strip()
        spec = str(row.get('品名規格', '')).strip()
        cid = str(row.get('會員卡號', row.get('客戶編號', ''))).strip().upper()
        qty = pd.to_numeric(row.get('交易數量', 0), errors='coerce') or 0
        rev = pd.to_numeric(row.get('原幣含稅金額', 0), errors='coerce') or 0
        
        res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val = "周邊商品", "不計人次", 0, 0, 0
        is_uncertain = False 

        # 通用票務關鍵字 (若含有這些字，自動判定為票務)
        ticket_keywords = ['票', '券', '卡', '分潤', '線上票', '核銷', '通路', '差額', '手續費']

        # --- [A] 人次與營收初步判定 ---
        if pname != "" and pname != "nan":
            res_watch_val = qty
            res_att_val = (2 if ('+' in pname or '＋' in pname) else 1) * qty
            res_rev = "票務"
            if cid.startswith('P') and "成人票" in spec: res_att_cat = "親子卡"
            elif 'VIP' in spec: res_att_cat = "VIP"
            elif any(x in spec for x in ['股東券', '股東票']): res_att_cat = "股東票"
            else: res_att_cat = "散客"
        elif any(k in spec for k in ['VR','體感','賽車','僵屍','LED']):
            res_rev, res_att_cat, res_att_val, res_esports_val = "電競館收入", "電競館", qty, qty
        elif any(k in spec for k in ticket_keywords):
            res_rev = "票務"
            res_att_cat = "平台" if "平台" in spec else "預售票"
        else:
            # 既沒影片也沒票字 -> 預設周邊，標記為「待確認」
            res_rev = "周邊商品"
            res_att_cat = "不計人次"
            is_uncertain = True 

        return pd.Series([res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val, rev, pname, spec, is_uncertain])

    # 3. 稼動率時段定義
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
        if "raw_df" not in st.session_state:
            df_in = pd.read_csv(uploaded_file, dtype=str) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, dtype=str)
            st.session_state.raw_df = df_in
            st.session_state.confirm_clicked = False 

        df_processed = st.session_state.raw_df.copy()
        df_processed['交易日期'] = pd.to_datetime(df_processed['交易日期'], errors='coerce')
        df_processed = df_processed.dropna(subset=['交易日期']).copy()
        df_processed['假期'] = df_processed['交易日期'].apply(get_holiday_type)
        df_processed['時段小時'] = pd.to_datetime(df_processed['場次時間'], format='%H:%M', errors='coerce').dt.hour
        df_processed['分鐘'] = pd.to_datetime(df_processed['場次時間'], format='%H:%M', errors='coerce').dt.minute

        # 基礎自動分類
        df_processed[['營收分類', '人次分類', '計算人次', '電競人次', '觀看總數', '含稅營收', '清單節目名稱', '原始規格', '待確認']] = df_processed.apply(classify_row, axis=1)

        # --- 置頂：人工判定區 (僅針對不確定項) ---
        uncertain_specs = sorted(df_processed[df_processed['待確認'] == True]['原始規格'].unique())
        manual_overrides = {}

        if len(uncertain_specs) > 0 and not st.session_state.get('confirm_clicked', False):
            with st.container():
                st.warning("⚠️ 偵測到新進/非票務品名，請確認分類 (確認後將隱藏此區塊)")
                for spec in uncertain_specs:
                    c1, c2, c3, c4 = st.columns([2, 1.2, 1.2, 1.2])
                    with c1: st.write(f"**{spec}**")
                    with c2: m_att = st.selectbox("人次", ["不計人次", "VIP", "VVIP", "平台", "股東票", "校園票", "散客", "無視", "團購券", "團體", "親子卡"], key=f"att_{spec}")
                    with c3: m_rev = st.selectbox("營收", ["周邊商品", "檔期商品", "票務", "平台", "無視", "預售票"], key=f"rev_{spec}")
                    with c4:
                        final_rev = m_rev
                        if m_rev == "檔期商品":
                            m_key = st.text_input("檔期關鍵字", placeholder="如: 巨人", key=f"key_{spec}")
                            final_rev = f"{m_key}周邊商品" if m_key else "檔期周邊商品"
                        else: st.empty()
                    manual_overrides[spec] = {"att": m_att, "rev": final_rev}
                
                if st.button("✅ 確認品名分類無誤"):
                    st.session_state.confirm_clicked = True
                    st.rerun()

        # 套用手動修正
        for spec, mapping in manual_overrides.items():
            mask = df_processed['原始規格'] == spec
            df_processed.loc[mask, '人次分類'] = mapping['att']
            df_processed.loc[mask, '營收分類'] = mapping['rev']

        # --- 側邊欄：設定表單 (一次性更新) ---
        with st.sidebar.form("global_settings"):
            st.header("⚙️ 營運參數")
            sel_site = st.selectbox("營運據點", ["i-Ride TAIPEI", "i-Ride KAOHSIUNG"])
            all_dates = sorted(df_processed['交易日期'].dt.date.unique())
            sel_range = st.date_input("分析區間", value=(all_dates[0], all_dates[-1]))
            sel_hols = st.multiselect("假期類型", ["平日", "假日"], default=["平日", "假日"])
            off_days = st.multiselect("排除公休日", options=all_dates, format_func=lambda x: f"{x} ({x.strftime('%a')})")
            
            st.divider()
            st.write("🎬 影片類別定義")
            films = sorted([f for f in df_processed['清單節目名稱'].unique() if f not in ["", "nan"]])
            film_tags = {f: st.text_input(f, value="未分類影片", key=f"tag_{f}") for f in films}
            
            run_report = st.form_submit_button("🔥 執行數據更新")

        # --- 報表產出區 ---
        if st.session_state.get('confirm_clicked', False) or len(uncertain_specs) == 0:
            df_processed['影片類別'] = df_processed['清單節目名稱'].map(film_tags)
            df_processed['統計用營收'] = df_processed.apply(lambda x: 0 if x['營收分類'] == '無視' else x['含稅營收'], axis=1)

            # 數據篩選
            start_d, end_d = (sel_range[0], sel_range[1]) if isinstance(sel_range, tuple) and len(sel_range) == 2 else (all_dates[0], all_dates[-1])
            f_df = df_processed[
                (df_processed['交易日期'].dt.date >= start_d) & 
                (df_processed['交易日期'].dt.date <= end_d) & 
                (df_processed['假期'].isin(sel_hols)) &
                (~df_processed['交易日期'].dt.date.isin(off_days))
            ].copy()

            st.header(f"📊 {sel_site} 營運分析報表")
            f_df_filtered = f_df[~f_df['人次分類'].isin(['無視', 'VIP', '不計人次', 'VVIP'])]

            # 指標卡
            c1, c2, c3 = st.columns(3)
            c1.metric("總計營收 (去無視)", f"{f_df['統計用營收'].sum():,.0f}")
            c2.metric("i-Ride 有效人次", f"{f_df_filtered['計算人次'].sum():,.0f}")
            c3.metric("電競館人次", f"{f_df['電競人次'].sum():,.0f}")

            # 合計表格
            st.divider()
            t1, t2 = st.columns(2)
            with t1:
                st.subheader("💰 營收分類合計")
                rev_res = f_df.groupby('營收分類')['含稅營收'].sum().reset_index()
                rev_res = pd.concat([rev_res, pd.DataFrame([{'營收分類':'合計(不含無視)','含稅營收':f_df['統計用營收'].sum()}])]).reset_index(drop=True)
                st.table(rev_res.style.format({'含稅營收': '{:,.0f}'}).apply(lambda x: [HIGHLIGHT_COLOR if x.name == len(rev_res)-1 else "" for _ in x], axis=1))
            with t2:
                st.subheader("👥 人次分類合計")
                att_res = f_df[f_df['人次分類'] != "不計人次"].groupby('人次分類')[['計算人次', '觀看總數']].sum().reset_index()
                att_res = pd.concat([att_res, pd.DataFrame([{'人次分類': '合計(有效)', '計算人次': f_df_filtered['計算人次'].sum(), '觀看總數': f_df_filtered['觀看總數'].sum()}])]).reset_index(drop=True)
                st.table(att_res.style.format({'計算人次': '{:,.0f}', '觀看總數': '{:,.0f}'}).apply(lambda x: [HIGHLIGHT_COLOR if x.name == len(att_res)-1 else "" for _ in x], axis=1))

            # 影片觀看分析
            st.divider()
            st.subheader("🎬 影片觀看分析")
            film_stats = f_df[f_df['清單節目名稱'].str.strip() != ""].groupby(['影片類別', '清單節目名稱'])['觀看總數'].sum().reset_index()
            final_film_list = []
            for cat, group in film_stats.groupby('影片類別'):
                final_film_list.append(group)
                final_film_list.append(pd.DataFrame([{'影片類別': cat, '清單節目名稱': f'【{cat} 合計】', '觀看總數': group['觀看總數'].sum()}]))
            if final_film_list:
                st.table(pd.concat(final_film_list).reset_index(drop=True).style.format({'觀看總數': '{:,.0f}'}).apply(lambda x: [HIGHLIGHT_COLOR if "合計" in str(x['清單節目名稱']) else "" for _ in x], axis=1))

            # 稼動率分析
            st.divider()
            st.subheader("⏰ 時段稼動率分析")
            hol_dates = f_df[f_df['假期'] == "假日"]['交易日期'].dt.strftime('%m/%d').unique()
            st.write(f"📅 **本區間假日日期：** {', '.join(sorted(hol_dates)) if len(hol_dates)>0 else '無'}")

            f_df['區段'] = f_df.apply(lambda x: get_slot_info(sel_site, x['假期'], x['時段小時'], x['分鐘']), axis=1)
            active_days_df = f_df.groupby(['交易日期', '假期']).size().reset_index()
            day_counts = active_days_df['假期'].value_counts().to_dict()
            
            # 時段配置
            slots_cfg = [("11:30-12:00", 2)] + [(f"{h:02d}:00-{(h+1):02d}:00", 4) for h in range(12, 20)] + [("20:00-21:00", 0)] if sel_site == "i-Ride TAIPEI" else \
                        [("09:30-10:00", 2)] + [(f"{h:02d}:00-{(h+1):02d}:00", 4) for h in range(10, 16)] + [("16:00-17:00", 4)]

            occ_results = []
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
                    occ_results.append({'時段': s_name, '類型': h_type, '值': rate, '稼動率': f"{rate:.2f}%"})

            if occ_results:
                occ_df = pd.DataFrame(occ_results)
                pivot_occ = occ_df.pivot(index='時段', columns='類型', values='稼動率').fillna("-")
                avg_vals = {h: f"平均: {occ_df[occ_df['類型']==h]['值'].mean():.2f}%" for h in sel_hols if h in pivot_occ.columns}
                final_occ_table = pd.concat([pivot_occ, pd.DataFrame(avg_vals, index=['平均稼動率'])])
                st.table(final_occ_table.style.apply(lambda x: [HIGHLIGHT_COLOR if x.name == '平均稼動率' else "" for _ in x], axis=1))
