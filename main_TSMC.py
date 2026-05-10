##### Shioaji 權勢策略 0510 TSMC 版本

import shioaji as sj
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from datetime import datetime, timedelta
import requests
import os
import io
import sys

# ==========================================
# --- 核心邏輯設定區 (建議由環境變數讀取) ---
# ==========================================
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK", "你的_DISCORD_WEBHOOK_URL")
TG_TOKEN = os.getenv("TG_TOKEN", "你的_TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "你的_TG_CHAT_ID")
API_KEY = os.getenv("API_KEY", "你的_API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY", "你的_SECRET_KEY")

# ==========================================
# --- 功能函數區 ---
# ==========================================

def upload_memory_to_discord(webhook_url, img_bytes, filename="tsmc_daily_report.png"):
    """將記憶體中的圖片數據傳送到 Discord 並獲取連結"""
    try:
        payload = {"content": f"📊 TSMC Daily Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}"}
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
print(f"--- 任務啟動 (TSMC): {now} ---")

# --- 週末檢查 (週一=0, ..., 週五=4, 週六=5, 週日=6) ---
if now.weekday() >= 5:
    print(f"⚠️ 今日為 {now.strftime('%A')} (週末)，程式停止執行。")
    sys.exit()

# 1. Shioaji 登入與資料抓取
api = sj.Shioaji()
api.login(api_key=API_KEY, secret_key=SECRET_KEY)

# 抓取近 60 天資料
start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
end_date = datetime.now().strftime('%Y-%m-%d')
contract = api.Contracts.Futures.CDF.CDFR1  # 台積電近月連續

print("正在從 Shioaji 抓取資料 (TSMC)...")
kbars = api.kbars(contract, start=start_date, end=end_date)
df_raw = pd.DataFrame({**kbars})
df_raw['ts'] = pd.to_datetime(df_raw['ts'])

# --- 轉換為日線邏輯 (僅取日盤 08:45 ~ 13:45) ---
df = df_raw[(df_raw['ts'].dt.time >= datetime.strptime("08:45", "%H:%M").time()) & 
            (df_raw['ts'].dt.time <= datetime.strptime("13:45", "%H:%M").time())].copy()

df = df.resample('1D', on='ts').agg({
    'Open': 'first',
    'High': 'max',
    'Low': 'min',
    'Close': 'last',
    'Volume': 'sum'
}).dropna().reset_index()

df.rename(columns={'ts': 'date', 'High': 'max', 'Low': 'min', 'Open': 'open', 'Close': 'close', 'Volume': 'volume'}, inplace=True)

# 2. 技術指標計算
df['20MA'] = df['close'].rolling(window=20).mean()
std = df['close'].rolling(window=20).std()
df['Upper'] = df['20MA'] + (std * 2)
df['Lower'] = df['20MA'] - (std * 2)

# RSI (N=3)
delta = df['close'].diff()
gain = delta.where(delta > 0, 0)
loss = -delta.where(delta < 0, 0)
window = 3
avg_gain = gain.ewm(alpha=1/window, min_periods=window, adjust=False).mean()
avg_loss = loss.ewm(alpha=1/window, min_periods=window, adjust=False).mean()
rs = avg_gain / avg_loss
df['RSI'] = 100 - (100 / (1 + rs))

# MACD
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

for i in range(1, len(df)):
    curr_o, curr_c, y_c = df.loc[i, 'open'], df.loc[i, 'close'], df.loc[i, 'prev_close']
    prev_rl, prev_bl = df.loc[i-1, 'RL'], df.loc[i-1, 'BL']
    prev_sig = df.loc[i-1, 'Signal']
    
    # 計算 RL (Red Line) 與 BL (Black Line)
    curr_rl = y_c if (curr_o > y_c and curr_c > y_c) else prev_rl
    curr_bl = y_c if (curr_o < y_c and curr_c < y_c) else prev_bl
    df.loc[i, 'RL'] = curr_rl
    df.loc[i, 'BL'] = curr_bl
    
    # 權勢策略狀態判斷
    if curr_c > curr_rl and curr_c > curr_bl:
        df.loc[i, 'Signal'] = 1
        df.loc[i, 'Message'] = "🚀【Keep多方勢】" if prev_sig == 1 else "🚀【空方勢轉多方勢】"
    elif curr_c < curr_rl and curr_c < curr_bl:
        df.loc[i, 'Signal'] = -1
        df.loc[i, 'Message'] = "📉【Keep空方勢】" if prev_sig == -1 else "📉【多方勢轉空方勢】"
    elif min(curr_rl, curr_bl) <= curr_c <= max(curr_rl, curr_bl):
        if curr_rl <= curr_bl:
            df.loc[i, 'Signal'] = prev_sig
            if prev_sig == 1:
                df.loc[i, 'Message'] = "🚀【Keep多方勢】"
            elif prev_sig == -1:
                df.loc[i, 'Message'] = "📉【Keep空方勢】"
            else:
                df.loc[i, 'Message'] = "⚖️【中性觀望】"
        else:
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

# 3. 訊號點設定
df['Entry'] = (df['Signal'] == 1) & (df['Signal'].shift(1) != 1)
df['Exit'] = (df['Signal'] == -1) & (df['Signal'].shift(1) != -1)

# 4. 繪圖與記憶體處理
print("繪製圖表中...")
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 12), sharex=True, 
                                     gridspec_kw={'height_ratios': [3, 1, 1]})
