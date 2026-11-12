# 技术栈

- 前端：Next.js、React、TypeScript、Tailwind CSS。
- 后端：FastAPI、Pydantic、Uvicorn、Python。
- AI 能力：Dify Agent。问答、课程辅导、动态出题、评价和补救均通过后端调用 Dify。
- 数据库：PostgreSQL，保存账户、课程目录、学习状态和历史成绩。课程资料与检索由 Dify 管理，不再需要 `pgvector`。

# 启动方式

## 环境变量

首次配置时，复制 `backend/.env.example` 为 `backend/.env.local`，填写 Dify 密钥、数据库和前端来源。已有配置请先备份再核对，旧版练习生成、去重和评价参数已不再使用。保留的掌握度参数仅用于解释历史评估与课程推荐：

```env
# PostgreSQL 连接串示例
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ml_coach

# 前端地址，默认即可用于本地开发
FRONTEND_ORIGIN=http://localhost:3000

# 已发布 Dify 应用的 Service API 地址和应用密钥
DIFY_API_BASE_URL=https://api.dify.ai/v1
DIFY_API_KEY=app-替换为你的应用密钥
DIFY_TIMEOUT_SECONDS=120
```

复制 `frontend/.env.example` 为 `frontend/.env.local`，配置：

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

如果前后端不在同一台机器或端口，需要同步修改后端的 `FRONTEND_ORIGIN` 和前端的 `NEXT_PUBLIC_API_BASE_URL` 。

模型、提示词、知识资料和检索策略在 Dify 应用中配置。前端不再填写模型或 Embedding 密钥；应用密钥仅保存在后端。自建 Dify 时请使用实例的 Service API 地址（包含 `/v1`），不要填写 WebApp 分享地址或知识库 API Key。

## 管理员账户

登录页可切换“学生”和“管理员”。选择管理员后，可登录已有账户，或点击“创建管理员”，填写姓名、用户名、密码、确认密码及 Authcode。创建成功后直接进入 `/admin` 管理后台；目前后台提供管理员账户信息和退出入口。

创建授权码配置在后端 `backend/.env.local`：

```env
ADMIN_AUTHCODE=填写独立的随机授权码
```

创建时输入同一授权码。该值仅由后端校验，不发送给前端读取、不写入数据库，也不要使用 `NEXT_PUBLIC_` 前缀。留空会禁止创建管理员，但已有账户仍可登录。修改环境变量后重启后端。

首次部署会随初始化脚本创建 `administrators` 表。已有数据库请从项目根目录执行一次：

```powershell
./backend/.venv/Scripts/python.exe operations/database/add_administrators.py
```

该迁移可重复执行，只新增一张管理员表，不修改学生或课程数据。管理员密码和登录凭据均以哈希保存；每个管理员同时保留一个有效会话，重新登录会使旧会话失效，会话最长有效期为 30 天，退出后立即撤销。管理员与学生账户独立，同名账户可分别创建，凭据不能互用于另一身份的受保护接口。

管理后台刷新时通过后端 `/api/v1/admins/me` 验证身份，不凭浏览器中保存的角色授予权限。管理员登录凭据与学生凭据分开保存在浏览器中，Authcode 不保存在浏览器存储里。

## Dify 应用要求

