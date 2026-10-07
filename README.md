# Progress Recorder Prototype v0.3

一個偏研究生 / 報告工作流的跨平台工作紀錄器雛型。

## 這版已經能做什麼

- 手動開始 / 停止記錄。
- 每 5 秒偵測一次目前前景視窗，將同一個視窗合併成一段工作 session。
- **閒置偵測（Windows）**：超過 5 分鐘沒有鍵盤 / 滑鼠操作就算閒置，不計入工作時間。只讀取「最後一次操作的時間」，不讀取內容。
- 電腦睡眠 / 休眠的期間不會被算進任何 session。
- **工作 / 非工作分類**：依程式名稱與視窗標題自動分成「工作 / 非工作 / 未分類 / 閒置」；工作列、快速設定等系統介面自動忽略。
- **收工審閱**：按「結束工作」會跳出審閱畫面：
  - ① 把未分類項目一鍵設為工作 / 非工作 / 忽略，存成規則，之後自動套用。
  - ② 工作被切成「工作區塊」（中間休息超過 10 分鐘就分段），每塊可選「不記錄 / 簡述 / 重點詳述」並補一句說明。
  - ③ 輸出 .md 報告，或複製 AI Prompt 貼到任何 AI 聊天框。
- 瀏覽器 / 編輯器標題會自動清掉「和其他 N 個頁面 - 個人 2 - Microsoft Edge」這類雜訊。
- 可管理（新增 / 移除）監控資料夾，監控 `.pptx/.ppt/.pdf/.docx/.xlsx/.py/.m/.lsf/.txt/.md` 的新增、修改與移動。
- 可以隨手輸入一句重要進度，例如「FDTD mesh 問題已解決」。
- SQLite 本機儲存，不需要帳號或伺服器。
- 不截圖、不記鍵盤內容。

## 平台支援

目前以 **Windows** 為主要開發平台。macOS / Linux 可以執行，但閒置偵測尚未實作（會當作一直有在操作），之後再補。

## 為什麼選 Python + PySide6

程式碼可讀性高、跨平台，而且後續要叫 AI 幫忙新增功能或修改單一模組很方便。
資料層、視窗追蹤、檔案監控、報表、UI 都分開，避免全部塞在一個檔案。

## 專案結構

```text
progress_recorder_prototype/
├─ main.py                      # 程式入口
├─ requirements.txt
├─ build_windows.bat
├─ build_linux_macos.sh
├─ progress_recorder/
│  ├─ config.py                 # 設定 / 資料路徑
│  ├─ database.py               # SQLite
│  ├─ tracker.py                # 前景視窗追蹤 + 閒置 / 睡眠切段
│  ├─ idle.py                   # 系統閒置時間（目前 Windows）
│  ├─ classifier.py             # 工作 / 非工作分類規則、標題清理
│  ├─ blocks.py                 # 工作區塊切分（無 Qt，可測試）
│  ├─ file_watcher.py           # 工作檔案變更
│  ├─ reporter.py               # 原始紀錄 / 審閱後報告 + AI prompt
│  ├─ ui.py                     # 主視窗
│  ├─ review.py                 # 收工審閱畫面
│  └─ dialogs.py                # 監控資料夾、分類規則設定
└─ tests/                       # python -m unittest discover -s tests
```

## 直接從原始碼執行

建議 Python 3.11～3.13。

### Windows PowerShell

```powershell
cd progress_recorder_prototype
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

### Linux / macOS

```bash
cd progress_recorder_prototype
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

Linux 如果缺少 Qt 系統相依套件，請依發行版補齊常見 X11 / xcb 套件。

## 使用方法

1. 開啟程式。
2. 按「監控資料夾」，加入你的 PPT / 論文 / 模擬專案資料夾。
3. 按「開始記錄」，然後正常做事（分心、吃飯都沒關係，會自動排除）。
4. 有關鍵事件時，可補一句手動備註。
5. 收工時按「結束工作」，在審閱畫面：
   1. 把未分類項目設為工作 / 非工作（只有前幾天需要，之後規則會自動套用）。
   2. 決定每個工作區塊「不記錄 / 簡述 / 重點詳述」，需要的話補一句說明。
   3. 按「輸出 .md」，或「複製 AI Prompt」貼到 ChatGPT / Claude / Gemini 等。
