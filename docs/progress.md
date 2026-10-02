# Voxora 进度记录

## 2026-10-02

### 今日完成

1. 真实 AI Provider 打通（未提交）
   - 新增 `backend/app/ai/openai_compatible.py`（166 行）：OpenAI 兼容 `/chat/completions` 适配器，
     默认指向 DeepSeek（`AI_BASE_URL=https://api.deepseek.com/v1`），可换厂商。
   - `core/config.py` 新增：`AI_PROVIDER` / `AI_BASE_URL` / `AI_MODEL` / `AI_API_KEY` /
     `AI_TIMEOUT_SECONDS=30` / `AI_MAX_TOKENS=400`。缺 `AI_MODEL` 或 `AI_API_KEY` 时启动即失败（fail fast）。
   - `main.py` 在 `lifespan` 内按 settings 构建 provider，shutdown 时 `aclose()`；
     `create_app(roleplay_provider=...)` 保持为测试注入点（外部传入的实例不被关闭）。
   - 错误映射：`RoleplayProviderError` → 502，`TimeoutError` → 504。

2. 测试
   - 新增 `tests/test_roleplay_provider.py`（232 行）：请求构造、host 解析、超时与 HTTP 错误映射。
   - 新增 `tests/api/test_provider_wiring.py`（51 行）：假 key 下断言 502 而非 mock 的 201，证明真适配器已接上。
   - `tests/api/test_health.py` 补健康检查用例。
   - 全量：45 passed（临时 SQLite，不需要 Postgres）。

3. PyCharm 调试排障
   - 结论：debug 会话本身正常（pydevd 附着、cwd=`backend/`、无 `--reload`，8000 端口唯一监听者就是它）。
     4 个断点全落在 `POST /{session_id}/messages` 链路，而当时在验 `POST /api/v1/practice/sessions`。
   - 经验已写入 `pycharm-run-configs` 技能：先确认断点覆盖目标接口的代码路径，再去审 run config。

4. 文档
   - README 补"Implemented API"、provider 切换说明、PyCharm 调试章节（含禁止 `--reload` 的理由）。
   - `docs/software-design-v0.1.md` 升到 Draft v0.3：语音输入决策落地（新增 §7.11 语音转写接口、
     §8.6 Speech 转写设计、§10.4 按住说话交互；§0.1 决策表新增"语音输入路径""转写执行位置"两行；
     §19 待决清单第 6 条改为已定）。

5. 设计文档升到 Draft v0.4：录音交互由“按住说话”改为麦克风开麦/闭麦
   - 触发原因：练习的是会议发言与面试的成段表达（30–90 秒），按住说话要求手指全程不松，
     干扰说话本身；且线上会议的通行形态就是麦克风 toggle，操作应与会议一致。
   - §10.4 重写为「麦克风开麦（语音输入）」；删除“上滑取消”手势（产物是文本回填，取消退化为清空输入框）。
   - 补 toggle 独有的失败模式约定：300 秒硬上限（最后 30 秒 UI 提示）；切后台/锁屏/来电/音频焦点被抢占时结束录音并转入转写且不丢音频；
     录音态可视化（红色 + 计时 + 电平）；录音期间禁用输入框。
   - §7.11 单段上限 60 秒 / 10 MB → 300 秒 / 32 MB；§8.6 明确转写超时必须独立于 AI_TIMEOUT_SECONDS 配置（SPEECH_TIMEOUT_SECONDS）。
   - Phase 5 需实测本机（GTX 1660 Ti 6 GB + i5-10300H）转写 300 秒音频在 GPU 与 CPU 回退两条路径上的耗时与显存/内存。
   - §10.4 明确不做后台录音（切后台即结束），故不申请 Android 前台服务。
   - §0.1 决策表新增“录音交互”一行；§1.4 排除项措辞同步。
   - 后端零改动：§7.11 转写契约未变，改的只是客户端触发方式与上限配置值。

6. 真实 provider 端到端实测（第一次带真 key 跑通，同时验证了 §19 待决第 2 条）
   - 配置：`AI_PROVIDER=openai_compatible`、`AI_MODEL=deepseek-flash`、base_url `https://api.deepseek.com/v1`。
     key 走环境变量注入，**没有**写进 `backend/.env`。
   - 事实：DeepSeek 当前 `/v1/models` 只提供 `deepseek-flash` 与 `deepseek-v4-pro`，`deepseek-chat` 已下线。
   - 路径：`httpx.ASGITransport` 直连 ASGI app 并进入 lifespan；库用真 Postgres（`infra-postgres-1`）。
   - 结果：`GET /health` 200；创建会话 201（1.3 s，opening line 是英文面试官开场白）；
     发送一轮 201（1.1 s，AI 追问“你本人在项目里的角色是什么”，没有插入逐轮点评，符合 §1.3 第 3 条）；
     `GET /sessions/{id}` 200，消息数 5（turn 0/1/2 的 user/assistant 齐全）。
   - 幂等：同一个 `client_message_id` 重发，首次 201、重发 200，未二次调用模型。
     响应体里**没有** replayed 字段（§7.6 的响应结构就是如此），200/201 是唯一外部信号，不算缺陷。
   - 延迟：`deepseek-flash` 开场 1.3 s、单轮 1.1 s —— 远低于可接受阈值。
   - 验证脚本是临时文件（`/home/j/.hermes/cache/scratch/voxora_e2e.py`），尚未进仓库；
     产生的 session `7dcae123-c390-47c5-9430-6e9f41f87ffa` 留在库里。

