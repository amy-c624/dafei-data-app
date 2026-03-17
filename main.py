import streamlit as st
import pandas as pd
import os

# --- 1. 初始化邏輯庫 ---
LOGIC_FILE = 'user_logic.csv'

def load_logic():
    if os.path.exists(LOGIC_FILE):
        return pd.read_csv(LOGIC_FILE)
    return pd.DataFrame(columns=['品名規格', '歸類營收', '歸類人次'])

# --- 2. 核心處理邏輯 ---
def process_data(df, user_logic):
    # 建立一個快速查詢字典
    mapping = dict(zip(user_logic['品名規格'], user_logic['歸類營收']))
    att_mapping = dict(zip(user_logic['品名規格'], user_logic['歸類人次']))

    def classify(row):
        spec = str(row['品名規格'])
        pname = str(row['節目名稱']) if pd.notna(row['節目名稱']) else ""
        rev = row['原幣含稅金額'] if pd.notna(row['原幣含稅金額']) else 0
        qty = row['交易數量'] if pd.notna(row['交易數量']) else 0
        
        # A. 優先檢查使用者已定義過的邏輯
        if spec in mapping:
            return pd.Series([mapping[spec], att_mapping[spec], rev, False])
        
        # B. 自動判斷邏輯 (您之前的規則)
        res_rev = "商品收入"
        res_att = "無視"
        needs_confirm = False

        if pname != "":
            res_rev = "票務"
            res_att = "待確認" # 觸發確認
            needs_confirm = True
        elif '票' in spec:
            needs_confirm = True
        
        return pd.Series([res_rev, res_att, rev, needs_confirm])

    df[['歸類營收', '歸類人次', '含稅營收', '需確認']] = df.apply(classify, axis=1)
    return df

# --- 3. 網頁介面 ---
st.title("📊 大飛數據 - 具備學習功能的對帳系統")

user_logic = load_logic()
uploaded_file = st.file_uploader("上傳原始檔", type=['csv', 'xlsx'])

if uploaded_file:
    df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
    processed = process_data(df, user_logic)
    
    # --- 顯示需要確認的項目 ---
    pending = processed[processed['需確認'] == True]['品名規格'].unique()
    
    if len(pending) > 0:
        st.warning(f"🔎 發現 {len(pending)} 個新項目，請在下方完成歸類：")
        new_rules = []
        for item in pending:
            col1, col2, col3 = st.columns([2, 1, 1])
            col1.write(f"品名: **{item}**")
            choice_rev = col2.selectbox("營收歸類", ["票務", "商品收入", "電競館", "平台收入", "預售票", "無視"], key=f"rev_{item}")
            choice_att = col3.selectbox("人次歸類", ["散客", "平台", "團體", "VIP", "無視", "電競館"], key=f"att_{item}")
            new_rules.append({'品名規格': item, '歸類營收': choice_rev, '歸類人次': choice_att})
        
        if st.button("✅ 確認並更新數據庫"):
            updated_logic = pd.concat([user_logic, pd.DataFrame(new_rules)]).drop_duplicates('品名規格', keep='last')
            updated_logic.to_csv(LOGIC_FILE, index=False)
            st.success("學習成功！請重新整理頁面或重新觸發計算。")
            st.rerun()

    st.subheader("數據概覽")
    st.write(processed.groupby('歸類營收')['含稅營收'].sum())
    st.dataframe(processed)
