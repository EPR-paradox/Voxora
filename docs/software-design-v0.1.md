# Voxora 软件设计详细规格

> 产品副标题：English for the semiconductor world  
> 文档状态：Draft v0.20（开发规格草案）  
> 日期：2026-10-03  
> 产品需求来源：`../semispeak.md`  
> 本文目标：让开发者可据此创建工程、实现数据库/API/核心流程，并编写验收测试。

---

## 0. 约定与决策状态

本文使用以下标记：

- **已定**：可以据此实现。
- **暂定**：MVP 实现按此执行；后续可通过 ADR（Architecture Decision Record）修改。
- **待决**：开发前需要产品负责人确认；未确认部分不得自行做影响数据兼容的假设。

### 0.1 本版默认决策

| 决策 | 状态 | 本版约定 |
|---|---|---|
| 客户端 | 已定 | Android-first；React Native + Expo + TypeScript |
| 后端 | 已定 | Python + FastAPI；在 PyCharm 中本地调试 |
| 数据库 | 已定 | PostgreSQL；Alembic 管理迁移 |
| ORM | 暂定 | SQLAlchemy 2.x async ORM；复杂报表可用显式 SQL |
| 系统形态 | 已定 | 单体后端，按业务模块分层；不拆微服务 |
| 缓存/队列 | 已定 | MVP 不引入 Redis/Celery |
| 首发交互 | 已定 | 文字 Roleplay 闭环先行；语音输入作为后续迭代（见 §7.11、§8.6、§10.4），数据模型预留 input_mode |
| 语音输入路径 | 已定 | 语音是输入方式而非消息类型：录音→上传→服务端转写→文本走现有发送接口；音频不写入会话与消息表 |
| 转写执行位置 | 已定 | 服务端转写（本机 faster-whisper）；设备端转写不作为本期方案，理由见 §8.6 |
| 录音交互 | 已定 | 麦克风按钮开麦/闭麦 toggle（点一次开始、再点一次结束并转写），不用按住说话；产物仍是文本回填输入框，理由见 §10.4 |
| 会议模式语音发送 | 已定 | 仅 Meeting 页例外：转写成功后直接发送，不回填输入框（会议里打断一次去改错比识别错误本身更糟）。单角色 Practice 页保持回填确认。见 §10.4、`docs/meeting-mode-v0.1.md` §10 |
| 用户范围 | 暂定 | 第一阶段个人私用；部署前不开放公网、不提供匿名多用户服务 |
| AI 评价目标 | 已定 | 评价英语沟通，不评判技术结论正确性 |
| 录音保存 | 已定 | 本版不保存音频：上传的音频仅用于一次转写，转写完成或失败后即删除，不落库、不进日志；将来若要保存，须先另定同意、存储、删除与保留政策 |
| Auth | 暂定 | 本地开发阶段不做完整注册；公网部署前必须加入服务端认证与数据归属校验 |

如要把应用交给他人或部署到公网，必须先完成 Auth、限流、隐私条款、备份和数据删除，不得把无认证开发版直接暴露公网。

## 1. 产品边界与验收目标

### 1.1 产品定位

Voxora 面向希望进入或已在半导体国际化企业工作的工程师，训练真实工作与生活场景中的英语沟通。目标公司覆盖半导体产业链上下游。公司、岗位、技术领域是场景上下文；英语表达能力是学习目标。

首个用户群体为半导体行业的工程师，典型诉求是在半年到一年内用英语完成技术岗位面试。长期场景覆盖面试、会议、技术讨论、汇报、客户沟通、商务出差和日常生活。

### 1.2 MVP 闭环

```text
选择场景
  → 创建练习
  → 多轮 Roleplay
  → 结束练习
  → 生成结构化英语反馈
  → 保存复习项
  → 在后续练习中再次使用/复测
```

### 1.3 MVP 必须完成的验收条件

1. 用户可以查看已发布场景，并按类别、岗位、难度筛选。
2. 用户可以基于场景创建练习会话；服务端保存会话和场景快照。
3. 用户可以逐轮发送消息；AI 在角色内回应，不在每轮插入语言教学点评。
4. 结束练习后生成并保存结构化评价，包含具体原话证据和可执行改进建议。
5. 用户可以把表达或错误加入复习列表，并查看、标记复习结果。
6. 刷新/重启客户端后，练习历史和已保存复习项仍可读取。
7. AI Provider 可在测试中替换为 Fake Provider；单元测试不依赖外部 LLM。
8. 后端可在 PyCharm 中断点调试；数据库迁移可从空库完整执行。

### 1.4 MVP 不做

- 社区、排行榜、积分商城、真人教师、直播课程。
- 实时 WebRTC、多人语音会议、音频实时分析、流式语音识别（开麦录音是“录完再传再转写”，不属于本项，见 §10.4）。
- 自动创建上百个未经审核的场景。
- 复杂个性化推荐算法、知识图谱、向量搜索。
- 微服务、Redis、任务队列、Kubernetes。
- 真实公司内部资料、真实面试题的声称或未经授权复用。

## 2. 术语

| 术语 | 定义 |
|---|---|
| Scenario | 经人工审核的训练模板，含角色、情境、目标和英语技能 rubric |
| Practice Session | 用户围绕一个 Scenario 完成的一次训练 |
| Turn | 一条用户消息以及对应 AI 回复；错误/重试仍属于同一 client_message_id |
| Roleplay | 与 AI 角色持续对话的阶段；AI 不即时打断纠错 |
| Evaluation | 会话结束后单独执行的英语沟通评价 |
| Review Item | 从反馈或用户主动添加的表达/错误，供后续场景复习 |
| Skill | 可训练英语沟通能力，如 project_update、clarifying_question |
| Industry Segment | 产业链分段，如 equipment、foundry、materials、EDA、OSAT |

## 3. 总体架构

```text
┌──────────────────────────────────────────┐
│ Android App                               │
│ React Native / Expo / TypeScript          │
│ screens → features → API client → storage│
└─────────────────────┬────────────────────┘
                      │ HTTPS + JSON REST
                      │ dev: Android Emulator → http://10.0.2.2:8000
┌─────────────────────▼────────────────────┐
│ FastAPI modular monolith                  │
│ API → application services → repositories│
│                         │                 │
│                         └→ AI provider    │
└───────────────┬───────────────────────────┘
                │ SQLAlchemy / asyncpg
┌───────────────▼───────────────────────────┐
│ PostgreSQL                                │
│ users / scenarios / sessions / messages  │
│ evaluations / review_items               │
└───────────────────────────────────────────┘
```

### 3.1 请求边界

- 客户端不直接访问 PostgreSQL，也不持有 LLM 密钥。
- 所有 AI 请求必须由后端发起。
- 客户端 API base URL 从环境配置读取，不硬编码生产 URL。
- 后端业务服务不依赖 FastAPI `Request` 对象，以便单元测试。
- API 层负责 HTTP 状态码、输入校验和序列化；Service 层负责业务流程；Repository 层负责数据库查询。
- 本地模式下的认证豁免只有一条规则，说清楚免得漏：**loopback 客户端免 token，其余一律要
  `Authorization: Bearer <API_ACCESS_TOKEN>`**。每个业务 router 都必须挂 `require_practice_access`，
  路由漏挂不会报错、也不会被 loopback 测试发现（`/scenarios` 就这么漏过一整个模块）。
  唯一有意公开的是 `GET /api/v1/health`：它是探活端点，不含业务数据，监控不该需要凭据。
  回归测试 `tests/test_access_coverage.py` 会遍历全部受保护路由。

### 3.2 本地网络约定

- Android Emulator 访问宿主机 API 时，开发配置默认 `http://10.0.2.2:8000`。
- 真机调试时使用开发机局域网 IP，并确保服务监听 `0.0.0.0`；不得将该设置误用于生产部署。
- PyCharm 本地启动 FastAPI；Docker Compose 初期只启动 PostgreSQL。
- Expo 开发服务器与 FastAPI 是不同进程；分别观察移动端日志和 PyCharm 后端日志。
- 浏览器预览（`expo start --web`，默认 8081）与 API 不同源，所以后端在本地模式下放行这几个来源的
  CORS（白名单 `CORS_ALLOW_ORIGINS`）。真机与模拟器不受浏览器同源策略约束，不需要这一项。
  白名单只列本地开发来源：一个对 loopback 客户端免 token 的 API 不该被任意网页驱动。

## 4. 技术栈与工程标准

### 4.1 技术选型

| 区域 | 方案 | 约定 |
|---|---|---|
| Android 客户端 | React Native + Expo + TypeScript | Android-first；UI 和网络层分离 |
| 路由 | Expo Router | 页面路由集中维护 |
| 服务端状态 | TanStack Query（暂定） | 请求缓存、加载/错误状态、重试策略 |
| 客户端表单 | React Hook Form + Zod（暂定） | 表单校验与 API Schema 尽量一致 |
| Python API | FastAPI + Pydantic v2 | OpenAPI 自动生成；所有请求/响应显式 Schema |
| ORM | SQLAlchemy 2.x async | AsyncSession 每请求/任务一个作用域 |
| DB Driver | asyncpg | PostgreSQL async 访问 |
| Migration | Alembic | Schema 变更必须提交 migration |
| 测试 | pytest + HTTPX + pytest-asyncio | 单元、API、Repository 测试分层 |
| 本地数据库 | PostgreSQL Docker Compose | 命名 volume；健康检查；非生产密码仅用于本机 |
| AI | 后端 Provider 接口 + 一个初始实现 | 模型名、超时和密钥来自环境配置 |
| 语音转写 | 后端 SpeechProvider + 本机 faster-whisper | 音频不保存；协议与供应商无关，测试用 FakeSpeechProvider |

版本统一由锁文件和依赖清单锁定；不在设计文档中写可能过期的 patch version。

### 4.2 代码质量要求

