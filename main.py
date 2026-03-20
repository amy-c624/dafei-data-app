import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

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
    def get_holiday_type(date):
        if pd.isna(date): return "未知"
        d_str = date.strftime('%Y-%m-%d')
        holidays_list = ['2025-01-01', '2025-01-27', '2025-01-28', '2025-01-29', '2025-01-30', '2025-01-31', '2026-01-01']
        return "假日" if (d_str in holidays_list or date.weekday() >= 5) else "平日"

    # 2. 稼動率時段
    def get_slot_info(site, holiday_type, hour, minute):
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

    # 3. 核心處理函數 (整合動態關鍵字與衝突偵測)
    def process_data(df, campaign_keys):
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
            is_anomaly = False # 紀錄衝突

            has_video = (pname != "" and pname != "nan")
            has_ticket_word = any(x in spec for x in ['票', '券', '卡', '門票', '核銷', '通路'])

            # --- [A] 人次分類與衝突偵測 ---
            if has_video:
                res_watch_val = qty
                n_films = 2 if ('+' in pname or '＋' in pname) else 1
                res_att_val = n_films * qty
                
                if cid.startswith('P') and "成人票" in spec: res_att_cat = "親子卡"
                elif cid == 'Z00054' and spec == "VIP貴賓券核銷": res_att_cat = "校園票"
                elif any(x in spec for x in ['股東券', '股東票']): res_att_cat = "股東"
                elif '貴賓體驗通行證核銷' in spec: res_att_cat = "VVIP"
                elif 'VIP貴賓券核銷' in spec: res_att_cat = "VIP"
                elif any(x in spec for x in ['團購兌換券展延', '團購兌換券核銷']): res_att_cat = "團購券"
                elif '平台通路票' in spec: res_att_cat = "平台"
                elif any(x in spec for x in ['企業優惠票', '團體優惠票']): res_att_cat = "團體"
                elif any(x in spec for x in ['市民票', '愛心票', '學生票', '優惠套票', '成人票']): res_att_cat = "散客"
                
                if any(x in spec for x in ['免費票', '員工票', '券差額', '券類溢收-商品', '商品兌換券', '票券核銷', '活動服務費']): 
                    res_att_cat = "無視"
                
                if res_att_cat == "不計人次": res_att_cat = "無視"
                
                # 衝突偵測 A: 有影片但品名完全沒提票/券
                if not has_ticket_word and res_att_cat != "無視": is_anomaly = True

            else:
                if any(k in spec for k in ['VR','體感','賽車','僵屍','LED']): 
                    res_att_cat, res_esports_val, res_att_val = "電競館", qty, qty
                elif has_ticket_word:
                    # 衝突偵測 B: 沒影片但品名有票字
                    is_anomaly = True
                    res_att_cat = "待確認票種"

            # --- [B] 營收分類 (整合動態關鍵字) ---
            matched_camp = next((k for k in campaign_keys if k in spec), None)

            if spec in ['商品兌換券', '票券核銷']: res_rev = "無視"
            elif any(x in spec for x in ['門票分潤', '線上票券']): res_rev = "平台收入"
            elif spec == '團購兌換券': res_rev = "預售票收入"
            elif matched_camp: res_rev = f"{matched_camp}周邊商品"
            elif has_video or has_ticket_word: res_rev = "票務"
            elif res_att_cat == "電競館": res_rev = "電競館收入"
            else: res_rev = "周邊商品"

            return pd.Series([res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val, rev, pname, is_anomaly, spec])

        df[['營收分類', '人次分類', '計算人次', '電競人次', '觀看總數', '含稅營收', '清單節目名稱', '是否衝突', '原始規格']] = df.apply(classify, axis=1)
        df['統計用營收'] = df.apply(lambda x: 0 if x['營收分類'] == '無視' else x['含稅營收'], axis=1)
        return df

    uploaded_file = st.file_uploader("1. 上傳數據文件 (CSV/Excel)", type=['csv', 'xlsx'])

    if uploaded_file:
        if "raw_df" not in st.session_state:
            df_raw = pd.read_csv(uploaded_file, dtype=str) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, dtype=str)
            st.session_state.raw_df = df_raw
            st.session_state.anomaly_confirmed = False

        # --- 側邊欄 Form (一次性更新) ---
        with st.sidebar.form("setting_form"):
            st.header("⚙️ 營運設定")
            sel_site = st.selectbox("營運據點", ["i-Ride TAIPEI", "i-Ride KAOHSIUNG"])
            
            # 檔期定義
            camp_input = st.text_input("檔期關鍵字 (用逗號隔開)", value="巨人, 妖怪")
            campaign_keys = [k.strip() for k in camp_input.split(',') if k.strip()]
            
            # 影片標籤
            unique_f = sorted([f for f in st.session_state.raw_df['節目名稱'].unique() if str(f) not in ["", "nan"]])
            tag_map = {f: st.text_input(f, value="未分類", key=f"tag_{f}") for f in unique_f}
            
            st.divider()
            submitted = st.form_submit_button("🔥 執行數據更新")

        # 處理數據
        processed = process_data(st.session_state.raw_df, campaign_keys)
        processed['影片類別'] = processed['清單節目名稱'].map(tag_map)

        # --- 置頂：僅顯示衝突對位區 ---
        anomaly_df = processed[processed['是否衝突'] == True]
        anomaly_specs = sorted(anomaly_df['原始規格'].unique())
        manual_fixes = {}

        if len(anomaly_specs) > 0 and not st.session_state.get('anomaly_confirmed', False):
            with st.container():
                st.error(f"🚨 偵測到 {len(anomaly_specs)} 項邏輯衝突品名，請修正後再顯示報表：")
                for spec in anomaly_specs:
                    c1, c2, c3 = st.columns([2, 1, 1])
                    with c1: st.write(f"❓ {spec}")
                    with c2: m_att = st.selectbox("人次類別", ["不計人次", "散客", "平台", "VIP", "無視"], key=f"fix_att_{spec}")
                    with c3: m_rev = st.selectbox("營收類別", ["票務", "周邊商品", "無視"], key=f"fix_rev_{spec}")
                    manual_fixes[spec] = {"att": m_att, "rev": m_rev}
                if st.button("✅ 確認修正並產出報表"):
                    st.session_state.anomaly_confirmed = True
                    st.rerun()

        # 套用手動修正
        if st.session_state.get('anomaly_confirmed', False):
            for spec, mapping in manual_fixes.items():
                mask = processed['原始規格'] == spec
                processed.loc[mask, '人次分類'] = mapping['att']
                processed.loc[mask, '營收分類'] = mapping['rev']

        # --- 報表產出 ---
        if st.session_state.get('anomaly_confirmed', False) or len(anomaly_specs) == 0:
            # 報表篩選 (維持原邏輯)
            all_dates = sorted(processed['交易日期'].dt.date.unique())
            sel_range = st.date_input("分析日期區間", value=(all_dates[0], all_dates[-1]))
            sel_hols = st.multiselect("類型篩選", ["平日", "假日"], default=["平日", "假日"])
            
            f_df = processed[
                (processed['交易日期'].dt.date >= sel_range[0]) & 
                (processed['交易日期'].dt.date <= sel_range[1]) &
                (processed['假期'].isin(sel_hols))
            ].copy()

            st.header(f"📊 {sel_site} 營運分析報表")
            f_df_filtered = f_df[~f_df['人次分類'].isin(['無視', 'VIP', '不計人次'])]

            # 指標卡
            c1, c2, c3 = st.columns(3)
            c1.metric("總計營收 (去無視)", f"{f_df['統計用營收'].sum():,.0f}")
            c2.metric("i-Ride 有效人次", f"{f_df_filtered['計算人次'].sum():,.0f}")
            c3.metric("電競館人次", f"{f_df['電競人次'].sum():,.0f}")

            # 營收與人次表
            st.divider()
            t1, t2 = st.columns(2)
            with t1:
                st.subheader("💰 營收分類合計")
                rev_f = f_df.groupby('營收分類')['含稅營收'].sum().reset_index()
                rev_f = pd.concat([rev_f, pd.DataFrame([{'營收分類':'合計(不含無視)','含稅營收':f_df['統計用營收'].sum()}])]).reset_index(drop=True)
                st.table(rev_f.style.format({'含稅營收': '{:,.0f}'}).apply(lambda x: [HIGHLIGHT_COLOR if x.name == len(rev_f)-1 else "" for _ in x], axis=1))
            with t2:
                st.subheader("👥 人次分類合計")
                att_f = f_df[f_df['人次分類'] != "不計人次"].groupby('人次分類')[['計算人次', '觀看總數']].sum().reset_index()
                att_f = pd.concat([att_f, pd.DataFrame([{'人次分類': '合計(不含無視)', '計算人次': f_df_filtered['計算人次'].sum(), '觀看總數': f_df_filtered['觀看總數'].sum()}])]).reset_index(drop=True)
                st.table(att_f.style.format({'計算人次': '{:,.0f}', '觀看總數': '{:,.0f}'}).apply(lambda x: [HIGHLIGHT_COLOR if x.name == len(att_f)-1 else "" for _ in x], axis=1))

            # 影片觀看分析
            st.divider()
            st.subheader("🎬 影片觀看分析 (以交易數量計)")
            film_stats = f_df[f_df['清單節目名稱'] != ""].groupby(['影片類別', '清單節目名稱'])['觀看總數'].sum().reset_index()
            final_list = []
            for cat, group in film_stats.groupby('影片類別'):
                final_list.append(group)
                final_list.append(pd.DataFrame([{'影片類別': cat, '清單節目名稱': f'【{cat} 合計】', '觀看總數': group['觀看總數'].sum()}]))
            if final_list:
                st.table(pd.concat(final_list).reset_index(drop=True).style.format({'觀看總數': '{:,.0f}'}).apply(lambda x: [HIGHLIGHT_COLOR if "合計" in str(x['清單節目名稱']) else "" for _ in x], axis=1))

            # 稼動率分析
            st.divider()
            st.subheader("⏰ 時段稼動率分析")
            f_df['區段'] = f_df.apply(lambda x: get_slot_info(sel_site, x['假期'], x['時段小時'], x['分鐘']), axis=1)
            active_days = f_df.groupby(['交易日期', '假期']).size().reset_index()
            day_counts = active_days['假期'].value_counts().to_dict()
            slots_cfg = [("11:30-12:00", 2)] + [(f"{h:02d}:00-{(h+1):02d}:00", 4) for h in range(12, 20)] + [("20:00-21:00", 0)] if sel_site == "i-Ride TAIPEI" else [("09:30-10:00", 2)] + [(f"{h:02d}:00-{(h+1):02d}:00", 4) for h in range(10, 16)] + [("16:00-17:00", 4)]

            occ_list = []
            for s_name, s_qty in slots_cfg:
                for h_type in sel_hols:
                    d_num = day_counts.get(h_type, 0)
                    if d_num == 0: continue
                    actual_qty = s_qty
                    if sel_site == "i-Ride TAIPEI" and s_name == "20:00-21:00": actual_qty = 5 if h_type == "假日" else 4
                    denom = 20 * actual_qty * d_num
                    num = f_df[(f_df['區段'] == s_name) & (f_df['假期'] == h_type) & (~f_df['人次分類'].isin(['無視','VIP','不計人次']))]['觀看總數'].sum()
                    rate = (num / denom * 100) if denom > 0 else 0
                    occ_list.append({'時段': s_name, '類型': h_type, '稼動率': f"{rate:.2f}%"})
            if occ_list:
                st.table(pd.DataFrame(occ_list).pivot(index='時段', columns='類型', values='稼動率').fillna("-"))
