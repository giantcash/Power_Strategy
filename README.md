# Power_Strategy
此專案是基於永豐銀行 Shioagi API開發的權勢策略自動偵測。每天13:47準時發車發送訊息到Telegram

# Required app / API
- Telegram API
- Discord API
- Shioagi API

# SOP-Telegram API(Max的程式語言筆記) 
https://stackoverflow.max-everyday.com/2025/12/telegram-notification-bot/

# SOP-Discord API
https://support.discord.com/hc/zh-tw/articles/228383668-%E4%BD%BF%E7%94%A8%E7%B6%B2%E7%B5%A1%E9%89%A4%E6%89%8B-Webhooks


# SOP-Shioagi API(永豐銀行)
https://ai.sinotrade.com.tw/python/Main/index.aspx#pag4

---

## 📊 系統邏輯說明 (System Logic)

基於 `權勢策略` 與 `main.py` 的核心運算邏輯，系統依據收盤價（Close）與兩條動態線 **RL (Red Line)** 與 **BL (Black Line)** 的相對位置來決定趨勢：

### 1. 指標定義
- **RL (Red Line)**: 當今日開盤與收盤皆高於昨日收盤時，更新為昨日收盤價；否則維持前一值。
- **BL (Black Line)**: 當今日開盤與收盤皆低於昨日收盤時，更新為昨日收盤價；否則維持前一值。

### 2. 策略邏輯圖
![策略邏輯圖](strategy.png)


---

## 🛠️ Synology NAS 部署指南 (SOP)

### 1. 使用 Container Manager (Docker Compose) 架設
Synology 的 Container Manager 支持「專案 (Project)」功能，可以直接使用 YAML 檔案部署環境。

**操作步驟：**
1. 開啟 **Container Manager**。
2. 點選左側 **「專案 (Project)」** -> **「新增」**。
3. 輸入專案名稱（例如：`power-strategy`），並選擇一個存放路徑。
4. 來源選擇 **「建立 docker-compose.yml」**。
5. 貼入下方的 YAML 範例，並根據您的 API Key 進行修改。
6. 完成後點選下一步並啟動。

#### **YAML 範例 (`docker-compose.yaml`)**
```yaml
version: '3.8'
services:
  power_strategy:
    image: python:3.9-slim
    container_name: power_strategy_app
    volumes:
      - /volume1/docker/power_strategy:/app
    working_dir: /app
    environment:
      - TZ=Asia/Taipei
      - DISCORD_WEBHOOK=你的_DISCORD_WEBHOOK_URL
      - TG_TOKEN=你的_TG_TOKEN
      - TG_CHAT_ID=你的_TG_CHAT_ID
      - API_KEY=你的_API_KEY
      - SECRET_KEY=你的_SECRET_KEY
    command: >
      sh -c "pip install --no-cache-dir shioaji pandas numpy matplotlib requests && python main.py"
    restart: "no"
```

### 2. 設定 Synology 「任務排程」定時執行
由於本策略為每天 13:47 執行一次，建議透過排程觸發 Container。

**操作步驟：**
1. 前往 **控制台 (Control Panel)** -> **任務排程 (Task Scheduler)**。
2. 點選 **「新增」** -> **「排程的任務」** -> **「使用者定義的指令碼」**。
3. **常規**：任務名稱輸入 `Run_Power_Strategy`，使用者選擇 `root`。
4. **排程**：設定為 **每天** 執行，時間設定在 **13:47**。
5. **任務設定**：在「執行指令」框中輸入以下指令：
   ```bash
   # 進入專案目錄並啟動容器
   cd /volume1/docker/power_strategy && /usr/local/bin/docker-compose up
   ```
   *(註：路徑請根據您實際存放 `docker-compose.yml` 的位置調整)*

---
*本專案僅供技術交流與參考，投資有風險，請謹慎評估。*