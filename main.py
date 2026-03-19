import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

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

st.set_page_config(page_title="i-Ride 營運智慧分析系統", layout="wide")
HIGHLIGHT_COLOR = "rgba(0, 123, 255, 0.4)" 

if check_password():
    # 1. 假期與公休日定義
    def get_holiday_type(date):
        if pd.isna(date): return "未知"
        d_str = date.strftime('%Y-%m-%d')
        holidays = ['2025-01-01', '2025-01-25', '2025-01-28', '2025-01-29', '2025-01-30', '2025-02-28', '2025-04-04', '2025-04-05', '2025-05-01', '2025-05-31', '2025-10-06', '2025-10-10']
        return "假日" if (d_str in holidays or date.weekday() >= 5) else "平日"

    def is_national_holiday(date):
        d_str = date.strftime('%Y-%m-%d')
        national_days = ['2025-01-01','2025-01-28','2025-01-29','2025-01-30','2025-02-28','2025-04-04','2025-04-05','2025-05-01','2025-05-31','2025-10-06','2025-10-10']
        return d_str in national_days

    # 2. 數據處理
    def process_data(df):
        df['交易日期'] = pd.to_datetime(df['交易日期'], errors='coerce')
        df = df.dropna(subset=['交易日期']).copy()
        df['月份'] = df['交易日期'].dt.strftime('%Y/%m月')
        df['假期'] = df['交易日期'].apply(get_holiday_type)
        df['時段小時'] = pd.to_datetime(df['場次時間'], format='%H:%M', errors='coerce').dt.hour
        
        def classify(row):
            pname, spec, cid = str(row.get('節目名稱','')).strip(), str(row.get('品名規格','')).strip(), str(row.get('會員卡號', row.get('客戶編號',''))).strip().upper()
            qty = pd.to_numeric(row.get('交易數量', 0), errors='coerce') or 0
            rev = pd.to_numeric(row.get('原幣含稅金額', 0), errors='coerce') or 0
            r_rev, r_cat, r_att, r_esp, r_wat = "周邊商品", "無視", 0, 0, 0
            if cid.startswith('P') and spec == "成人票": r_cat = "親子卡"
            elif cid == 'Z00054' and spec == "VIP貴賓券核銷": r_cat = "校園優惠票"
            elif any(x in spec for x in ['股東', 'VVIP', 'VIP', '團購', '平台', '團體', '企業']): r_cat = spec[:3]
            elif any(x in spec for x in ['市民', '愛心', '學生', '成人']): r_cat = "散客"
            if any(x in spec for x in ['免費', '員工', '券差額', '溢收', '核銷', '服務費']): r_cat = "無視"
            if pname != "" and pname != "nan":
                r_wat = qty
                n_f = 2 if ('+' in pname or '＋' in pname) else 1
                r_att = n_f * qty
            else:
                if any(k in spec for k in ['LED','VR','4D','飛行','賽艇','賽車','僵屍']): r_cat, r_esp = "電競館", qty
                if r_cat != "電競館": r_att, r_wat = 0, 0
            if spec in ['商品兌換券', '票券核銷']: r_rev = "無視"
            elif any(x in spec for x in ['分潤', '線上票']): r_rev = "平台收入"
            elif (pname != "" and pname != "nan") or ("票" in spec) or (r_cat not in ["無視", "周邊商品", "電競館"]): r_rev = "票務收入"
            elif r_cat == "電競館": r_rev = "電競館收入"
            else: r_rev = "周邊商品"
            return pd.Series([r_rev, r_cat, r_att, r_esp, r_wat, rev, pname])

        df[['營收分類', '人次分類', '計算人次', '電競人次', '觀看總數', '含稅營收', '清單名稱']] = df.apply(classify, axis=1)
        df['統計用營收'] = df.apply(lambda x: 0 if x['營收分類'] == '無視' else x['含稅營收'], axis=1)
        return df

    file = st.file_uploader("1. 上傳原始檔", type=['csv', 'xlsx'])
    if file:
        df_raw = pd.read_csv(file, dtype=str) if file.name.endswith('.csv') else pd.read_excel(file, dtype=str)
        proc = process_data(df_raw)
        
        st.sidebar.header("🏢 營運與標籤設定")
        with st.sidebar.form("cfg"):
            site = st.selectbox("據點", ["台北店", "高雄店"])
            off_d = st.date_input("高雄公休", value=[])
            st.form_submit_button("🔘 更新設定")

        films = sorted([f for f in proc['清單名稱'].unique() if f != "" and f != "nan"])
        with st.sidebar.form("tag"):
            tag_map = {f: st.text_input(f, value="未分類", key=f"k_{f}") for f in films}
            st.form_submit_button("🔘 更新標籤")

        proc['標籤'] = proc['清單名稱'].map(tag_map)
        proc.loc[proc['標籤'] == '無視', ['計算人次', '觀看總數']] = 0
        
        mths = st.sidebar.multiselect("月份", sorted(proc['月份'].unique()), default=proc['月份'].unique())
        hols = st.sidebar.multiselect("類型", ["平日", "假日"], default=["平日", "假日"])
        f_df = proc[(proc['月份'].isin(mths)) & (proc['假期'].isin(hols))].copy()
        f_df_u = f_df[f_df['人次分類'] != '無視']
        f_df_f = f_df[~f_df['人次分類'].isin(['無視', 'VIP'])]

        # Capacity
        def get_cap(df_in, site_n, off_dt):
            dts = df_in['交易日期'].dt.date.unique()
            res = []
            for d in dts:
                if site_n == "高雄店" and d in off_dt and not is_national_holiday(d): continue
                rng = pd.date_range(f"{d} 11:30", f"{d} 20:45", freq='15min') if site_n == "台北店" else pd.date_range(f"{d} 09:30", f"{d} 16:45", freq='15min')
                is_h = True if (site_n=="台北店" and get_holiday_type(d)=="假日") else False
                for s in rng:
                    c = 40 if (site_n=="台北店" and s.hour==20 and s.minute==45 and is_h) else 20
                    res.append({'時段小時': s.hour, '容量': c, '假期': get_holiday_type(d)})
            return pd.DataFrame(res)

        cap_df = get_cap(f_df, site, off_d)

        # 指標
        st.header(f"📊 {site} 分析報告")
        c = st.columns(4)
        c[0].metric("總計營收", f"{f_df['統計用營收'].sum():,.0f}")
        c[1].metric("i-Ride人次", f"{f_df_f['計算人次'].sum():,.0f}")
        c[2].metric("總觀看(含VIP)", f"{f_df_u['觀看總數'].sum():,.0f}")
        c_s = cap_df['容量'].sum() if not cap_df.empty else 0
        c[3].metric("稼動率", f"{(f_df_u['觀看總數'].sum()/c_s*100):.2f}%" if c_s>0 else "0%")

        def style_fn(x, total_len):
            # 判斷是否為合計列：最後一行 OR 欄位包含「小計」或「合計」
            is_tot = (x.name == total_len - 1) or any("小計" in str(v) or "合計" in str(v) for v in x.values)
            return [f'background-color: {HIGHLIGHT_COLOR}; font-weight: bold' if is_tot else '' for _ in x]

        st.divider()
        t1, t2 = st.columns(2)
        with t1:
            st.subheader("💰 營收分類")
            r_t = f_df.groupby('營收分類')['含稅營收'].sum().reset_index()
            r_f = pd.concat([r_t, pd.DataFrame([{'營收分類':'合計','含稅營收':f_df['統計用營收'].sum()}])]).reset_index(drop=True)
            # 修正：指定只對數字欄位格式化
            st.table(r_f.style.format({'含稅營收': '{:,.0f}'}).apply(style_fn, total_len=len(r_f), axis=1))
        with t2:
            st.subheader("👥 人次分類")
            a_t = f_df.groupby('人次分類')[['計算人次','觀看總數','電競人次']].sum().reset_index()
            a_f = pd.concat([a_t, pd.DataFrame([{'人次分類':'合計','計算人次':f_df_f['計算人次'].sum(),'觀看總數':f_df_f['觀看總數'].sum(),'電競人次':f_df['電競人次'].sum()}])]).reset_index(drop=True)
            # 修正：指定對多個數字欄位格式化
            st.table(a_f.style.format({'計算人次': '{:,.0f}', '觀看總數': '{:,.0f}', '電競人次': '{:,.0f}'}).apply(style_fn, total_len=len(a_f), axis=1))

        st.divider()
        st.subheader("🎬 影片組合統計")
        f_s = f_df_f[f_df_f['清單名稱'] != ""].groupby(['標籤','清單名稱']).agg({'計算人次':'sum','觀看總數':'sum'}).reset_index()
        f_c = f_s.groupby('標籤').agg({'計算人次':'sum','觀看總數':'sum'}).reset_index()
        f_c['清單名稱'] = "--- 類別小計 ---"
        f_fin = pd.concat([f_s, f_c]).sort_values(['標籤','清單名稱'], ascending=[True, False]).reset_index(drop=True)
        # 修正：格式化指定欄位
        st.table(f_fin.style.format({'計算人次': '{:,.0f}', '觀看總數': '{:,.0f}'}).apply(style_fn, total_len=len(f_fin), axis=1))

        st.divider()
        st.subheader("⏰ 時段稼動率")
        if not cap_df.empty:
            c_g = cap_df.groupby(['時段小時','假期'])['容量'].sum().reset_index()
            a_g = f_df_u.groupby(['時段小時','假期'])['觀看總數'].sum().reset_index()
            m_g = pd.merge(c_g, a_g, on=['時段小時','假期'], how='left').fillna(0)
            m_g['稼動率'] = (m_g['觀看總數']/m_g['容量']*100).map('{:.2f}%'.format)
            piv = m_g.pivot(index='時段小時', columns='假期', values='稼動率').fillna("-")
            piv.index = [f"{h:02d}:00-{h+1:02d}:00" for h in piv.index]
            st.table(piv)
