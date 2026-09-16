# Personal Health Service System · 个人健康服务系统

智慧医养大数据公共服务平台的个人端。当前开发应用位于 `frontend/` 和 `backend/`，支持真实本地持久化与前后端交互。界面以英文为主；原型是设计参考，功能根据实际需求完善。

## 1. 技术栈与运行原理

- 前端：React 19、Vite 8、Ant Design 6、React Router 7、Axios、Recharts、Day.js。
- 后端：Python 3.11+、Flask 3.1、Flask-Login、Flask-SQLAlchemy。
- 数据库：SQLite，本地文件存储，无需注册云数据库平台。
- 检查工具：pytest、ESLint、Vite build；已安装 Vitest，但当前前端尚无测试用例。
- 当前没有配置 Docker、Nginx 部署或 GitHub Actions 工作流。

浏览器访问 `http://127.0.0.1:5173` → Vite 将 `/api` 代理到 `http://127.0.0.1:5001` → Flask 校验会话并读写 SQLite。必须同时运行前后端。前端没有独立 `.env` 配置；代理配置在 `frontend/vite.config.js`。

## 2. 克隆与环境要求

安装 Git、Python 3.11+、Node.js 22.12+（推荐 Node.js 24 LTS，包含 npm）。Vite 8 也支持 Node.js 20.19+；较旧 Node.js 无法运行。先检查：

```bash
git --version
python3 --version
node --version
npm --version
git clone https://github.com/CuSO4Ink/oc2m-personal-health.git
cd oc2m-personal-health
```

Windows 使用 `py -3 --version` 检查 Python。以下所有路径均相对克隆后的仓库根目录。不要进入 `tmp/sketch` 启动，它是旧版原型，不是当前开发网站。

## 3. 首次启动：macOS / Linux

### 终端一：后端环境、测试数据、API

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
```

将最后一条输出复制到 `.env` 的 `FLASK_SECRET_KEY` 中，替换示例值。保留其他配置，然后执行：

```bash
python seed_demo.py
python run.py
```

保持该终端运行。后端地址：`http://127.0.0.1:5001`；健康检查：`http://127.0.0.1:5001/api/health`，应返回 `status: ok`。

### 终端二：前端

在另一个终端进入仓库根目录后：

```bash
cd frontend
npm ci
npm run dev
```

保持该终端运行，在浏览器打开 **http://127.0.0.1:5173**。统一使用 `127.0.0.1`，避免与 `localhost` 混用导致 Cookie 或跨域问题。

## 4. 首次启动：Windows PowerShell

在仓库根目录打开终端一：

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

编辑 `.env` 的密钥后：

```powershell
.\.venv\Scripts\python.exe seed_demo.py
.\.venv\Scripts\python.exe run.py
```

在仓库根目录打开终端二：

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

访问同样的 `http://127.0.0.1:5173`。这里直接调用虚拟环境 Python 和 `npm.cmd`，不需要修改 PowerShell 脚本执行策略。

## 5. 日常再次启动与停止

首次安装完成后无需重复安装或初始化数据。

macOS / Linux 后端：

```bash
cd backend
source .venv/bin/activate
python run.py
```

Windows 后端：`cd backend` 后运行 `.\.venv\Scripts\python.exe run.py`。

前端：`cd frontend` 后运行 `npm run dev`（Windows 可用 `npm.cmd run dev`）。停止服务时分别在两个终端按 `Ctrl+C`。更新依赖后，前端重新 `npm ci`，后端重新安装 `requirements.txt`。

## 6. 测试账号、数据和上传

