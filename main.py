import streamlit as st
import pandas as pd
import datetime

# --- 0. 密碼驗證功能 ---
def check_password():
    """如果密碼正確，則回傳 True"""
    def password_entered():
        # --- 在這裡設定您的專屬密碼 ---
        if st.session_state["password"] == "Brogent42646262": 
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # 驗證後刪除輸入內容以防外流
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # 第一次進入網頁，顯示輸入框
        st.text_input(
            "請輸入公司內部授權密碼", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        # 密碼錯誤，再次顯示輸入框
        st.text_input(
            "密碼錯誤，請重新輸入", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 密碼不正確，請聯繫管理員。")
        return False
    else:
        # 密碼正確
        return True

# --- 開始網頁渲染 ---
st.set_page_config(page_title="大飛數據對帳系統", layout="wide")

if check_password():
    # --- 以下是原本的核心程式邏輯，只有密碼正確才會執行 ---
    
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
            reason, needs_confirm = "", False

            if pname != "":
                res_rev = "票務"
                n_films = get_num_films(pname)
                res_att_val = n_films * qty
                if any(x in spec for x in ['免費票', '券差額', '員工優惠票']): res_att_cat = "無視"
                elif 'VIP貴賓券核銷' in spec: res_att_cat = "校園優惠票" if cid == 'Z00054' else "VIP"
                elif any(x in spec for x in ['市民票', '愛心票', '學生票', '優惠套票', '成人票']):
                    res_att_cat = "親子卡" if ('成人票' in spec and cid.startswith('P')) else "散客"
                elif
