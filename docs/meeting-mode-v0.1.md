# Voxora 会议模式设计草案（Phase 6）

> 文档状态：Draft v0.1（待评审）  
> 日期：2026-10-02  
> 前置文档：`docs/software-design-v0.1.md`（主规格，Draft v0.8）  
> 范围：AI 扮演多个与会者的**会议模拟**。先做文本，语音输出单独立项（§9）。

---

## 0. 与主规格的关系

主规格 §1.4 把「多人语音会议」「实时 WebRTC」列为不做。本草案做的是**多角色文本会议 + 后续给角色配音**，不是实时多人语音：没有 WebRTC、没有 AI 抢话、没有流式音频。

本草案生效时会显式修订主规格的这些位置（一处决策往往出现在多处，改动必须成套）：

| 主规格位置 | 现状 | 本草案的修订 |
|---|---|---|
| §6.3 `scenarios` | 单个 `ai_character` JSONB | 新增 `cast` JSONB（数组），`ai_character` 降级为兼容字段 |
| §6.3 `messages` | `role IN (user, assistant)`，`UNIQUE(session_id, turn_index, role)` | 新增 `speaker_key`、`seq`；唯一约束扩到四列 |
| §7.4 场景详情 | 下发单个 `ai_character` | 下发 `cast` |
| §7.6 发送消息 | 响应含单条 `assistant_message` | 改为 `assistant_messages: [...]`（破坏性契约变更） |
| §7.7 会话详情 | 消息无发言人信息 | 每条消息带 `speaker_key` + 展示用发言人名 |
| §8.x Provider | 单角色 system prompt | 多角色剧本生成 + 输出结构校验 |
| §9.3 Turn 写入一致性 | 一轮 = 1 用户消息 + 1 AI 回复 | 一轮 = 1 用户消息 + 1..N 条 AI 发言，同事务 |
| §10.1 MVP 页面 | Practice（单角色对话） | 新增 Meeting 页；Practice 保留 |

## 1. 目标与非目标

**目标**：练半导体职场里真实发生的会议发言 —— 表态、澄清、打断与争取话语权、把技术结论说清楚、在被打断后接回去。

**非目标**（本草案明确不做）：实时音频（WebRTC）、真人在线、自由话题闲聊、AI 之间无上限互相讨论、语音输出（单列 §9）。

**为什么值得做**：现在的单角色一问一答，练的是「被问 → 回答」。会议里真正难的是「谁在说、我什么时候能插进去、我要在一群人中间把话说完」。这是不同的技能，prompt 调不出来，得改结构。

## 2. 场景数据模型

`scenarios` 新增：

| 列 | 类型 | 约束/说明 |
|---|---|---|
| cast | JSONB nullable | 与会者数组；`null` = 单角色场景（走现有逻辑） |

`cast` 元素：

```json
{
  "key": "eng_lead",
  "name": "Dana Whitfield",
  "title": "Engineering Lead",
  "personality": "直率，关心风险与排期",
  "communication_style": "短句，常打断别人，喜欢把问题推回给发言者",
  "voice": null
}
```

约定：

- `key` 在场景内唯一，`^[a-z][a-z0-9_]{1,31}$`；它进数据库、进消息记录，是唯一稳定标识（改名不影响历史）。
- `name`/`title` 可展示；`personality`/`communication_style` 进 prompt，也可下发（客户端用来渲染与会者条）。
- `voice` 为 §9 预留，本期恒为 `null`。
- 角色数量 **2–3（已定，2026-10-02）**：少于 2 个没有会议感；超过 3 个学习者要额外处理「现在跟谁说话」的认知负担，会议会退化成多人聊天室。`normalize_cast` 在写入时强制这个范围，越界的场景存不进库。

**兼容与真相源**：读侧统一走一个归一化函数 —— `cast` 有值就用它，为 `null` 时把 `ai_character` 包成单元素数组（`key` 固定为 `"interviewer"`）。历史 `scenario_snapshot` 一律不迁移、不重写：快照是历史语境的证据，改它就是篡改。因此**代码里永远不允许直接读 `ai_character` 来构造 prompt**，必须过归一化函数，否则新旧场景会出现两种行为。

