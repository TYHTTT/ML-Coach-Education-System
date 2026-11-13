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
npm run test:knowledge-graph
npm run build
```

## 运行数据说明

业务数据存储在 `DATABASE_URL` 指向的 PostgreSQL 数据库中，课程资料由 Dify 管理。首次部署须在项目根目录执行 `backend/.venv/Scripts/python.exe operations/database/initialize.py`；应用运行时不会创建或修改表结构。

## 相关知识点与知识图谱

学生端顶部“知识图谱”（`/knowledge-graph`）和管理员导航“知识图谱”（`/admin/knowledge-graph`）可查看按课程聚类的节点与连线。每个知识点只归属其所在课程；悬停节点高亮其全部连线和直接关联的知识点，点击可固定选择。支持搜索定位、课程定位、拖动、缩放和适应画布；键盘可用 Tab 选择节点、Enter 固定、Escape 取消。

图谱采用 Obsidian 风格的力导向布局：课程颜色分组、自然聚拢的节点、细连线及随缩放淡入的标签。节点大小随关联数量变化；拖动节点会带动附近节点重新排布，点击后以浮层展示详情。默认浅色画布，可切换深色和全屏，详情浮层不占据固定侧栏。手形光标使用固定黑色描边及白色填充，兼顾两种背景的可见性。布局计算只影响当前页面，不写入数据库或生成新的关联。

学生端显示已启用课程的有效知识点，管理员端还可查看停用课程；已删除课程及已移除知识点不展示，连线仅在两个端点均可见时展示。图谱不自动推断关联，未设置关联的知识点仍显示为独立节点。修改关联后点击“刷新图谱”即可更新，无需重启。

管理员在课程详情的知识点编辑浮窗中，可多选本课程和其他课程的“相关知识点”，支持名称或 ID 搜索、按课程筛选和分页。关联双向保存：A 关联 B 后，编辑 B 也能看到 A。关联不会改变课程目录或学习顺序。

关系保存在独立的 `topic_relations` 表中，按两个稳定知识点 ID 归一化去重，记录 `relation_type='related'` 和创建时间，作为知识图谱的边数据。管理员接口返回 `related_topic_ids` 和带课程信息的 `related_topics`；更新时省略或传 `null` 保留原关联，传 `[]` 清空。不能关联自身或新选择已移除的知识点；已有关联在知识点停用后保留，可在浮窗中移除。

已有数据库启用该功能前，执行以下迁移。脚本会先备份，再新增关联表并校验既有数据；新部署的初始化脚本已包含该表。

```powershell
./backend/.venv/Scripts/python.exe operations/database/enable_topic_relations.py
```

可通过 `--pg-dump` 指定 PostgreSQL 备份程序路径。

## 数据保存与已移除功能

自由问答历史保存在当前浏览器的 `localStorage`；知识点对话、会话凭证、草稿和最近学习位置也按学生保存在 `localStorage`。关闭后重开或刷新仍可恢复，清除站点数据、使用无痕模式或更换浏览器会影响恢复。聊天没有后端同步功能，数据库备份也不包含浏览器聊天或 Dify 配置。

本地知识库、上传检索、题库、固定正文与例题、前置小测、独立练习测试面板、学习记录面板及其生成、批改、补救接口已移除。课程目录、开始学习状态和课程概览仍然保留。Dify 的自然语言反馈不会自动写成本地分数或量化掌握度。

新部署不创建本地知识库、题库或固定教学内容表。历史练习表仍供课程概览只读查询，不再通过本地接口生成新试卷或评价。浏览器对话和本地资料文件不受数据库清理影响。

## 当前代码结构

```text
backend/app/
  api/             # 问答、账户、课程目录、知识图谱、概览和开始学习
  core/            # 环境配置、异常、日志与课程枚举
  curriculum/      # 四门课程目录与幂等同步
  db/              # PostgreSQL 连接
  learning/        # 概览仍使用的历史进度判定与推荐
  schemas/         # 当前请求响应及历史进度类型
  services/        # Dify、会话签名、账户与学习状态
frontend/
  app/             # 自由问答、登录、课程学习、知识图谱、课程管理、设置
  components/      # 对话、目录、输入及会话状态
  lib/             # 统一 API、类型、存储、参考答案分离
  tests/           # 存储兼容、对话恢复、答案展示与图谱布局测试
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
| `GET /api/v1/courses` | 学生端可用课程列表 |
| `GET /api/v1/knowledge-graph` | 学生登录后读取已启用课程的知识图谱 |
| `GET /api/v1/admin/knowledge-graph` | 管理员读取知识图谱（含停用课程） |
| `GET`、`POST /api/v1/admin/courses` | 管理员查询、新增课程 |
| `GET`、`PATCH`、`DELETE /api/v1/admin/courses/{course_id}` | 管理员查看、修改、删除课程 |
| `GET /api/v1/admin/related-topics` | 搜索相关知识点候选，支持课程、当前节点排除和分页 |
| `GET`、`POST /api/v1/admin/courses/{course_id}/topics` | 查询编排、新增知识点 |
| `PUT`、`DELETE /api/v1/admin/courses/{course_id}/topics/{topic_id}` | 修改、移除所属知识点 |
| `POST /api/v1/admin/courses/{course_id}/topics/{topic_id}/restore` | 恢复知识点 |
| `PUT /api/v1/admin/courses/{course_id}/topics/order` | 调整章内知识点顺序 |
| `PATCH /api/v1/admin/courses/{course_id}/topics/groups/{stage}` | 重命名章节 |
| `POST /api/v1/admin/courses/{course_id}/topics/groups/order` | 调整章节顺序 |
| `GET /api/v1/curriculum/topics`、`topics/{topic_id}` | 知识点列表与详情 |
| `GET /api/v1/courses/{course}/outline` | 分组课程目录 |
| `GET /api/v1/learning/dashboard` | 课程概览和历史成绩 |
| `POST /api/v1/learning/topics/{topic_id}/start` | 保存开始学习状态 |

学习状态接口使用 `Authorization: Bearer <登录凭证>`。后端测试检查旧接口保持不可访问，并覆盖 Dify 短句、会话隔离、四门课程与登录。