- 邮箱：`alex.morgan@example.com`
- 密码：`HealthDemo2026!`
- 账号由 `backend/seed_demo.py` 创建，包含健康记录、指标趋势、共享活动、预约、提醒、社区内容和个人资料。
- 通知由相关操作及通知接口访问时同步生成，并非独立后台定时任务。
- 新注册账号的数据为空，与测试账号隔离。
- 上传入口：Health Records → 打开已保存记录详情 → 附件区域；新增记录页需先保存，再上传。
- 支持 PDF、PNG、JPEG：每条记录最多 10 个附件，每个不超过 10 MB。医院来源记录只读，使用自建记录测试上传和编辑。
- 附件内容也保存在 SQLite，克隆代码不会带入这台电脑已有的上传文件或私人测试数据。
- `seed_demo.py` 会重置测试账号密码，并开启其社区资料/恢复示例圈子成员关系；已有业务数据通常不覆盖，不是完整重置脚本。
- 部分健康指标、记录及共享示例日期固定在 2026 年，日期久远后可能过期或不出现在短期筛选中。预约时段首次生成时相对初始化时间；过期后请使用新演示数据库，或增加有效测试时段。不要用真实患者数据。

## 7. 环境配置、数据库与备份

`backend/.env`（不会上传 GitHub）：

```dotenv
FLASK_SECRET_KEY=填写自己生成的随机密钥
DATABASE_URL=sqlite:///personal_health.db
RESET_CODE_DELIVERY=demo
```

- `FLASK_SECRET_KEY` 用于签名会话，修改后旧登录状态失效。不要提交真实密钥。
- SQLite 相对路径基于 Flask instance 目录，默认文件是 `backend/instance/personal_health.db`。
- 首次运行自动创建目录和缺失的数据库表。`db.create_all()` 不会迁移已有表结构；修改已有字段前需安排数据库迁移。
- `RESET_CODE_DELIVERY=demo`：密码恢复、邮箱变更代码显示在页面，仅供演示，没有发送真实邮件，也不证明邮箱所有权。当前其他模式没有真实投递实现。
- 备份：停止后端后复制整个 `backend/instance/` 到仓库外安全位置，保留数据库与附件数据。
- 全新演示环境：停止后端，备份后将 `backend/instance/personal_health.db` 改名，再运行 `seed_demo.py` 与 `run.py`。这会创建全新数据库，旧数据只有恢复备份后才能继续使用。
- `.venv/`、`node_modules/`、`.env`、`instance/`、`dist/` 不提交；各组员需自行安装环境和初始化数据。

## 8. 代码文件结构

```text
oc2m-personal-health/
├── README.md                     本地启动、功能、测试与协作说明
├── .gitignore                    排除密钥、数据库与生成文件
├── backend/
│   ├── .env.example              后端配置模板
│   ├── requirements.txt          Python 依赖版本
│   ├── run.py                    开发服务器入口，端口 5001
│   ├── seed_demo.py              演示账号与业务数据初始化
│   ├── pytest.ini                pytest 配置
│   ├── tests/test_system.py      API 功能、安全边界及数据隔离测试
│   ├── app/
│   │   ├── __init__.py           应用工厂、配置、蓝图、会话加载、建表
│   │   ├── extensions.py         数据库及登录扩展
│   │   ├── models.py             数据模型、关系、序列化
│   │   └── routes/
│   │       ├── auth.py           注册、登录、退出、密码恢复
│   │       ├── account.py        资料、邮箱/密码变更、会话、安全记录
│   │       ├── overview.py       总览聚合
│   │       ├── records.py        健康档案、版本历史、附件
│   │       ├── insights.py       指标、趋势、参考规则、提醒审核
│   │       ├── sharing.py        授权、字段预览、访问记录与审核
│   │       ├── services.py       医疗目录、预约、改期、健康提醒、养老目录
│   │       ├── community.py      圈子、帖子、评论、举报与拉黑
│   │       ├── notifications.py  通知生成、状态、过滤、偏好
│   │       └── system.py         健康检查及模块列表
│   └── instance/                 本地生成的 SQLite 数据库（不提交）
├── frontend/
│   ├── package.json              npm 依赖与命令
│   ├── package-lock.json         锁定依赖，使用 npm ci
│   ├── vite.config.js            开发服务器与 /api 代理
│   ├── eslint.config.js          代码检查规则
│   ├── index.html                页面入口
│   └── src/
│       ├── main.jsx              React 挂载入口
│       ├── App.jsx               路由、公共布局、登录/恢复等页面
│       ├── api.js                Axios 客户端与会话失效处理
│       ├── auth.jsx              登录状态 Provider
│       ├── authContext.js        共享认证 Context
│       ├── styles.css            公共样式与响应式布局
│       ├── HealthOverview.jsx    健康总览
│       ├── HealthRecords.jsx     档案列表、表单与详情
│       ├── RecordAttachments.jsx 附件上传、预览与下载
│       ├── HealthInsights.jsx    健康指标及趋势
│       ├── SharingPrivacy.jsx    共享和隐私
│       ├── CareServices.jsx      医养服务、预约与提醒
│       ├── Community.jsx         社区
│       ├── Notifications.jsx     通知中心
│       └── AccountSecurity.jsx   账号与安全
└── tmp/
    ├── Project_Architecture_and_Open_Source_Technology_Selection_2026-09-11.md
    │                             早期技术选型参考，最终以实际代码为准
    └── sketch/                   旧版原型源码，仅供参考
```