- Python 使用类型标注；API Schema 与 ORM Model 不混用。
- 所有时间戳存 UTC；客户端本地化显示。
- 主键使用 UUID；所有外部 API 暴露 UUID，不暴露数据库自增 ID。
- DB 列名 `snake_case`；JSON 字段 `snake_case`，日期为 ISO-8601 UTC。
- JSON API 默认 UTF-8；请求/响应均有 Pydantic Schema。
- 对核心 Service 编写单元测试；对每个 API 的主要成功和失败分支写测试。
- SQL migration 可审阅；ORM 自动生成 migration 后必须检查差异，不盲目提交。

## 5. 推荐仓库结构

```text
voxora/
├── apps/
│   └── mobile/
│       ├── app/                       # Expo Router routes
│       ├── src/
│       │   ├── components/            # 通用 UI
│       │   ├── features/
│       │   │   ├── scenarios/
│       │   │   ├── practice/
│       │   │   ├── evaluation/
│       │   │   └── review/
│       │   ├── lib/                   # API client、配置、日志
│       │   ├── hooks/
│       │   └── types/
│       ├── assets/
│       └── tests/
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/
│   │   └── versions/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── deps.py
│   │   │   ├── errors.py
│   │   │   └── v1/
│   │   │       ├── router.py
│   │   │       └── endpoints/
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── logging.py
│   │   │   └── security.py
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   └── seed.py
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── repositories/
│   │   ├── services/
│   │   └── ai/
│   │       ├── base.py
│   │       ├── prompts/
│   │       ├── schemas.py
│   │       └── providers/
│   └── tests/
│       ├── unit/
│       ├── api/
│       └── integration/
├── infra/
│   └── docker-compose.yml
├── docs/
│   ├── software-design-v0.1.md
│   ├── progress.md
│   └── adr/
├── .env.example
├── .gitignore
└── README.md
```

模块依赖方向：

```text
api → services → repositories → models/db
             ↘ ai interfaces
```

禁止 `models` 导入 `api`；禁止 API endpoint 直接拼接 SQL/调用 LLM SDK；禁止客户端绕过 API 访问 AI Provider。

## 6. 数据库设计

### 6.1 通用约定

- PostgreSQL schema 使用 `public`；全部业务表含 `created_at`，可变实体含 `updated_at`。
- 时间列用 `TIMESTAMPTZ NOT NULL DEFAULT now()`。
- JSONB 仅用于版本化、结构变化较大的内容（scenario config、evaluation payload、snapshot）；常用过滤字段保持普通列。
- 删除行为：用户删除时级联删除其私有训练数据；公共 Scenario 不因用户删除而删除。
- MVP 不硬删除 Scenario；以 `status='archived'` 下架。
- ID 使用 `UUID`；由应用生成或数据库 `gen_random_uuid()`，项目统一一种策略。

### 6.2 ER 关系

```text
users 1──1 user_profiles
users 1──N practice_sessions N──1 scenarios
practice_sessions 1──N messages
practice_sessions 1──0..1 evaluations
users 1──N review_items
review_items N──0..1 source_message
scenarios N──N skills（通过 scenario_skills）
```

### 6.3 表定义

#### `users`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| id | UUID | PK |
| email | CITEXT nullable | 唯一；仅加入账号系统后使用 |
| display_name | VARCHAR(80) nullable | 展示名 |
| status | VARCHAR(20) | `active`, `disabled` |
| created_at | TIMESTAMPTZ | not null |
| updated_at | TIMESTAMPTZ | not null |

第一阶段可 seed 一个本地用户；未做认证的开发实例只允许本机访问。

#### `user_profiles`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| user_id | UUID | PK + FK users.id ON DELETE CASCADE |
| current_status | VARCHAR(32) | student/researcher/employee 等；允许扩展 |
| target_industry_segments | JSONB | 产业链标签数组 |
| target_companies | JSONB | 目标公司名称数组 |
| target_roles | JSONB | 目标岗位数组 |
| primary_role | VARCHAR(100) nullable | 主目标岗位 |
| career_goal | VARCHAR(40) | interview/workplace/travel/general |
| daily_minutes | SMALLINT nullable | 10–60，CHECK |
| english_level | VARCHAR(20) nullable | 自评等级；非诊断结论 |
| created_at / updated_at | TIMESTAMPTZ | not null |

#### `scenarios`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| id | UUID | PK |
| slug | VARCHAR(120) | UNIQUE 稳定标识 |
| title | VARCHAR(160) | 标题 |
| summary | TEXT | 场景摘要 |
| category | VARCHAR(24) | interview/workplace/travel/daily_life |
| industry_segment | VARCHAR(40) nullable | equipment/foundry/IDM/EDA/materials/OSAT 等 |
| companies | JSONB | 语境标签，不代表公司官方内容 |
| roles | JSONB | 适用岗位标签 |
| difficulty | SMALLINT | 1–5 CHECK |
| english_level | VARCHAR(20) nullable | CEFR 或内部等级，后续明确 |
| situation | TEXT | 用户可见背景 |
| ai_character | JSONB | name/title/personality/communication_style；单角色场景的发言者，会议场景保留为第一位与会者 |
| cast | JSONB nullable | 会议模式与会者数组（2–5 项：key/name/title/personality/communication_style/voice）；null = 单角色场景。上限 2026-10-03 由 3 上调到 5（正式技术会议），每轮最多 3 条发言的上限不变，见 `docs/meeting-mode-v0.1.md` §2 |
| user_objective | TEXT | 用户要完成的沟通任务 |
| target_skills | JSONB | skill key 数组 |
| target_expressions | JSONB | expression/meaning/usage 示例 |
| roleplay_instructions | TEXT | 角色行为约束，不存 API Secret |
| evaluation_rubric | JSONB | 评价维度与版本 |
| estimated_minutes | SMALLINT | 正数 |
| status | VARCHAR(20) | draft/published/archived |
| version | INTEGER | 默认 1；发布后修改需递增 |
| created_at / updated_at | TIMESTAMPTZ | not null |

发布后练习会保存 scenario snapshot，避免内容更新改变历史练习语境。

#### `skills`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| id | UUID | PK |
| key | VARCHAR(80) | UNIQUE，例如 `clarifying_question` |
| name | VARCHAR(120) | 展示名 |
| description | TEXT | 能力定义 |
| created_at | TIMESTAMPTZ | not null |

`scenario_skills(scenario_id, skill_id, importance)`：复合 PK；importance 1–3。

#### `practice_sessions`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK users.id ON DELETE CASCADE；索引 |
| scenario_id | UUID | FK scenarios.id RESTRICT |
| scenario_version | INTEGER | 创建会话时的版本 |
| scenario_snapshot | JSONB | 创建时的必要场景快照 |
| status | VARCHAR(20) | active/completed/abandoned |
| input_mode | VARCHAR(12) | text/voice；MVP 只启用 text。语音迭代启用后写入 voice，仅作会话偏好标记，不改变消息结构 |
| turn_count | INTEGER | 默认 0，CHECK >= 0 |
| processing_turn_id | UUID nullable | 非空表示本会话正在处理一轮消息 |
| last_activity_at | TIMESTAMPTZ | not null |
| started_at | TIMESTAMPTZ | not null |
| completed_at | TIMESTAMPTZ nullable | 完成时间 |
| created_at / updated_at | TIMESTAMPTZ | not null |

约束：完成会话必须有 `completed_at`；活动会话不得有 `completed_at`。每用户按 `created_at DESC` 查询。

#### `messages`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| id | UUID | PK |
| session_id | UUID | FK practice_sessions.id ON DELETE CASCADE |
| client_message_id | UUID | 客户端生成；用于请求重试幂等 |
| turn_index | INTEGER | 从 1 递增；同一用户输入与 AI 回复共享 turn_index |
| seq | INTEGER | 会话内展示顺序，> 0。客户端按它排序；`created_at` 不行（同一事务里 `now()` 是常量） |
| role | VARCHAR(12) | user/assistant |
| speaker_key | VARCHAR(32) | NOT NULL DEFAULT ''；空串 = 学习者，否则为 `cast[].key`。**不用 NULL**：唯一约束里 NULL 互不相等，可空等于放弃约束 |
| content | TEXT | 文本内容；长度上限由 API 配置 |
| status | VARCHAR(12) | pending/completed/failed |
| audio_metadata | JSONB nullable | 始终为 null；音频不写入数据库（见 §7.11） |
| created_at | TIMESTAMPTZ | not null |

约束：`UNIQUE(session_id, client_message_id, role)`；`UNIQUE(session_id, turn_index, role, speaker_key)`（v0.10 起：一轮里每个发言人各一条，会议因此可以有 1–3 条 AI 记录，而学习者那一轮仍只能有一条）。

#### `evaluations`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| id | UUID | PK |
| session_id | UUID | UNIQUE + FK practice_sessions.id ON DELETE CASCADE |
| status | VARCHAR(16) | pending/processing/completed/failed |
| rubric_version | VARCHAR(40) | 例如 `english-communication-v1` |
| provider | VARCHAR(80) | Provider 名称，不含密钥 |
| model | VARCHAR(120) | 实际模型标识 |
| prompt_version | VARCHAR(40) | 评价 Prompt 版本 |
| result | JSONB nullable | 结构化评价；completed 时必填 |
| error_code | VARCHAR(60) nullable | 不保存敏感原始错误 |
| attempt_count | SMALLINT | 默认 0 |
| created_at / updated_at | TIMESTAMPTZ | not null |

#### `review_items`

| 列 | 类型 | 约束/说明 |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK users.id ON DELETE CASCADE |
| source_session_id | UUID nullable | 来源练习；删除 session 时置空 |
| source_message_id | UUID nullable | 来源消息；删除时置空 |
| item_type | VARCHAR(24) | expression/grammar/clarity/pronunciation/communication |
| original_text | TEXT nullable | 用户原表达或错误 |
| target_text | TEXT | 推荐表达/复习提示 |
| explanation | TEXT nullable | 简短解释 |
| status | VARCHAR(16) | new/reviewing/mastered/archived |
| due_at | TIMESTAMPTZ nullable | 下次复习时间 |
| success_count | INTEGER | 默认 0 |
| failure_count | INTEGER | 默认 0 |
| created_at / updated_at | TIMESTAMPTZ | not null |

