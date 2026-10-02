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
- **未验证**：Android 模拟器与真机 —— 本机没有 Android SDK / emulator。§1.3 第 6 条的
  “从 Android Emulator 完成全闭环”要等装了 SDK 或用 Expo Go 真机扫码后才能盖章。

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