7. Phase 3 完成：Evaluation 与复习（§1.3 第 4、5 条）
   - 新增 `evaluations` / `review_items` 两张表（迁移 `5d07a878bd32`）：session 唯一约束、
     completed 必须有 result 的 CHECK、item_type/status 的 CHECK、review 列表索引。
   - `EvaluationProvider` 协议 + `FakeEvaluationProvider` + `OpenAICompatibleEvaluationProvider`
     （json mode）。评价 prompt 存在 `app/ai/prompts/evaluation_english_v1.txt`，版本随评价落库，
     存下的报告能追到产生它的 prompt。
   - 输出校验（`app/ai/evaluation.py`）：五个维度必须齐全、rating 只能是三档、evidence 必须能在
     学习者发言里找到（规范化后严格子串匹配，≥6 词的引用才允许 85% 词重叠的容错）。整份报告一条
     可归属的 evidence 都没有就直接判失败 —— 编造的语言报告比失败更糟。
   - 端点：`POST /sessions/{id}/finish`、`GET /sessions/{id}/evaluation`、
     `POST /sessions/{id}/evaluation/retry`，统一响应结构
     （evaluation_status / error_code / retryable / attempt_count）。
   - 评价失败不返回 5xx：会话确实结束了，报告状态放正文，客户端从首次调用到重放只写一条分支。
     同一 session 永远只有一行 evaluation，retry 只递增 attempt_count。
   - Review Item：`GET/POST /api/v1/review-items`、`PATCH /api/v1/review-items/{id}`。只允许改
     status / due_at / success_count / failure_count，归属字段客户端改不了（有测试盯着）。
   - 测试 92 → 101：输出校验 16 条、API 契约 14 条、review 13 条、评价 provider 9 条。

8. 真 provider 评价实测（第一次端到端生成真实评价）
   - 预算教训：`AI_EVALUATION_MAX_TOKENS` 初值 1200 时**必然失败**。`deepseek-flash` 一次评价消耗
     2000–2800 completion tokens，其中约一半是模型内部推理开销、不产生可见输出，逐次浮动；
     预算烧在推理上，content 就是空的或被截断。默认值改为 4000。
   - 因此补了两道防御：HTTP 层检查 `finish_reason=length` 并报明确错误（不再把半截 JSON 丢给下游
     去猜）；provider 内部对「空输出 / 校验失败」各重试一次（这类故障换个时刻就成功），**超时不重试**。
   - 实测结果：预算 4000 下连续 2 次 finish 均 attempt=1 成功。评价质量可用 —— evidence 全部来自
     学习者原话，指出的是「回答了但没答到点上」「More frames means → More frames mean」这类具体问题，
     不评判技术结论（符合 §8.4）。
   - 延迟：单轮 roleplay 1.1–2.2 秒；三轮对话后生成评价 13–15 秒。

## Phase 4 —— Android 客户端

- 工程 `apps/mobile`：Expo SDK 57 + Expo Router + TypeScript + TanStack Query，目录按 §5 / §10.2
  （`app/` 放路由，`src/{api,components,features,storage,theme}` 放其余）。
- 页面全部接真实 API，没有静态假数据：Home（继续上次练习 / 开始新练习 / 复习 / 设置）、场景列表
  （分类筛选）、场景详情（开始练习）、对话（发送、失败重试、结束）、评价（五维 + 原话证据 +
  加入复习 + 失败重试）、复习列表（状态筛选 + 记住了/没记住）、设置（后端健康 + 本地缓存）。
- 契约对齐：`src/api/types.ts` 逐字段对应后端 schema，字段名保持 `snake_case`，不做 camelCase 转换
  —— 中间层只会静默漂移。错误按 §7.12 的 `error.code` 分支，`isRetryable` 决定要不要给重试按钮。
- 对话页的状态划分：消息列表是服务端状态，只有“还没确认的那一轮”放在本地 outbox。失败保留原文与
  同一个 `client_message_id`，所以重试不会写出第二条用户消息（§7.6 / §9.3）。
- **后端补了 CORS**：浏览器预览（8081）与 API（8000）不同源，不加中间件所有请求都会被拦掉，而真机
  不受影响 —— 这种差异只有浏览器里才看得见。白名单 `CORS_ALLOW_ORIGINS` 只列本地开发来源，
  3 个测试盯着。
- 验证到哪一步：`tsc --noEmit` 干净；`expo export --platform web` 打包成功（846 模块）；用 headless
  Chrome 逐页渲染真实数据并截图核对（首页 / 场景列表 / 场景详情 / 对话 / 评价 / 复习），
  确认排版正常且数据来自真实 API。
- 补上 `GET /api/v1/practice/sessions`（§7.7 **本来就有**这个端点，是后端实现漏了它，不是新增契约）。
  Home 的“继续上次 / 最近练习”现在完全来自服务端，跨设备与重装后都正确；本地那个 session 指针降级为
  调试信息，不再参与任何决策 —— 两处真相源迟早会不一致。9 个测试覆盖排序、筛选、分页、归属与快照标题。
- 真机准备（走 Expo Go 路线）：后端改绑 `0.0.0.0`、生成 `API_ACCESS_TOKEN` 写进 `backend/.env`、
  `apps/mobile/.env.local` 写局域网地址与同一个令牌（该文件被 gitignore）、客户端补上 bearer 头
  —— 少了任何一条，手机上的请求都是 401。本机局域网地址 `192.168.1.6`（enp8s0），Expo 端口 8081。
  配置步骤写进 README 的 "Running on a physical phone"。
- **未验证**：Android 模拟器与真机 —— 本机没有 Android SDK / emulator，真机正在装 Expo Go。
  §1.3 第 6 条的“从 Android Emulator 完成全闭环”要等模拟器或真机跑通后才能盖章。

### 仓库状态

- 仓库已公开：https://github.com/EPR-paradox/Voxora（2026-10-02 设为 public）
- 公开前做过：邮箱重写（3 个提交作者改为 90894421+EPR-paradox@users.noreply.github.com，
  本仓库已设 user.email，后续提交不再泄露复旦邮箱）、设计文档 §1.1 去个人化、全历史密钥扫描。
- HEAD：ae0dffa（provider 接入）。提交历史 6 个：设计规格 → scenario 目录后端 → 文本练习会话流 →
  文档语音决策 → provider 接入 → 设计文档 v0.4。
- 工作树：本地领先远端 1 个提交（`82274fd`），push 未能完成 —— 本机代理（Mihomo Party，
  `127.0.0.1:7890`）当时没有运行，而国内直连 github.com:443 超时。开代理后 `git push origin main` 即可。