- 自由问答不再选择或绑定课程，请求不传 `course`、`topic_id`，直接把用户的问题发给 Dify，并按对话复用会话。Dify 输入中的课程变量应允许省略；`DIFY_INPUTS` 中的同名默认值也不会用于绑定自由问答。已有各课程的本地聊天自动合并到统一历史列表，保留原消息和当前对话；旧课程范围的会话凭证不会复用。
- 使用已发布、支持 `/chat-messages` 的 Agent、Chatbot 或 Chatflow 应用；后端使用流式请求并汇总为现有 API 响应。接口参考：[Dify 对话消息 API](https://docs.dify.ai/en/api-reference/chat-messages/send-chat-message)。
- 点击“开始学习”时，Dify 的 `query` 为纯文本 `当前课程是[课程名]，我要开始学习[知识点名称]`，例如 `当前课程是机器学习，我要开始学习机器学习基础`。课程名随当前知识点所属课程变化。教学规则由 Dify 应用的内置提示词负责，不附加本地教学提示、学习目标或 JSON 消息包装。
- 讲解结束后显示“没看懂”和“做练习”，均在原对话页面继续。“没看懂”展开行内输入框，发送 `我没看懂：[疑问]`；“做练习”发送 `当前课程是[课程名]，我要做[知识点]的练习。请只出题，不要给答案或解析，等我提交答案后再评价。`。页面不展示自动提示词，点击后立即显示“正在出题…”并滚动到可见位置，Agent 返回题目后在正文下方显示作答框，提交时发送 `我的答案是：[答案]`，页面只展示用户实际输入的内容。
- 练习回复里的 `<details>` 折叠块和明确标注的“参考答案”“解析”等 Markdown 段落会与题干分离，作答前不渲染这些内容或题目来源，提交成功并收到反馈后才显示“查看参考答案与解析”折叠入口。Dify 仍应在内置提示词中遵守先出题、等待作答、再评价的顺序；页面只能识别有明确边界的参考内容。收起输入区和请求失败时保留草稿，支持停止和重试，不弹窗、不要求题目 JSON。
- 教学、练习和作答反馈均直接使用 Dify 对话，不再发送本地长提示词或 JSON 结构化任务。Agent 内置提示应负责先出题、等待作答、再评价；网页指定知识点时直接开始讲解，不必重新规划其他知识点。
- 建议在 Dify 定义 `course` 和 `topic_id` 输入变量，并在知识检索节点使用元数据筛选，确保当前课程和知识点范围。额外必填输入可用 `DIFY_INPUTS={"变量名":"值"}` 配置。应用已配置的模型与采样参数统一在 Dify 调整。
- 知识点页已移除“知识点资料”“练习与测试”“学习记录”入口及对应面板，不再加载固定正文、例题、学习历史或后台恢复旧测试。普通练习由 Agent 自行出题和评价，数量与格式遵循 Dify 配置，其自然语言反馈不直接计入本地量化掌握度或正式测试成绩。旧结构化测试 API 已移除；课程概览仅保留历史成绩读取。
- 同一知识点的讲解、追问、练习和作答复用 Dify `conversation_id`，后端以签名凭证将会话绑定当前学生、课程和知识点。后续只发送当前短句，不重发讲解正文。每个知识点独立保存对话，首次访问新知识点才开启新会话。仅当上游未返回会话 ID 时，才使用近期对话作为兼容上下文。
- 知识点对话、Agent 会话凭证、追问草稿及未提交答案按学生、课程和知识点保存在当前浏览器。切到自由问答或设置页时，进行中的生成请求继续完成，返回后恢复原内容；顶部“课程学习”会回到最近的知识点。刷新后恢复已保存内容，尚未完成的请求提示重试，不会自动重复发起。退出或切换账户时终止原账户的后台请求，其他账户不会读取其知识点对话。
- `/health` 的 `dify_configured` 只表示地址与密钥已填写，不代表已完成远端连通性验证。

## 安装依赖

需要 Node.js、Python 和 PostgreSQL。在项目根目录运行：

```powershell
python -m venv backend/.venv
./backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
cd frontend
npm install
cd ..
```

## 运维初始化

根目录 `operations/` 存放部署、初始化和维护脚本，不会由后端运行时自动执行。首次启动后端前，在项目根目录运行：

```powershell
.\backend\.venv\Scripts\python.exe .\operations\database\initialize.py
```

脚本读取 `backend/.env.local` 中的 `DATABASE_URL`，执行 `operations/database/initialize_postgresql.sql` 创建当前全部表、索引、函数和触发器。该脚本面向空数据库；重复执行不会重复创建已有对象，但不会把旧版本数据库升级到当前结构。

## 数据备份与迁移

代码包不包含 PostgreSQL 中的学生和学习记录。需要交付现有数据时，安装 PostgreSQL 客户端工具，并在源端导出，例如：

```powershell
$env:DATABASE_URL = "postgresql://user:password@host:5432/ml_coach"
.\operations\database\backup.ps1 -OutputPath .\ml-coach.backup
```

在接收方创建空的 PostgreSQL 数据库后，使用同样方式设置目标 `DATABASE_URL`，再恢复备份，例如：

```powershell
$env:DATABASE_URL = "postgresql://user:password@host:5432/ml_coach"
.\operations\database\restore.ps1 -BackupPath .\ml-coach.backup
```

恢复会清除目标数据库中的同名对象，目标必须是专用的可覆盖数据库。仅交付空系统时，无需备份和恢复，只执行上面的数据库初始化命令。

## PostgreSQL 架构测试

后端测试默认不会连接数据库。为验证全新 PostgreSQL 数据库的建表脚本，请创建专用空库（不可指向开发或生产库），并运行：

```powershell
$env:POSTGRES_TEST_DATABASE_URL = "postgresql://user:password@host:5432/ml_coach_test"
cd backend
.\.venv\Scripts\python.exe -m pytest -q tests/test_learning_migrations.py
```

该测试会连续两次执行初始化脚本，并校验核心业务表是否存在。

## 后端

Windows PowerShell：

```powershell
cd backend
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

后端健康检查：`http://localhost:8000/health`

## 前端

```powershell
cd frontend
npm run dev
```

然后访问 `http://localhost:3000`。

## 测试和构建

```powershell
# 后端测试
cd backend
./.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider

# 前端检查和生产构建
cd ../frontend
npm run typecheck
npm run lint
npm run test:practice-content
npm run test:storage
npm run build
```

## 运行数据说明

业务数据存储在 `DATABASE_URL` 指向的 PostgreSQL 数据库中，课程资料由 Dify 管理。首次部署须在项目根目录执行 `backend/.venv/Scripts/python.exe operations/database/initialize.py`；应用运行时不会创建或修改表结构。

## 数据保存与已移除功能

自由问答历史保存在当前浏览器的 `localStorage`；知识点对话、会话凭证、草稿和最近学习位置也按学生保存在 `localStorage`。关闭后重开或刷新仍可恢复，清除站点数据、使用无痕模式或更换浏览器会影响恢复。聊天没有后端同步功能，数据库备份也不包含浏览器聊天或 Dify 配置。

本地知识库、上传检索、题库、固定正文与例题、前置小测、独立练习测试面板、学习记录面板及其生成、批改、补救接口已移除。课程目录、前置关系、开始学习状态和课程概览仍然保留。Dify 的自然语言反馈不会自动写成本地分数或量化掌握度。

新部署不创建本地知识库、题库或固定教学内容表。历史练习表及前置能力记录仍供课程概览只读查询，不再通过本地接口生成新试卷或评价。浏览器对话和本地资料文件不受数据库清理影响。

### 清理旧数据库

从项目根目录运行以下命令，默认只列出待删除对象：

```powershell
./backend/.venv/Scripts/python.exe operations/database/cleanup_retired.py
```

确认需要清理时执行：

```powershell
./backend/.venv/Scripts/python.exe operations/database/cleanup_retired.py --apply
```

脚本读取 `backend/.env.local` 的数据库配置，先通过 `pg_dump` 完整备份到 `operations/database/backups/`，再在事务内删除以下停用表：

- `documents`、`document_chunks`：本地知识库与向量片段。
- `question_bank_items`、`question_bank_topics`、`content_review_events`、`assessment_blueprints`：旧题库与组卷配置。
- `lessons`、`worked_examples`、`content_exposures`：固定正文、例题与曝光记录。

同时移除旧字段 `practice_sets.blueprint_id` 及 `practice_questions` 的 `bank_item_id`、`item_version`、`solution_steps_json`，并移除本地检索使用的 `vector` 扩展。若扩展或表还有其他依赖，事务会回滚，不会级联删除额外对象。账户、课程、学习状态和仍在读取的历史评估表保留，并校验保留行的数量与内容一致。

需要 PostgreSQL 客户端；不在 PATH 时，可用 `--pg-dump "完整路径/pg_dump.exe"` 指定。备份失败时不会执行删除。重复运行已完成的清理不会再次修改数据。备份文件含账户及历史数据，已在 `.gitignore` 中排除，可通过前述恢复脚本还原。

## 当前代码结构

```text
backend/app/
  api/             # 问答、账户、课程目录、概览和开始学习
  core/            # 环境配置、异常、日志与课程枚举
  curriculum/      # 四门课程目录、前置关系与幂等同步
  db/              # PostgreSQL 连接
  learning/        # 概览仍使用的历史进度判定与推荐
  schemas/         # 当前请求响应及历史进度类型
  services/        # Dify、会话签名、账户与学习状态
frontend/
  app/             # 自由问答、登录、课程学习、设置
  components/      # 对话、目录、输入及会话状态
  lib/             # 统一 API、类型、存储、参考答案分离
  tests/           # 存储兼容、对话恢复与答案展示测试
operations/database/ # 初始化、备份和恢复
```

## 当前 API

| 接口 | 用途 |
| --- | --- |
| `GET /health` | 服务状态 |
| `POST /api/v1/chat` | 自由问答与知识点对话 |
| `POST /api/v1/students/register`、`login`、`logout` | 账户操作 |
| `GET /api/v1/students/me` | 当前学生 |
| `POST /api/v1/admins/register`、`login`、`logout` | 管理员创建、登录和退出 |
| `GET /api/v1/admins/me` | 验证当前管理员 |
| `GET /api/v1/curriculum/topics`、`topics/{topic_id}` | 知识点列表与详情 |
| `GET /api/v1/courses/{course}/outline` | 分组课程目录 |
| `GET /api/v1/learning/dashboard` | 课程概览和历史成绩 |
| `POST /api/v1/learning/topics/{topic_id}/start` | 保存开始学习状态 |

学习状态接口使用 `Authorization: Bearer <登录凭证>`。后端测试检查旧接口保持不可访问，并覆盖 Dify 短句、会话隔离、四门课程与登录。

浏览器冒烟脚本为 `frontend/scripts/browser-smoke.mjs`，使用模拟 API 和独立会话，覆盖开始学习、追问、练习、作答、失败重试、切页与刷新恢复及自由问答。运行前准备 Playwright 和前端服务，通过 `COURSE_UI_BASE_URL` 指定地址；外部安装可通过 `COURSE_PLAYWRIGHT_MODULE` 指定模块路径，通过 `COURSE_BROWSER_PATH` 指定浏览器路径。