### 6.4 索引

```text
users(email) UNIQUE WHERE email IS NOT NULL
scenarios(status, category, difficulty)
practice_sessions(user_id, created_at DESC)
practice_sessions(user_id, status, last_activity_at DESC)
messages(session_id, turn_index)
messages(session_id, client_message_id)
review_items(user_id, status, due_at)
```

对 JSONB 暂不默认添加 GIN 索引；只有查询路径和数据量证明需要时再加。

### 6.5 Migration 规则

1. 修改 ORM Model 后生成 Alembic revision。
2. 人工检查 `upgrade()`、`downgrade()`，确保默认值、索引和约束正确。
3. 在空测试库执行 `upgrade head`；必要时执行 downgrade/upgrade 回归。
4. 不在应用启动时自动创建/修改生产表。
5. 初始 Scenario 通过可重复执行的 seed 脚本写入；seed 使用 slug upsert，不产生重复数据。

## 7. API 约定

### 7.1 全局约定

- Base URL：`/api/v1`。
- Content-Type：`application/json`；统一 UTF-8。
- 字段命名：JSON `snake_case`。
- 时间：RFC 3339 UTC，例如 `2026-10-01T12:00:00Z`。
- UUID 格式：标准 UUID 字符串。
- 成功响应直接返回资源对象；列表响应使用 `{ "items": [], "next_cursor": null }`。
- 错误响应格式统一：

```json
{
  "error": {
    "code": "session_not_active",
    "message": "This practice session is no longer active.",
    "request_id": "uuid",
    "details": {}
  }
}
```

- 所有请求生成/传递 `X-Request-ID`；若客户端未提供，服务端生成并在响应返回。
- 分页默认 `limit=20`，允许 1–100；初版数据少时可先用 limit/offset，后续改 cursor 时新增契约版本或兼容字段。
- API 文案对用户显示前可由客户端本地化；机器判断必须使用 `error.code`。

### 7.2 健康检查

`GET /api/v1/health`

响应 200：

```json
{"status":"ok","database":"ok","version":"0.1.0"}
```

数据库不可用时返回 503，不输出连接串或内部异常。

### 7.3 列出场景

`GET /api/v1/scenarios?category=interview&industry_segment=equipment&role=algorithm_engineer&difficulty=2&limit=20&offset=0`

响应 200：

