# Power_Strategy 權勢策略自動偵測系統

本專案基於永豐金證券 `Shioaji API` 開發，旨在自動化追蹤台指期 (TXF) 與台積電期 (CDF) 的「權勢策略」趨勢。系統每日定時分析市場數據，並透過 Telegram 與 Discord 發送圖文並茂的分析報告。

---

## 🚀 核心功能 (Key Features)

- **自動化趨勢偵測**：每日 13:47 自動執行，精確計算 RL (紅底線) 與 BL (黑頂線)。
- **多商品支援**：同步監控台指期連續合約 (`main_settlement.py`) 與台積電期貨 (`main_TSMC.py`)。
- **視覺化分析圖表**：
    - **結算價標註**：自動標記過去三個月的換倉成本（結算價），輔助判斷長期支撐壓力。
    - **佈局優化**：移除冗餘指標（如 MACD），放大 K 線主體，提供更佳的視覺體驗。
    - **技術指標輔助**：整合 20MA、RSI3、RSI6 等關鍵數據。
- **即時通知系統**：
    - **Telegram**：傳送包含策略狀態（多/空/斷勢）與關鍵數據的摘要訊息。
    - **Discord**：作為圖表託管中心，確保圖片能穩定顯示於行動裝置。

---

## 📂 檔案結構說明

| 檔案 / 資料夾 | 說明 |
| :--- | :--- |
| `main_settlement.py` | **核心主程式**(台指期版本)。 |
| `main_TSMC.py` | **核心主程式**(台積電期版本)。 |
| `main.py` | 舊版本(可忽略)。 |
| `README.md` | 專案說明文件。 |

---

## 📊 策略邏輯 (Strategy Logic)

系統依據收盤價 (Close) 與動態線 **RL (Red Line)** 與 **BL (Black Line)** 的相對位置決定趨勢：

### 1. 指標定義
- **RL (Red Line)**: 
    - 若 `Open > Yesterday_Close` 且 `Close > Yesterday_Close`，則 `RL = Yesterday_Close`。
    - 否則維持前值。
- **BL (Black Line)**: 
    - 若 `Open < Yesterday_Close` 且 `Close < Yesterday_Close`，則 `BL = Yesterday_Close`。
    - 否則維持前值。

### 2. 趨勢判斷
- **🚀 多方勢**：`Close > RL` 且 `Close > BL`。
- **📉 空方勢**：`Close < RL` 且 `Close < BL`。
- **⚖️ 斷勢/觀望**：價格進入兩線之間或發生特定交叉邏輯（詳見 PDF 文件）。

![策略邏輯圖](strategy.png)

---

## 🛠️ 部署指南 (Deployment)

### 環境變數設定
請在系統中設定以下環境變數或修改程式碼：
- `API_KEY` / `SECRET_KEY`: 永豐 Shioaji API 憑證。
- `TG_TOKEN` / `TG_CHAT_ID`: Telegram Bot 資訊。
- `DISCORD_WEBHOOK`: Discord Webhook 連結。

### Synology NAS (Docker) 部署
1. 開啟 **Container Manager** -> **專案** -> **新增**。
2. 建立 `docker-compose.yaml`：
```yaml
version: '3.8'
services:
  power_strategy:
    image: python:3.9-slim
    container_name: power_strategy_app
    volumes:
      - /volume1/docker/power_strategy:/app
    environment:
      - TZ=Asia/Taipei
      - DISCORD_WEBHOOK=你的_DISCORD_WEBHOOK_URL
      - TG_TOKEN=你的_TG_TOKEN
      - TG_CHAT_ID=你的_TG_CHAT_ID
      - API_KEY=你的_API_KEY
      - SECRET_KEY=你的_SECRET_KEY

    command: >
      sh -c "pip install --no-cache-dir shioaji pandas numpy matplotlib requests && python main_settlement.py && python main_TSMC.py"
    restart: "no"
```
3. 於 **任務排程** 設定每日 13:47 執行 `docker-compose up`。

---

## 🔗 相關資源 (Resources)

- **Shioaji API 文件**: [永豐 Python API](https://ai.sinotrade.com.tw/python/Main/index.aspx)
- **Telegram Bot SOP**: [Max 的程式語言筆記](https://stackoverflow.max-everyday.com/2025/12/telegram-notification-bot/)
- **Discord Webhook SOP**: [Discord 官方支援](https://support.discord.com/hc/zh-tw/articles/228383668)

---
*免責聲明：本專案僅供技術研究與參考，不構成任何投資建議。投資有風險，請獨立評估並自負盈虧。*