- 质量门禁全绿：`pytest` 45 passed；`ruff check` / `ruff format --check` 均通过。
- `.env` 保持 `AI_PROVIDER=mock`（默认开发不烧钱）；真实 provider 的端到端验证靠环境变量注入 key 完成，
  见上一节第 6 条。

### 后端已实现接口

- `GET /api/v1/health` — Postgres 探活 + request id。
- `GET /api/v1/scenarios` — 列出已发布场景，支持 category / industry_segment / role / difficulty / limit / offset。
- `GET /api/v1/scenarios/{id}` — 场景公开详情（不下发 roleplay_instructions 与 evaluation_rubric）。
- `POST /api/v1/practice/sessions` — 创建文本会话，快照场景，落库开场白。
- `POST /api/v1/practice/sessions/{id}/messages` — 一轮对话，`client_message_id` 幂等重试。
- `GET /api/v1/practice/sessions/{id}` — 恢复会话状态与消息历史。

### 对照设计文档 §1.3 验收条件

**八条全部满足**：1–3、6–8 见前几节；4（结束练习 + 结构化评价）与 5（复习项）由本节的 Phase 3
补齐，各自有契约测试兜底。

剩余缺口只有一个：前端 / 移动端整体未开始（§10）。另外真 provider 的冒烟脚本还是临时文件，
尚未固化进仓库。

### 下一步

后端 MVP 闭环已经完整（选场景 → 练习 → 结构化反馈 → 复习 → 再练），接下来是 Phase 4 —— Android 客户端：

1. Expo + TypeScript 工程骨架 + API client（`EXPO_PUBLIC_API_BASE_URL`）。
2. Scenario 列表/筛选 → Practice 对话页 → Evaluation 报告页 → Review 列表页。
3. Emulator 上跑通全闭环；断网/超时提示可恢复；App 重启后历史可加载（§1.3 第 6 条）。
4. 把真 provider 冒烟脚本固化进仓库（读环境变量即可跑），让“真 key 能通”成为一条可重复的命令，
   而不是一次性手工验证。
5. 语音（Phase 5）继续往后排：它只是输入方式，闭环价值已经在文本路径上兑现。

## 2026-10-02（夜）真机联调修正

### 1. 手机跑通闭环后暴露的三个问题

- **「AI 一直重复问同一个问题」= 跑的是 mock provider，不是模型或 prompt 的问题。** `backend/.env` 里
  `AI_PROVIDER=mock` 是设计默认（测试与离线开发用、不烧钱），正在服务的 uvicorn 继承了它，于是每轮都返回
  `FakeRoleplayProvider` 的同一句硬编码。证据：该会话三条 assistant 回复逐字相同，且等于
  `app/ai/roleplay.py` 里的字面量。修法不动 `.env`：启动脚本从 `~/.hermes/.env` 读 key，把
  `AI_PROVIDER=openai_compatible` / `AI_MODEL=deepseek-flash` / `AI_BASE_URL` / `AI_API_KEY` 作为进程
  环境注入，key 不落仓库、不回显。修后实测开场白与两轮追问均为真实模型输出且各不相同。
- **偶发 502（已修）**：切换 provider 后头两次请求返回 `ai_provider_error`，其后连续成功。原因是 roleplay
  provider 没有重试，而上游的空输出/5xx 是掷硬币式的偶发失败。现在按 §13.2 补上「可重试失败各重试一次」：
  判定落在共享传输层的 `ModelEndpointError.retryable`（空输出、5xx、429/408/409/425、传输错误可重试；
  401/403/422、`finish_reason=length`、超时不可重试），roleplay 与 evaluation 共用同一套判定 —— 顺带修掉了
  evaluation 连 401 也要重试一次的白花。测试 132 → 138（新增 6 条：空输出重试成功、5xx 重试成功、两次
  失败仍上报、401 不重试、截断不重试、超时不重试）。
- **复习项点不进去**：不是渲染 bug。§10.1 原来只有 Review List 一页，没有详情页；卡片把用户原话与推荐表达
  并排铺开，也就没有回忆环节。按用户选择做「详情页」方案（A 方案「列表卡片翻面」未做）。

### 2. 本次交付

- 新增 `GET /api/v1/review-items/{id}`（§7.10）：与列表项同一个 DTO；不存在或非本人统一 404
  `resource_not_found`，不区分「没有」与「别人的」。服务层 `get_review_item` 本来就有，缺的是一条路由。
- 新增 Review Detail 页（§10.1 第 7 条，原 Profile 顺延为第 8 条）
  `apps/mobile/app/review/[id].tsx`：原话、推荐表达、解释、复习记录（记住/忘了、下次复习、加入时间）、
  来源练习反馈入口（`source_session_id` → `/evaluation/[sessionId]`）、就地「记住了 / 还没记住」。
  按 id 直读而不从列表缓存里找，深链与冷启动可渲染。
- 列表卡片改为可点入详情，并加「详情 ›」提示；卡片被按下时给透明度反馈。
- 间隔阶梯（`gradeReviewItemInput` / `nextDueDate` / `MASTERY_THRESHOLD`）与日期格式化
  （`formatDue` / `formatDateTime`）上移到 `src/features/review/{api,format}.ts`：列表与详情共用一个
  真相源，两份实现必然漂移。
- 测试 127 → 132：新增单条读取 5 条（结构与列表一致、patch 后可见、未知 id 404、他人条目 404 而非 403、
  非法 uuid 422），并把新路由加进 `test_access_coverage.py` 的「非 loopback 必须 401」清单。
- 质量门禁：`ruff check` / `ruff format --check` 通过；`pytest -q` 132 passed；`tsc --noEmit` 干净。
- 设计文档升到 Draft v0.7（§7.10 增单条读取、§10.1 增 Review Detail 页）。

### 3. 运行方式（今天改过的地方）

- 后端与 Metro 都用 `persist_on_release` 的后台进程启动：父进程是 agent 会话，会话结束不再被回收。
  今天早些时候真机卡在 Expo Go 的 99%，就是 dev server 被回收（手机侧连接停在 FIN-WAIT-2），
  bundle 传到一半服务端没了。