```json
{
  "items": [
    {
      "id": "uuid",
      "slug": "kla-project-explanation-01",
      "title": "Explain a metrology software project",
      "summary": "Practice explaining your contribution and decisions.",
      "category": "interview",
      "industry_segment": "equipment",
      "companies": ["KLA", "ASML"],
      "roles": ["metrology_software_engineer", "algorithm_engineer"],
      "difficulty": 2,
      "estimated_minutes": 12,
      "target_skills": ["project_explanation", "follow_up_response"]
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

只返回 `status=published` 的场景。排序默认 `category, difficulty, title`；后续可加入推荐排序，但不得隐式随机。

### 7.4 读取场景详情

`GET /api/v1/scenarios/{scenario_id}`

返回详细 situation、角色简介、用户目标、目标表达、预估时长，以及会议场景的 `cast`（与会者，`null` 表示单角色场景）。**不返回隐藏的 `roleplay_instructions`、评价标准内部权重或 system prompt。**

### 7.5 创建练习会话

`POST /api/v1/practice/sessions`

请求：

```json
{
  "scenario_id": "uuid",
  "input_mode": "text"
}
```

响应 201：

```json
{
  "id": "uuid",
  "scenario": {"id":"uuid","title":"Explain a metrology software project"},
  "status": "active",
  "input_mode": "text",
  "messages": [],
  "started_at": "2026-10-01T12:00:00Z"
}
```

校验：scenario 必须 published；MVP 只接受 `text`，语音迭代启用后接受 `voice`（仅偏好标记，请求体不携带音频）；初始 AI opening line 作为 turn 0 assistant message 保存并返回，确保 UI 重载后状态一致。

### 7.6 发送用户消息

`POST /api/v1/practice/sessions/{session_id}/messages`

请求：

```json
{
  "client_message_id": "uuid-generated-by-client",
  "content": "I worked on a measurement pipeline that..."
}
```

响应 201：

```json
{
  "user_message": {
    "id":"uuid","client_message_id":"uuid","turn_index":1,"seq":2,
    "role":"user","speaker_key":"","speaker":null,
    "content":"I worked on a measurement pipeline that...",
    "created_at":"2026-10-01T12:01:00Z"
  },
  "assistant_messages": [
    {
      "id":"uuid","turn_index":1,"seq":3,"role":"assistant",
      "speaker_key":"eng_lead",
      "speaker":{"key":"eng_lead","name":"Dana Whitfield","title":"Engineering Lead"},
      "content":"What was the main challenge you had to solve?",
      "created_at":"2026-10-01T12:01:03Z"
    }
  ],
  "session_status":"active"
}
```

**AI 回复永远是数组**（v0.10 起）：单角色场景是一个元素，会议场景是 1–3 个（`docs/meeting-mode-v0.1.md` §5）。客户端只写一条渲染分支。每条消息带 `seq`（会话内展示顺序，客户端按它排序而不是按数组位置）与 `speaker_key`（空串 = 学习者；绝不为 null）。

行为约定：

1. content 去除首尾空白；空字符串 422；超过配置长度 413 或 422（实现统一选一种并写测试）。
2. session 不属于当前用户或不存在时统一返回 404，避免泄露资源存在性。
3. session 非 active 时返回 409 `session_not_active`。
4. `client_message_id` 已处理时返回已保存的原结果（会议场景是**同一组、同一顺序**的多条 AI 发言），不再次调用模型，保证移动网络重试幂等。
5. 同一 session 同时只处理一轮消息；若 `processing_turn_id` 已占用，返回 409 `turn_in_progress`。
6. AI 超时：用户消息保留为 failed/pending 状态，释放 processing lock；返回 502 `ai_provider_timeout`，客户端可用同一个 client_message_id 重试。
7. 对话上下文仅加载当前 session 的场景快照和最近 N 轮消息；N 从配置读取，超限策略为保留开场、最近消息及必要摘要。MVP 首轮不做自动总结，超过 token/字符预算时返回可解释的 `context_limit_reached`，并记录指标。

并发实现要求：使用短事务原子声明 `processing_turn_id`，提交事务后再调用外部模型；不得在等待 LLM 时长期持有数据库事务/行锁。成功后用新短事务写 AI 消息、更新 turn_count 和 last_activity_at、清除 processing 标记。进程崩溃遗留的 processing 状态由请求超时回收；具体超时时长配置化。

### 7.7 获取练习详情/历史

会话详情返回 `participants`（本会话自己快照里的与会者：`key`/`name`/`title`）与每条消息的 `seq`、`speaker_key`、`speaker`。客户端不解析 `scenario_snapshot`。

`GET /api/v1/practice/sessions/{session_id}`

返回会话状态、场景快照摘要、按 turn_index 升序的消息、评价状态。所有字段按当前用户做归属校验。消息分页暂不做；若会话长度达到上限再加入游标分页。

`GET /api/v1/practice/sessions?status=completed&limit=20&offset=0`

返回当前用户练习摘要，不包含完整消息正文，避免列表响应过大。

字段：`id`、`scenario`（取会话快照里的 id 与 title，而不是当前场景 —— 场景改名不该改写历史练习当时的样子）、
`status`、`turn_count`、`evaluation_status`（未生成评价时为 null）、`started_at`、`last_activity_at`、
`completed_at`；按 `last_activity_at` 倒序，同一时刻用 `id` 兜底保证顺序稳定。
客户端首页靠这一条请求就能区分“继续练”和“看反馈”，不需要逐行再查评价。

### 7.8 结束练习与生成评价

`POST /api/v1/practice/sessions/{session_id}/finish`

请求：

```json
{"reason":"user_finished"}
```

响应 200（评价已生成）：

```json
{
  "session_id":"uuid",
  "session_status":"completed",
  "evaluation_status":"completed",
  "evaluation": {"...":"..."}
}
```

约定：

- 结束接口幂等；已完成会话再次调用返回现有结果。
- 至少有一条用户消息才触发评价；否则 409 `session_has_no_user_turns`。
- 本版同步调用评价服务；设置明确的 provider timeout。评价失败时 session 保持 completed、evaluation 状态为 failed，可通过 `POST /sessions/{id}/evaluation/retry` 重试。
- 保存唯一 session evaluation，retry 更新同一记录 attempt_count，不重复插入。
- 评价输入只使用用户与 assistant 对话、场景目标和 rubric；不向评价 Prompt 传入密钥或无关用户数据。
- UI 若请求超时，先 GET session 查看 evaluation 状态，再决定是否 retry，不能盲目创建新 session。
- 三种结果用同一个响应结构表达，不靠 HTTP 状态码区分：评价成功 → `evaluation_status=completed` + `evaluation`；评价失败 → `evaluation_status=failed` + `error_code` + `retryable=true` + `evaluation=null`；重复调用 → 直接回放已保存的结果。
- 评价失败**不**用 5xx 表达。会话确实已经结束，把报告的状态放进响应正文，客户端从「首次调用」到「重放」只写一条分支；5xx 会与「会话结束失败」混淆，而后者不可能发生。
- `error_code` 取值：`ai_provider_timeout`、`invalid_ai_output`（模型输出无法通过 §8.3 校验）、`ai_provider_error`（协议层失败，包含模型返回空内容或答案被 token 上限截断 —— 两者都会先重试一次，§8.1）。
- `GET /{id}/evaluation` 复用同一结构：`pending`/`processing` 返回 202，`completed`/`failed` 返回 200，尚无评价返回 404 `evaluation_not_found`。

### 7.9 获取评价

`GET /api/v1/practice/sessions/{session_id}/evaluation`

- completed：200 + evaluation JSON。
- pending/processing：202 + `{ "status":"processing" }`。
- failed：200 返回状态和可重试提示，或使用明确错误码；实现统一选一种并写契约测试。
- 尚无 evaluation：404 `evaluation_not_found`。

### 7.10 复习项

`GET /api/v1/review-items?status=new&due_before=...&limit=20&offset=0`

`GET /api/v1/review-items/{id}`

`POST /api/v1/review-items`

单条读取的行为约定：响应结构与列表项一致（同一个 DTO，详情页不需要更窄的模型）；不存在或不属于当前用户统一返回 404 `resource_not_found`，不区分「没有」与「别人的」。详情页按 id 直读，不依赖列表缓存 —— 深链、冷启动、应用重装后都必须能渲染。

请求：

```json
{
  "source_session_id":"uuid",
  "source_message_id":"uuid-or-null",
  "item_type":"expression",
  "original_text":"The precision becomes bad.",
  "target_text":"The measurement precision has degraded.",
  "explanation":"Use a precise noun phrase and the verb degrade.",
  "due_at":"2026-10-04T12:00:00Z"
}
```

`PATCH /api/v1/review-items/{id}` 请求仅允许更新 `status`, `due_at`, `success_count`, `failure_count`；禁止通过客户端更改 user_id/source ownership。

### 7.11 语音转写

`POST /api/v1/practice/speech/transcriptions`

Content-Type：`multipart/form-data`；字段 `audio_file`（必填）、`language`（可选，默认 `en`）、`duration_ms`（可选）。

响应 200：

```json
{
  "text": "I worked on a measurement pipeline that improved throughput.",
  "language": "en",
  "duration_ms": 3240,
  "provider": "faster_whisper",
  "model": "distil-large-v3"
}
```

行为约定：

1. 这是**输入法端点，不是消息端点**：只把音频转成文本返回，不创建消息、不修改会话状态、不推进 `turn_count`、不写 `processing_turn_id`。客户端拿到 `text` 后走 §7.6 发送，复用同一套幂等与并发规则。
2. 音频不落库、不进日志、不进 transcript。转写在临时文件上完成，无论成功失败都在响应返回前删除。
3. 上限：单段最长 300 秒、最大 32 MB（均为配置项；v0.4 由 60 秒 / 10 MB 上调，理由与实测要求见 §10.4）。32 MB 覆盖 300 秒 44.1 kHz 单声道 WAV（约 26 MB）与全部 AAC 情况（约 5 MB）；双声道 WAV 会被本上限拒绝，而转写只需单声道，客户端默认上传 AAC；接受 `audio/m4a`、`audio/aac`、`audio/wav`、`audio/mpeg`、`audio/ogg`。超限返回 413 `payload_too_large`，格式不支持返回 415 `unsupported_media_type`。
4. 未识别出有效语音时返回 422 `speech_not_recognized`，而不是返回空文本 —— 客户端据此提示重录，避免生成空消息。
5. 转写 provider 超时返回 504 `ai_provider_timeout`，上游异常返回 502 `ai_provider_error`；客户端可重试同一段音频。
6. 该端点不接收 `session_id`，与会话解耦。若将来要把转写绑定到场景上下文（例如用场景提示词提升专有名词准确率），必须重新定义契约，不得直接加字段。
7. 转写结果不进入任何历史记录，客户端不得把它当持久数据（同 §10.2）；最终以发送的文本为准。

### 7.12 错误码清单

| HTTP | code | 含义 |
|---:|---|---|
| 400 | invalid_request | JSON/参数格式不合法 |
| 404 | resource_not_found | 资源不存在或不属于当前用户 |
| 409 | session_not_active | session 已结束/放弃 |
| 409 | turn_in_progress | 同 session 有另一轮正在生成 |
| 409 | session_has_no_user_turns | 没有可评价的用户发言 |
| 409 | session_is_not_a_meeting | 单角色场景不能推进（§7.14） |
| 409 | advance_limit_reached | 本场会议的旁听额度已用尽（§7.14） |
| 409 | session_has_user_turns | 有学习者发言时不允许放弃，应走 finish（§7.15） |
| 413 | payload_too_large | 文本、请求或音频超限 |
| 415 | unsupported_media_type | 音频格式不在允许列表内 |
| 422 | validation_error | 字段校验失败 |
| 422 | speech_not_recognized | 音频中未识别出有效语音 |
| 502 | ai_provider_error | 上游 AI 错误/无效响应 |
| 503 | service_unavailable | 数据库或依赖暂时不可用 |
| 504 | ai_provider_timeout | AI 调用超时 |

不得向客户端返回 Python traceback、SQL、内部路径、API key 或供应商原始凭据。

### 7.13 语音合成（TTS）

`POST /api/v1/practice/speech/synthesis`

请求体 `application/json`：`{"text": "...", "voice": "en_US-lessac-medium"}`。`voice` 取自会话详情里 `participants[].voice`（§9），客户端不保存音色目录副本。

响应 200：**直接返回音频字节**，`Cache-Control: no-store`。不套 JSON 信封 —— 客户端要把响应直接交给播放器，包一层只会多一次解码。`Content-Type` 由 provider 决定（默认 Piper → `audio/wav`；edge-tts → `audio/mpeg`），客户端**按 Content-Type 决定落盘扩展名** —— 写死 `.mp3` 的播放器会拒绝 RIFF 数据。

行为约定：

1. 这是**输出法端点，不是消息端点**：不创建消息、不修改会话状态。会议里的发言在生成时就已入库（§7.7），把一句话读出来不产生任何新状态。
2. **合成音频不落盘、不进数据库、不缓存**（会议草案 §9.2）：音频只作为响应体存在，服务端不留副本，也不允许端上/中间层缓存（`no-store`）。代价是重放要重新合成 —— 实测本机 Piper 单句 0.15–0.25 秒（首次调用另加 0.69 秒模型加载），可接受。
3. 与会话解耦，理由同 §7.11 规则 6：读一句话不依赖场景，绑定会话是契约变更而不是加字段。
4. 不可朗读的输入在调用供应商**之前**就拒绝：文本去空白后为空、超过 `SPEECH_SYNTHESIS_MAX_CHARS`（默认 1000，会议单条发言上限 60 词远低于此）、或 `voice` 不在服务端音色目录内，一律 422 `validation_error`。音色目录在服务端，客户端传错名字必须立刻失败，而不是变成一个「按下没反应」的按钮。
5. 供应商超时 504 `ai_provider_timeout`，上游异常 502 `ai_provider_error`；客户端可重试同一句。
6. 错误响应（4xx/5xx）是 JSON（§7.12 的统一错误信封），成功响应才是音频。客户端按 `Content-Type` 分流。

### 7.14 会议推进（旁听）

`POST /api/v1/practice/sessions/{session_id}/advance`，请求 `{"after_seq": 12}`。

用于**学习者不发言、只听**的场合（会议草案 §12）：让房间里的人自己把讨论往下推。

响应 200：

```json
{
  "assistant_messages": [ { "...": "同 §7.7 的消息结构" } ],
  "session_status": "active",
  "advances_remaining": 9
}
```

行为约定：

1. **不是消息端点**：不创建用户消息、不动 `turn_count`、不改变会话状态。房间里说的话作为**独立的一轮**写入（`turn_index` 递增），一个事务内落库，`seq` 连续（同 §9.3）。
2. 单角色场景返回 409 `session_is_not_a_meeting` —— 对面只有一个人，没有「他们继续聊」这回事。
3. 会话已结束返回 409 `session_not_active`；上一轮还在生成返回 409 `turn_in_progress`；额度用尽返回 409 `advance_limit_reached`。
4. **`after_seq` 幂等**：它是客户端已看到的最大 `seq`。服务端若已超过该位置，返回已写入的发言而不重新调用模型。这样网络重试不会买到第二份模型调用。
5. 额度由 `MEETING_MAX_ADVANCES`（默认 10）封顶，服务端强制执行：沉默不产生无限计费。第 0 轮（开场）不计入。
6. 超时 504 `ai_provider_timeout`，上游异常 502 `ai_provider_error`，均按 §8.1 的规则重试一次。
7. **没有发言就没有评价**：本端点不会为旁听者生成报告（`finish` 仍按既有规则返回 409 `session_has_no_user_turns`）。这是诚实的答案 —— 没有可评的内容，不编造维度。

### 7.15 结束一场没有发言的会话（放弃）

`POST /api/v1/practice/sessions/{session_id}/abandon`，无请求体。

响应 200：`{"status": "abandoned"}`。

**为什么需要它**：旁听会话没有别的出路。`finish` 的作用是生成评价，评价需要学习者的发言，而只旁听的人一句
都没有 —— 于是会话能被打开、却关不掉（这是一个真实 bug：客户端「结束」按钮因 `turn_count == 0` 而禁用，
就算点得动，服务端也会返回 409）。停下来也是一种结束，它应该有对应的接口，而不是逼着学习者编一句话出来。

行为约定：

1. **状态是 `abandoned`，不是 `completed`**。数据库把 `completed` 与「`completed_at` 非空」绑在一起
   （`ck_practice_sessions_status`），而 `completed` 在评价语义里意味着「已出报告」。把无报告的空会话塞进
   `completed` 会让它混进「已完成」里。
2. **幂等**：已经是 `abandoned` 再调一次返回 200 与同样的响应体（把已经关掉的东西关掉，就是调用方想要的结果）。
3. **有学习者发言时拒绝**：返回 409 `session_has_user_turns`。丢弃一份还能生成的评价必须是明确的选择，所以那种
   情况请走 `finish`。已 `completed` 的会话返回 409 `session_not_active` —— 这个接口不能成为绕过报告的暗门。
4. **不生成评价行、不生成维度、不写任何假数据**：记录仍可读（`GET /sessions/{id}` 对 `abandoned` 返回 200）。
5. 未知会话 404 `resource_not_found`（同 §7.12 的越权规则）。

客户端（§10.6）：会议页的「结束」按钮在 `turn_count == 0` 时走本接口，并提前说明「还没有你的发言：结束就是收起
这场会议，不会生成评价」；结束后回到首页，而不是跳进一个没有报告的评价页。

## 8. Roleplay 与 Evaluation AI 设计

### 8.1 Provider 接口

```python
class RoleplayProvider(Protocol):
    async def reply(self, request: RoleplayRequest) -> RoleplayReply: ...

