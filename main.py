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
    # 1. 輔助函數 (保留稼動率邏輯)
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
            else: # KAOHSIUNG
                if h == 9 and m >= 30: return "09:30-10:00"
                if 10 <= h < 16: return f"{h:02d}:00-{(h+1):02d}:00"
                if h == 16: return "16:00-17:00"
        except: pass
        return "不計入時段"

    if "confirmed_mapping" not in st.session_state: st.session_state.confirmed_mapping = {}
    if "anomaly_finished" not in st.session_state: st.session_state.anomaly_finished = False

    uploaded_file = st.file_uploader("1. 上傳數據文件 (CSV/Excel)", type=['csv', 'xlsx'])

    if uploaded_file:
        if "raw_df" not in st.session_state:
            # 【KeyError 防護】: 自動去除欄位空格
            raw = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
            raw.columns = raw.columns.str.strip() 
            st.session_state.raw_df = raw

        df = st.session_state.raw_df.copy()
        
        # 【數據流加固】: 確保日期與時間解析成功，不丟失校園票
        df['交易日期'] = pd.to_datetime(df['交易日期'], errors='coerce')
        df = df.dropna(subset=['交易日期']).copy()
        
        # 兼容高雄時間格式 (H:M 或 H:M:S)
        df['temp_time'] = pd.to_datetime(df['場次時間'], format='%H:%M:%S', errors='coerce').fillna(
                          pd.to_datetime(df['場次時間'], format='%H:%M', errors='coerce'))
        df['時段小時'] = df['temp_time'].dt.hour
        df['分鐘'] = df['temp_time'].dt.minute
        df['月份'] = df['交易日期'].dt.strftime('%Y/%m月')
        df['假期'] = df['交易日期'].apply(get_holiday_type)

        with st.sidebar.form("filter_settings"):
            st.header("⚙️ 營運設定")
            sel_site = st.selectbox("營運據點", ["i-Ride TAIPEI", "i-Ride KAOHSIUNG"])
            sel_range = st.date_input("日期區間", value=(df['交易日期'].min().date(), df['交易日期'].max().date()))
            sel_hols = st.multiselect("類型", ["平日", "假日"], default=["平日", "假日"])
            off_days = st.multiselect("選擇公休日", options=sorted(df['交易日期'].dt.date.unique()), format_func=lambda x: f"{x}({x.strftime('%a')})")
            camp_input = st.text_input("檔期關鍵字", value="巨人, 妖怪")
            campaign_keys = [k.strip() for k in camp_input.split(',') if k.strip()]
            unique_f = sorted([str(f) for f in df['節目名稱'].unique() if str(f) not in ["", "nan"]])
            tag_map = {f: st.text_input(f, value="未分類", key=f"tag_{f}") for f in unique_f}
            st.form_submit_button("🔥 執行數據更新")

        # --- 核心分類邏輯 (保留所有原定分類) ---
        def classify(row):
            pname, spec = str(row.get('節目名稱', '')).strip(), str(row.get('品名規格', '')).strip()
            cid = str(row.get('會員卡號', row.get('客戶編號', ''))).strip().upper()
            qty = pd.to_numeric(row.get('交易數量', 0), errors='coerce') or 0
            rev = pd.to_numeric(row.get('原幣含稅金額', 0), errors='coerce') or 0
            res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val = "周邊商品", "待確認票種", 0, 0, 0
            is_anomaly = False

            has_video = (pname != "" and pname != "nan")

            # 1. 優先捕捉校園票 (強化規則，確保 1675 人次不遺漏)
            if "校園" in spec or cid == 'Z00054' or "校園" in pname:
                if "商品" not in spec: res_att_cat = "校園票"

            # 2. 其他票種判斷 (北高共用邏輯)
            if res_att_cat == "待確認票種":
                if has_video:
                    if cid.startswith('P') and "成人票" in spec: res_att_cat = "親子卡"
                    elif any(x in spec for x in ['股東', '員工']): res_att_cat = "股東票"
                    elif 'VVIP' in spec or '體驗通行證' in spec: res_att_cat = "VVIP"
                    elif 'VIP' in spec: res_att_cat = "VIP"
                    elif '團購' in spec: res_att_cat = "團購券"
                    elif '平台' in spec or '通路' in spec: res_att_cat = "平台"
                    elif any(x in spec for x in ['企業', '團體']): res_att_cat = "團體"
                    elif any(x in spec for x in ['市民', '愛心', '學生', '套票', '成人', '現場']): res_att_cat = "散客"
                    if any(x in spec for x in ['免費', '券差額', '商品兌換']): res_att_cat = "無視"
                else:
                    if any(k in spec for k in ['VR','體感','賽車','僵屍','LED']): res_att_cat = "電競館"

            # 3. 數值指派 (確保即便無影片，校園票也能被計入)
            if res_att_cat != "無視" and res_att_cat != "待確認票種":
                res_watch_val = qty
                res_att_val = (2 if ('+' in pname or '＋' in pname) else 1) * qty
                if res_att_cat == "電競館": res_esports_val = qty
            
            # 觸發人工判定條件
            if res_att_cat == "待確認票種" and (has_video or any(x in spec for x in ['票','券','卡'])):
                is_anomaly = True

            # 4. 營收類別邏輯
            matched_camp = next((k for k in campaign_keys if k in spec), None)
            if spec in ['商品兌換券', '票券核銷']: res_rev = "無視"
            elif any(x in spec for x in ['門票分潤', '線上票券']): res_rev = "平台"
            elif '團購' in spec: res_rev = "預售票"
            elif matched_camp: res_rev = f"{matched_camp}周邊商品"
            elif has_video or any(x in spec for x in ['票','券','卡']): res_rev = "票務"
            elif res_att_cat == "電競館": res_rev = "電競館收入"
            else: res_rev = "周邊商品"

            return pd.Series([res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val, rev, pname, is_anomaly, spec])

        df[['營收分類', '人次分類', '計算人次', '電競人次', '觀看總數', '含稅營收', '清單節目名稱', '是否衝突', '原始規格']] = df.apply(classify, axis=1)

        # --- 2. 人工判定區 (保留完整手動修正功能) ---
        anomaly_specs = sorted(df[df['是否衝突'] == True]['原始規格'].unique())
        if len(anomaly_specs) > 0 and not st.session_state.anomaly_finished:
            with st.form("anomaly_fix_form"):
                st.error(f"🚨 偵測到 {len(anomaly_specs)} 項需要手動分類：")
                temp_fixes = {}
                for spec in anomaly_specs:
                    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
                    with c1: st.write(f"**{spec}**")
                    with c2: temp_fixes[f"{spec}_att"] = st.selectbox("人次類別", ["校園票", "散客", "平台", "VIP", "股東票", "團體", "親子卡", "無視"], key=f"a_att_{spec}")
                    with c3: temp_fixes[f"{spec}_rev"] = st.selectbox("營收類別", ["票務", "周邊商品", "平台", "預售票", "無視", "檔期商品"], key=f"a_rev_{spec}")
                    with c4: temp_fixes[f"{spec}_key"] = st.text_input("檔期名", key=f"a_key_{spec}")
                if st.form_submit_button("✅ 確認並套用數據"):
                    for spec in anomaly_specs:
                        rev_val = f"{temp_fixes[f'{spec}_key']}周邊商品" if temp_fixes[f"{spec}_rev"] == "檔期商品" else temp_fixes[f"{spec}_rev"]
                        st.session_state.confirmed_mapping[spec] = {"att": temp_fixes[f"{spec}_att"], "rev": rev_val}
                    st.session_state.anomaly_finished = True
                    st.rerun()

        # --- 3. 數據套用 ---
        if st.session_state.anomaly_finished:
            for spec, mapping in st.session_state.confirmed_mapping.items():
                mask = df['原始規格'] == spec
                df.loc[mask, '人次分類'] = mapping['att']
                df.loc[mask, '營收分類'] = mapping['rev']
                # 強制補回人次數據
                if mapping['att'] != "無視":
                    df.loc[mask, '計算人次'] = pd.to_numeric(df.loc[mask, '交易數量'], errors='coerce').fillna(0)
                    df.loc[mask, '觀看總數'] = df.loc[mask, '計算人次']

        df.loc[df['人次分類'] == "無視", ['計算人次', '觀看總數']] = 0
        df['統計用營收'] = df.apply(lambda x: 0 if x['營收分類'] == '無視' else x['含稅營收'], axis=1)
        df['影片類別'] = df['清單節目名稱'].map(tag_map)

        # --- 4. 報表產出 ---
        if st.session_state.anomaly_finished or len(anomaly_specs) == 0:
            start_d, end_d = (sel_range[0], sel_range[1]) if isinstance(sel_range, tuple) else (sel_range, sel_range)
            f_df = df[(df['交易日期'].dt.date >= start_d) & (df['交易日期'].dt.date <= end_d) & (df['假期'].isin(sel_hols)) & (~df['交易日期'].dt.date.isin(off_days))].copy()
            f_df_valid = f_df[f_df['人次分類'] != "無視"]

            st.header(f"📊 {sel_site} 分析報表")
            c1, c2, c3 = st.columns(3)
            c1.metric("總計營收 (去無視)", f"{f_df['統計用營收'].sum():,.0f}")
            c2.metric("有效總人次", f"{f_df_valid['計算人次'].sum():,.0f}")
            c3.metric("觀看總數量", f"{f_df_valid['觀看總數'].sum():,.0f}")

            # 分類合計表
            st.divider()
            t1, t2 = st.columns(2)
            with t1:
                st.subheader("💰 營收分類合計")
                rev_sum = f_df.groupby('營收分類')['含稅營收'].sum().reset_index()
                st.table(rev_sum.style.format({'含稅營收': '{:,.0f}'}))
            with t2:
                st.subheader("👥 人次分類合計")
                att_sum = f_df_valid.groupby('人次分類')[['計算人次', '觀看總數']].sum().reset_index()
                st.table(att_sum.style.format({'計算人次': '{:,.0f}', '觀看總數': '{:,.0f}'}))

            # 影片觀看分析 (保留類別加總功能)
            st.divider()
            st.subheader("🎬 影片觀看分析")
            film_df = f_df_valid[f_df_valid['清單節目名稱'].str.strip() != ""].copy()
            if not film_df.empty:
                film_stats = film_df.groupby(['影片類別', '清單節目名稱'])['觀看總數'].sum().reset_index()
                final_list = []
                for cat, grp in film_stats.groupby('影片類別'):
                    final_list.append(grp)
                    final_list.append(pd.DataFrame([{'影片類別': cat, '清單節目名稱': f'【{cat} 合計】', '觀看總數': grp['觀看總數'].sum()}]))
                st.table(pd.concat(final_list).reset_index(drop=True).style.apply(lambda x: [HIGHLIGHT_COLOR if "合計" in str(x['清單節目名稱']) else "" for _ in x], axis=1))

            # 稼動率分析 (保留台北/高雄自動切換)
            st.divider()
            st.subheader("⏰ 時段稼動率分析")
            f_df['區段'] = f_df.apply(lambda x: get_slot_info(sel_site, x['假期'], x['時段小時'], x['分鐘']), axis=1)
            active_days = f_df.groupby(['交易日期', '假期']).size().reset_index()['假期'].value_counts().to_dict()
            slots = [("11:30-12:00", 2)] + [(f"{h:02d}:00-{(h+1):02d}:00", 4) for h in range(12, 20)] + [("20:00-21:00", 0)] if sel_site == "i-Ride TAIPEI" else [("09:30-10:00", 2)] + [(f"{h:02d}:00-{(h+1):02d}:00", 4) for h in range(10, 16)] + [("16:00-17:00", 4)]
            occ_data = []
            for s_name, s_qty in slots:
                for h_type in sel_hols:
                    d_count = active_days.get(h_type, 0)
                    if d_count == 0: continue
                    act_q = 5 if (sel_site == "i-Ride TAIPEI" and s_name == "20:00-21:00" and h_type == "假日") else (4 if sel_site == "i-Ride TAIPEI" and s_name == "20:00-21:00" else s_qty)
                    denom = 20 * act_q * d_count
                    num = f_df[(f_df['區段'] == s_name) & (f_df['假期'] == h_type) & (f_df['人次分類'] != "無視")]['觀看總數'].sum()
                    occ_data.append({'時段': s_name, '類型': h_type, '率': (num/denom*100) if denom > 0 else 0})
            if occ_data:
                piv = pd.DataFrame(occ_data).pivot(index='時段', columns='類型', values='率').fillna(0)
                st.table(piv.applymap(lambda x: f"{x:.2f}%"))
