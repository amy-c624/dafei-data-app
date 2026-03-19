import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

# --- 0. 驗證與基礎設定 ---
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
        # (此處建議保留您之前的完整 holidays_2025/2026 清單)
        holidays = ['2025-01-01', '2025-02-28'] # 範例
        return "假日" if (d_str in holidays or date.weekday() >= 5) else "平日"

    # 2. 核心分類邏輯
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

            # --- [A] 分類判定 ---
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

            # --- [B] 原始人次計算 ---
            if pname != "" and pname != "nan":
                res_watch_val = qty
                n_films = 2 if ('+' in pname or '＋' in pname) else 1
                res_att_val = n_films * qty
                if res_att_cat == "不計人次": res_att_cat = "無視"
            else:
                if any(k in spec for k in ['VR','體感','賽車','僵屍']): 
                    res_att_cat = "電競館"
                    res_esports_val = qty
                    res_att_val = qty

            # --- [C] 營收細分 ---
            if spec in ['商品兌換券', '票券核銷']: res_rev = "無視"
            elif any(x in spec for x in ['門票分潤', '線上票券']): res_rev = "平台收入"
            elif spec == '團購兌換券': res_rev = "預售票收入"
            elif '巨人' in spec: res_rev = "巨人周邊商品"
            elif '妖怪' in spec: res_rev = "妖怪周邊商品"
            elif (pname != "" and pname != "nan") or ("票" in spec) or ("券" in spec): res_rev = "票務"
            else: res_rev = "周邊商品"

            return pd.Series([res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val, rev, pname])

        df[['營收分類', '人次分類', '計算人次', '電競人次', '觀看總數', '含稅營收', '清單節目名稱']] = df.apply(classify, axis=1)
        return df

    # --- 3. 稼動率區段定義 ---
    def get_slot_info(site, holiday_type, hour, minute):
        # 建立區段名稱與該時段場次數
        if site == "台北店":
            if hour == 11 and minute >= 30: return "11:30-12:00", 2
            if 12 <= hour < 20: return f"{hour:02d}:00-{(hour+1):02d}:00", 4
            if hour == 20: 
                num = 5 if holiday_type == "假日" else 4
                return "20:00-21:00", num
        else: # 高雄店
            if hour == 9 and minute >= 30: return "09:30-10:00", 2
            if 10 <= hour < 16: return f"{hour:02d}:00-{(hour+1):02d}:00", 4
            if hour == 16: return "16:00-17:00", 4
        return None, 0

    uploaded_file = st.file_uploader("1. 上傳數據文件", type=['csv', 'xlsx'])

    if uploaded_file:
        df_raw = pd.read_csv(uploaded_file, dtype=str) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, dtype=str)
        processed = process_data(df_raw)
        
        # --- 左側 SideBar Form (一鍵更新) ---
        with st.sidebar.form("global_settings"):
            st.header("⚙️ 營運設定")
            sel_site = st.selectbox("營運據點", ["台北店", "高雄店"])
            
            # 多選公休日
            all_dates = sorted(processed['交易日期'].dt.date.unique())
            off_days = st.multiselect("選擇公休日 (不計分母)", all_dates)
            
            sel_months = st.multiselect("月份篩選", sorted(processed['月份'].unique()), default=processed['月份'].unique())
            sel_holidays = st.multiselect("平假日篩選", ["平日", "假日"], default=["平日", "假日"])
            
            st.divider()
            st.write("🎬 影片分類標籤")
            unique_f = sorted([f for f in processed['清單節目名稱'].unique() if f not in ["", "nan"]])
            tag_map = {f: st.text_input(f, value="未分類", key=f) for f in unique_f}
            
            submitted = st.form_submit_button("🔥 確認更新並計算數據")

        # --- 資料動態處理 ---
        # 1. 標籤與無視處理
        processed['影片類別'] = processed['清單節目名稱'].map(tag_map)
        if submitted:
            ign_mask = processed['影片類別'] == "無視"
            processed.loc[ign_mask, ['計算人次', '觀看總數']] = 0
            processed.loc[ign_mask, '人次分類'] = "無視"

        # 2. 篩選與排除公休日
        f_df = processed[
            (processed['月份'].isin(sel_months)) & 
            (processed['假期'].isin(sel_holidays)) &
            (~processed['交易日期'].dt.date.isin(off_days))
        ].copy()

        # --- 右側呈現 ---
        st.header(f"📊 {sel_site} 營運分析報告")
        
        # 1. 影片觀看分析 (交易數量 + 類別合計)
        st.subheader("🎬 影片觀看分析 (以交易數量計)")
        film_df = f_df[f_df['清單節目名稱'] != ""].groupby(['影片類別', '清單節目名稱'])['觀看總數'].sum().reset_index()
        
        # 插入類別合計行
        styled_film_list = []
        for cat, group in film_df.groupby('影片類別'):
            styled_film_list.append(group)
            cat_total = pd.DataFrame([{'影片類別': cat, '清單節目名稱': f'--- {cat} 合計 ---', '觀看總數': group['觀看總數'].sum()}])
            styled_film_list.append(cat_total)
        
        full_film_df = pd.concat(styled_film_list).reset_index(drop=True)
        st.table(full_film_df.style.apply(lambda x: [HIGHLIGHT_COLOR if "合計" in str(x['清單節目名稱']) else "" for _ in x], axis=1))

        # 2. 稼動率分析
        st.divider()
        st.subheader("⏰ 時段稼動率分析")
        
        # 計算區段場次
        f_df['區段'], _ = zip(*f_df.apply(lambda x: get_slot_info(sel_site, x['假期'], x['時段小時'], x['分鐘']), axis=1))
        
        # 建立分母表 (依據篩選後的天數)
        active_days = f_df.groupby(['交易日期', '假期']).size().reset_index()[['交易日期', '假期']]
        day_counts = active_days['假期'].value_counts().to_dict() # 平日幾天, 假日幾天
        
        # 產生該店所有可能的區段
        slots_config = []
        if sel_site == "台北店":
            slots_config = [("11:30-12:00", 2)] + [(f"{h:02d}:00-{(h+1):02d}:00", 4) for h in range(12, 20)] + [("20:00-21:00", 0)]
        else:
            slots_config = [("09:30-10:00", 2)] + [(f"{h:02d}:00-{(h+1):02d}:00", 4) for h in range(10, 16)] + [("16:00-17:00", 4)]

        occ_rows = []
        for slot_name, base_cap in slots_config:
            for h_type in sel_holidays:
                days = day_counts.get(h_type, 0)
                if days == 0: continue
                
                # 特殊處理台北末場
                actual_base = base_cap
                if sel_site == "台北店" and slot_name == "20:00-21:00":
                    actual_base = 5 if h_type == "假日" else 4
                
                denom = 20 * actual_base * days
                num = f_df[(f_df['區段'] == slot_name) & (f_df['假期'] == h_type) & (~f_df['人次分類'].isin(['無視','VIP','不計人次']))]['觀看總數'].sum()
                rate = (num / denom * 100) if denom > 0 else 0
                occ_rows.append({'時段區間': slot_name, '類型': h_type, '稼動率': f"{rate:.2f}%"})

        if occ_rows:
            occ_final = pd.DataFrame(occ_rows).pivot(index='時段區間', columns='類型', values='稼動率').fillna("-")
            st.table(occ_final)