class EvaluationProvider(Protocol):
    async def evaluate(self, request: EvaluationRequest) -> EvaluationResult: ...
```

Service 层只依赖协议，不直接 import 某供应商 SDK。Provider 实现负责：调用、超时、结构化输出解析、供应商异常映射。测试用 `FakeRoleplayProvider` 和 `FakeEvaluationProvider`。

**重试语义（§13.2）**：两个 provider 共用同一套判定，落在共享传输层 `app/ai/openai_compatible_http.py` 的 `ModelEndpointError.retryable` 上：

- 可重试（各重试一次）：空输出或不可用的响应体、5xx、429/408/409/425、传输层错误。
- 不可重试：401/403/422 等被端点拒绝的请求（同样的请求会被同样拒绝）、超时（重试只会把等待翻倍）。
- **可重试：`finish_reason=length`（2026-10-02 修正，原判为不可重试）**。原假设「预算不足，重试只会再截断一次」被实测推翻：deepseek-flash 对**同一个 prompt** 的内部推理长度极不稳定，预算耗尽时可见输出为空。400 token 预算下这是 1/10 的调用（经 API 是 8 次里 2 次），每次都以裸 502 落到学习者面前 —— 比多发一次请求糟。
- **token 预算按实测钉死（2026-10-02）**：可见输出只有 50–150 token，其余全是内部推理，而推理长度是重尾分布。单角色场景（设计评审 prompt，15 次）：中位 326、最大 **3039**，其中 1 次超过 1000；轻场景（酒店前台 15 次）最大 206。会议（3 人 + JSON，12 次）：中位 222、最大 1004，从未触及旧值 1200，但已占 84%。据此 `AI_MAX_TOKENS=2000`、`AI_MEETING_MAX_TOKENS=1600` —— 上限定高不花钱（不生成的 token 不计费），定低则要在尾巴上付「先截断、再重试」的双份延迟。
- 超时永不重试：一个超时已经花掉一整个窗口，再试一次是把学习者的等待翻倍 —— 由调用方映射为 504，人工重试路径在 §9.2。
- 重试只在同一轮内发生，不重放用户消息；§9.3 的 `client_message_id` 仍是唯一防重复写入的防线。

### 8.2 Roleplay 输入

```text
- 固定产品安全/行为规则
- 场景 roleplay_instructions
- 场景快照与 user_objective
- 最近对话历史
- 用户当前消息
```

Roleplay 输出只包含下一句角色回复（可选内部结束标记）；不得返回打分、语法纠错或完整示范答案。每轮 AI 回复原则上 1–3 句，保持自然追问，不在角色中途跳出授课。

### 8.3 Evaluation 输出 Schema

```json
{
  "rubric_version": "english-communication-v1",
  "summary": "A concise, evidence-based summary.",
  "dimensions": {
    "clarity": {
      "rating": "strong|developing|needs_work",
      "evidence": ["Exact or clearly attributable excerpt from user speech."],
      "feedback": "One actionable point."
    },
    "fluency": {"rating":"...","evidence":[],"feedback":"..."},
    "naturalness": {"rating":"...","evidence":[],"feedback":"..."},
    "professional_tone": {"rating":"...","evidence":[],"feedback":"..."},
    "response_relevance": {"rating":"...","evidence":[],"feedback":"..."}
  },
  "strengths": ["..."],
  "improvements": ["..."],
  "suggested_rephrases": [
    {"original":"...","suggestion":"...","reason":"..."}
  ],
  "review_items": [
    {"item_type":"expression|grammar|clarity|communication","original_text":"...","target_text":"...","explanation":"..."}
  ]
}
```

解析规则：字段缺失、rating 越界、数组过长、引用不属于 transcript 等应拒绝或规范化，并记录 `invalid_ai_output`；不能把未经校验的模型 JSON 直接送前端。

### 8.4 评价标准

- 只引用用户自己的发言作为语言证据；不能把 AI 台词冒充用户表达。
- 反馈优先级：是否回答问题 → 信息组织/清晰度 → 自然度/语法细节。
- 一次评价最多给 3 个主要改进点，避免堆砌纠错。
- 技术问题答错不等于英语差；若影响沟通清晰度，可以指出“表达未说明依据”，但不判技术正确性。
- 建议重写不得改变用户原意；无法确认意图时提出澄清，不臆造技术事实。
- 保存 `provider`, `model`, `prompt_version`, `rubric_version`，用于复现与后续评估。

实现约定（2026-10-02 实测）：

- 评价 provider 的 token 预算与超时独立配置（`AI_EVALUATION_MAX_TOKENS` / `AI_EVALUATION_TIMEOUT_SECONDS`），不沿用 roleplay 的值。
- 实测（`deepseek-flash`）：一次评价消耗 2000–2800 completion tokens，其中约一半是模型内部推理开销、不产生可见输出，且逐次浮动。预算贴近这个平均值就会得到空输出或半截 JSON；默认 4000 是留了余量的值。
- 空输出与「输出通不过 §8.3 校验」是瞬时故障（同一请求换个时刻即成功），provider 内部各重试一次；**超时不重试**——已经等满一个超时窗口，重试只会让用户等两倍。两次都失败才写 `failed`，交给 §9.2 的显式 retry。
- 实测延迟：三轮对话后生成评价约 13–15 秒（本机直连 DeepSeek）。

### 8.5 Prompt 版本管理

Prompt 文件放在 `backend/app/ai/prompts/`，以明确版本名保存，例如：

```text
roleplay_v1.txt
evaluation_english_v1.txt
```

Prompt 内容只通过场景的受控字段拼接；用户输入视为不可信文本，不能让其覆盖 system/developer 规则。修改评价定义时更新 prompt/rubric version，并新增回归样例。

### 8.6 Speech 转写设计

```python
class SpeechProvider(Protocol):
    async def transcribe(
        self, audio: bytes, *, content_type: str, language: str
    ) -> TranscriptResult: ...
```

`TranscriptResult` 至少含 `text`、`language`、`duration_ms`、`provider`、`model`。与 §8.1 同规则：Service 只依赖协议，测试用 `FakeSpeechProvider`；真实实现负责超时、异常映射与输出校验（空文本、非目标语言、重复幻觉片段）。

实现选择（本版已定）：

- **服务端转写，不做设备端。** 两个理由：一是国内 Android 机型普遍缺少可用的系统语音服务，设备端方案的可用性不成立；二是 §3.1 已定客户端不持有模型与密钥，端上跑 Whisper 还要把模型塞进安装包。
- 本期实现为本机 `faster-whisper`（CUDA，量化推理）。个人使用阶段音频不出本机，无 per-minute 成本，也不依赖境外网络。GPU 不可用时回退 CPU 或更小模型，由配置决定。
- **已实现（2026-10-02）**：`app/ai/speech.py`（协议 + Fake）、`app/ai/faster_whisper_speech.py`（本机实现）、`app/api/speech.py`（§7.11 端点）。默认 `SPEECH_MODEL=small.en`、`SPEECH_COMPUTE_TYPE=int8`；模型首次使用时加载（不是 import 时），解码跑在线程里，空闲不占 GPU。
- **实测（2026-10-02，i5-10300H 8 线程，small.en / CPU int8）**：17.4 秒音频 1.7 秒转完（10.0x 实时），313 秒音频 26.9 秒转完（11.6x 实时），文字与合成原文逐字一致。据此 `SPEECH_TIMEOUT_SECONDS=180` 对 300 秒上限有约 6.7 倍余量，保留该值。
- **CUDA 路径的坑**：CTranslate2 按自身构建参数判定 CUDA 可用性，不看机器上有没有运行库 —— 实测 `SPEECH_DEVICE=auto` 会选中 CUDA、模型加载成功、然后在第一次编码时抛 `libcublas.so.12 is not found`。实现因此在推理期捕获「缺库」错误并在 CPU 上重建模型重跑同一段音频（有测试盯着），避免配错一次之后每段音频都 502。
- 云 STT 不属本期实现，但协议保持供应商无关：换云服务只需新增一个 `SpeechProvider` 实现，API 契约不变。
- 转写与 Roleplay / Evaluation 是彼此独立的 provider，超时分别配置；转写失败不得映射为会话状态变化。
- 转写超时不得沿用 Roleplay 的 AI_TIMEOUT_SECONDS：§7.11 允许单段 300 秒音频，CPU 回退路径下顺序解码可达分钟级，30 秒级超时是必然失败。用独立的 SPEECH_TIMEOUT_SECONDS，初值在 Phase 5 按实测最坏耗时上浮后写定；超时返回 504，客户端可重试同一段音频。
- 不做流式识别。一期是“录完 → 整段转写”，流式属于 §1.4 的不做范围。

转写无 prompt，不适用 §8.5 的 prompt 版本管理，但 `provider` / `model` 必须随结果返回并记入指标，便于在准确率回归时定位模型变更。

**语音合成（输出侧，§7.13）**：

```python
class SpeechSynthesisProvider(Protocol):
    async def synthesize(self, text: str, *, voice: str) -> SynthesisResult: ...
