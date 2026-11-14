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

## 后端

新数据库先在项目根目录运行 `./backend/.venv/Scripts/python.exe operations/database/initialize.py` 初始化表结构。需要默认课程时，再进入 `backend` 目录执行 `./.venv/Scripts/python.exe -m app.cli.seed_curriculum` 手动导入；该命令会重新写入默认知识点，仅在需要导入时使用。服务启动不再自动导入课程，以免永久删除的知识点在重启后重新出现。

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

业务数据存储在 `DATABASE_URL` 指向的 PostgreSQL 数据库中，课程资料由 Dify 管理。

管理员删除知识点为永久删除：知识点、目录位置、所有课程中的相关连线、学生学习与维度状态、对应历史练习（题目、提交、作答、错误记录）及相关学习会话在同一事务中清理，无法恢复。其他知识点、课程和账户保留。历史软删除数据会显示在课程详情的“历史待清理知识点”中，可逐项永久删除；恢复接口已移除。浏览器本地聊天和 Dify 远端会话不属于数据库记录，不会由此删除。

课程详情支持“删除章节”，确认浮窗列出本章全部知识点（含历史待清理记录）及数量。确认后整章及其知识点相关数据在同一事务中永久清理；若章节名称、顺序或成员在确认期间变化，请刷新目录并重新确认。删除部分失败时整章操作回滚，其他章节和课程保留。

管理员可点击章节标题或箭头折叠、展开知识点列表，也可使用“展开全部／收起全部”。折叠后保留章节数量及操作按钮；当前页面内调整章节顺序、保存或刷新目录时会保留对应章节的折叠状态。

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
| `PUT`、`DELETE /api/v1/admin/courses/{course_id}/topics/{topic_id}` | 修改、永久删除所属知识点及数据库相关数据 |
| `PUT /api/v1/admin/courses/{course_id}/topics/order` | 调整章内知识点顺序 |
| `PATCH /api/v1/admin/courses/{course_id}/topics/groups/{stage}` | 重命名章节 |
| `DELETE /api/v1/admin/courses/{course_id}/topics/groups/{stage}` | 永久删除章节及其知识点，需提交确认的 `title` 和 `topic_ids` |
| `POST /api/v1/admin/courses/{course_id}/topics/groups/order` | 调整章节顺序 |
| `GET /api/v1/curriculum/topics`、`topics/{topic_id}` | 知识点列表与详情 |
| `GET /api/v1/courses/{course}/outline` | 分组课程目录 |
| `GET /api/v1/learning/dashboard` | 课程概览和历史成绩 |
| `POST /api/v1/learning/topics/{topic_id}/start` | 保存开始学习状态 |

学习状态接口使用 `Authorization: Bearer <登录凭证>`。后端测试检查旧接口保持不可访问，并覆盖 Dify 短句、会话隔离、四门课程与登录。