- 真 provider 启动脚本：读 `~/.hermes/.env` 的 `DEEPSEEK_API_KEY` → export `AI_*` → `exec uvicorn`
  （`0.0.0.0:8000`）。
- 本地仍领先远端 9 个提交（代理未开：`127.0.0.1:7890` 无监听，直连 github.com 超时）。

### 4. 未验证 / 待办

- 「点卡片 → 跳详情」已在真机确认（手机 IP 发起了 `GET /api/v1/review-items/<id>` → 200）。
- 复习页的回忆环节仍未解决：详情页给了内容展开的地方，但列表卡片依旧把原话与答案并排显示（用户选择不做 A 方案）。
- 真 provider 冒烟脚本还没进仓库（仍在 scratch 目录，闲置 24 小时会被清）。
- 语音（Phase 5）未开工，契约见 §7.11 / §8.6 / §10.4。
- 本地领先远端仍是 9 个提交（代理未开）。

## 2026-10-02（夜）会议模式设计草案

产品决策：语音不做「按住/开麦 + 回填输入框」的单角色延伸，而是要做**多人会议情景模拟**。经拆解，这是
Phase 6 级别的产品变更（不是给 Phase 5 加个接口），范围定为「AI 扮演多个与会者的文本会议，语音输出单独立项」。

- 草案独立成文：`docs/meeting-mode-v0.1.md`（Draft v0.1），主规格 §17 增加 Phase 6 指针。
- 草案里最硬的两处是数据模型与状态机：`scenarios.ai_character`（单角色 JSONB）要扩成 `cast` 数组；
  `messages.role IN ('user','assistant')` + `UNIQUE(session_id, turn_index, role)` 决定了「每轮只能有一条 AI
  回复」，多角色必须加 `speaker_key` 与 `seq`（`now()` 在同一事务里是常量，只有 `created_at` 排序会不稳定），
  并把唯一约束扩到四列；`speaker_key` 用空串而非 NULL 表示学习者，否则 PostgreSQL 的唯一约束对用户消息失效。
- 编排取向：一次调用产出 1–3 条发言（json mode + 严格校验：未知发言人一律拒绝），而不是每个角色各调一次
  （N 倍延迟、角色之间无法真正接话）。
- 契约取向：`POST /messages` 的响应从单条 `assistant_message` 改为 `assistant_messages: [...]`，一次性切换、
  不留兼容分支；§7.6 / §7.7 / §7.4 / §9.3 / §10.1 按草案的对照表成套修订。
- 待用户拍板 5 项（草案 §10）：每轮发言条数上限、会议中是否改为「说完自动发出」、会议人数、是否新增会议
  专属评价维度、角色用虚构人名还是职位称谓。

## 2026-10-02（夜）会议模式 6.1 完成：数据模型

用户拍板（草案 §10 已改为「已定决策」）：每轮 AI 发言上限 3、会议人数 2–3、会议中语音转写后**自动发送**、
本期不加会议专属评价维度、角色用虚构人名。其中「自动发送」是对主规格 §10.4 决策的**例外**，已在 §0.1
决策表新增一行并在 §10.4 写清（只对 Meeting 页生效，Practice 页仍回填确认）。规格升 Draft v0.9。

6.1 交付（迁移 `3c9f1a7d24b8`）：

- `scenarios.cast` JSONB nullable：与会者数组。为 null 表示单角色场景，`ai_character` 继续生效；
  形状校验放在应用层（`normalize_cast`）而不是 CHECK 约束 —— `jsonb_typeof` 在测试用的 SQLite 里不存在。
- `messages.speaker_key` VARCHAR(32) NOT NULL DEFAULT ''：空串 = 学习者。**不用 NULL**：PostgreSQL 的唯一
  约束里 NULL 互不相等，可空的话 `UNIQUE(session_id, turn_index, role, speaker_key)` 对用户消息完全不设防。
- `messages.seq` INTEGER NOT NULL + `ck_messages_seq`：会话内展示顺序。**`created_at` 干不了这件事** ——
  `now()` 在同一事务里是常量，一轮写入的多条消息时间戳完全相同，只按时间排序会让客户端消息顺序漂移。
- 唯一约束 `UNIQUE(session_id, turn_index, role)` → `UNIQUE(..., speaker_key)`；服务层新增
  `_next_message_seq()`，创建开场白、写入用户消息、写入 AI 回复三处都补了序列号；`GET /sessions/{id}`
  与评价 transcript 的排序改用 `seq`。
- 新增 `app/scenario_cast.py`：`scenario_cast()`（cast 优先，否则把旧 `ai_character` 包成单元素）、
  `is_meeting()`、`speaker_index()`、`normalize_cast()`。**所有读侧必须过它**，禁止直接读 `ai_character`
  造 prompt，否则新旧场景行为分叉。历史 `scenario_snapshot` 未做任何迁移或改写。
- 验证：`alembic upgrade head` 在生产库（21 会话 / 105 消息）跑通，105 行全部回填 seq（min=1，无重复）；
  `downgrade -1` → 列与约束复原、105 行无损 → 再 `upgrade head` 成功（可逆往返）；`GET /review-items` 等
  既有接口不受影响；真 provider 新建会话 + 一轮对话 201，库里顺序为 `turn 0 opening(seq 1) → user(seq 2)
  → assistant(seq 3)`。
- 质量门禁：`ruff check` / `ruff format --check` 全过；`pytest -q` 138 → **169 passed**（新增
  `test_scenario_cast.py` 19 条、`test_message_speakers.py` 5 条 —— 后者专门盯「同一轮两个 AI 可以各说一句」
  与「同一轮只能有一条学习者消息」这两条互为反向的约束）。

### 2026-10-02（夜）会议模式 6.2 / 6.3 / 6.5 完成：一场会议真的能开起来

**Provider（6.2）**

- 契约变复数：`RoleplayProvider.opening_turns()` / `reply()` 返回 `list[RoleplayTurn]`（`speaker_key` + `content`）。
  单角色场景是退化情形：恰好一条，key 由 `scenario_cast()` 决定（旧的 `ai_character` 场景是 `interviewer`）。