## 9. API 与前后端协作

各接口前缀：`/api/auth`、`/api/account`、`/api/overview`、`/api/records`、`/api/insights`、`/api/sharing`、`/api/services`、`/api/community`、`/api/notifications`。`/api/health` 与 `/api/modules` 为系统接口。具体方法、字段及校验规则以相应 routes 文件和测试为准。

会话通过 Cookie 认证，不使用前端硬编码用户 ID。前端统一使用 `src/api.js`；新增功能应同时修改页面、API、数据模型及必要测试。附件接口用二进制响应，其他主要接口使用 JSON。

## 10. 测试与构建

后端从 `backend/` 目录运行（虚拟环境已激活）：

```bash
python -m pytest -q
```

Windows 使用 `.\.venv\Scripts\python.exe -m pytest -q`。测试通过应用工厂使用独立内存数据库，不要求启动开发服务器，不修改本地演示数据库。当前 18 个测试函数覆盖认证、档案、附件、指标、授权、预约、社区、通知和会话等流程；并不等于全部需求已经验收。

前端从 `frontend/` 目录运行：

```bash
npm run lint
npm run build
```

`npm test` 调用 Vitest，但目前没有前端测试文件，不能视为已有前端自动化覆盖。构建输出在 `frontend/dist/`，不提交；已有大包体积警告需后续优化。`npm run preview` 只用于静态构建预览，当前没有配置其 API 代理，不能代替开发时的 `npm run dev` 完成全栈测试。

当前尚未提供正式压力测试报告或完整安全审计。开发服务器开启 debug，仅用于本地；公网部署前必须另行配置生产服务器、HTTPS、密钥和安全措施。

## 11. 常见问题

- 页面显示 “Records could not be loaded” 等：先确认后端健康检查正常，再检查后端终端报错、前端代理和登录状态；不要把接口错误当作无数据。
- 无法登录：先运行 `seed_demo.py`；确认使用正确数据库及邮箱密码；触发限流后等待 15 分钟再试。修改密钥、撤销会话后需重新登录。
- 5173 被占用：Vite 可能自动改端口，应停止旧进程释放端口。当前 CORS 固定为 5173；确需改端口时同时调整相关配置。
- 5001 被占用：停止旧后端；若改端口，需同时修改 `backend/run.py` 和前端代理。5000 在 macOS 上可能被 AirPlay 占用。
- 缺 Python 包：确认当前目录是 `backend/`，使用虚拟环境解释器重新安装依赖。
- npm/Vite 启动失败：检查 Node.js 版本；确保在 `frontend/` 运行 `npm ci`，不要混用旧原型依赖。
- 页面更新不正常：刷新浏览器；查看两个终端日志及浏览器 Console/Network，不要先删除数据库。

## 12. 组员开发与提交

```bash
git switch main
git pull --ff-only origin main
git switch -c feature/your-module
```

