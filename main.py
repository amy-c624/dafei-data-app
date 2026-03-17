import streamlit as st
import pandas as pd
import numpy as np

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

st.set_page_config(page_title="i-Ride 營收數據分析", layout="wide")

# 設定醒目顏色
HIGHLIGHT_COLOR = "rgba(0, 123, 255, 0.4)" 

if check_password():
    # 1. 假期定義
    def get_holiday_type(date):
        if pd.isna(date): return "未知"
        d_str = date.strftime('%Y-%m-%d')
        holidays = ['2025-01-01', '2025-01-25', '2025-01-26', '2025-01-27', '2025-01-28', '2025-01-29', '2025-01-30', '2025-01-31', '2025-02-02', '2025-02-28', '2025-04-03', '2025-04-04', '2025-04-05', '2025-04-06', '2025-05-31', '2025-06-01', '2025-06-02', '2025-10-04', '2025-10-05', '2025-10-06', '2025-10-10', '2026-01-01', '2026-02-16', '2026-02-17', '2026-02-18', '2026-02-19', '2026-02-20', '2026-02-21', '2026-02-22', '2026-02-28', '2026-03-01', '2026-03-02']
        return "假日" if (d_str in holidays or date.weekday() >= 5) else "平日"

    # 2. 核心處理函數
    def process_data(df):
        df['交易日期'] = pd.to_datetime(df['交易日期'], errors='coerce')
        df = df.dropna(subset=['交易日期']).copy()
        df['月份'] = df['交易日期'].dt.strftime('%Y/%m月')
        df['假期'] = df['交易日期'].apply(get_holiday_type)

        def classify(row):
            pname = str(row.get('節目名稱', '')).strip()
            spec = str(row.get('品名規格', '')).strip()
            # 優先讀取「會員卡號」，若無則讀取「客戶編號」
            cid = str(row.get('會員卡號', row.get('客戶編號', ''))).strip().upper()
            
            qty = pd.to_numeric(row.get('交易數量', 0), errors='coerce') or 0
            rev = pd.to_numeric(row.get('原幣含稅金額', 0), errors='coerce') or 0
            
            res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val = "商品收入", "無視", 0, 0, 0

            # --- [最新正名邏輯] 人次分類 ---
            
            # 1. 親子卡：會員 P 開頭 且 品名精確等於 "成人票"
            if cid.startswith('P') and spec == "成人票":
                res_att_cat = "親子卡"
            
            # 2. 校園票：會員精確等於 Z00054 且 品名精確等於 "VIP貴賓券核銷"
            elif cid == 'Z00054' and spec == "VIP貴賓券核銷":
                res_att_cat = "校園優惠票"
                
            # 3. 其他分類 (包含判斷)
            elif any(x in spec for x in ['股東券', '股東票']): res_att_cat = "股東"
            elif '貴賓體驗通行證核銷' in spec: res_att_cat = "VVIP"
            elif 'VIP貴賓券核銷' in spec: res_att_cat = "VIP" # 非 Z00054 的會掉到這裡
            elif any(x in spec for x in ['團購兌換券展延', '團購兌換券核銷']): res_att_cat = "團購券"
            elif '平台通路票' in spec: res_att_cat = "平台"
            elif any(x in spec for x in ['企業優惠票', '團體優惠票']): res_att_cat = "團體"
            elif any(x in spec for x in ['市民票', '愛心票', '學生票', '優惠套票', '成人票']): res_att_cat = "散客"
            
            # 人次無視清單 (免費/券差額/員工等)
            if any(x in spec for x in ['免費票', '員工票', '券差額', '商品兌換券', '票務核銷']): 
                res_att_cat = "無視"

            # --- 營收分類 ---
            if pname != "" and pname != "nan":
                res_rev, res_watch_val = "票務收入", qty
                n_films = 2 if ('+' in pname or '＋' in pname) else 1
                res_att_val = n_films * qty
            else:
                # 判斷電競
                esports_k = ['LED體感','VR','4D劇院','飛行模擬器','極速賽艇','體感賽車','僵屍籠','殭屍籠']
                if any(k in spec for k in esports_k): 
                    res_rev, res_att_cat, res_esports_val = "電競館收入", "電競館", qty
                # 營收分類判定
                elif any(x in spec for x in ['門票分潤', '線上票券']): 
                    res_rev = "平台收入"
                elif any(x in spec for x in ['VIP貴賓券', '商品兌換券', '票券核銷']): 
                    res_rev = "無視"
                elif '團購兌換券' in spec: 
                    res_rev = "預售票收入"
                elif '票' in spec: 
                    res_rev = "票務收入"
                else:
                    # 周邊商品邏輯
                    if '巨人' in spec: 
                        res_rev = "巨人周邊商品"
                    elif spec in ['妖怪森林公仔', '妖怪森林公仔-煞', '妖怪森林外傳', '妖怪森林盲盒']:
                        res_rev = "妖怪周邊商品"
                    else:
                        res_rev = "周邊商品"
                
                # 若無節目名稱且非電競，人次與觀看歸零
                if res_att_cat != "電競館":
                    res_att_val, res_watch_val = 0, 0
                    if res_rev != "票務收入": res_att_cat = "無視"

            return pd.Series([res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val, rev, pname])

        df[['營收分類', '人次分類', '計算人次', '電競人次', '觀看總數', '含稅營收', '清單節目名稱']] = df.apply(classify, axis=1)
        df['統計用營收'] = df.apply(lambda x: 0 if x['營收分類'] == '無視' else x['含稅營收'], axis=1)
        return df

    # --- 介面呈現 ---
    uploaded_file = st.file_uploader("1. 上傳原始檔 (CSV 或 Excel)", type=['csv', 'xlsx'])

    if uploaded_file:
        df = pd.read_csv(uploaded_file, dtype={'會員卡號': str, '客戶編號': str}) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, dtype={'會員卡號': str, '客戶編號': str})
        
        processed = process_data(df)
        
        st.sidebar.header("📅 數據篩選")
        all_months = sorted(processed['月份'].unique())
        sel_months = st.sidebar.multiselect("選擇月份", all_months, default=all_months)
        sel_holiday = st.sidebar.multiselect("日期類型", ["平日", "假日"], default=["平日", "假日"])
        
        f_df = processed[(processed['月份'].isin(sel_months)) & (processed['假期'].isin(sel_holiday))].copy()

        st.header(f"📊 營收統計分析")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("總計營收", f"{f_df['統計用營收'].sum():,.0f}")
        c2.metric("i-Ride 人次", f"{f_df['計算人次'].sum():,.0f}")
        c3.metric("影片觀看總數", f"{f_df['觀看總數'].sum():,.0f}")
        c4.metric("電競館人次", f"{f_df['電競人次'].sum():,.0f}")

        def apply_style(x, df_len):
            return [f'background-color: {HIGHLIGHT_COLOR}; font-weight: bold' if x.name == df_len-1 else '' for _ in x]

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
                '人次分類': '合計(不含無視)', 
                '計算人次': f_df['計算人次'].sum(), '觀看總數': f_df['觀看總數'].sum(), '電競人次': f_df['電競人次'].sum()
            }])]).reset_index(drop=True)
            st.table(att_final.style.format({'計算人次': '{:,.0f}', '觀看總數': '{:,.0f}', '電競人次': '{:,.0f}'}).apply(apply_style, df_len=len(att_final), axis=1))

        st.divider()
        st.subheader("📄 數據明細")
        st.dataframe(f_df)