- 一次调用产出整段剧本（1–3 条，json mode，`AI_MEETING_MAX_TOKENS` 初值 1200），不是每个角色各调一次。
  Fake provider 在会议里回两条，客户端的分组与多行写入路径因此不需要模型就能测。
- 输出校验：`speaker` 必须在 cast 内、1–3 条、每条 ≤60 词、非相邻的同一发言人判不合格；不合格按 §13.2
  重试一次，两次都坏才 502，且整轮不落库。
- **实测踩到的坑（值得记）**：deepseek-flash 带着 `response_format={"type":"json_object"}` 也会用提示词里的
  roster 记法回话（`[eng_lead] ...`），不是 JSON。第一次真机验收因此吃了两次 502（内容其实完全正确，只是
  格式）。修法两条：提示词里写死「只输出一个 json 对象、不要 `[speaker]` 行、不要 markdown 围栏」，同时让
  解析器接受两种形状（json 允许被 ``` 围栏包住；逐行 `[key] 内容`），两者走同一套校验。读不懂的格式才算失败。
  另外：同一位与会者在同一轮里重复出现（非相邻）会被唯一约束挡住，判不合格；相邻两句合并成一条。
- 真 provider 实测：3 人设计评审，开场 3 条、两轮追问分别 3 条与 2 条（模型自己决定谁不必发言），参与者会
  互相点名回应（"Careful, Dana."）并追问具体数字；单轮 1.6–6.1 秒。

**服务层与 API（6.3）**

- 一轮 = 1 条用户消息 + 1..N 条 AI 发言，**同一事务写入**、`seq` 连续；幂等重放返回同一组、同一顺序。
- `POST /messages` 响应从 `assistant_message` 改为 `assistant_messages: [...]`（破坏性，一次性切换，不留兼容
  分支）；每条消息带 `seq` / `speaker_key` / `speaker`（`{key,name,title}`，来自会话快照）。
- `GET /sessions/{id}` 增 `participants`；`GET /scenarios/{id}` 增 `cast`（null = 单角色场景）。
- 测试 169 → 197：新增 `test_meeting_provider.py`（提示词、两种输出形状、围栏、未知发言人、超长、重复发言人、
  重试与两次失败）与 `api/test_meeting_flow.py`（两个声音的开场、一轮两行且 seq 连续、重放同一组、cast 下发、
  单角色场景不受影响）。

**场景种子（6.5）**：`design-review-scope-01`（3 人：工程负责人 / 产品经理 / QA）与 `standup-blocker-01`
（2 人：组长 / 现场工程师）。种子写入前过 `normalize_cast()`（越界的 cast 存不进库），`ai_character` 镜像第一位
与会者以兼容旧读者。

**客户端（6.4）**：**没有另开 Meeting 页** —— 计划里这一步原本是新页面，动手时改成「同一个对话页按 cast 参数化」，
因为 outbox / 失败重试 / `client_message_id` / 结束练习那套逻辑复制一份到新页面必然漂移。现在 `participants > 1`
时会话页顶部有与会者条，AI 气泡左侧竖线取发言人颜色（由 key 稳定哈希派生），名字只在换人那条显示，同一人连续
发言收紧间距。场景详情页也列出参会人。`tsc --noEmit` 干净，web 预览渲染核对通过（截图
`~/.hermes/cache/scratch/meeting.png`），真机待确认。

**规格同步**：主规格升 Draft v0.10（§6.3 表、§7.4、§7.6、§7.7、§9.3、§10.1）；会议草案升到记录实测与修正后的
客户端方案。`ruff check` / `ruff format --check` 全过；`pytest -q` 197 passed。

## 2026-10-02（深夜）语音输入（Phase 5 的一半）：§7.11 端点 + 手机上的开麦

用户要求语音输入与语音输出都要。先做语音输入。

### 后端：转写端点（§7.11 / §8.6）

- `app/ai/speech.py`：`SpeechProvider` 协议 + `TranscriptResult` + `FakeSpeechProvider`；`SpeechNotRecognized`
  → 422 `speech_not_recognized`（不是空文本 —— 空消息比「请再说一遍」更糟）。
- `app/ai/faster_whisper_speech.py`：本机实现。模型**首次使用时加载**（不拖累 pytest 与启动）；解码跑在线程里
  （`transcribe` 返回的是生成器，迭代时才解码，放在事件循环上会冻住所有请求）；不启用 VAD；Whisper 在静音上会
  幻觉出 "Thank you."，所以按模型自己的 `no_speech_prob` 丢掉疑似无语音片段，全被丢掉就报 422。
- `app/api/speech.py`：`POST /api/v1/practice/speech/transcriptions`（multipart，字段 `audio_file` /
  `language` / `duration_ms`）。上传按上限**流式读取**，超限直接 413，不先把 200 MB 落盘。音频不落库、不进日志、
  不进任何消息（§7.11 规则 1/2/7），响应只有文本与元数据。
- 配置：`SPEECH_PROVIDER`（mock/faster_whisper）、`SPEECH_MODEL=small.en`、`SPEECH_DEVICE=auto`、
  `SPEECH_COMPUTE_TYPE=int8`、`SPEECH_TIMEOUT_SECONDS=180`（**不能**复用 `AI_TIMEOUT_SECONDS`，§8.6 已写明）、
  `SPEECH_MAX_SECONDS=300`、`SPEECH_MAX_BYTES`。`.env.example` 与规格 §11.1 同步。
- 测试 197 → 208：新增 `test_speech_transcriptions.py`（成功路径、413/415/422/502/504、空上传、错误响应不含内部
  路径，以及「转写不写任何东西」—— 断言会话表与消息表都还是 0）与 `test_faster_whisper_speech.py`（CUDA 失败
  回退、静音、超时、模型只加载一次）。

### 实测（这台机器）

```
edge-tts 生成测试音频：17.4 秒 / 313 秒（顺带证明云 TTS 直连可用，不需要代理）
small.en + CPU int8（i5-10300H 8 线程）：
  17.4s 音频 → 1.7s  （10.0x 实时）
  313s 音频 → 26.9s  （11.6x 实时），转写文字与合成原文逐字一致