```

`SynthesisResult` 含 `audio`（bytes）、`content_type`、`voice`、`provider`、`model`。与转写同规则：Service 只依赖协议，测试用 `FakeSpeechSynthesisProvider`（返回**可播放的静音 WAV**，不是占位字节 —— mock 模式下手机要真的能播，否则客户端 bug 会被「反正 mock」掩盖）。

- **已实现（2026-10-02）**：`app/ai/speech_synthesis.py`（协议 + Fake）、`app/ai/piper_synthesis.py`（本地实现，当前默认）、`app/ai/edge_tts_synthesis.py`（云端实现，保留）、`app/ai/synthesis_factory.py`（三选一：mock / piper / edge_tts）、`app/services/speech_synthesis.py`、`app/api/speech.py` 的 §7.13 路由。音色目录在 `app/ai/voices.py`（8 个 Piper 英文音色，美/英，男女各半），按 key 确定性分配（会议草案 §9.1）。
- **选型：piper（第二版，当前默认）。** 第一版 edge-tts 的「直连可用、不需要代理」在**延迟**上不成立：实测本机单句 **6.4–10.1 秒**，其中到微软端点的 TLS 握手本身就占 3.3–4.1 秒，且会间歇性连接超时（三次测速 2.1 / 10.3 / 3.4 秒）；走代理 6.4 秒。对一个「几百毫秒」的预算，这是选型问题不是调优问题。Piper 在本机跑 ONNX 音色：**零网络、零密钥、零外部依赖**，模型加载 0.69 秒，单句合成 0.20 秒（20.7–22.0x 实时）。协议不变、只换实现 —— 这正是当初把合成藏在协议后面的目的。
- **音色目录与合成器绑定**：`VOICE_CATALOG` 里的名字属于当前配置的合成器，因此 edge-tts id 不再出现。库里已存的旧 id 由读路径（`scenario_cast`、`participant_payloads`）确定性修复成一个目录音色，不会变成「念不出来的会话」。
- **实测闭环（2026-10-02）**：第一版 edge-tts 三个音色各合成同一句 → 各自的 MP3（32/36/42 KB，5.3/6.0/7.0 秒）→ 再喂回 §7.11 转写端点 → **三个都逐字还原原文**。第二版 Piper 同样闭环通过：`audio/wav`、RIFF 容器合法、本地合成 0.29–1.18 秒，7.2 秒音频转写逐字还原（`en_US-lessac-medium`）。
- 合成**不落盘、不缓存**（§7.13 规则 2，会议草案 §9.2）：服务端不留副本，响应带 `Cache-Control: no-store`。要改成缓存必须先立 ADR 回答「留多久、谁能删」。
- 合成与转写是两个独立 provider、两个独立超时（合成 30 秒 vs 转写 180 秒），理由同前：两者的耗时形态完全相反（一句话几百毫秒 vs 一段音频几十秒）。

## 9. 会话状态与一致性

### 9.1 Session 状态机

```text
ACTIVE ──finish──> COMPLETED
  │
  └──abandon/expiry──> ABANDONED
```

终态不可返回 ACTIVE。已完成 session 的 finish 请求返回原状态；已放弃 session 的消息请求返回 409。

### 9.2 Evaluation 状态机

```text
PENDING → PROCESSING → COMPLETED
                   └→ FAILED → PROCESSING（显式 retry）
```

同一 session 只能有一条 evaluation 行。

### 9.3 Turn 写入一致性

外部 AI 调用不可与数据库事务保持原子性。实现采用“幂等键 + pending 消息 + 短事务 + 可重试”而不是假设外部调用能回滚：

1. 事务 A：确认 session active、确认无 processing turn、创建用户消息 pending、设置 processing_turn_id；提交。
2. 调用 provider（事务外）。会议场景下 provider 一次返回 1–3 条发言。
3. 成功时事务 B：用户消息标记 completed、插入 assistant message、更新计数/时间、清 processing_turn_id；提交。
4. provider 失败时事务 B：用户消息标记 failed、清 processing_turn_id；保留同 client_message_id 重试依据。
5. 复用 client_message_id 的重试不得追加第二条用户消息；若已成功则返回原用户/助手消息；若失败则重新请求 provider。
6. 每一步按状态条件更新，防止并发请求重复完成同一轮。

## 10. 移动端页面与客户端设计

### 10.1 MVP 页面

1. **Home**：继续练习、今日建议场景、最近练习；不显示虚假能力分数。
2. **Scenario List**：分类筛选（Interview / Workplace / Travel & Life）、岗位和难度筛选。
3. **Scenario Detail**：Situation、AI 角色、练习目标、预计时间、开始按钮。
4. **Practice**：对话列表、文本输入、发送状态、结束按钮；防止发送中重复点击。会话的场景有 `cast`（会议）时，同页顶部显示与会者条、每条 AI 消息带发言人名字与颜色、同一人连续发言视觉成组。**不为会议另开页面**：outbox、失败重试、`client_message_id` 那套逻辑复制一份必然漂移，差异是 props 不是页面。语音输入（§10.4）与语音播放（§10.5）都挂在同一页：开麦按钮在输入框左侧，标题栏有「有声/静音」，每条 AI 气泡可单句朗读。
5. **Evaluation**：总结、优势、最多 3 个改进、原句与改写、加入复习按钮。
6. **Review List**：待复习表达、状态、练习结果；卡片可点入详情。
7. **Review Detail**：一条复习项的完整内容 —— 用户原话、推荐表达、解释、复习记录（记住/忘了次数、下次复习、加入时间），以及返回来源练习反馈的入口（`source_session_id`）。在此页也可直接标记「记住了 / 还没记住」，与列表页共用同一套间隔阶梯。
8. **Profile / Settings**：目标公司/岗位、API 环境状态、清理本地缓存。

### 10.2 客户端目录约定

```text
apps/mobile/src/
├── api/                 # fetch wrapper、错误类型、DTO
├── components/          # Button、Loading、ErrorView 等
├── features/
│   ├── scenarios/{api,components,hooks,types}/
│   ├── practice/{api,components,hooks,types}/
│   ├── evaluation/{api,components,types}/
│   └── review/{api,components,hooks,types}/
├── storage/             # 本地设置/非敏感缓存
└── theme/
```

客户端不将 AI 对话当作可靠的本地持久数据源；服务端成功保存后再确认发送状态。网络失败时保留输入草稿，使用原 `client_message_id` 重试。

### 10.3 发送消息交互

- 点击发送后立即禁用该会话的再次提交按钮，显示等待状态。
- 成功：追加服务端返回的 user_message 与 assistant_message。
- 超时：显示可重试状态，保留文本与 client_message_id；重试走幂等 API。
- 409 turn_in_progress：轮询 session/提示等待，不新建 client_message_id 重发。
- 401/403（未来启用鉴权）：按认证失效流程处理，不无限重试。
- App 被杀后恢复：GET session，使用服务端消息重建界面。

### 10.4 麦克风开麦（语音输入）

**交互模型：麦克风按钮 toggle —— 点一次开麦，再点一次闭麦。不用按住说话。**

为什么不是按住说话（v0.4 修订，2026-10-02）：

- 练习目标是会议发言与技术岗位面试的成段表达，一段回答 30–90 秒是常态。按住说话要求手指全程不松，会干扰说话本身，而流利度正是训练目标。
- 线上会议与会议软件的通行形态是麦克风开麦/闭麦，不是按住说话。练的是会议发言，操作形态就该与会议一致，肌肉记忆可迁移。
- 本产品的产物是文本回填输入框（§7.11 是输入法端点，不是消息端点）。按住说话借的是“微信语音消息”的手势外壳，与“转写后先人工确认再发送”的语义并不匹配。

交互：

```text
点击输入框右侧麦克风 →（首次）申请录音权限 → 开始录音，麦克风呈红色激活态，显示计时与电平
  ├─ 再次点击麦克风  → 结束录音 → 上传转写 → 文本回填输入框 → 用户可改 → 发送
  ├─ 达到 300 秒上限 → 自动结束录音，其余同上（已录内容不丢弃；最后 30 秒 UI 变色提示）
  └─ 系统中断（切后台 / 锁屏 / 来电 / 音频焦点被抢占）→ 立即结束录音并转入转写，已录内容不丢弃
