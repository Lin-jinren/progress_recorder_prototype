# Progress Recorder Prototype v0.1

一個偏研究生 / 報告工作流的跨平台工作紀錄器雛型。

## 這版已經能做什麼

- 手動開始 / 停止記錄。
- 每 5 秒偵測一次目前前景視窗，將同一個視窗合併成一段工作 session。
- 可指定工作資料夾，監控 `.pptx/.ppt/.pdf/.docx/.xlsx/.py/.m/.lsf/.txt/.md` 的新增、修改與移動。
- 可以隨手輸入一句重要進度，例如「FDTD mesh 問題已解決」。
- SQLite 本機儲存，不需要帳號或伺服器。
- 一鍵產生當日 Markdown 進度。
- 一鍵複製「AI 整理 Prompt」，目前不綁定任何特定 AI 廠商。
- 不截圖、不記鍵盤內容。

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
│  ├─ tracker.py                # 前景視窗追蹤
│  ├─ file_watcher.py           # 工作檔案變更
│  ├─ reporter.py               # 每日報告 + AI prompt
│  └─ ui.py                     # PySide6 GUI
└─ tests/
   └─ test_reporter.py
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
2. 按「加入監控資料夾」，選你的 PPT / 論文 / 模擬專案資料夾。
3. 按「開始記錄」。
4. 正常做事。
5. 有關鍵事件時，可補一句手動備註。
6. 收工前按「產生今日進度」。
7. Markdown 會存到 `~/.progress_recorder/exports/`。

資料庫位於：

```text
~/.progress_recorder/progress.db
```

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

## 下一版最值得加的功能

1. System tray 常駐與開機自動啟動。
2. 自動判斷「真正工作」與閒置時間。
3. 從 PowerPoint / LibreOffice / VS Code 視窗標題推測專案名稱。
4. 將多次儲存合併成「今天主要修改了哪些檔案」。
5. 接任意 LLM API，把 `reporter.build_ai_prompt()` 送出去取得真正自然語言摘要。
6. 接 Notion API / Notion integration，經確認後自動寫入指定 database/page。
7. 每週自動彙整 weekly progress。

## 對 AI 修改最重要的幾個入口

- 想改「記什麼」：`tracker.py`、`file_watcher.py`
- 想改「怎麼整理」：`reporter.py`
- 想改「畫面」：`ui.py`
- 想改「資料格式」：`database.py`
- 想接 ChatGPT / Claude / Gemini：新增 `ai_provider.py`，不要把 API 呼叫直接塞進 UI
- 想接 Notion：新增 `notion_provider.py`，由 UI 呼叫 provider

這樣之後即使 AI 幫你改錯一個功能，也不容易把整套程式一起弄壞。
