import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

# --- 0. 驗證 ---
def check_password():
    if "password_correct" not in st.session_state:
        def password_entered():
            if st.session_state["password"] == "TEST":
                st.session_state["password_correct"] = True
                del st.session_state["password"]
            else: st.session_state["password_correct"] = False
        st.text_input("請輸入授權密碼", type="password", on_change=password_entered, key="password")
        return False
    return st.session_state["password_correct"]

st.set_page_config(page_title="i-Ride 營運決策系統", layout="wide")
HIGHLIGHT_COLOR = "background-color: rgba(0, 123, 255, 0.4); font-weight: bold"

if check_password():
    # 1. 假期與時段輔助函數
    def get_holiday_type(date_val):
        if pd.isna(date_val): return "未知"
        d_str = date_val.strftime('%Y-%m-%d')
        holidays = ['2025-01-01', '2025-01-27', '2025-01-28', '2025-01-29', '2025-01-30', '2025-01-31', '2026-01-01']
        return "假日" if (d_str in holidays or date_val.weekday() >= 5) else "平日"

    def get_slot_info(site, h_type, hour, minute):
        try:
            h, m = int(hour), int(minute)
            if site == "i-Ride TAIPEI":
                if h == 11 and m >= 30: return "11:30-12:00"
                if 12 <= h < 20: return f"{h:02d}:00-{(h+1):02d}:00"
                if h == 20: return "20:00-21:00"
            else:
                if h == 9 and m >= 30: return "09:30-10:00"
                if 10 <= h < 16: return f"{h:02d}:00-{(h+1):02d}:00"
                if h == 16: return "16:00-17:00"
        except: pass
        return "不計入時段"

    # 2. 數據上傳與初始化
    uploaded_file = st.file_uploader("1. 上傳數據文件", type=['csv', 'xlsx'])

    if uploaded_file:
        if "raw_df" not in st.session_state:
            df_in = pd.read_csv(uploaded_file, dtype=str) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, dtype=str)
            st.session_state.raw_df = df_in
            st.session_state.anomaly_confirmed = False

        df = st.session_state.raw_df.copy()
        df['交易日期'] = pd.to_datetime(df['交易日期'], errors='coerce')
        df = df.dropna(subset=['交易日期']).copy()
        df['假期'] = df['交易日期'].apply(get_holiday_type)
        df['時段小時'] = pd.to_datetime(df['場次時間'], format='%H:%M', errors='coerce').dt.hour
        df['分鐘'] = pd.to_datetime(df['場次時間'], format='%H:%M', errors='coerce').dt.minute

        # --- 側邊欄設定表單 ---
        with st.sidebar.form("settings_form"):
            st.header("⚙️ 營運設定")
            sel_site = st.selectbox("營運據點", ["i-Ride TAIPEI", "i-Ride KAOHSIUNG"])
            sel_range = st.date_input("分析區間", value=(df['交易日期'].min().date(), df['交易日期'].max().date()))
            sel_hols = st.multiselect("類型篩選", ["平日", "假日"], default=["平日", "假日"])
            off_days = st.multiselect("排除公休日", options=sorted(df['交易日期'].dt.date.unique()), format_func=lambda x: f"{x}({x.strftime('%a')})")
            
            st.divider()
            st.write("🏷️ 檔期關鍵字定義")
            campaign_input = st.text_input("輸入檔期關鍵字 (用逗號隔開)", value="巨人, 柯南", help="例如: 巨人, 柯南, 妖怪")
            campaign_keys = [k.strip() for k in campaign_input.split(',') if k.strip()]

            st.write("🎬 影片類別標籤")
            films = sorted([f for f in df['節目名稱'].unique() if str(f) not in ["", "nan"]])
            film_tags = {f: st.text_input(f, value="未分類影片", key=f"tag_{f}") for f in films}
            
            submit_btn = st.form_submit_button("🔥 執行數據更新")

        # --- 3. 核心自動分類邏輯 (含衝突偵測) ---
        def auto_classify(row):
            pname = str(row.get('節目名稱', '')).strip()
            spec = str(row.get('品名規格', '')).strip()
            cid = str(row.get('會員卡號', row.get('客戶編號', ''))).strip().upper()
            qty = pd.to_numeric(row.get('交易數量', 0), errors='coerce') or 0
            rev = pd.to_numeric(row.get('原幣含稅金額', 0), errors='coerce') or 0
            
            res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val = "周邊商品", "不計人次", 0, 0, 0
            is_anomaly = False

            has_video = (pname != "" and pname != "nan")
            has_ticket_word = any(k in spec for k in ['票', '券', '卡', '核銷', '通路', '分潤'])

            # A. 正常票務判定
            if has_video:
                res_rev, res_watch_val = "票務", qty
                res_att_val = (2 if ('+' in pname or '＋' in pname) else 1) * qty
                if cid.startswith('P') and "成人票" in spec: res_att_cat = "親子卡"
                elif 'VIP' in spec: res_att_cat = "VIP"
                else: res_att_cat = "散客"
                # 衝突 A: 有影片但品名完全沒提票/券
                if not has_ticket_word: is_anomaly = True
            
            # B. 電競館判定
            elif any(k in spec for k in ['VR','體感','賽車','僵屍','LED']):
                res_rev, res_att_cat, res_att_val, res_esports_val = "電競館收入", "電競館", qty, qty

            # C. 周邊與檔期判定
            else:
                # 檢查是否命中檔期關鍵字
                matched_camp = next((k for k in campaign_keys if k in spec), None)
                if matched_camp:
                    res_rev = f"{matched_camp}周邊商品"
                elif has_ticket_word:
                    # 衝突 B: 沒影片名但品名有票/券字眼
                    res_rev, res_att_cat, is_anomaly = "票務", "待確認票種", True
                else:
                    res_rev = "周邊商品"

            return pd.Series([res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val, rev, is_anomaly])

        df[['營收分類', '人次分類', '計算人次', '電競人次', '觀看總數', '含稅營收', '是否衝突']] = df.apply(auto_classify, axis=1)

        # --- 4. 僅顯示衝突品名 (Anomaly UI) ---
        anomaly_specs = sorted(df[df['是否衝突'] == True]['品名規格'].unique())
        manual_fix = {}

        if len(anomaly_specs) > 0 and not st.session_state.get('anomaly_confirmed', False):
            with st.container():
                st.error(f"🚨 偵測到 {len(anomaly_specs)} 項邏輯衝突品名，請手動校正：")
                for spec in anomaly_specs:
                    c1, c2, c3 = st.columns([2, 1, 1])
                    with c1: st.write(f"❓ **{spec}**")
                    with c2: m_att = st.selectbox("人次類別", ["不計人次", "散客", "平台", "VIP", "無視"], key=f"fix_att_{spec}")
                    with c3: m_rev = st.selectbox("營收類別", ["票務", "周邊商品", "無視"], key=f"fix_rev_{spec}")
                    manual_fix[spec] = {"att": m_att, "rev": m_rev}
                if st.button("✅ 確認校正並隱藏區塊"):
                    st.session_state.anomaly_confirmed = True
                    st.rerun()

        # 套用手動修正與過濾
        if st.session_state.get('anomaly_confirmed', False):
            for spec, mapping in manual_fix.items():
                mask = df['品名規格'] == spec
                df.loc[mask, '人次分類'] = mapping['att']
                df.loc[mask, '營營收分類'] = mapping['rev']

        # --- 5. 產出報表 ---
        if st.session_state.get('anomaly_confirmed', False) or len(anomaly_specs) == 0:
            df['影片類別'] = df['節目名稱'].map(film_tags)
            df['統計用營收'] = df.apply(lambda x: 0 if x['營收分類'] == '無視' else x['含稅營收'], axis=1)

            # 區間篩選
            start_d, end_d = (sel_range[0], sel_range[1]) if isinstance(sel_range, tuple) and len(sel_range) == 2 else (df['交易日期'].min().date(), df['交易日期'].max().date())
            f_df = df[
                (df['交易日期'].dt.date >= start_d) & (df['交易日期'].dt.date <= end_d) & 
                (df['假期'].isin(sel_hols)) & (~df['交易日期'].dt.date.isin(off_days))
            ].copy()

            # 顯示結果指標
            st.header(f"📊 {sel_site} 營運報表")
            f_df_valid = f_df[~f_df['人次分類'].isin(['無視', '不計人次'])]
            
            c1, c2, c3 = st.columns(3)
            c1.metric("總計營收 (去無視)", f"{f_df['統計用營收'].sum():,.0f}")
            c2.metric("有效總人次", f"{f_df_valid['計算人次'].sum():,.0f}")
            c3.metric("觀看總數量", f"{f_df_valid['觀看總數'].sum():,.0f}")

            # 營收與人次表
            st.divider()
            t1, t2 = st.columns(2)
            with t1:
                st.subheader("💰 營收合計")
                rev_sum = f_df.groupby('營收分類')['含稅營收'].sum().reset_index()
                st.table(rev_sum.style.format({'含稅營收': '{:,.0f}'}))
            with t2:
                st.subheader("👥 人次合計")
                att_sum = f_df[f_df['人次分類'] != "不計人次"].groupby('人次分類')[['計算人次', '觀看總數']].sum().reset_index()
                st.table(att_sum.style.format({'計算人次': '{:,.0f}', '觀看總數': '{:,.0f}'}))

            # 稼動率分析
            st.divider()
            st.subheader("⏰ 時段稼動率分析")
            hols_found = f_df[f_df['假期'] == "假日"]['交易日期'].dt.strftime('%m/%d').unique()
            st.write(f"📅 **假日日期：** {', '.join(sorted(hols_found)) if len(hols_found)>0 else '無'}")

            f_df['區段'] = f_df.apply(lambda x: get_slot_info(sel_site, x['假期'], x['時段小時'], x['分鐘']), axis=1)
            active_days = f_df.groupby(['交易日期', '假期']).size().reset_index()['假期'].value_counts().to_dict()
            
            slots = [("11:30-12:00", 2)] + [(f"{h:02d}:00-{(h+1):02d}:00", 4) for h in range(12, 20)] + [("20:00-21:00", 0)] if sel_site == "i-Ride TAIPEI" else \
                    [("09:30-10:00", 2)] + [(f"{h:02d}:00-{(h+1):02d}:00", 4) for h in range(10, 16)] + [("16:00-17:00", 4)]

            occ_data = []
            for s_name, s_qty in slots:
                for h_type in sel_hols:
                    d_count = active_days.get(h_type, 0)
                    if d_count == 0: continue
                    act_q = 5 if (sel_site == "i-Ride TAIPEI" and s_name == "20:00-21:00" and h_type == "假日") else (4 if sel_site == "i-Ride TAIPEI" and s_name == "20:00-21:00" else s_qty)
                    denom = 20 * act_q * d_count
                    num = f_df[(f_df['區段'] == s_name) & (f_df['假期'] == h_type) & (~f_df['人次分類'].isin(['無視','不計人次']))]['觀看總數'].sum()
                    occ_data.append({'時段': s_name, '類型': h_type, '率': (num/denom*100) if denom > 0 else 0})

            if occ_data:
                occ_df = pd.DataFrame(occ_data)
                piv = occ_df.pivot(index='時段', columns='類型', values='率').fillna(0)
                # 補上百分比格式化與平均值
                avg_row = {h: f"平均: {occ_df[occ_df['類型']==h]['率'].mean():.2f}%" for h in piv.columns}
                piv_display = piv.applymap(lambda x: f"{x:.2f}%")
                final_occ = pd.concat([piv_display, pd.DataFrame(avg_row, index=['平均稼動率'])])
                st.table(final_occ.style.apply(lambda x: [HIGHLIGHT_COLOR if x.name == '平均稼動率' else "" for _ in x], axis=1))
