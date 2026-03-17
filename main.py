import streamlit as st
import pandas as pd
import io

# --- 1. 核心處理函數 ---
def process_data(df):
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
        reason = ""
        needs_confirm = False

        # 邏輯判斷開始
        if pname != "":
            res_rev = "票務"
            n_films = get_num_films(pname)
            res_att_val = n_films * qty
            reason = f"有節目名稱({n_films}部片)"
            
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
                res_att_cat = "待確認票種"
                needs_confirm = True
                reason = "有節目名稱但品名不符預設規則"
        else:
            esports_k = ['LED體感','VR','4D劇院','飛行模擬器','極速賽艇','體感賽車','僵屍籠','殭屍籠']
            if any(k in spec for k in esports_k):
                res_rev, res_att_cat, res_esports_val = "電競館", "電競館", qty
                reason = "品名符合電競館關鍵字"
            elif any(x in spec for x in ['門票分潤', '線上票券']):
                res_rev, reason = "平台收入", "品名符合平台分潤關鍵字"
            elif any(x in spec for x in ['VIP貴賓券', '商品兌換券', '票券核銷']):
                res_rev, rev, reason = "無視", 0, "品名為無視項目(不計營收)"
            elif '團購兌換券' in spec:
                res_rev, reason = "預售票", "品名符合預售票關鍵字"
            else:
                reason = "無節目名稱且非特定項目 -> 預設為商品"
                if '票' in spec:
                    needs_confirm = True
                    reason = "無節目名稱但品名含『票』字，需人工確認"

        return pd.Series([res_rev, res_att_cat, res_att_val, res_esports_val, rev, needs_confirm, reason])

    df[['營收分類', '人次分類', '計算人次', '電競人次', '含稅營收', '需確認', '系統判斷依據']] = df.apply(classify, axis=1)
    return df

# --- 2. 網頁介面 ---
st.set_page_config(page_title="大飛數據分析系統", layout="wide")
st.title("📊 大飛數據 - 多功能對帳系統")

uploaded_file = st.file_uploader("1. 上傳原始 Excel 或 CSV", type=['csv', 'xlsx'])

if uploaded_file:
    df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
    processed = process_data(df)
    
    # 月份篩選器 (側邊欄)
    st.sidebar.header("日期篩選")
    all_months = sorted(processed['月份'].unique().tolist())
    selected_months = st.sidebar.multiselect("選擇月份 (可多選)", all_months, default=all_months)
    
    # 根據篩選過濾數據
    filtered_df = processed[processed['月份'].isin(selected_months)]

    # --- 數據概覽看板 ---
    st.header(f"📈 數據概覽 ({', '.join(selected_months) if len(selected_months) < 3 else '多月份總和'})")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("總計營收", f"{filtered_df['含稅營收'].sum():,.0f}")
    c2.metric("i-Ride 總人次", f"{filtered_df['計算人次'].sum():,.0f}")
    c3.metric("電競館總人次", f"{filtered_df['電競人次'].sum():,.0f}")

    # --- 詳細統計表格 ---
    t1, t2 = st.columns(2)
    with t1:
        st.subheader("💰 營收類別合計")
        rev_sum = filtered_df.groupby('營收分類')['含稅營收'].sum().reset_index()
        st.table(rev_sum.style.format({'含稅營收': '{:,.0f}'}))
        
    with t2:
        st.subheader("👥 人次類別合計")
        # 合併計算 i-Ride 與 電競人次 (分開呈現)
        att_sum = filtered_df.groupby('人次分類')[['計算人次', '電競人次']].sum().reset_index()
        st.table(att_sum)

    # --- 異常攔截區 ---
    pending = filtered_df[filtered_df['需確認'] == True]
    if not pending.empty:
        st.error(f"⚠️ 發現 {len(pending)} 筆需人工確認的項目")
        st.write("請根據下方『系統判斷依據』決定如何調整邏輯：")
        st.dataframe(pending[['品名規格', '節目名稱', '客戶編號', '系統判斷依據', '含稅營收']])

    st.subheader("原始數據明細")
    st.dataframe(filtered_df)
