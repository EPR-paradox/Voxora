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

### 仓库状态

- 仓库已公开：https://github.com/EPR-paradox/Voxora（2026-10-02 设为 public）
- 公开前做过：邮箱重写（3 个提交作者改为 90894421+EPR-paradox@users.noreply.github.com，
  本仓库已设 user.email，后续提交不再泄露复旦邮箱）、设计文档 §1.1 去个人化、全历史密钥扫描。
- HEAD：ae0dffa（provider 接入）。提交历史 6 个：设计规格 → scenario 目录后端 → 文本练习会话流 →
  文档语音决策 → provider 接入 → 设计文档 v0.4。
- 工作树：本轮文档提交后干净。
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

已满足：1（场景筛选）、2（创建会话 + 快照）、3（多轮 roleplay，AI 不逐轮点评）、6（历史可恢复）、7（Fake Provider 可替换）、8（PyCharm 断点 + 空库迁移）。

未完成：
- 4 结束练习 + 生成结构化评价（§7.8 / §7.9，evaluation 状态机未落地）
- 5 复习项（§7.10）
- 前端 / 移动端整体未开始（§10）
- 真实 provider 已在真 key 下端到端跑通（见上一节第 6 条），但这条路径还没有可重复的脚本固化下来

### 下一步

Phase 3 —— Evaluation 与复习。这是后端 MVP 闭环的最后一块，对应 §1.3 第 4、5 条：

1. Evaluation 模型 + 状态机（§9.2）：结束时生成、失败可重试、同一 session 不重复生成。
2. §8.3 结构化输出 schema 与校验：评价必须带用户原话证据，只评英语沟通，不评判技术结论。
3. §7.8 / §7.9 端点：结束会话、获取评价、重试评价。
4. §7.10 Review Item CRUD。
5. 评价 prompt 的版本管理（§8.5），保证反馈可追溯。
6. 把真 provider 冒烟脚本固化进仓库（读环境变量即可跑），让“真 key 能通”成为一条可重复的命令，
   而不是一次性手工验证。