6. 報告存到 `~/.progress_recorder/exports/progress-日期.md`；「匯出原始紀錄」則是 `raw-日期.md`。

「審閱 / 產生報告」按鈕可以隨時打開審閱畫面，也能切換日期回顧前幾天。

資料庫位於：

```text
~/.progress_recorder/progress.db
```

## 設定與分類規則

設定檔位於 `~/.progress_recorder/config.json`，常用欄位：

| 欄位 | 預設 | 說明 |
|---|---|---|
| `poll_seconds` | 5 | 幾秒偵測一次前景視窗 |
| `idle_threshold_seconds` | 300 | 多久沒操作算閒置（最少 30） |
| `classification_rules` | `[]` | 自訂分類規則，優先於內建規則 |

內建規則：PowerPoint、Word、VS Code、MATLAB、Lumerical、Zotero 等算「工作」；
標題含 YouTube、Netflix、Facebook 等算「非工作」；瀏覽器本身預設「未分類」。
報告中的「未分類活動」會列出最花時間的項目，方便你決定要不要加規則。

自訂規則是「程式名稱（`app`）或視窗標題（`title`）包含某字串」，不分大小寫，由上往下第一條符合的生效：

```json
"classification_rules": [
  {"field": "title", "contains": "lecture", "category": "work"},
  {"field": "app", "contains": "line.exe", "category": "nonwork"}
]
```

`category` 可以是 `work`、`nonwork` 或 `ignored`（忽略，例如系統介面）。
一般不需要手改：在審閱畫面或主視窗的「分類規則」就能新增 / 刪除。規則會套用到過去的紀錄（分類是產生報告時才計算的）。

## Linux Wayland 注意

Wayland 對其他程式的前景視窗資訊有權限限制，因此「前景視窗追蹤」可能拿不到完整資料。
這時程式不會當掉；手動備註與資料夾檔案監控仍能使用。
如果你在 X11/Xorg session，前景視窗追蹤通常會完整許多。

## macOS 注意

讀取其他程式視窗資訊可能需要到「系統設定 → 隱私權與安全性 → 輔助使用」授權。

## 打包成可執行程式

先確認原始碼模式可以正常執行，再打包。

Windows：

```bat
build_windows.bat
```

Linux / macOS：

```bash
./build_linux_macos.sh
```

PyInstaller 不是 cross-compiler：Windows 版本要在 Windows 上 build、Linux 版本在 Linux 上 build、macOS 版本在 macOS 上 build。
目前使用 `onedir` 而不是 `onefile`，比較容易除錯，也比較適合第一版。

## Roadmap

1. ~~閒置偵測、工作 / 非工作分類~~（v0.2，Windows）
2. ~~工作區塊、收工審閱畫面、監控資料夾 / 分類規則管理~~（v0.3）
3. 選配 AI：API 設定放在 `~/.progress_recorder/`（不進 repo）。沒有設定時退回「複製 Prompt + .md」，或完全不用 AI。
4. 接 Notion API，經確認後寫入指定 database。
5. 生成 .pptx 進度報告。
6. System tray 常駐、開機自動啟動；macOS / Linux 閒置偵測。

## 對 AI 修改最重要的幾個入口

- 想改「記什麼」：`tracker.py`、`file_watcher.py`
- 想改「怎麼整理」：`reporter.py`
- 想改「畫面」：`ui.py`
- 想改「資料格式」：`database.py`
- 想接 ChatGPT / Claude / Gemini：新增 `ai_provider.py`，不要把 API 呼叫直接塞進 UI
- 想接 Notion：新增 `notion_provider.py`，由 UI 呼叫 provider

這樣之後即使 AI 幫你改錯一個功能，也不容易把整套程式一起弄壞。
