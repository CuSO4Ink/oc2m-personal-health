# Personal Health Service System · 个人健康服务系统

基于 React、Flask 和 SQLite 的个人健康管理项目，支持健康资料、报告同步与提取、身体指标、AI 健康建议、资料共享及社区交流。界面默认英文，可切换中文。

## 环境准备

- Git
- Python 3.11 或更高版本
- Node.js 24.x（含 npm）；使用 Node.js 22 时需至少 22.13.0

安装后重新打开终端，确认 `git --version`、`node --version`、`npm --version` 能运行；Windows PowerShell 可用 `npm.cmd --version`。Python 在 Windows 用 `py -3 --version` 检查，在 macOS / Linux 用 `python3 --version` 检查。以下依赖安装需要联网。

```bash
git clone https://github.com/CuSO4Ink/oc2m-personal-health.git
cd oc2m-personal-health
```

当前应用位于 `backend/` 和 `frontend/`。`tmp/sketch/` 是旧原型，不用于启动。

## 首次启动：Windows PowerShell

在仓库根目录打开第一个终端，安装后端依赖并启动：

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_demo.py
```

在仓库根目录打开第二个终端，安装前端依赖并启动：

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

保持两个终端运行，打开 **http://127.0.0.1:5173**。后端地址为 `http://127.0.0.1:5001`，前端会自动代理 API 请求。

## 首次启动：macOS / Linux

在仓库根目录打开第一个终端：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run_demo.py
```

在仓库根目录打开第二个终端：

```bash
cd frontend
npm ci
npm run dev
```

保持两个终端运行，打开 **http://127.0.0.1:5173**。

macOS / Linux 支持文本型 PDF 提取，图片和扫描版 PDF 的自动识别目前仅在 Windows 后端可用，详见下方 OCR 准备。

## 登录与再次启动

主演示账号：**`start@example.test`**，密码：**`HealthDemo2026!`**。登录页还提供另外 5 个测试账号。

首次运行 `run_demo.py` 会自动创建数据库、会话密钥和测试账号，**无需配置 `.env`、安装数据库服务或运行额外的初始化脚本**。所有账号初始健康资料为空，共用 8 份医院 PDF 样本及原始社区示例。

以后启动只需在两个终端分别执行：

| 位置 | Windows PowerShell | macOS / Linux |
|---|---|---|
| `backend/` | `.\.venv\Scripts\python.exe run_demo.py` | `.venv/bin/python run_demo.py` |
| `frontend/` | `npm.cmd run dev` | `npm run dev` |

在各终端按 `Ctrl+C` 停止。普通启动保留上次的数据；账户设置中的“重置我的演示数据”可清空当前账号的练习数据。若需全新演示库，在后端启动命令末尾加 `--fresh`，旧数据库仍会保留。

## 可选：配置 DeepSeek 健康建议

在 `backend/` 新建 `.env.deepseek`，填写自己的 API 密钥：

```dotenv
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_MODEL=deepseek-flash
```

保存后重启后端。未配置密钥时，其余功能仍可使用；健康建议需在页面确认后调用云端服务。若已有 `.env` 或系统环境变量，请确保其中没有同名的空值或旧配置覆盖此文件。

`.env`、`.env.deepseek`、本地数据库、虚拟环境及前端依赖已由 `.gitignore` 排除，不上传 GitHub。其他电脑首次使用时需自行安装依赖并配置密钥。

## 图片与扫描版 PDF：Windows OCR 准备

**需要识别图片或扫描版 PDF 时，请完成本节；只使用可选中文字的文本型 PDF 可跳过。** 8 份演示 PDF 中的 `scanned-care-2026-09-20.pdf` 是英文扫描件，也需要 OCR。OCR 在运行后端的 Windows 电脑上执行，不取决于浏览器使用的系统；不需要额外的 OCR API 密钥或安装 Tesseract、Poppler。

### 1. 检查已有 OCR 语言

在 Windows 的仓库根目录运行以下只读检查，无需启动网站或管理员权限：

```powershell
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\backend\app\windows_ocr.ps1 -Capabilities
```

输出中 `available: true` 表示 OCR 引擎可用；`languages` 中 `en-US` 表示英文，`zh-Hans-CN` 表示简体中文。确认包含所需语言即可跳过安装；只有 `available: true` 并不代表所有语言都已安装。

### 2. 安装缺少的语言组件

在开始菜单搜索 **Windows PowerShell**，选择“以管理员身份运行”（`powershell.exe`）。保持联网，按需执行以下命令。OCR 组件依赖同语言的 Basic 组件，先安装 Basic，再安装 OCR；这是 [Microsoft 的语言组件要求](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/features-on-demand-language-fod?view=windows-11)。

```powershell
# 缺少英文 OCR 时执行（用于英文演示扫描件）
Add-WindowsCapability -Online -Name "Language.Basic~~~en-US~0.0.1.0"
Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"

# 需要识别简体中文报告时，再安装中文组件
Add-WindowsCapability -Online -Name "Language.Basic~~~zh-CN~0.0.1.0"
Add-WindowsCapability -Online -Name "Language.OCR~~~zh-CN~0.0.1.0"
```

组件从 Windows Update 下载；已安装的组件可重复执行。若下载失败，检查网络和 Windows Update；由学校或公司管理的电脑可能需要管理员协助。命令及下载机制见 [Microsoft 安装说明](https://learn.microsoft.com/en-us/powershell/module/dism/add-windowscapability)。不需要切换 Windows 的显示语言。

若返回 `RestartNeeded: True`，先重启电脑。然后重新运行上一步的检查，确认所需语言已出现。**重启项目后端并刷新页面**，以更新程序缓存的 OCR 语言列表。日常启动项目不需要管理员权限。

### 3. 用自带扫描件验证

在仓库根目录运行以下命令，不会导入个人数据库：

```powershell
$ocrSample = (Resolve-Path .\backend\app\hospital_samples\scanned-care-2026-09-20.pdf).Path
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\backend\app\windows_ocr.ps1 -InputPath $ocrSample -Language en-US -PageNumbers 1
```

返回的 `pages` 中应有非空 `text`，包含护理报告正文。此样本没有血压等指标，识别成功不代表一定产生指标候选。

如果在安装 OCR 之前已经同步或上传报告，进入报告详情，在附件旁点击“重新整理”（英文界面为 `Rearrange`），更新之前失败或不完整的全文索引及待核对内容；只刷新页面不会重新识别旧报告。识别结果仍需人工核对后才能导入健康信息。

### 无法使用 Windows OCR 时

macOS、Linux（包括以 Linux 环境运行后端的 WSL）尚未接入图片 OCR；这些环境仍可保存和预览原件、提取文本型 PDF、手动录入指标。扫描件可在“核对报告信息”的原文页粘贴文字，再点击“按此原文重新查找”并核对候选。**手动粘贴只更新核对草稿，不会补齐扫描页的 PDF 全文搜索索引**；要恢复该索引，需使用已配置 OCR 的 Windows 后端重新整理原件。

## 运行说明

- 医院同步、医生访问及预约使用模拟服务；社区好友与私聊在本地账号之间真实保存。
- 演示数据库位于 `backend/instance/usability-demo/`，8 份原始 PDF 随代码提供。不要用旧版 `seed_demo.py` 初始化当前演示。
- 页面无法连接时，检查两个终端是否运行、5001 和 5173 端口是否被占用；后端健康检查地址为 `http://127.0.0.1:5001/api/health`。
- 上述命令用于本地开发与演示。详细演示及重置范围见 [空白演示与重置说明](docs/空白演示与重置说明.md)。