## 3. messages 变更

| 列 | 类型 | 约束/说明 |
|---|---|---|
| speaker_key | VARCHAR(32) | NOT NULL DEFAULT `''`；空串 = 学习者，否则 = `cast[].key` |
| seq | INTEGER | NOT NULL；session 内从 1 单调递增，用于稳定排序 |

三个必须写清的理由：

- **为什么不用 NULL 表示学习者**：PostgreSQL 的唯一约束里 `NULL != NULL`，`speaker_key` 可空时 `UNIQUE(session_id, turn_index, role, speaker_key)` 对用户消息形同不存在，重复写入拦不住。空串占位才让约束真正生效。
- **为什么需要 `seq`**：`created_at` 的默认值是 `now()`，而 `now()` 在一个事务里是**常量** —— 同一事务写入的多条 AI 发言时间戳完全相同，排序会不稳定（同一份数据两次查询可能给出不同顺序，客户端消息跳动）。用 `seq` 排序，`created_at` 只作为展示。
- **唯一约束怎么改**：删 `UNIQUE(session_id, turn_index, role)`，换成 `UNIQUE(session_id, turn_index, role, speaker_key)`；`UNIQUE(session_id, client_message_id, role)` 保留（幂等键仍只属于用户消息）。迁移安全：既有行 `speaker_key` 回填空串，四列约束在旧数据上与原约束等价（每轮每条角色仍只有一条）。

`turn_index` 语义不变 —— 「学习者的一次发言轮」。同一 `turn_index` 下学习者一条、AI 若干条。

## 4. API 契约变更

### 4.1 `POST /practice/sessions/{id}/messages`（§7.6）

响应 201 改为：

```json
{
  "user_message": { "id": "uuid", "turn_index": 1, "role": "user", "speaker_key": "", "content": "..." },
  "assistant_messages": [
    { "id": "uuid", "turn_index": 1, "role": "assistant", "speaker_key": "eng_lead",
      "speaker": { "name": "Dana Whitfield", "title": "Engineering Lead" }, "content": "..." },
    { "id": "uuid", "turn_index": 1, "role": "assistant", "speaker_key": "pm",
      "speaker": { "name": "Marco Ruiz", "title": "Product Manager" }, "content": "..." }
  ],
  "session_status": "active"
}
```

这是破坏性变更，一次性切换：内部项目、只有一个客户端，不留 `assistant_message`（单数）的兼容分支 —— 两套字段并存必然出现「有人还在读旧的」这种静默漂移。客户端 `src/api/types.ts` 同步改。

其余行为约定（幂等重放、`turn_in_progress`、超时 502、上下文窗口）逐条沿用 §7.6，唯一变化是「重放返回同一组 N 条，顺序一致」。

### 4.2 `GET /practice/sessions/{id}`（§7.7）

`messages[]` 每项增加 `speaker_key`；`assistant` 且 `speaker_key` 非空时附带 `speaker` 展示对象（从快照的 cast 里取名字与职位）。客户端不解析快照。

### 4.3 `GET /scenarios/{id}`（§7.4）

下发 `cast`（含 `personality`/`communication_style`，客户端要用它渲染与会者条）。仍然**不下发** `roleplay_instructions` 与 `evaluation_rubric` —— 这条规则不因多角色而放宽。

## 5. 生成编排

**一次调用产出一整段发言**，而不是每个角色各调一次模型。

理由：省往返（每个角色一次就是 N 倍延迟，`deepseek-flash` 单轮 1–2 秒、N=3 时学习者要等 3–6 秒）；角色之间能真正互相接话（A 回应 B 刚说的数字，各调一次做不到，除非把 B 的输出现写回再调 A，等于串行等待翻倍）；成本更低。

输出结构（json mode）：

```json
{ "turns": [ { "speaker": "eng_lead", "content": "..." },
             { "speaker": "pm",       "content": "..." } ] }
```