结论：SPEECH_TIMEOUT_SECONDS=180 对 300 秒上限有约 6.7 倍余量，保留。
```

**踩到的坑**：CTranslate2 按自己的构建参数声称 CUDA 可用，不看机器上有没有运行库 —— `SPEECH_DEVICE=auto`
会选中 CUDA、模型加载成功、然后在第一次编码时抛 `libcublas.so.12 is not found`。若不管，配错一次之后每段音频
都是 502。现在推理期捕获缺库错误 → CPU 重建模型重跑同一段（有测试）。CUDA 运行库（`nvidia-cublas-cu12` /
`nvidia-cudnn-cu12`，约 1.2 GB）仍在下载，装好后补测 GPU 路径耗时。

### 客户端：对话页的开麦按钮（§10.4）

- `src/features/speech/useVoiceInput.ts`：开麦/闭麦 toggle；300 秒硬上限（最后 30 秒变色提示）；系统中断
  （切后台/来电/音频焦点被抢）由 SDK 的状态回调触发「结束并转写」，**已录内容不丢**；失败时保留音频文件，
  「重试同一段」重传同一文件；权限被拒则本会话不再弹窗、退回打字。
- `src/api/client.ts` 新增 `apiUpload`（multipart；刻意不设 Content-Type，让 fetch 自己写 boundary），
  并把响应处理抽成 `unwrap`；转写超时单独设为 240 秒 —— 必须比服务端的 180 秒更长，否则客户端会在答案到达前
  自己放弃。取消上传真的会 abort（新增 `AbortError`，与「失败」区分）。
- 对话页：录音时输入框与发送按钮禁用、红色电平条 + 计时；转写中显示「识别中…」并可取消；失败显示「重试同一段 /
  重新录」；会议场景（`participants > 1`）**转写完直接发出**，单角色场景回填输入框让人先改错 —— 这条差异就是
  §0.1 / §10.4 里定下的会议例外。`tsc --noEmit` 干净。

### 还没做

- 语音输出（TTS）：每个与会者一个音色 + 播放队列 + 开麦时停播 + 「输出音频是否缓存」的隐私决策。
- 真机验收：开麦、300 秒上限、中断、会议自动发送都还没在真机上跑过。
- GPU 路径：**决定不做**。CPU（small.en / int8）已 11.6x 实时，300 秒音频 27 秒转完；CUDA 要多装 1.2 GB
  运行库，且 CTranslate2 会谎报可用性（见上）。本机 `SPEECH_DEVICE=cpu` 钉死，换大模型时再评估。
- 注：`.venv/bin/pip` 在这个 venv 里存在但曾报 `No such file or directory`（某个后台进程），装包一律用
  `.venv/bin/python -m pip`，别依赖 `pip` 脚本。

## 2026-10-02（语音输出 6.6a）：每个角色一个音色

草案 §9 说 TTS 的前置是 `cast[].voice` 落地，先做这块。

- `app/ai/voices.py`：8 个 edge-tts 英文音色（en-US/en-GB/en-IN，男女各半），名字用 `edge_tts.list_voices()`
  逐个验证过。`resolve_voice(key, taken)` 对 key 做 sha256 取模、跳过已占用的音色 —— **按 key 而非按位置**
  分配，否则加一个与会者就会把后面所有人的声音换掉。
- `normalize_cast`：显式音色必须在目录里，否则 `ValueError`（拼错的音色不该等到按下播放才炸）；没给就确定性分配。
  `scenario_cast()` 读侧遇到 `None` 或已改名音色就地补齐，不因数据旧而让播放失败。旧数据无需迁移。
- 测试 212 → 216：新增音色稳定性、同房间不共用音色、目录外音色写侧被拒 / 读侧被替换；`test_seed` 改为断言
  每位与会者都有音色且互不重复。`ruff` 全过。
- 已定决策写进草案 §9.1/§9.2 与 §10：合成音频**不落盘、不缓存**（与输入音频同一条隐私线，代价是重放重新合成）。

6.6b（edge-tts provider + 端点）与 6.6c（客户端播放队列、开麦即停播）是下一步。

## 2026-10-02（语音输出 6.6b）：一句话变成音频

- `app/ai/speech_synthesis.py`：`SpeechSynthesisProvider` 协议 + `FakeSpeechSynthesisProvider`。Fake 返回**真实的静音
  WAV**，不是占位字节 —— mock 模式下手机要真的能播，否则客户端 bug 会被「反正 mock」掩盖。
- `app/ai/edge_tts_synthesis.py`：edge-tts 实现。`edge_tts` 在调用内 import（它拖进 websocket 客户端，不该出现在一个
  可能永远不开口的 API 的启动路径上）；整句缓冲后一次性返回（播放需要完整文件，而音频不落盘，没有地方可流）；
  流式累积时有 8 MB 上限，防跑飞。超时翻译成内建 `TimeoutError`（服务层映射 504），其他异常包成
  `SpeechSynthesisError`（502），空音频也算失败 —— 否则客户端拿到的是「200 + 空文件」。
- `app/services/speech_synthesis.py`：调用供应商**之前**先验文本与音色：空、超 1000 字符、音色不在目录 → 422。
- §7.13 端点：`POST /api/v1/practice/speech/synthesis`，请求 `{text, voice}`，成功**直接回音频字节**
  （`audio/mpeg`，`Cache-Control: no-store`），失败回 §7.12 的 JSON 错误信封 —— 客户端按 Content-Type 分流。
- 顺带统一了一处不一致：`/scenarios/{id}` 的 `cast` 之前直接读原始 JSON（旧数据 `voice: null`），现在与会话详情的
  `participants` 一样走 `participant_payloads()`，客户端不可能拿到「没有音色的与会者」。新的共享投影函数放在
  `scenario_cast.py`，消息侧的 `speaker_index` 保持只管展示字段（消息不需要音色）。
- 配置：`SPEECH_SYNTHESIS_PROVIDER`（mock/edge_tts）、`SPEECH_SYNTHESIS_TIMEOUT_SECONDS=30`、
  `SPEECH_SYNTHESIS_MAX_CHARS=1000`；`.env.example` 与规格 §11.1 同步。合成与转写是两个独立 provider、两个独立超时
  （合成 30 秒 vs 转写 180 秒）—— 两者耗时形态相反。
- 测试 216 → 234：`tests/api/test_speech_synthesis.py`（可播放音频、`no-store`、什么都不写、空/超长/未知音色的 422、
  504/502、错误响应不泄露内部路径）与 `tests/test_edge_tts_synthesis.py`（忽略非音频块、空音频、超时、客户端爆炸、
  配置失败闭合）。

### 闭环实测（真 provider，经运行中的 API）

```
同一句："Can I flag one risk before we move on? Cutting that would cost us the calibration pass."
en-US-AndrewMultilingualNeural  200 audio/mpeg no-store  31968 B  2.8s
en-GB-SoniaNeural               200 audio/mpeg no-store  36144 B  2.3s
en-IN-NeerjaExpressiveNeural    200 audio/mpeg no-store  41904 B  1.7s