完成开发、运行相关检查后：

```bash
git add 要提交的文件路径
git commit -m "feat: describe your change"
git push -u origin feature/your-module
```

在 GitHub 创建 Pull Request 合入 `main`，说明功能、验证方法及限制。不要提交真实健康数据、密码、数据库或本地环境目录，不要使用强制推送覆盖队友提交。完整网站代码同时发布到 `feature/fullstack-foundation` 分支；组员从 `main` 创建自己的功能分支。

## 13. 已实现功能与当前边界

以下目录、设备来源、医护身份和医院同步记录均包含演示数据；本地 verified 标记不等于外部真实身份核验。预约仅保存到本地平台，不发送给医院；健康规则用于成人参考提示，不构成诊断或医生审核的建议。


- Account registration, session login, logout and development password reset
- Account-scoped health overview with refresh, pending alerts, overdue tasks, upcoming appointments and active sharing counts
- Latest measurements with collection time, source, missing-data and stale-data notices
- Recently updated records, expiring permissions, historical unusual access and working module shortcuts
- Health record search and filtering by keyword, type, source and date
- Self-reported record creation, editing and version history
- Persistent PDF/PNG/JPEG attachments with preview, download, confirmed deletion and account ownership checks
- Attachment limits: 10 files per record, 10 MB per file; file extension and signature validation
- Read-only provider-synced records with source and sync provenance
- Ownership checks and optimistic version conflict protection in the API
- Blood pressure, blood glucose and heart-rate trend charts with time filters
- Validated manual reading entry with fixed units, source and collection time
- Versioned reference-threshold alerts with pending/reviewed history and preserved original rules
- Context filters, timestamped reading history, multi-date data-sufficiency checks and diastolic averages
- Explainable adult reference flags with AHA/NIDDK/ADA source links; no normal classification for unsupported contexts
- Data-sufficiency notices and traceable rule-based trend summaries
- Demonstration healthcare-recipient directory and fixed-record sharing permissions
- Field selection and owner-only preview of the locally enforced active permission
- Permission preview, view/download controls, expiry and immediate revocation
- Access-event review state with honest demonstration-location provenance
- Account-isolated access activity with action, result, time, location and review flags
- Demonstration medical-service catalogue with live local appointment capacity
- Appointment review, confirmation, duplicate/full-slot checks and cancellation
- Same-service appointment rescheduling with atomic capacity reservation and changed-time notifications
- Personal health reminders with due-state tracking and completion
- Daily/weekly UTC recurrence after completion, completed occurrence history and stop-repeat control
- Searchable elder-care information directory with source and update provenance
- Care appointment and task summaries on the health overview
- Optional Community profile with explicit on/off control
- Peer-circle membership, anonymous experience posts, likes and comments
- Post and comment reporting with account-isolated submission history
- Owner comment deletion, anonymous-safe member blocking and reversible block management
- Bidirectional content/interaction filtering and removal of blocked/deleted comment notifications
- Basic persistent posting/comment frequency limits with health-record isolation and safety guidance
- Unified in-app notifications for health, care, sharing, security and community events
- Persistent unread state, category/status filters, search, mark-all-read and clear actions
- Global unread badge with persisted optional-category mute preferences
- Resolved-event history for completed tasks, reviewed alerts/access activity and ended appointments/shares
- Resolved notices stay in the inbox but no longer count in the attention badge
- Account profile management with protected sign-in email changes
- Current-password-verified password changes that revoke other sessions
- Active-session management and account security activity history
- Remember cookies bound to server sessions, preventing revoked/expired session resurrection
- Database-backed login and password-recovery attempt limits
- Two-step email change with expiring, attempt-limited development verification codes (no real mailbox delivery)

Provider system integration, recipient identity-directory integration, correction requests, OCR, visit folders, clinically approved personalised risk reports, cross-system access enforcement, payments, online consultations, live elder-care booking, private community messages, the moderator workbench, SMS/face authentication and external email/SMS/push delivery are planned for a later phase.