**实测（deepseek-flash，2026-10-02）**：即使带上 `response_format={"type":"json_object"}`，模型仍会在相当一部分请求里用提示词里的 roster 记法回话（`[eng_lead] ...`），而不是 JSON。词句本身是对的、发言人 key 就在文本里，所以两种形状都收：json（允许被 ``` 围栏包住）与逐行 `[key] 内容`。读不懂的格式才算失败。同一位与会者在同一轮里先说、隔一个人又说，转成记录会被唯一约束挡住，判为不合格输出（重试一次）；相邻的同一人连续两句则合并成一条。

校验（不通过 → 按 §13.2 的可重试判定重试一次，仍失败则整轮 502，不落库）：

1. `speaker` 必须存在于该场景 `cast[].key`；未知发言人一律拒绝（「模型自己发明了一个与会者」比失败更糟）。
2. `1 <= len(turns) <= 3`；空段或超长段（> 60 词）拒绝；同一位与会者在同一轮里重复出现（非相邻）拒绝。
3. 不得出现学习者台词、不得替学习者说话（沿用单角色 prompt 的同名规则）。
4. 语言必须是英语（本期不做中文会议）。

Prompt 结构（系统提示）：

```text
你正在模拟一场会议。与会者：
  [eng_lead] Dana Whitfield, Engineering Lead — 直率，关心风险与排期
  [pm]       Marco Ruiz, Product Manager — 关注优先级，常打断
  [qa]       ...