```

约定：

- 语音是输入方式：转写文本先回填输入框，而不是直接发消息，用户能先修正识别错误再发送。练英语时这是优点，不是妥协。**例外（2026-10-02 定）：Meeting 页直接发送** —— 会议模拟里停下来改错会打断发言节奏，而识别错误在会议语境里可以用重说一遍自然纠正；发送失败仍按 §10.3 保留草稿与同一个 `client_message_id`，`speech_not_recognized` 不发送并提示重录。判定入口是会话走的是 Practice 还是 Meeting 页，不是全局开关，见 `docs/meeting-mode-v0.1.md` §10。
- 不设“上滑取消”：toggle 模式没有松手这个动作；而且产物只是回填输入框，用户不满意直接清空重录，不需要专门的取消手势。（v0.4 删除原上滑取消。）
- 忘记闭麦是 toggle 模式独有的失败模式，只能由客户端兜住：300 秒硬上限 + 上一条的系统中断处理，不依赖用户记得回来点第二次。最后 30 秒给 UI 提示，避免一句话在结尾被硬切。
- 录音状态必须显式可视化：红色激活态 + 计时 + 电平。这是原来由手指按住提供的物理反馈的替代，不是装饰。
- 录音期间禁用该会话的输入框与发送按钮，避免“边录边说边发”的状态歧义。
- 300 秒是设计值，不是实测值：本机为 GTX 1660 Ti（6 GB） + i5-10300H（4 核 8 线程），Phase 5 必须分别实测 GPU 路径与 CPU 回退路径下转写 300 秒音频的耗时与显存/内存占用。若单段耗时超出可接受范围，回退上限或改为分段上传；不得用静默截断音频来掩盖。
  - **实测（2026-10-02）**：CPU 回退路径（small.en / int8）转 313 秒音频耗时 26.9 秒（11.6x 实时），300 秒上限保留。
  - **决定（2026-10-02）**：本机固定 `SPEECH_DEVICE=cpu`，不启用 GPU 路径。理由：CPU 已比实时快 11.6 倍（300 秒音频 27 秒转完），而 CUDA 路径要额外装约 1.2 GB 运行库（cuBLAS + cuDNN），且 CTranslate2 会谎报 CUDA 可用（见 §8.6），收益为零、风险不小。将来若为准确率换 `large-v3` / `distil-large-v3` 导致 CPU 太慢，再装运行库并补测 GPU 耗时 —— 届时这份文档要补上实测值，不许默认 GPU 更快。
- 不做后台录音：切后台或锁屏即结束录音并转入转写（见上一条），因此不申请 Android 前台服务，也不需要 Android 14 的前台服务类型声明。转写若在切后台时尚未完成，回前台后接续显示“识别中”。
- 整段转写不需要客户端切分：faster-whisper 内部按固定窗口顺序解码长音频，客户端只上传一个文件。把“一次开麦”拆成多段转写再拼接是体验改动，须先改本节。
- 本版不做语音活动检测（VAD）自动断句：静音自动停止会引入“一句话说到一半被截断”的新失败模式，且属于 §1.4 排除的范围。若 300 秒上限在真实使用中频繁触发，再单独评估。
- 权限：`RECORD_AUDIO`，首次点击麦克风时申请；被拒后给一次性说明并回退到手动输入，不反复弹窗。
- 录音格式 `m4a`/AAC（`expo-audio` 默认输出），落在 §7.11 的允许格式内，客户端不需要转码。
- 转写中状态：输入框禁用、显示“识别中”，允许取消；取消要中止上传。
- 转写失败（504 / 502 / 422）：把录音文件留在本地缓存，提示“重录”或“重试”；重试上传同一文件，不要求用户重录。
- 发送失败：复用 §10.3 的重试规则与同一个 `client_message_id`，录音与文本草稿一并保留。
- 本地只保留最近一条自定义录音，发送成功后删除；转写文本的持久化只走服务端。
- 上传前先按 §7.11 的上限校验时长与体积，超限本地直接提示，省一次必然失败的往返。

### 10.5 语音播放（语音输出）

- **已实现（2026-10-02）**：AI 的每条发言都可以被读出来。客户端拿到 `participants[].voice`（§9）后按顺序合成与播放，一句播完再播下一句 —— 三个人同时说话是噪音，不是会议。
- **顺序播放 + 队列**：一轮里 AI 可能发 1–3 条，客户端把它们排成一队依次合成（§7.13 是「一句一请求」），当前这句播完才轮到下一句。
- **打开麦克风必须停播**（草案 §9.2）：不是优化。扬声器还在响的时候开麦，学习者会把 AI 的声音录进自己这一轮。
- **不缓存音频**：服务端只在一个请求里存在这段音频（§7.13 规则 2），所以重播就是重新合成（1–2 秒，免费）。客户端把字节写进自己的缓存目录交给播放器，播完即删；删不掉也不影响使用（系统会回收缓存目录）。
- **进入会话不朗读历史**：第一次拿到消息时只把它们标记为「已听过」，之后新到的才入库播放。否则进一个十轮的会话，手机会先独白一分钟。
- **静音开关放在标题栏**（有声 / 静音）；静音只拦自动播放，手动点「朗读」仍然生效 —— 手动意图高于开关。
- **单条可以在气泡上点「朗读」/「停止」**：会议里漏听一句是常态，重播必须是一下点击，不是「重新发一遍让你再说一次」。
- **合成失败不阻塞队列**：语音是增强项，一句读不出来不该让剩下的回答全没声音。失败只在页面底部提示一行，轮次与文字都在。
- 音频路由：`playsInSilentMode` + `duckOthers`（语音练习要能在静音档下出声，且压低别的音频而不是抢焦点）。
- 不做：语速/音色选择、逐词高亮、下载留存离线听（属 §1.4）。

### 10.6 旁听（会议里只听不说）

- **已实现（2026-10-03）**：会议页多一个「旁听」开关（只在与会者 > 1 且会话进行中时出现）。打开后客户端按 §7.14 反复推进会议，你只听：房间里的人自己往下讨论，谁也不会向你提问。
- **推进等语音播完**（§10.5 的自然推论）。听到内容是旁听的全部意义；文字跑到声音前面就变成速读。每轮拿到新发言后先给 700 ms 让合成开始，再每 400 ms 检查一次播放队列，空了才推进下一轮。静音或没有音频时退化为固定 900 ms 的间隔。
- **开口即结束旁听**：点「开麦」或直接发一句话都会停掉推进 —— 你要发言了，就不再是旁听。停掉之后想接着听，再点一次「旁听」。
- **额度可见**：按钮旁边显示「只听不说 · 还能推进 N 次」。数字来自服务端的 `advances_remaining`，不是客户端自己数的 —— 上限属于服务端（§7.14 规则 5）。
- **额度用完**或会议讨论完了：停止推进并给一句明确的话（「说一句，或者结束这场会议」），而不是静默失败。
- **旁听会话没有评价**：`finish` 仍按既有规则返回 409 `session_has_no_user_turns`，页面提示「这次你只旁听，没有可评价的发言」。不编造维度、不生成假报告。
- **单次推进最多 1–3 条发言**，与说话时的一轮一致；因此一次「旁听」大约覆盖 5–8 分钟的会议（`MEETING_MAX_ADVANCES=10`）。

## 11. 配置、密钥与环境

### 11.1 Backend 环境变量

`.env.example` 只放空值/示例值，不提交真实 `.env`：

```dotenv
APP_ENV=local
APP_NAME=voxora-api
API_V1_PREFIX=/api/v1
DATABASE_URL=postgresql+asyncpg://voxora:voxora_dev_only@localhost:5432/voxora
LOCAL_USER_ID=10000000-0000-4000-8000-000000000001
API_ACCESS_TOKEN=
AI_PROVIDER=mock
AI_BASE_URL=https://api.deepseek.com/v1
AI_API_KEY=
AI_MODEL=
AI_TIMEOUT_SECONDS=30
AI_MAX_TOKENS=2000
AI_MEETING_MAX_TOKENS=1600
MEETING_MAX_ADVANCES=10
AI_JSON_MODE=true
AI_EVALUATION_TIMEOUT_SECONDS=60
AI_EVALUATION_MAX_TOKENS=4000
SPEECH_PROVIDER=mock
SPEECH_MODEL=small.en
SPEECH_DEVICE=auto
SPEECH_COMPUTE_TYPE=int8
SPEECH_TIMEOUT_SECONDS=180
SPEECH_MAX_SECONDS=300
SPEECH_MAX_BYTES=33554432
SPEECH_SYNTHESIS_PROVIDER=mock
SPEECH_SYNTHESIS_PIPER_DIR=
SPEECH_SYNTHESIS_MP3_BIT_RATE=0
SPEECH_SYNTHESIS_TIMEOUT_SECONDS=30
SPEECH_SYNTHESIS_MAX_CHARS=1000
MAX_USER_MESSAGE_CHARS=4000
MAX_CONTEXT_MESSAGES=24
LOG_LEVEL=INFO
```

生产环境密钥通过部署平台 Secret 管理，不写入 Git、客户端包、日志或场景数据。配置通过 Pydantic Settings 校验；缺少生产必需配置时启动失败。

### 11.2 Mobile 环境变量

```text
EXPO_PUBLIC_API_BASE_URL=http://10.0.2.2:8000/api/v1
```

`EXPO_PUBLIC_*` 会进入客户端构建，不能放服务端密钥。

未设置时的平台默认值：Android `http://10.0.2.2:8000/api/v1`（模拟器访问宿主机），其余（web 预览、
iOS 模拟器）`http://127.0.0.1:8000/api/v1`。真机必须在 `apps/mobile/.env.local` 写开发机的局域网 IP，
并在后端 `.env` 设置 `API_ACCESS_TOKEN`：非 loopback 客户端要带 `Authorization: Bearer <token>`。

## 12. 安全与隐私

- HTTPS 是非本机环境的强制要求；开发 HTTP 仅限本地设备/模拟器。
- 未认证的本地 MVP 不可绑定公网 IP，也不可部署为公开服务。
- 上线前实现 Auth；每条用户私有资源查询均使用 `current_user.id` 作为条件，不信任客户端传来的 user_id。认证契约（邀请码、设备令牌、配额与限速、跨用户隔离规则）见 `docs/multi-user-v0.1.md`（Draft v0.1，未实现）。
- AI API key 仅存在后端；错误日志须过滤 Authorization、API key、连接串。
- 用户输入、Prompt 和 AI 输出均是不可信内容；渲染时做文本安全处理，不执行 HTML/脚本。
- 初版不保存音频。语音迭代上传的音频仅用于一次转写，在响应返回前删除，不落库、不进日志（§7.11）；将来若要保存音频，需单独记录用户同意并提供撤回/删除路径。
- 用户可删除练习历史和账户数据；保留期限与备份中的删除时限需在上线前写入隐私说明。
- AI 生成内容标识为训练模拟，不声称代表指定公司的内部流程或官方面试题。

## 13. 日志、监控与错误处理

### 13.1 结构化日志字段

```text
timestamp, level, request_id, route, method, status_code,
latency_ms, user_id(optional), session_id(optional), error_code,
ai_provider, ai_model, prompt_version
```

默认不记录完整 transcript 和原始音频。调试个人数据时应显式启用本地 debug logging，且不得用于生产。

语音转写只记录 `audio_duration_ms`、`transcript_provider`、`transcript_model` 与结果状态；不记录音频内容，也不记录转写全文。

