import streamlit as st
import pandas as pd
import io

# --- 1. 核心邏輯函數 ---
def process_data(df):
    def get_num_films(pname):
        if pd.isna(pname) or str(pname).strip() == '': return 0
        p = str(pname)
        return 2 if ('+' in p or '＋' in p) else 1

    def classify(row):
        pname = str(row['節目名稱']) if pd.notna(row['節目名稱']) else ""
        spec = str(row['品名規格']) if pd.notna(row['品名規格']) else ""
        cid = str(row['客戶編號']) if pd.notna(row['客戶編號']) else ""
        qty = row['交易數量'] if pd.notna(row['交易數量']) else 0
        rev = row['原幣含稅金額'] if pd.notna(row['原幣含稅金額']) else 0

        # 初始化
        res_rev = "商品收入"
        res_att_cat = "無視"
        res_att_val = 0
        res_esports_val = 0
        needs_confirm = False

        # --- A. 有節目名稱 (優先判斷票務) ---
        if pname != "":
            res_rev = "票務"
            n_films = get_num_films(pname)
            
            if any(x in spec for x in ['免費票', '券差額', '員工優惠票']):
                res_att_cat = "無視"
            elif 'VIP貴賓券核銷' in spec:
                res_att_cat = "校園優惠票" if cid == 'Z00054' else "VIP"
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
            res_att_val = n_films * qty

        # --- B. 無節目名稱 ---
        else:
            esports_k = ['LED體感','VR','4D劇院','飛行模擬器','極速賽艇','體感賽車','僵屍籠','殭屍籠']
            if any(k in spec for k in esports_k):
                res_rev = "電競館"; res_att_cat = "電競館"; res_esports_val = qty
            elif any(x in spec for x in ['門票分潤', '線上票券']):
                res_rev = "平台收入"
            elif any(x in spec for x in ['VIP貴賓券', '商品兌換券', '票券核銷']):
                res_rev = "無視"; rev = 0
            elif '團購兌換券' in spec:
                res_rev = "預售票"
            else:
                # 自動分類：判斷是否為巨人或妖怪
                if '進擊的巨人' in spec or '巨人' in spec: res_rev = "巨人周邊商品"
                elif '妖怪' in spec: res_rev = "妖怪周邊商品"
                else: res_rev = "周邊商品"
                
                if '票' in spec: needs_confirm = True # 攔截含票字新商品
        
        return pd.Series([res_rev, res_att_cat, res_att_val, res_esports_val, rev, needs_confirm])

    df[['營收分類', '人次分類', '計算人次', '電競人次', '含稅營收', '需確認']] = df.apply(classify, axis=1)
    return df

# --- 2. 網頁介面 ---
st.set_page_config(page_title="大飛數據對帳系統", layout="wide")
st.title("📊 大飛數據多人操作對帳系統")

uploaded_file = st.file_uploader("請上傳原始 Excel 或 CSV", type=['csv', 'xlsx'])

if uploaded_file:
    df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
    processed = process_data(df)
    
    col1, col2, col3 = st.columns(3)
    col1.metric("總計營收", f"{processed['含稅營收'].sum():,.0f}")
    col2.metric("i-Ride 總人次", f"{processed['計算人次'].sum():,.0f}")
    col3.metric("電競館總人次", f"{processed['電競人次'].sum():,.0f}")

    # 警告區
    pending = processed[processed['需確認'] == True]
    if not pending.empty:
        st.error(f"⚠️ 發現 {len(pending)} 筆含『票』字但無法自動歸類的項目，請檢查！")
        st.dataframe(pending[['品名規格', '客戶編號', '含稅營收']])

    st.subheader("分析結果總表")
    st.dataframe(processed)
    
    # 下載
    csv = processed.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 下載對齊後 CSV 報表", csv, "對齊後報表.csv", "text/csv")
