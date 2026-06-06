##### Shioaji 權勢策略_台指期 0606 加入換倉成本 & 關卡版本(Findmind抓取歷史結算價)
import shioaji as sj
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from datetime import datetime, timedelta, time, date
import requests
import os
import io
import sys
import calendar
from FinMind.data import DataLoader

# ==========================================
# --- 核心邏輯設定區 (建議由環境變數讀取) ---
# ==========================================
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK", "你的_DISCORD_WEBHOOK_URL")
TG_TOKEN = os.getenv("TG_TOKEN", "你的_TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "你的_TG_CHAT_ID")
API_KEY = os.getenv("API_KEY", "你的_API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY", "你的_SECRET_KEY")
FINDMIND_TOKEN = os.getenv("FINDMIND_TOKEN", "你的_FINDMIND_TOKEN")

# ==========================================
# --- 功能函數區 ---
# ==========================================

def get_settlement_day(year: int, month: int) -> date:
    """台指期結算日：每月第三個星期三"""
    cal = calendar.monthcalendar(year, month)
    wednesdays = [w[calendar.WEDNESDAY] for w in cal if w[calendar.WEDNESDAY] != 0]
    return date(year, month, wednesdays[2])

def get_target_contract_month(dt: date) -> str:
    """計算目標合約月份：每個月第三個禮拜三(包含)使用當月，之後使用次月"""
    sd = get_settlement_day(dt.year, dt.month)
    if dt <= sd:
        return dt.strftime('%Y%m')
    else:
        # 下個月
        nm = dt.replace(day=28) + timedelta(days=7)
        return nm.strftime('%Y%m')

def get_recent_settlement_days(n: int) -> list[date]:
    """取得最近 n 個結算日（不超過今日），由舊到新排序"""
    today = date.today()
    results: list[date] = []
    year, month = today.year, today.month

    while len(results) < n:
        sd = get_settlement_day(year, month)
        if sd <= today:
            results.append(sd)
        month -= 1
        if month == 0:
            year -= 1
            month = 12
    return sorted(results)

def get_trading_date(ts):
    """計算交易日：15:00 後歸為下一交易日 (週五夜盤歸週一)"""
    if ts.time() >= time(15, 0):
        days_to_add = 3 if ts.weekday() == 4 else 1
        return (ts + timedelta(days=days_to_add)).date()
    elif ts.time() <= time(5, 0):
        return ts.date()
    else:
        return ts.date()

def upload_memory_to_discord(webhook_url, img_bytes, filename="tx_daily_report.png"):
    """將記憶體中的圖片數據傳送到 Discord 並獲取連結"""
    try:
        payload = {"content": f"📊 TX Daily Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}"}
        # 包裝記憶體數據
        files = {"file": (filename, img_bytes, "image/png")}
        r = requests.post(webhook_url, data=payload, files=files)
        
        if r.status_code == 200:
            return r.json()['attachments'][0]['url']
        else:
            print(f"❌ Discord 上傳失敗: {r.status_code}")
            return None
    except Exception as e:
        print(f"❌ Discord 連線異常: {e}")
        return None

def send_telegram_with_photo_url(token, chat_id, message, photo_url):
    """透過圖片網址傳送 Telegram 訊息"""
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    payload = {
        "chat_id": chat_id,
        "photo": photo_url,
        "caption": message,
        "parse_mode": "Markdown"
    }
    try:
        r = requests.post(url, data=payload)
        return r.json()
    except Exception as e:
        print(f"❌ Telegram 發送失敗: {e}")
        return None

# ==========================================
# --- 主程式邏輯 ---
# ==========================================
now = datetime.now()
print(f"--- 任務啟動: {now} ---")

# --- 週末檢查 (週一=0, ..., 週五=4, 週六=5, 週日=6) ---
if now.weekday() >= 5:
    print(f"⚠️ 今日為 {now.strftime('%A')} (週末)，程式停止執行。")
    sys.exit()

# 1. Shioaji 登入
api = sj.Shioaji()
api.login(api_key=API_KEY, secret_key=SECRET_KEY)

# --- 資料抓取 (分兩部分) ---
# 1. 歷史 K 棒: 使用 Findmind API
print("正在從 Findmind 抓取歷史資料...")
now_date = now.date()
start_date_fm = (now_date - timedelta(days=110)).strftime('%Y-%m-%d')

# 現在時間小於 15:00, end_date_fm 請用昨天; 大於等於 15:00, end_date_fm 請用今天
if now.time() < time(15, 0):
    end_date_fm = (now_date - timedelta(days=1)).strftime('%Y-%m-%d')
else:
    end_date_fm = now_date.strftime('%Y-%m-%d')

fm_loader = DataLoader()
fm_loader.login_by_token(api_token=FINDMIND_TOKEN)
df_fm_raw = fm_loader.taiwan_futures_daily(
    futures_id="TX",
    start_date=start_date_fm,
    end_date=end_date_fm
)

if not df_fm_raw.empty:
    # 邏輯過濾
    # (5) trading_session = position
    df_fm = df_fm_raw[df_fm_raw['trading_session'] == 'position'].copy()
    
    # (6) contract_date: 每個月第三個禮拜三(包含), 請使用當月. 每個月第三個禮拜三之後請用次月
    df_fm['date_dt'] = pd.to_datetime(df_fm['date'])
    df_fm['target_contract'] = df_fm['date_dt'].apply(lambda x: get_target_contract_month(x.date()))
    df_fm = df_fm[df_fm['contract_date'] == df_fm['target_contract']].copy()
    
    # (4) 收盤價(結算價): if settlement_price != 0 請使用 settlement_price, else close
    df_fm['close_price'] = np.where(df_fm['settlement_price'] != 0, df_fm['settlement_price'], df_fm['close'])
    
    # 格式轉換
    df_fm = df_fm[['date', 'open', 'max', 'min', 'close_price', 'volume']].copy()
    df_fm.rename(columns={'close_price': 'close'}, inplace=True)
    df_fm['date'] = pd.to_datetime(df_fm['date'])
else:
    df_fm = pd.DataFrame()

# 2. 當日 K 棒: 使用 Shioaji API
print("正在從 Shioaji 抓取當日資料...")
start_date = (now - timedelta(days=3)).strftime('%Y-%m-%d')
end_date = now.strftime('%Y-%m-%d')
contract = api.Contracts.Futures.TXF.TXFR1
kbars = api.kbars(contract, start=start_date, end=end_date)

df_sj_raw = pd.DataFrame({**kbars})
if not df_sj_raw.empty:
    df_sj_raw['ts'] = pd.to_datetime(df_sj_raw['ts'])
    df_sj_raw['trading_date'] = df_sj_raw['ts'].apply(get_trading_date)
    last_trading_date = df_sj_raw['trading_date'].max()

    # 雙重過濾
    is_last_td = (df_sj_raw['trading_date'] == last_trading_date)
    is_day_session = (df_sj_raw['ts'].dt.time >= time(8, 45)) & (df_sj_raw['ts'].dt.time <= time(13, 45))
    
    now_time = now.time()
    if time(8, 45) <= now_time <= time(13, 45):
        current_target_mask = (df_sj_raw['ts'].dt.time == time(8, 46))
    elif time(13, 46) <= now_time <= time(15, 0):
        current_target_mask = is_day_session
    elif time(15, 1) <= now_time or now_time <= time(8, 44):
        current_target_mask = (df_sj_raw['ts'].dt.time == time(15, 1))
    else:
        current_target_mask = is_day_session

    df_sj_filtered = df_sj_raw[
        (~is_last_td & is_day_session) | 
        (is_last_td & current_target_mask)
    ].copy()

    # 聚合為日線
    df_sj_daily = df_sj_filtered.groupby('trading_date').agg({
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum'
    }).reset_index()

    df_sj_daily.rename(columns={'trading_date': 'date', 'High': 'max', 'Low': 'min', 'Open': 'open', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
    df_sj_daily['date'] = pd.to_datetime(df_sj_daily['date'])
else:
    df_sj_daily = pd.DataFrame()

# 合併資料
df = pd.concat([df_fm, df_sj_daily], ignore_index=True)
df = df.drop_duplicates(subset=['date'], keep='last').sort_values('date').reset_index(drop=True)

# 確保只留近 100 天
df = df.tail(100).reset_index(drop=True)

# 2. 技術指標計算
df['20MA'] = df['close'].rolling(window=20).mean()
std = df['close'].rolling(window=20).std()
df['Upper'] = df['20MA'] + (std * 2)
df['Lower'] = df['20MA'] - (std * 2)

# RSI (N=3, N=6)
delta = df['close'].diff()
gain = delta.where(delta > 0, 0)
loss = -delta.where(delta < 0, 0)

# RSI 3
window3 = 3
avg_gain3 = gain.ewm(alpha=1/window3, min_periods=window3, adjust=False).mean()
avg_loss3 = loss.ewm(alpha=1/window3, min_periods=window3, adjust=False).mean()
df['RSI3'] = 100 - (100 / (1 + (avg_gain3 / avg_loss3)))

# RSI 6
window6 = 6
avg_gain6 = gain.ewm(alpha=1/window6, min_periods=window6, adjust=False).mean()
avg_loss6 = loss.ewm(alpha=1/window6, min_periods=window6, adjust=False).mean()
df['RSI6'] = 100 - (100 / (1 + (avg_gain6 / avg_loss6)))

# MACD (保留計算但繪圖移除)
ema12 = df['close'].ewm(span=12, adjust=False).mean()
ema26 = df['close'].ewm(span=26, adjust=False).mean()
df['MACD_Hist'] = (ema12 - ema26) - (ema12 - ema26).ewm(span=9, adjust=False).mean()

# --- 權勢策略指標計算 ---
df['RL'] = np.nan
df['BL'] = np.nan
df['Signal'] = 0
df['Message'] = "⚖️【中性觀望】"
df['prev_close'] = df['close'].shift(1)
df.loc[0, 'RL'] = df.loc[0, 'close']
df.loc[0, 'BL'] = df.loc[0, 'close']

now_time = now.time()

for i in range(1, len(df)):
    curr_o, curr_c, y_c = df.loc[i, 'open'], df.loc[i, 'close'], df.loc[i, 'prev_close']
    prev_rl, prev_bl = df.loc[i-1, 'RL'], df.loc[i-1, 'BL']
    prev_sig = df.loc[i-1, 'Signal']
    
    # 針對最後一根 K 棒 (當前交易日) 進行時段邏輯判斷
    is_last_bar = (i == len(df) - 1)
    
    if is_last_bar:
        if (time(8, 45) <= now_time <= time(13, 45)) or (time(15, 1) <= now_time or now_time <= time(8, 44)):
            # 1. 08:45-13:45 或 15:01-24:00: RL/BL 直接使用前一根K棒的RL/BL
            curr_rl, curr_bl = prev_rl, prev_bl
        else:
            # 2. 13:46-15:00: 套用目前的權勢策略指標計算
            curr_rl = y_c if (curr_o > y_c and curr_c > y_c) else prev_rl
            curr_bl = y_c if (curr_o < y_c and curr_c < y_c) else prev_bl
    else:
        # 歷史資料正常計算
        curr_rl = y_c if (curr_o > y_c and curr_c > y_c) else prev_rl
        curr_bl = y_c if (curr_o < y_c and curr_c < y_c) else prev_bl
        
    df.loc[i, 'RL'] = curr_rl
    df.loc[i, 'BL'] = curr_bl
    
    # 權勢策略狀態判斷 (PDF 邏輯)
    if curr_c > curr_rl and curr_c > curr_bl:
        # 多方勢
        df.loc[i, 'Signal'] = 1
        df.loc[i, 'Message'] = "🚀【Keep多方勢】" if prev_sig == 1 else "🚀【空方勢轉多方勢】"
    elif curr_c < curr_rl and curr_c < curr_bl:
        # 空方勢
        df.loc[i, 'Signal'] = -1
        df.loc[i, 'Message'] = "📉【Keep空方勢】" if prev_sig == -1 else "📉【多方勢轉空方勢】"
    elif min(curr_rl, curr_bl) <= curr_c <= max(curr_rl, curr_bl):
        # 處於兩線之間
        if curr_rl <= curr_bl:
            # RL 在下，BL 在上 -> 趨勢持續 (Case 3, 7)
            df.loc[i, 'Signal'] = prev_sig
            if prev_sig == 1:
                df.loc[i, 'Message'] = "🚀【Keep多方勢】"
            elif prev_sig == -1:
                df.loc[i, 'Message'] = "📉【Keep空方勢】"
            else:
                df.loc[i, 'Message'] = "⚖️【中性觀望】"
        else:
            # BL 在下，RL 在上 -> 斷勢 (Case 4, 8)
            df.loc[i, 'Signal'] = 0
            if prev_sig == 1:
                df.loc[i, 'Message'] = "⚖️【斷多方勢】"
            elif prev_sig == -1:
                df.loc[i, 'Message'] = "⚖️【斷空方勢】"
            else:
                df.loc[i, 'Message'] = "⚖️【中性觀望】"
    else:
        df.loc[i, 'Signal'] = 0
        df.loc[i, 'Message'] = "⚖️【中性觀望】"

df['RL'] = df['RL'].ffill()
df['BL'] = df['BL'].ffill()

# 3. 訊號點設定 (用於繪圖)
df['Entry'] = (df['Signal'] == 1) & (df['Signal'].shift(1) != 1)
df['Exit'] = (df['Signal'] == -1) & (df['Signal'].shift(1) != -1)

# --- 結算價資料點準備 ---
settlement_dates = get_recent_settlement_days(3)
settlement_info = []
for sd in settlement_dates:
    sd_ts = pd.Timestamp(sd)
    # 在 df 中尋找最接近該結算日的交易資料 (向後找最多 3 天，以防假日)
    for delta in range(0, 4):
        target_date = sd_ts + pd.Timedelta(days=delta)
        mask = df['date'].dt.date == target_date.date()
        if mask.any():
            idx = df.index[mask][0]
            settlement_info.append({
                'idx': idx,
                'date_str': sd.strftime('%m/%d'),
                'price': df.loc[idx, 'close'],
                'high': df.loc[idx, 'max']
            })
            break

# 4. 繪圖與記憶體處理
print("繪製圖表中...")
# 移除 MACD 圖表，改為 2 個子圖
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 12), sharex=True, 
                                     gridspec_kw={'height_ratios': [3, 1]})
x_idx = np.arange(len(df))
y_range = df['max'].max() - df['min'].min()
label_offset = y_range * 0.05

# 主圖 K 線與策略線
for i in x_idx:
    row = df.iloc[i]
    color = 'red' if row['close'] >= row['open'] else 'green'
    ax1.vlines(i, row['min'], row['max'], color=color)
    ax1.add_patch(Rectangle((i-0.3, min(row['open'], row['close'])), 0.6, abs(row['close']-row['open']), color=color))

ax1.plot(x_idx, df['20MA'], color='blue', ls='--', label='20MA', alpha=0.6)
ax1.step(x_idx, df['RL'], color='#e91e63', label='RL', where='post', lw=1.5)
ax1.step(x_idx, df['BL'], color='black', label='BL', where='post', lw=1.5)

# 標註進出場
ax1.scatter(np.where(df['Entry'])[0], df.loc[df['Entry'], 'min']-100, marker='^', color='orange', s=150, label='In')
ax1.scatter(np.where(df['Exit'])[0], df.loc[df['Exit'], 'max']+100, marker='v', color='darkblue', s=150, label='Out')

# --- 標註結算價 (Settlement) ---
colors = ['#BBDEFB', '#64B5F6', '#1565C0'] # 淺藍到深藍
for i, info in enumerate(settlement_info):
    color = colors[min(i, len(colors)-1)]
    # 垂直線
    ax1.axvline(x=info['idx'], color=color, linestyle='--', alpha=0.6, lw=1.2)
    # 水平延伸線 (從結算日延伸到最右側)
    ax1.hlines(y=info['price'], xmin=info['idx'], xmax=len(df)-1, color=color, linestyle='-', alpha=0.7, lw=3)
    # 文字標籤 (顯示在該日最高價上方)
    ax1.text(info['idx'], info['high'] + label_offset, f"{info['date_str']}\nSettle\n{info['price']:.0f}", 
             color='navy', fontsize=15, fontweight='bold', va='bottom', ha='center',
             bbox=dict(boxstyle='round,pad=0.3', facecolor='lightyellow', edgecolor=color, alpha=0.8))

ax1.set_title(f"TX Continuous - Power Strategy Daily Analysis (with Settlement)")
ax1.legend(loc='upper left', ncol=2)
ax1.grid(alpha=0.2)

# 成交量與 RSI (原本的 ax3 變為 ax2)
ax2.bar(x_idx, df['volume'], color='gray', alpha=0.3)
ax2_rsi = ax2.twinx()
ax2_rsi.plot(x_idx, df['RSI3'], color='purple', lw=1.2, label='RSI3')
ax2_rsi.plot(x_idx, df['RSI6'], color='orange', lw=1.2, label='RSI6')
ax2_rsi.set_ylim(0, 100)
ax2_rsi.legend(loc='upper left')

# X 軸設定
step = max(1, len(df) // 10)
ax2.set_xticks(x_idx[::step])
ax2.set_xticklabels(df['date'].dt.strftime('%m-%d').iloc[::step], rotation=45)

plt.tight_layout()

# --- 核心：儲存至記憶體 ---
img_buffer = io.BytesIO()
plt.savefig(img_buffer, format='png', bbox_inches='tight')
plt.close(fig)
img_buffer.seek(0)

# 5. 上傳與通知
print("正在上傳圖表至 Discord (記憶體直傳)...")
public_img_url = upload_memory_to_discord(DISCORD_WEBHOOK_URL, img_buffer)

if public_img_url:
    print(f"上傳成功: {public_img_url}")
    last = df.iloc[-1]
    
    # --- 關卡計算 (向上與向下各 5 關) ---
    current_close = last['close']
    unique_levels = []
    seen_prices = set()
    # 由新到舊遍歷，同一價格只取最新的一筆描述 (排除當天資料，從前一天開始找)
    for i in range(len(df)-2, -1, -1):
        row = df.iloc[i]
        d_str = row['date'].strftime('%m/%d')
        for p, label in [(row['open'], "開盤價"), (row['close'], "收盤價"), (row['max'], "最高點"), (row['min'], "最低點")]:
            if p not in seen_prices:
                unique_levels.append({'price': p, 'desc': f"{d_str} {label}"})
                seen_prices.add(p)
    
    # 向上 5 關 (高於目前收盤，由低到高排)
    up_levels = sorted([l for l in unique_levels if l['price'] > current_close], key=lambda x: x['price'])[:5]
    # 向下 5 關 (低於目前收盤，由高到低排)
    down_levels = sorted([l for l in unique_levels if l['price'] < current_close], key=lambda x: x['price'], reverse=True)[:5]
    
    up_msg = "\n".join([f"{i+1}. {l['desc']}: `{l['price']:.0f}`" for i, l in enumerate(up_levels)])
    down_msg = "\n".join([f"{i+1}. {l['desc']}: `{l['price']:.0f}`" for i, l in enumerate(down_levels)])

    # Telegram 訊息
    message = (f"📊 *台指期權勢策略報告*\n"
               f"📅 日期：`{last['date'].strftime('%Y-%m-%d')}`\n"
               f"📖 開盤： `{last['open']:.0f}`\n"
               f"💰 收盤：`{last['close']:.0f}`\n"
               f"🔴 紅底： `{last['RL']:.0f}`\n"
               f"⚫ 黑頂： `{last['BL']:.0f}`\n"
               f"🧪 RSI3/6： `{last['RSI3'].round(2)} / {last['RSI6'].round(2)}`\n"
               f"📊 差值(3-6)： `{ (last['RSI3'] - last['RSI6']):.2f}`\n"
               f"🚦 狀態：{last['Message']}\n\n"
               f"📈 *向上5關卡*:\n{up_msg}\n\n"
               f"📉 *向下5關卡*:\n{down_msg}")
    
    send_telegram_with_photo_url(TG_TOKEN, TG_CHAT_ID, message, public_img_url)
    print("✅ Telegram 報告發送完畢。")
else:
    print("❌ 圖片上傳失敗，停止發送 Telegram。")

# 登出與清理
api.logout()
img_buffer.close()
print("--- 任務結束 ---")
