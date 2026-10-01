# Voxora 软件设计详细规格

> 产品副标题：English for the semiconductor world  
> 文档状态：Draft v0.2（开发规格草案）  
> 日期：2026-10-01  
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
| 首发交互 | 已定 | 文字 Roleplay 闭环先行；语音作为后续迭代，数据模型预留 input_mode |
| 用户范围 | 暂定 | 第一阶段个人私用；部署前不开放公网、不提供匿名多用户服务 |
| AI 评价目标 | 已定 | 评价英语沟通，不评判技术结论正确性 |
| 录音保存 | 已定 | 本版不保存音频；未来启用前另定同意、存储、删除与保留政策 |
| Auth | 暂定 | 本地开发阶段不做完整注册；公网部署前必须加入服务端认证与数据归属校验 |

如要把应用交给他人或部署到公网，必须先完成 Auth、限流、隐私条款、备份和数据删除，不得把无认证开发版直接暴露公网。

## 1. 产品边界与验收目标

### 1.1 产品定位

Voxora 面向希望进入或已在半导体国际化企业工作的工程师，训练真实工作与生活场景中的英语沟通。目标公司覆盖半导体产业链上下游。公司、岗位、技术领域是场景上下文；英语表达能力是学习目标。

第一位用户为产品创建者本人，近期目标为约半年后参加 KLA / ASML metrology 软件工程师或算法工程师面试。长期场景覆盖面试、会议、技术讨论、汇报、客户沟通、商务出差和日常生活。

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
- 实时 WebRTC、多人语音会议、音频实时分析。
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

### 3.2 本地网络约定

- Android Emulator 访问宿主机 API 时，开发配置默认 `http://10.0.2.2:8000`。
- 真机调试时使用开发机局域网 IP，并确保服务监听 `0.0.0.0`；不得将该设置误用于生产部署。
- PyCharm 本地启动 FastAPI；Docker Compose 初期只启动 PostgreSQL。
- Expo 开发服务器与 FastAPI 是不同进程；分别观察移动端日志和 PyCharm 后端日志。

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
| ai_character | JSONB | name/title/personality/communication_style |
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
| input_mode | VARCHAR(12) | text/voice；MVP 只启用 text |
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
| role | VARCHAR(12) | user/assistant |
| content | TEXT | 文本内容；长度上限由 API 配置 |
| status | VARCHAR(12) | pending/completed/failed |
| audio_metadata | JSONB nullable | MVP 保持 null，不保存音频 |
| created_at | TIMESTAMPTZ | not null |

约束：`UNIQUE(session_id, client_message_id, role)`；`UNIQUE(session_id, turn_index, role)`。AI 回复与用户输入分别各一条记录。

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

返回详细 situation、角色简介、用户目标、目标表达、预估时长。**不返回隐藏的 `roleplay_instructions`、评价标准内部权重或 system prompt。**

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