再把三段 MP3 喂回 /practice/speech/transcriptions：
  三个都逐字还原原文（duration_ms 5328 / 6024 / 6984）
未知音色 → 422 validation_error；空白文本 → 422 validation_error
```

这条闭环是这次真正值钱的东西：它同时证明合成音频**可播、可懂、文本正确**，而不是「返回了一堆字节」。

**踩坑记录**（写给未来的自己）：我写了一个自动折行脚本处理 E501，它把 `#:` 注释标记、docstring 的结束三引号、
以及缩进续行都拆坏过（`app/ai/speech.py` 的 `module has\nno ORM imports` 就是它的手笔，已修）。教训：折行脚本必须
只处理「整行注释块」或「docstring 段落」，并且每次都要 `py_compile` + 跑测试验证；能用手写就手写。

### 还没做

- 6.6c：客户端播放队列、「按麦克风即停播」、发言气泡上的播放按钮。
- 真机验收：合成语音在 Expo Go 里的播放（web 渲染过不等于 native 过）。

## 2026-10-02（语音输出 6.6c）：让它真的开口

客户端播放链路，`apps/mobile`：

- `src/api/client.ts`：新增 `apiBinary`（成功是音频字节，失败仍是 §7.12 的 JSON 信封 —— 错误路径与 `apiRequest`
  共用，屏幕只按 `ApiError.code` 分支）；超时 `SYNTHESIS_TIMEOUT_MS=60s`（要长过服务端 30s）。
- `src/features/speech/synthesis.ts`：把响应字节写进 `Paths.cache` 里的临时文件再交给播放器。**扩展名跟随
  Content-Type**（mock 返回 WAV，硬写成 .mp3 播放器可能拒绝）；播完即删，服务端本来就没留副本。
- `src/features/speech/useSpeechOutput.ts`：队列 + 播放状态机。一条一条播（三个人同时说话是噪音）；开麦即
  `stop()`（扬声器还在响就开麦，学习者会把 AI 的声音录进自己这轮）；一行读不出来只提示不阻塞队列（语音是增强
  项）；`stop()` 会 resolve 掉正在等的「播完」promise，避免队列卡死；卸载时释放播放器与临时文件。
- 对话页：新到的 AI 发言自动入队播放（**首次加载只标记为已听过，不朗读历史**，否则进一个十轮会话手机会先独白
  一分钟）；标题栏加「有声/静音」（静音只拦自动播放，手动朗读仍生效 —— 手动意图高于开关）；每条 AI 气泡上有
  「朗读/停止」；`participants[].voice` 决定用哪个音色，客户端不保存音色目录副本。
- 规格：主规格升 Draft v0.12，新增 §10.5（音频不缓存、开麦停播、路由 `playsInSilentMode` + `duckOthers`、
  不做语速/音色选择/离线留存）。会议草案 §11 的 6.6 行标为完成（真机待确认）。

### 验证

- `tsc --noEmit` 干净。
- `npx expo export --platform android` 成功（3.0 MB `.hbc`），在产物里逐个确认新代码存在：
  `/practice/speech/synthesis`、`voxora-line-`、`expo-file-system`、`duckOthers` 各命中；中文按 utf-16-le 计数
  （朗读 2、有声 1、静音 1、朗读失败 1）。web 渲染过不等于 native 过，所以这一步是必须的。
- Metro 已用 `--clear` 重启（pid 在 8081），手机侧需要硬重载（从最近任务划掉再开，切前后台不算）。
- 真机验收待做：播放是否出声、开麦是否真的停播、临时文件是否被清掉。

## 2026-10-02（真机联调）：开麦报「连不上后端」的真因

真机症状：播放正常（`/speech/synthesis` 200），一点开麦就提示「连不上后端，检查网络或服务是否在跑」，
而服务器日志里**手机从来没请求过 `/speech/transcriptions`**（其他请求全部 200/201）。

排查路径（都靠证据，不靠猜）：

1. 错误文案对应 `NetworkError`（fetch 被拒），不是 4xx/5xx —— 后端根本没被联系上。
2. 手机聊天请求全部正常 → 排除 base URL / token / 局域网。
3. 在 `useVoiceInput` 里把 clip 的 URI 与字节数打到 `console.warn`，手机端日志出现在 Metro 日志里：

```
[voice] clip file:///data/user/0/host.exp.exponent/cache/.../recording-ef4d...m4a (80841 bytes)
[voice] transcription failed [NetworkError: Unsupported FormDataPart implementation]
```

真因：**Expo SDK 57 用的是 expo 自己的 fetch**，其 multipart 写入器
（`node_modules/expo/src/winter/fetch/convertFormData.ts`）只接受三种部件：`string`、`instanceof Blob`、
或**带 `bytes()` 方法的对象**。旧的 React Native 写法 `{ uri, name, type }` 三者都不是，直接抛错；这个错误
在客户端表现为网络失败，于是文案说「连不上后端」。