x_idx = np.arange(len(df))

# 主圖 K 線與策略線
for i in x_idx:
    row = df.iloc[i]
    color = 'red' if row['close'] >= row['open'] else 'green'
    ax1.vlines(i, row['min'], row['max'], color=color)
    ax1.add_patch(Rectangle((i-0.3, min(row['open'], row['close'])), 0.6, abs(row['close']-row['open']), color=color))

ax1.plot(x_idx, df['20MA'], color='blue', ls='--', label='20MA', alpha=0.6)
ax1.step(x_idx, df['RL'], color='#e91e63', label='RL', where='post', lw=1.5)
ax1.step(x_idx, df['BL'], color='black', label='BL', where='post', lw=1.5)

# 標註進出場 (針對 TSMC 調整 offset)
ax1.scatter(np.where(df['Entry'])[0], df.loc[df['Entry'], 'min']-5, marker='^', color='orange', s=150, label='Up')
ax1.scatter(np.where(df['Exit'])[0], df.loc[df['Exit'], 'max']+5, marker='v', color='darkblue', s=150, label='Down')

ax1.set_title(f"TSMC Continuous - Power Strategy Daily Analysis")
ax1.legend(loc='upper left', ncol=2)
ax1.grid(alpha=0.2)

# MACD & RSI
ax2.bar(x_idx, df['MACD_Hist'], color=['red' if x > 0 else 'green' for x in df['MACD_Hist']], alpha=0.5)
ax3.bar(x_idx, df['volume'], color='gray', alpha=0.3)
ax3_rsi = ax3.twinx()
ax3_rsi.plot(x_idx, df['RSI'], color='purple', lw=1.2)
ax3_rsi.set_ylim(0, 100)

# X 軸設定
step = max(1, len(df) // 10)
ax3.set_xticks(x_idx[::step])
ax3.set_xticklabels(df['date'].dt.strftime('%m-%d').iloc[::step], rotation=45)

plt.tight_layout()

# --- 核心：儲存至記憶體 ---
img_buffer = io.BytesIO()
plt.savefig(img_buffer, format='png', bbox_inches='tight')
plt.close(fig)
img_buffer.seek(0)

# 5. 上傳與通知
print("正在上傳圖表至 Discord (記憶體直傳)...")
public_img_url = upload_memory_to_discord(DISCORD_WEBHOOK_URL, img_buffer, filename="tsmc_daily_report.png")

if public_img_url:
    print(f"上傳成功: {public_img_url}")
    last = df.iloc[-1]
    
    message = (f"📊 *台積電期權勢策略報告*\n"
               f"📅 日期：`{last['date'].strftime('%Y-%m-%d')}`\n"
               f"📖 開盤： `{last['open']:.1f}`\n"
               f"💰 收盤：`{last['close']:.1f}`\n"
               f"🔴 紅底： `{last['RL']:.1f}`\n"
               f"⚫ 黑頂： `{last['BL']:.1f}`\n"
               f"🧪 RSI： `{last['RSI'].round(1)}`\n"
               f"🚦 狀態：{last['Message']}")
    
    send_telegram_with_photo_url(TG_TOKEN, TG_CHAT_ID, message, public_img_url)
    print("✅ Telegram 報告發送完畢。")
else:
    print("❌ 圖片上傳失敗，停止發送 Telegram。")

# 登出與清理
api.logout()
img_buffer.close()
print("--- 任務結束 ---")