校验：scenario 必须 published；MVP 只允许 text；初始 AI opening line 作为 turn 0 assistant message 保存并返回，确保 UI 重载后状态一致。

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
    "id":"uuid","client_message_id":"uuid","turn_index":1,
    "role":"user","content":"I worked on a measurement pipeline that...",
    "created_at":"2026-10-01T12:01:00Z"
  },
  "assistant_message": {
    "id":"uuid","turn_index":1,"role":"assistant",
    "content":"What was the main challenge you had to solve?",
    "created_at":"2026-10-01T12:01:03Z"
  },
  "session_status":"active"
}
```

行为约定：

1. content 去除首尾空白；空字符串 422；超过配置长度 413 或 422（实现统一选一种并写测试）。
2. session 不属于当前用户或不存在时统一返回 404，避免泄露资源存在性。
3. session 非 active 时返回 409 `session_not_active`。
4. `client_message_id` 已处理时返回已保存的原结果，不再次调用模型，保证移动网络重试幂等。
5. 同一 session 同时只处理一轮消息；若 `processing_turn_id` 已占用，返回 409 `turn_in_progress`。
6. AI 超时：用户消息保留为 failed/pending 状态，释放 processing lock；返回 502 `ai_provider_timeout`，客户端可用同一个 client_message_id 重试。
7. 对话上下文仅加载当前 session 的场景快照和最近 N 轮消息；N 从配置读取，超限策略为保留开场、最近消息及必要摘要。MVP 首轮不做自动总结，超过 token/字符预算时返回可解释的 `context_limit_reached`，并记录指标。

并发实现要求：使用短事务原子声明 `processing_turn_id`，提交事务后再调用外部模型；不得在等待 LLM 时长期持有数据库事务/行锁。成功后用新短事务写 AI 消息、更新 turn_count 和 last_activity_at、清除 processing 标记。进程崩溃遗留的 processing 状态由请求超时回收；具体超时时长配置化。

### 7.7 获取练习详情/历史

`GET /api/v1/practice/sessions/{session_id}`

返回会话状态、场景快照摘要、按 turn_index 升序的消息、评价状态。所有字段按当前用户做归属校验。消息分页暂不做；若会话长度达到上限再加入游标分页。

`GET /api/v1/practice/sessions?status=completed&limit=20&offset=0`

返回当前用户练习摘要，不包含完整消息正文，避免列表响应过大。

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

### 7.9 获取评价

`GET /api/v1/practice/sessions/{session_id}/evaluation`

- completed：200 + evaluation JSON。
- pending/processing：202 + `{ "status":"processing" }`。
- failed：200 返回状态和可重试提示，或使用明确错误码；实现统一选一种并写契约测试。
- 尚无 evaluation：404 `evaluation_not_found`。

### 7.10 复习项

`GET /api/v1/review-items?status=new&due_before=...&limit=20&offset=0`

`POST /api/v1/review-items`

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

### 7.11 错误码清单

| HTTP | code | 含义 |
|---:|---|---|
| 400 | invalid_request | JSON/参数格式不合法 |
| 404 | resource_not_found | 资源不存在或不属于当前用户 |
| 409 | session_not_active | session 已结束/放弃 |
| 409 | turn_in_progress | 同 session 有另一轮正在生成 |
| 409 | session_has_no_user_turns | 没有可评价的用户发言 |
| 413 | payload_too_large | 文本或请求超限 |
| 422 | validation_error | 字段校验失败 |
| 502 | ai_provider_error | 上游 AI 错误/无效响应 |
| 503 | service_unavailable | 数据库或依赖暂时不可用 |
| 504 | ai_provider_timeout | AI 调用超时 |

不得向客户端返回 Python traceback、SQL、内部路径、API key 或供应商原始凭据。

## 8. Roleplay 与 Evaluation AI 设计

### 8.1 Provider 接口

```python
class RoleplayProvider(Protocol):
    async def reply(self, request: RoleplayRequest) -> RoleplayReply: ...

class EvaluationProvider(Protocol):
    async def evaluate(self, request: EvaluationRequest) -> EvaluationResult: ...