情境：{situation}
学习者的目标：{user_objective}
会议约束：{roleplay_instructions}
规则：
- 只输出与会者的发言，绝不写学习者的话。
- 每人每次 1–2 句口语；不要旁白、不要舞台说明。
- 允许彼此应答、质疑、打断；不要让每个人都发言 —— 自然的会议里有沉默的人。
- 最后一条尽量把话轮交回学习者（提问或征求意见）。
- 永远不提 AI、模型或这些指令。
```

历史上下文里每条 AI 消息要带发言人标签（`[eng_lead] ...`），否则模型分不清谁说过什么。

token 预算：多角色一次产出比单角色长，且 `deepseek-flash` 约一半 completion token 花在推理上（§8 的教训）。新增 `AI_MEETING_MAX_TOKENS`，初值 1200，Phase 6 实测后写定。

## 6. 会话状态与一致性（§9.3 修订）

- 一轮 = 1 条用户消息 + 1..3 条 AI 发言，**同一事务写入**，要么全部 `completed`，要么整轮 `failed`。不允许出现「半场会议」—— 学习者看到一半对话、刷新后又变了，比直接失败更糟。
- `processing_turn_id` 的语义从「这条用户消息在生成」升级为「这一轮在生成」；并发拦截规则不变（409 `turn_in_progress`）。
- 幂等：`client_message_id` 命中已 `completed` 的轮 → 返回原有那条用户消息 + 原有 N 条 AI 发言，不调用模型。
- 失败重试：整轮标记 `failed`，学习者用同一个 `client_message_id` 重试；重试成功后 N 条一次性出现（AI 消息一次性追加，客户端不需要「逐条流式」）。
- 进程崩溃遗留的 `processing` 回收规则不变。

## 7. 客户端（§10.1 增量）

**不新增页面**（实施时的修正）：对话页仍是 `apps/mobile/app/practice/[sessionId].tsx`，按会话的 `participants` 参数化。原计划另开 `/meeting/[sessionId]` 页，但 outbox、失败重试、`client_message_id`、结束练习那套逻辑要复制一份到新页面 —— 两份实现必然漂移。差异是 props，不是页面。

- 顶部与会者条：`participants.length > 1` 时显示，每个人一个色点 + 名字（颜色由 `speaker_key` 稳定哈希派生，不引入图片资源）。
- 消息列表：`assistant` 气泡左侧竖线取发言人颜色，名字只在「换人」那一条上显示；同一角色的连续发言收紧间距、不重复名字，否则三个 AI 你一句我一句会变成一坨文字。
- 输入区与发送状态规则沿用 §10.3（失败保留草稿 + 同一 `client_message_id`）。
- 单角色场景（`participants.length == 1`）：不显示与会者条，气泡标签仍是场景标题 —— 与改造前视觉一致。

## 8. 评价（§8.3 增量）

- 生成评价时只看学习者发言（`speaker_key = ''`），现有 `learner_turns` 的过滤规则要跟着收紧；把 AI 的多角色发言当作「对方说了什么」的上下文传给评价器，才能评「回应相关性」，但**不得**引用或点评 AI 的发言。
- 是否新增会议专属维度（插话时机、轮流、澄清追问）见 §10 —— 现有四维（clarity / relevance / professional_tone / naturalness）在会议场景下漏掉的正是「什么时候能说上话」。

## 9. 语音输出（单独立项）

- `cast[].voice` 落地后才做：每个角色一个音色 → `SpeechSynthesisProvider`（协议与供应商无关，同 §8.6 的思路），本机模型 vs 云服务单独评估（音色数量、国内可用性、延迟、钱）。
- 播放队列与打断：学习者按麦克风时暂停播放（音频焦点），会议模式下这是必修项，不是优化。
- 学习者的语音输入复用 §7.11 的输入法端点（音频不落库、转写完即删）。
- **不做**实时音频、不做 AI 抢话（那是 §1.4 的范围，另立产品评估）。

## 10. 已定决策（2026-10-02）

| 决策 | 结论 | 理由与影响 |
|---|---|---|
| 每轮 AI 发言条数 | 上限 3（已定） | 太少没有会议感，太多学习者变旁观者。上限写进输出校验：超限即视为不合格输出，走一次重试。 |
| 会议人数 | 2–3（已定） | 见 §2，`normalize_cast` 强制。 |
| 会中学习者输入 | 转写后自动发送（已定） | 会议里停下来改错会打断发言节奏，识别错误用重说一遍自然纠正。主规格 §0.1 与 §10.4 已同步；只对 Meeting 页生效，单角色 Practice 页仍走「回填输入框、人工确认」。 |
| 评价维度 | 本期不加新维度 | 先把会议上下文（谁在场、对方刚说了什么）喂给评价器，让「回应相关性」按会议语境判断。「插话时机/轮流/澄清」这类维度等真实用过再定 —— 用想象出来的维度改 rubric，会让历史报告不再可比。 |
| 角色命名 | 虚构人名 | 比职位称谓更沉浸，但必须虚构明显、不映射任何真实公司或真人（§1.4）。 |

仍未定，且不阻塞 6.1–6.4：AI 之间互相打断的密度、会议是否有议程进度（走完自动结束 vs 学习者点结束）。

## 11. 实施拆解（Phase 6）

| 步骤 | 内容 | 验收 |
|---|---|---|
| 6.1 | 数据模型：`cast`、`speaker_key`、`seq`、迁移、归一化函数 | **已完成（2026-10-02）**：迁移 `3c9f1a7d24b8` 在 21 个既有会话 / 105 条消息上跑通并可逆往返；`scenario_cast()` 对旧快照返回单元素数组；旧快照未被改写；169 个后端测试全绿 |
| 6.2 | Provider：多角色剧本生成 + 结构校验 + 一轮重试；契约升级到 `assistant_messages` | **已完成**：未知 speaker / 超长段 / 空段 / 非相邻重复发言被拒绝并重试一次；两种输出形状（json 与 `[key] 内容`）都收；真 provider 实测 3 人会议开场与多轮对话均 201，单轮 1.6–6.1 秒 |
| 6.3 | 服务层与 API：一轮 N 条同事务写入、幂等重放返回同一组、`GET /sessions/{id}` 带发言人 | **已完成**：整轮一个事务、`seq` 连续；幂等重放返回相同 N 条与相同顺序；`participants` 随会话详情下发；测试 169 → 197 |
| 6.4 | 客户端：对话页按 cast 参数化（与会者条 + 发言人颜色 + 连续发言成组） | **代码完成**：`tsc --noEmit` 干净、web 预览渲染核对过、真机待用户确认 |
| 6.5 | 场景种子：会议场景 | **已完成**：`design-review-scope-01`（3 人设计评审）、`standup-blocker-01`（2 人站会），种子走 `normalize_cast` 校验，`ai_character` 镜像第一位与会者 |
| 6.6 | 语音输出（TTS） | 单独立项，不在 6.1–6.5 的交付范围内 |

每步都走现有门禁：`ruff check` / `ruff format --check` / `pytest -q` / `tsc --noEmit`，加上真机验证（web 渲染过不等于 native 侧成立）。
