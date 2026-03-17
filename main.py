import streamlit as st
import pandas as pd
import datetime

# --- 0. 密碼驗證功能 ---
def check_password():
    def password_entered():
        if st.session_state["password"] == "Brogent": # 您可以自行修改此密碼
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    if "password_correct" not in st.session_state:
        st.text_input("請輸入公司內部授權密碼", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("密碼錯誤，請重新輸入", type="password", on_change=password_entered, key="password")
        st.error("😕 密碼不正確。")
        return False
    else:
        return True

# --- 開始網頁渲染 ---
st.set_page_config(page_title="大飛數據對帳系統", layout="wide")

if check_password():
    # 1. 台灣國定假日定義
    def get_holiday_type(date):
        if pd.isna(date): return "未知"
        d_str = date.strftime('%Y-%m-%d')
        holidays = [
            '2025-01-01', '2025-01-25', '2025-01-26', '2025-01-27', '2025-01-28', '2025-01-29', '2025-01-30', '2025-01-31', '2025-02-02',
            '2025-02-28', '2025-04-03', '2025-04-04', '2025-04-05', '2025-04-06', '2025-05-31', '2025-06-01', '2025-06-02',
            '2025-10-04', '2025-10-05', '2025-10-06', '2025-10-10', '2026-01-01', 
            '2026-02-16', '2026-02-17', '2026-02-18', '2026-02-19', '2026-02-20', '2026-02-21', '2026-02-22',
            '2026-02-28', '2026-03-01', '2026-03-02',
        ]
        if d_str in holidays or date.weekday() >= 5: return "假日"
        return "平日"

    # 2. 核心處理函數
    def process_data(df):
        if '交易日期' in df.columns:
            df['交易日期'] = pd.to_datetime(df['交易日期'], errors='coerce')
            df = df.dropna(subset=['交易日期']).copy()
            df['月份'] = df['交易日期'].dt.strftime('%Y/%m月')
            df['星期'] = df['交易日期'].dt.day_name().replace({
                'Monday':'星期一','Tuesday':'星期二','Wednesday':'星期三',
                'Thursday':'星期四','Friday':'星期五','Saturday':'星期六','Sunday':'星期日'
            })
            df['假期'] = df['交易日期'].apply(get_holiday_type)

        def get_num_films(pname):
            if pd.isna(pname) or str(pname).strip() == '': return 0
            return 2 if ('+' in str(pname) or '＋' in str(pname)) else 1

        def classify(row):
            pname = str(row['節目名稱']) if pd.notna(row['節目名稱']) else ""
            spec = str(row['品名規格']) if pd.notna(row['品名規格']) else ""
            cid = str(row['客戶編號']) if pd.notna(row['客戶編號']) else ""
            qty = row['交易數量'] if pd.notna(row['交易數量']) else 0
            rev = row['原幣含稅金額'] if pd.notna(row['原幣含稅金額']) else 0
            res_rev, res_att_cat, res_att_val, res_esports_val = "商品收入", "無視", 0, 0
            needs_confirm = False

            if pname != "":
                res_rev = "票務"
                n_films = get_num_films(pname)
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
                else: res_att_cat, needs_confirm = "待確認票種", True
            else:
                esports_k = ['LED體感','VR','4D劇院','飛行模擬器','極速賽艇','體感賽車','僵屍籠','殭屍籠']
                if any(k in spec for k in esports_k):
                    res_rev, res_att_cat, res_esports_val = "電競館", "電競館", qty
                elif any(x in spec for x in ['門票分潤', '線上票券']): res_rev = "平台收入"
                elif any(x in spec for x in ['VIP貴賓券', '商品兌換券', '票券核銷']): res_rev, rev = "無視", 0
                elif '團購兌換券' in spec: res_rev = "預售票"
                else:
                    if '票' in spec: needs_confirm = True
            return pd.Series([res_rev, res_att_cat, res_att_val, res_esports_val, rev, needs_confirm])

        df[['營收分類', '人次分類', '計算人次', '電競人次', '含稅營收', '需確認']] = df.apply(classify, axis=1)
        return df

    # --- 3. 網頁呈現 ---
    st.title("📊 大飛數據 - 多人操作對帳系統")
    uploaded_file = st.file_uploader("1. 上傳原始檔", type=['csv', 'xlsx'])

    if uploaded_file:
        df = pd.read_csv(uploaded_file, dtype={'客戶編號': str}) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, dtype={'客戶編號': str})
        processed = process_data(df)
        
        st.sidebar.header("數據篩選")
        sel_months = st.sidebar.multiselect("月份", sorted(processed['月份'].unique()), default=processed['月份'].unique())
        sel_holiday = st.sidebar.multiselect("日期類型", ["平日", "假日"], default=["平日", "假日"])
        
        f_df = processed[(processed['月份'].isin(sel_months)) & (processed['假期'].isin(sel_holiday))]

        st.header(f"📈 數據看板")
        c1, c2, c3 = st.columns(3)
        c1.metric("總計營收", f"{f_df['含稅營收'].sum():,.0f}")
        c2.metric("i-Ride 人次", f"{f_df['計算人次'].sum():,.0f}")
        c3.metric("電競館人次", f"{f_df['電競人次'].sum():,.0f}")

        t1, t2 = st.columns(2)
        with t1:
            st.subheader("💰 營收分類合計")
            st.table(f_df.groupby('營收分類')['含稅營收'].sum().reset_index().style.format({'含稅營收': '{:,.0f}'}))
        with t2:
            st.subheader("👥 人次分類合計")
            st.table(f_df.groupby('人次分類')[['計算人次', '電競人次']].sum().reset_index())

        pending = f_df[f_df['需確認'] == True]
        if not pending.empty:
            st.error(f"⚠️ 需確認項目 ({len(pending)} 筆)")
            st.dataframe(pending[['品名規格', '客戶編號', '含稅營收']])

        st.subheader("數據明細")
        st.dataframe(f_df)
        st.download_button("📥 下載報表", f_df.to_csv(index=False).encode('utf-8-sig'), "對齊報表.csv")