```

Service 层只依赖协议，不直接 import 某供应商 SDK。Provider 实现负责：调用、超时、结构化输出解析、供应商异常映射。测试用 `FakeRoleplayProvider` 和 `FakeEvaluationProvider`。

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

### 8.5 Prompt 版本管理

Prompt 文件放在 `backend/app/ai/prompts/`，以明确版本名保存，例如：

```text
roleplay_v1.txt
evaluation_english_v1.txt
```

Prompt 内容只通过场景的受控字段拼接；用户输入视为不可信文本，不能让其覆盖 system/developer 规则。修改评价定义时更新 prompt/rubric version，并新增回归样例。

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
2. 调用 provider（事务外）。
3. 成功时事务 B：用户消息标记 completed、插入 assistant message、更新计数/时间、清 processing_turn_id；提交。
4. provider 失败时事务 B：用户消息标记 failed、清 processing_turn_id；保留同 client_message_id 重试依据。
5. 复用 client_message_id 的重试不得追加第二条用户消息；若已成功则返回原用户/助手消息；若失败则重新请求 provider。
6. 每一步按状态条件更新，防止并发请求重复完成同一轮。

## 10. 移动端页面与客户端设计

### 10.1 MVP 页面

1. **Home**：继续练习、今日建议场景、最近练习；不显示虚假能力分数。
2. **Scenario List**：分类筛选（Interview / Workplace / Travel & Life）、岗位和难度筛选。
3. **Scenario Detail**：Situation、AI 角色、练习目标、预计时间、开始按钮。
4. **Practice**：对话列表、文本输入、发送状态、结束按钮；防止发送中重复点击。
5. **Evaluation**：总结、优势、最多 3 个改进、原句与改写、加入复习按钮。
6. **Review List**：待复习表达、状态、练习结果。
7. **Profile / Settings**：目标公司/岗位、API 环境状态、清理本地缓存。

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

## 11. 配置、密钥与环境

### 11.1 Backend 环境变量

`.env.example` 只放空值/示例值，不提交真实 `.env`：

```dotenv
APP_ENV=local
APP_NAME=voxora-api
API_V1_PREFIX=/api/v1
DATABASE_URL=postgresql+asyncpg://voxora:voxora_dev_only@localhost:5432/voxora
AI_PROVIDER=mock
AI_API_KEY=
AI_MODEL=
AI_TIMEOUT_SECONDS=30
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

## 12. 安全与隐私

- HTTPS 是非本机环境的强制要求；开发 HTTP 仅限本地设备/模拟器。
- 未认证的本地 MVP 不可绑定公网 IP，也不可部署为公开服务。
- 上线前实现 Auth；每条用户私有资源查询均使用 `current_user.id` 作为条件，不信任客户端传来的 user_id。
- AI API key 仅存在后端；错误日志须过滤 Authorization、API key、连接串。
- 用户输入、Prompt 和 AI 输出均是不可信内容；渲染时做文本安全处理，不执行 HTML/脚本。
- 初版不保存音频；未来启用需单独记录用户同意并提供撤回/删除路径。
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

### 13.2 超时与重试

- DB 超时与 AI 超时分别配置。
- AI 请求仅对明确可重试的网络错误/限流做有限退避重试；不可对用户消息重复落库。
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

交付：首批人工审校场景、练习体验记录、录音/转写技术 spike（不默认保存音频）。
验收：按实际连续使用结果调整 Rubric、场景质量和反馈长度；再决定实时语音与多人测试用户。

## 18. ADR（架构决策记录）待建事项

遇到改变成本较高的决策时，在 `docs/adr/` 新建编号文档，记录背景、备选方案、决策、后果：

- ADR-001：个人 MVP 的认证边界与公网部署条件。
- ADR-002：LLM / Speech Provider、数据区域与成本上限。
- ADR-003：录音是否上传/保存、保留时长和删除机制。
- ADR-004：英语评价 Rubric 与人工校准方案。
- ADR-005：同步评价升级为持久任务队列的触发条件。

## 19. 开发前仍需产品确认

这些事项不阻挡本地骨架与文本闭环开发，但对应功能上线前必须明确：

1. 首版是否只由本人使用；是否计划马上邀请外部测试用户。
2. AI 服务商、可接受月成本和可接受响应时长。
3. 首批 10 个左右高质量场景的清单及人工校对责任。
4. 英语评价使用三档描述还是其他等级；各维度的明确定义。
5. 文本 transcript 的保留/删除方式。
6. 语音试验使用设备本地转写还是服务端转写，以及数据处理地区。

---

**文档状态说明：** 本版足以启动后端工程骨架、数据库 Schema、REST API 和文本 Roleplay 的实现。标记为“待决”的认证、语音、成本与评分校准事项不得被当作已完成设计；实现者应在对应功能开发前更新本文或补充 ADR。