### 13.2 超时与重试

- DB 超时与 AI 超时分别配置。
- AI 请求仅对明确可重试的网络错误/限流做有限退避重试；不可对用户消息重复落库。上限一次，且只在同一轮内重试。
- 可重试集合：空/不可用响应体、5xx、429/408/409/425、传输层错误、`finish_reason=length`（理由见 §8.1：同 prompt 的推理长度不稳定，截断是抽签不是请求属性）。不可重试集合：401/403/422 等被端点拒绝的请求、超时。
- 不对 4xx 输入错误重试。
- 记录 provider 延迟、错误率、token/cost（若可取得）；MVP 可先只记录请求耗时和 provider/model。

## 14. 测试与质量门禁

### 14.1 测试层级

- Unit：SessionService 状态规则、评价 JSON 校验、review item 生成、idempotency。
- Repository：CRUD、唯一约束、外键、排序/筛选；使用独立 PostgreSQL 测试库。
- API：HTTP 状态、Schema、错误码、归属校验、重试行为。
- Provider contract：Fake Provider 返回合法/非法 JSON、超时、限流、空响应。
- E2E：Android 创建 session → 发多轮消息 → finish → 查看评价 → 保存复习项。

### 14.2 必须覆盖的边界测试

1. 空白消息拒绝。
2. 同一个 client_message_id 重复发送不生成重复消息，也不重复扣 AI 成本。
3. 两个并发 turn 只有一个成功获得 session lock。
4. Provider 超时后锁被释放，用户可安全重试。
5. Completed/abandoned session 不接受新消息。
6. 无用户发言的 session 不可评价。
7. Scenario 被归档后不可新建 session；既有 session 可读历史快照。
8. 越权访问返回统一 404。
9. AI 输出缺字段或引用非用户原话时不作为有效评价保存。
10. Alembic 从空数据库迁移成功。
11. 转写端点只返回文本：不创建消息、不改变 session 状态、不推进 turn_count。
12. 超过时长/体积上限的音频返回 413；不支持的格式返回 415；无有效语音返回 422 而不是空文本。
13. 转写失败不影响会话：同一段音频可重试，会话仍可继续发送文本。
14. 空文本、超长文本、目录外音色在调用供应商前返回 422；成功响应是音频且带 `Cache-Control: no-store`；失败响应仍是 JSON 错误信封。
15. 合成失败与超时（502/504）不写任何东西，重试同一句可成功；一段音频的合成请求不得产生消息或会话状态变化。

### 14.3 本地质量命令（项目初始化后固定）

具体命令由 `pyproject.toml` 和 package scripts 落地，至少包括：

```text
backend: format/lint/typecheck/test
mobile: lint/typecheck/test
infra: migration check + compose health check
```

CI 至少执行格式/静态检查、后端测试和移动端 TypeScript 检查；真实 AI API 测试不得作为每次 PR 的必需门禁。

## 15. 本地开发与 PyCharm 调试

### 15.1 启动顺序

1. 在 `infra/docker-compose.yml` 启动 PostgreSQL。
2. 在 PyCharm 打开 `backend/`，配置项目 Python Interpreter/虚拟环境。
3. 设置 Backend Run Configuration：模块 `uvicorn`，参数 `app.main:app --reload --host 0.0.0.0 --port 8000`，工作目录 `backend/`，加载本地 `.env`。
4. 运行 `alembic upgrade head` 和可重复 seed。
5. 在 `app/services/practice_service.py`、API endpoint 或 AI adapter 设断点。
6. 用 Swagger `/docs` 或 Android Emulator 发请求；检查变量、调用栈和 DB 状态。
7. 修改 DB Model 后创建 migration，再运行 migration 与测试。

### 15.2 PyCharm 断点建议

优先在以下边界设置断点，而不是只在路由入口：

- `PracticeService.send_message()`：检查 session 状态、幂等和消息顺序。
- `RoleplayService.generate_reply()`：检查上下文构造与 Provider 输出。
- `EvaluationService.evaluate_session()`：检查 transcript、rubric 和 Pydantic 解析。
- Repository 写入方法：检查 ORM entity 与事务状态。

禁止在提交代码中遗留 `breakpoint()`、硬编码 API key 或真实用户内容日志。

## 16. 部署形态（MVP）

本地：

```text
Android Emulator / Device
          ↓
PyCharm local FastAPI
          ↓
Docker PostgreSQL
          ↓
External AI Provider (optional; local Fake Provider for tests)
Local Speech Provider / faster-whisper (optional; FakeSpeechProvider in tests)
```

部署前置条件：Auth、HTTPS、数据库托管与备份、密钥管理、迁移流程、隐私说明、错误监控、成本限额。MVP 阶段不定义具体云厂商，以免在用户验证前引入额外成本/锁定。

## 17. 实施顺序与交付件

### Phase 0 — 仓库与开发环境

交付：目录结构、README、`.env.example`、Compose PostgreSQL、FastAPI health、PyCharm Run Configuration 文档。
验收：本地 `/api/v1/health` 返回 200；数据库连接状态可验证；Fake AI Provider 可启动。

### Phase 1 — Schema 与 Scenario

交付：ORM models、Alembic 初始 migration、seed 场景、scenario list/detail API、Repository/API 测试。
验收：空库迁移 + seed 可重复执行；API 只返回 published 场景。

### Phase 2 — 文本 Roleplay

交付：Session/Message 模型、创建会话、opening line、发送消息、幂等、并发保护、Mock Provider 和真实 Provider adapter。
验收：多轮消息持久化；超时可重试；重启后恢复历史。

### Phase 3 — Evaluation 与复习

交付：Evaluation 模型和状态、结构化输出校验、finish/retry、Review Item CRUD。
验收：评价聚焦英语且有原话证据；失败可重试；同 session 不重复生成记录。

### Phase 4 — Android 客户端

交付：Scenario、Practice、Evaluation、Review 页面与 API client。
验收：从 Android Emulator 完成全闭环；断网/超时提示可恢复；App 重启后会话历史可加载。

### Phase 5 — 个人真实使用与语音试验

交付：首批人工审校场景、练习体验记录、开麦/闭麦语音输入（§7.11 / §8.6 / §10.4）、转写速度与准确率实测（不保存音频）。
状态（2026-10-02）：语音输入与语音合成两端均已实现并实测（§8.6、§7.13）；GPU 路径经评估后放弃（CPU int8 已 11.6x 实时，理由见 §10.4），因此「GPU 与 CPU 回退两条路径」这一条按实测改为**只测 CPU 路径**，理由是收益为零、维护成本不为零。真机验收（Expo Go 上的开麦与播放）待补。
验收：按实际连续使用结果调整 Rubric、场景质量和反馈长度；再决定实时语音与多人测试用户。

### Phase 6 — 会议模式（多角色会议模拟）

设计与实施拆解独立成文：`docs/meeting-mode-v0.1.md`（Draft v0.1）。范围是 AI 扮演多个与会者的**文本会议**（多角色、轮流发言），语音输出单独立项；不做实时音频与 AI 抢话（仍属 §1.4）。本规格的 §6.3、§7.4、§7.6、§7.7、§8.x、§9.3、§10.1 在该草案生效时按其中的对照表成套修订。

### Phase 7 — 多用户（草案，未排期）

设计与实施拆解独立成文：`docs/multi-user-v0.1.md`（Draft v0.1）。范围是让一台后端服务多人（邀请制），
仍是单机部署；不做自助注册、计费、组织/团队。**当前未实现**，动机是将来邀请他人一起练，而不是现在
就需要。本规格的 §3.1、§6.3、§7.12、§10.1、§10.2、§11.2、§12、§14.2 在该草案生效时按其中的对照表
成套修订。

## 18. ADR（架构决策记录）待建事项

遇到改变成本较高的决策时，在 `docs/adr/` 新建编号文档，记录背景、备选方案、决策、后果：

- ADR-001：个人 MVP 的认证边界与公网部署条件。（决策输入已就位：`docs/multi-user-v0.1.md` §2/§4/§12；多用户动工前须把本文落成文件。）
- ADR-002：LLM / Speech Provider、数据区域与成本上限。
- ADR-003：录音是否上传/保存、保留时长和删除机制。（本版已定：上传仅用于单次转写、不保存；将来若要保存，须先补本 ADR。）
- ADR-004：英语评价 Rubric 与人工校准方案。
- ADR-005：同步评价升级为持久任务队列的触发条件。

## 19. 开发前仍需产品确认

这些事项不阻挡本地骨架与文本闭环开发，但对应功能上线前必须明确：

1. 首版是否只由本人使用；是否计划马上邀请外部测试用户。（**若邀请**：实施拆解与认证契约见 `docs/multi-user-v0.1.md`；若只是两三个人，优先选该文 §14.4 的"一人一个实例"路线，零代码改动。）
2. AI 服务商、可接受月成本和可接受响应时长。**响应时长已定（2026-10-02 实测）**：`deepseek-flash` 单轮 roleplay 1.1–2.2 秒，完整评价 13–15 秒，均可接受；月成本待账单累计后确认。
3. 首批 10 个左右高质量场景的清单及人工校对责任。
4. 英语评价使用三档描述还是其他等级；各维度的明确定义。
5. 文本 transcript 的保留/删除方式。
6. ~~语音试验使用设备本地转写还是服务端转写~~ —— **已定（2026-10-02）**：服务端转写，本机 faster-whisper，音频不出本机且仅用于单次转写。若将来改用云 STT，须先补 ADR-002（数据区域与成本上限）。

---

**文档状态说明：** 本版足以启动后端工程骨架、数据库 Schema、REST API、文本 Roleplay 与语音输入（§7.11 / §8.6 / §10.4）的实现。语音的转写位置、音频保留与接口契约已定；仍标记为“待决”的认证、成本与评分校准事项不得被当作已完成设计，实现者应在对应功能开发前更新本文或补充 ADR。