修法：`src/features/speech/api.ts` 的 `clipFormPart()` 改成 `{ bytes: () => new File(uri).bytes(), name, type }`
（`name` / `type` 会成为部件在网线上的 `Content-Disposition` / `Content-Type`，服务端正是按这两者选解析器）。
同时保留 `normalizeClipUri()`（无 scheme 的路径补 `file://`）与 `clipSize()`（空文件提前报明确错误）。

**验证（不靠手机）**：把 expo 的 `convertFormData.ts` 复制到 scratch（Node 拒绝 strip `node_modules` 里的 TS），
用手写的 RN-FormData 替身驱动它（Node 原生 FormData 会把非 Blob 值强转成字符串，复现不了 RN 行为），再把生成的
字节 POST 给真实 API：

```
legacy {uri,name,type}        → Unsupported FormDataPart implementation   （手机上的同一条错误）
fixed  {bytes,name,type}      → body 104948 B → HTTP 200，转写文字正确
```

`tsc` 干净，`expo export --platform android` 成功且产物含 `clipFormPart`。提交 `b7c2249`。

顺带一条教训：手机是黑盒，但 **Metro 日志就是它的 console** —— `console.warn` 出来的东西能直接读到；
遇到「手机上说网络不通、服务器却一条请求都没收到」时，先怀疑请求体，再怀疑网络。

---

## 2026-10-02 当日总览（收尾）

一天把 Phase 0→6 走完（除离线 TTS 与实时音频）。**当日 31 个 commit，全部已推 `origin/main`**。

### 交付

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 0–1 | 仓库/环境、Schema、场景种子、迁移基线 | 完成 |
| Phase 2 | 文本 Roleplay（真 DeepSeek，非 mock） | 完成 |
| Phase 3 | Evaluation + 复习项（评测证据必须可归属到原话） | 完成 |
| Phase 4 | Android 客户端（Expo Go 真机可用） | 完成 |
| Phase 5 | 语音输入（§7.11 转写）+ 语音输出（§7.13 合成） | 完成（GPU 路径经评估放弃，见下） |
| Phase 6 | 会议模式 6.1–6.6（cast / speaker_key / seq、多角色编排、音色、真机播放） | 完成 |

### 数字

- 后端测试 **45 → 234**（今日净增 189）；`ruff check` / `ruff format --check` 全过；移动端 `tsc --noEmit` 干净。
- 迁移今日新增 2 个：`5d07a878bd32`（evaluations / review_items）、`3c9f1a7d24b8`（会议 cast / speaker_key / seq），均可逆往返。
- 规格 `docs/software-design-v0.1.md` **v0.3 → v0.12**；新增 `docs/meeting-mode-v0.1.md`（会议模式草案）。
- 延迟实测（deepseek-flash + 本机）：开场 1.3 s；单轮 roleplay 1.1–2.2 s；会议一轮 1–3 条 1.4–6.1 s；完整评价 13–15 s。

### 语音链路的实测数字（都是本机跑出来的，不是估的）

```
转写 small.en / CPU int8（i5-10300H 8 线程）
  17.4 秒音频 → 1.7 秒（10.0x 实时）
  313 秒音频 → 26.9 秒（11.6x 实时），文字与原文逐字一致
  → SPEECH_TIMEOUT_SECONDS=180 对 300 秒上限有 ~6.7 倍余量

合成 edge-tts（不需要代理、无密钥）
  单句 1.7–2.8 秒；三个音色各合成 → 再喂回 §7.11 转写 → 三个都逐字还原原文（闭环）
```

### 今天定下的决策（每条背后都有证据或实测）

1. **语音是输入法**，不是消息类型；音频在输入与输出两端都不落库、不缓存（输出侧带 `Cache-Control: no-store`）。
2. **开麦即停播** —— 不是优化：扬声器还在响时开麦，学习者会把 AI 的声音录进自己这一轮。
3. **音色按 cast key 哈希分配**，不按位置：按位置的话，加一个与会者会把后面所有人的声音换掉。
4. **放弃 GPU 转写路径**：CPU int8 已 11.6x 实时，而 CUDA 要额外装 ~1.2 GB 运行库；将来换 large-v3 再评估。
5. **会议**：每轮 AI 上限 3 条、2–3 人、会议中转写后自动发送（单角色仍回填输入框人工确认）、沉默的与会者合规、不另开页面（按 cast 参数化同一对话页）。
6. **不设会议专属评价维度**：先用内容维度，等真实用过再定，免得历史报告不可比。

### 今天踩到的三个真坑（都已写进 skill）

1. **CTranslate2 谎报 CUDA 可用** —— 它按自身构建参数判断，不看机器有没有运行库：`SPEECH_DEVICE=auto` 会选中 CUDA、模型加载成功、然后第一次编码抛 `libcublas.so.12 is not found`，若不处理则每段音频都 502。现在推理期捕获缺库 → CPU 重建模型重跑同一段。
2. **Expo SDK 57 用自家 fetch**，multipart 只接受 `string` / `instanceof Blob` / 带 `bytes()` 的对象；旧 RN 写法 `{ uri, name, type }` 抛 `Unsupported FormDataPart implementation`，在客户端表现为网络错误 —— 文案说「连不上后端」，后端却一条请求都没收到。
3. **手机是黑盒，但 Metro 日志就是它的 console**。判据要这样用：服务器日志空白 + 端上报网络错误 → 先怀疑请求体，再怀疑网络；`console.warn` 出来的 clip URI 与字节数是唯一现场证据。

### 还欠着的

- Phase 5 的正式验收：连续使用后调 rubric、场景质量与反馈长度（真机链路今天已通过）。
- 离线 TTS（piper）与实时音频/AI 抢话（后者属 §1.4 不做范围）。
- 端到端冒烟脚本进仓库（`voxora_e2e.py` / `voxora_eval_e2e.py` 仍只在 scratch）。
- 仍未定：会议议程进度（走完自动结束 vs 学习者点结束）、AI 之间互相打断的密度。

