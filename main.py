import streamlit as st
import pandas as pd
import numpy as np

# --- 0. 密碼驗證 ---
def check_password():
    def password_entered():
        if st.session_state["password"] == "dafei2026":
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

st.set_page_config(page_title="大飛數據對帳系統", layout="wide")

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
            pname, spec, cid = str(row['節目名稱']) if pd.notna(row['節目名稱']) else "", str(row['品名規格']), str(row['客戶編號'])
            qty, rev = row['交易數量'] if pd.notna(row['交易數量']) else 0, row['原幣含稅金額'] if pd.notna(row['原幣含稅金額']) else 0
            res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val = "商品收入", "無視", 0, 0, 0

            if pname != "":
                res_rev = "票務收入"
                res_watch_val = qty # 純交易數量
                n_films = 2 if ('+' in pname or '＋' in pname) else 1
                res_att_val = n_films * qty
                
                if any(x in spec for x in ['免費票', '券差額', '員工優惠票']): res_att_cat = "無視"
                elif 'VIP貴賓券核銷' in spec: res_att_cat = "校園優惠票" if cid == 'Z00054' else "VIP"
                elif any(x in spec for x in ['市民票', '愛心票', '學生票', '優惠套票', '成人票']):
                    res_att_cat = "親子卡" if ('成人票' in spec and cid.startswith('P')) else "散客"
                elif '平台通路票' in spec: res_att_cat = "平台"
                elif any(x in spec for x in ['企業優惠票', '團體優惠票']): res_att_cat = "團體"
                elif '股東券' in spec: res_att_cat = "股東"
                elif '貴賓體驗通行證核銷' in spec: res_att_cat = "VVIP"
                elif any(x in spec for x in ['團購兌換券展延', '團購兌換券核銷']): res_att_cat = "團購券"
            else:
                esports_k = ['LED體感','VR','4D劇院','飛行模擬器','極速賽艇','體感賽車','僵屍籠','殭屍籠']
                if any(k in spec for k in esports_k): res_rev, res_att_cat, res_esports_val = "電競館收入", "電競館", qty
                elif any(x in spec for x in ['門票分潤', '線上票券']): res_rev = "平台收入"
                elif any(x in spec for x in ['VIP貴賓券', '商品兌換券', '票券核銷']): res_rev = "無視"
                elif '團購兌換券' in spec: res_rev = "預售票收入"
                elif '票' in spec: res_rev = "票務收入"
                else:
                    if '巨人' in spec: res_rev = "巨人周邊商品"
                    elif '妖怪' in spec: res_rev = "妖怪周邊商品"
                    else: res_rev = "周邊商品"
            return pd.Series([res_rev, res_att_cat, res_att_val, res_esports_val, res_watch_val, rev, pname])

        df[['營收分類', '人次分類', '計算人次', '電競人次', '觀看總數', '含稅營收', '清單節目名稱']] = df.apply(classify, axis=1)
        df['統計用營收'] = df.apply(lambda x: 0 if x['營收分類'] == '無視' else x['含稅營收'], axis=1)
        return df

    st.title("📊 大飛數據分析系統")
    uploaded_file = st.file_uploader("1. 上傳原始檔", type=['csv', 'xlsx'])

    if uploaded_file:
        df = pd.read_csv(uploaded_file, dtype={'客戶編號': str}) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, dtype={'客戶編號': str})
        processed = process_data(df)
        
        st.sidebar.header("數據篩選")
        all_months = sorted(processed['月份'].unique())
        sel_months = st.sidebar.multiselect("選擇月份", all_months, default=all_months)
        sel_holiday = st.sidebar.multiselect("日期類型", ["平日", "假日"], default=["平日", "假日"])
        
        f_df = processed[(processed['月份'].isin(sel_months)) & (processed['假期'].isin(sel_holiday))].copy()

        # --- 頂部看板 ---
        st.header(f"📈 數據統計看板")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("總計營收 (不含無視)", f"{f_df['統計用營收'].sum():,.0f}")
        c2.metric("i-Ride 人次", f"{f_df['計算人次'].sum():,.0f}")
        c3.metric("影片觀看總數", f"{f_df['觀看總數'].sum():,.0f}")
        c4.metric("電競館人次", f"{f_df['電競人次'].sum():,.0f}")

        # --- 第一層：合計表 ---
        t1, t2 = st.columns(2)
        with t1:
            st.subheader("💰 營收分類合計")
            rev_table = f_df.groupby('營收分類')['含稅營收'].sum().reset_index()
            total_rev = f_df['統計用營收'].sum()
            rev_final = pd.concat([rev_table, pd.DataFrame([{'營收分類': '--- 合計(不含無視) ---', '含稅營收': total_rev}])])
            st.table(rev_final.style.format({'含稅營收': '{:,.0f}'}))
        
        with t2:
            st.subheader("👥 人次分類合計")
            att_table = f_df.groupby('人次分類')[['計算人次', '觀看總數', '電競人次']].sum().reset_index()
            att_final = pd.concat([att_table, pd.DataFrame([{'人次分類': '--- 合計 ---', '計算人次': f_df['計算人次'].sum(), '觀看總數': f_df['觀看總數'].sum(), '電競人次': f_df['電競人次'].sum()}])])
            st.table(att_final.style.format({'計算人次': '{:,.0f}', '觀看總數': '{:,.0f}', '電競人次': '{:,.0f}'}))

        # --- 第二層：影片觀看清單 ---
        st.divider()
        st.subheader("🎬 影片觀看人數統計 (按節目名稱)")
        # 僅統計有節目名稱的資料
        watch_df = f_df[f_df['清單節目名稱'] != ""].groupby('清單節目名稱')['觀看總數'].sum().reset_index()
        watch_df = watch_df.rename(columns={'清單節目名稱': '節目名稱', '觀看總數': '觀看人數(交易數量)'})
        watch_df = watch_df.sort_values(by='觀看人數(交易數量)', ascending=False)
        
        # 加入合計行
        watch_total = watch_df['觀看人數(交易數量)'].sum()
        watch_final = pd.concat([watch_df, pd.DataFrame([{'節目名稱': '--- 總觀看合計 ---', '觀看人數(交易數量)': watch_total}])])
        st.table(watch_final.style.format({'觀看人數(交易數量)': '{:,.0f}'}))

        st.divider()
        st.subheader("數據明細")
        st.dataframe(f_df)
        st.download_button("📥 下載篩選報表", f_df.to_csv(index=False).encode('utf-8-sig'), "篩選報表.csv")
