# Voxora 多用户设计草案（Phase 7）

> 文档状态：Draft v0.1（待评审，**尚未实现**）
> 日期：2026-10-03
> 前置文档：`docs/software-design-v0.1.md`（主规格，Draft v0.20）、`docs/meeting-mode-v0.1.md`
> 范围：让**一台后端服务多个人**（邀请制，本人 + 少量受邀者），仍是本机/单机部署。
> 本文不覆盖：云托管（另一份部署文档）、付费与计费、组织/团队概念。

---

## 0. 与主规格的关系

主规格 §12 写的是「上线前实现 Auth；每条用户私有资源查询均使用 `current_user.id`」，§7.12 的
错误码表里却没有 401/429，§18 把「ADR-001 认证边界与公网部署条件」列为待建。本文把那句话落成
可实现的契约。

本草案生效时会显式修订主规格的这些位置（一处决策往往出现在多处，改动必须成套）：

| 主规格位置 | 现状 | 本草案的修订 |
|---|---|---|
| §3.1 请求边界 | loopback 免 token，其余共用 `API_ACCESS_TOKEN` | 业务路由改为「解析令牌 → `current_user`」；共享 token 降级为**仅本地开发**开关 |
| §6.3 `users` | email/display_name/status | 新增 `monthly_token_budget`、`last_seen_at`；`status` 增加 `invited` |
| §6.3 `user_profiles` | 规格里有，**代码里没有这张表** | 本文仍不实现，单列 §14 作为独立缺口 |
| §7.12 错误码 | 无认证/配额类 | 新增 401 `authentication_required` / `invalid_token`、429 `rate_limited` / `quota_exceeded`、403 `account_disabled` |
| §10.1 MVP 页面 | 无登录页 | 新增 Login（邀请码）；启动时先读本地令牌 |
| §10.2 客户端目录 | `src/api/client.ts` 从环境变量取 token | token 改为运行时从 `expo-secure-store` 读 |
| §11.2 Mobile 环境变量 | 只列了 base URL，但实现把同一个共享 token 也内嵌进 APK | 客户端不再内嵌长期凭据：令牌运行时兑换并存入 `expo-secure-store` |
| §12 安全与隐私 | 「未认证的本地 MVP 不可绑定公网 IP」 | 收口为：生产入口只接受用户令牌；共享 token 仅 loopback 开发用 |
| §14.2 边界测试 | 第 8 条「越权返回统一 404」 | 扩为跨用户全资源矩阵 + 令牌生命周期 + 配额 + 迁移 |

### 0.1 与现状的一处不一致（必须在 M1 收掉）

当前线上实例（`https://api.semispeak.com`）是「公网可达 + 一个共享 bearer token」，而该 token 是
**内嵌在 APK 里的**（`EXPO_PUBLIC_API_ACCESS_TOKEN` 在打包时被替换进 Hermes bundle，任何人下载
这个 APK 都能取出来）。单用户时这只是偷懒；多用户时它等于「没有认证」。M1 的定义就是把它收掉，
不是可选优化。

---

## 1. 目标与非目标

**目标**

1. 同一个人换手机/重装 App 后，训练数据仍在（数据在服务端，已经如此）。
2. 受邀者各自登录，彼此**看不到对方的会话、消息、评价、复习项**。
3. 谁的 AI 花销算在谁头上，且能封顶 —— 否则多用户就是「你替所有人付 DeepSeek 账单」。
4. 一台机器（本机或一台云主机）能跑住 3–10 个人，不被某一个人的长音频拖垮。

**非目标**（本文明确不做）

- 自助注册、邮箱验证、找回密码、社交登录（无邮件基础设施，见 §2 的取舍）。
- 组织/团队/班级、共享场景集、排行、社交。
- 计费与支付。
- 管理后台 UI：封禁、发邀请码、看用量都用命令行或 SQL 完成（用户量 ≤10）。
- 每用户独立数据库/独立进程（那是另一条更简单的路，见 §14）。
- 实时多人语音（仍在主规格 §1.4 范围外）。

**为什么值得做**：他本人预计 2027 年前是唯一用户。真要做多用户，动机只有一个 —— 想让同学/同事
一起练，且愿意替他们承担 AI 成本。本文把「到时候该怎么做」一次写清楚，避免临时起意做出一个
半吊子认证。

---

## 2. 身份模型

### 2.1 决策：邀请制 + 一次性邀请码，先不做密码

| 方案 | 需要的基础设施 | 工作量 | 结论 |
|---|---|---|---|
| A. 自助注册 + 邮箱密码 | SMTP、验证邮件、找回密码、防刷 | 最大 | **不做** |
| B. 邮箱 + 密码（管理员发号） | argon2id、找回密码仍缺 | 中 | 备选，推迟 |
| C. magic link（邮件一次性登录） | SMTP + 邮件模板 | 中 | 不做（同上，无邮件） |
| D. **一次性邀请码 → 长期令牌** | 只需要一个发码通道（微信/口头/SQL） | 最小 | **已定（默认）** |

选 D 的理由：受邀者 ≤10 人，发码通道本来就有（他通过微信收 Hermes 消息），而密码体系真正贵的
不是"存密码"，是**找回密码**那条链路（没有邮件就必然变成人工重置）。D 把"忘记凭据"退化成
"再发一个邀请码"，人工成本与 A/B 的找回流程相同，但代码量小一个数量级。

**已定**：

- 邀请码由已存在的用户（第一个是引导账号）签发，`POST /api/v1/auth/invite-codes`。
- 邀请码**单次使用**，默认 7 天过期，只存哈希。
- 客户端输入邀请码 → 换回一个**设备令牌**（长期），存 `expo-secure-store`。
- 换令牌时同时创建 `users` 行；`display_name` 由邀请码携带（"发码时写名字"）。
- 丢失设备 = 管理员禁用该设备令牌或再发一个码，不引入密码。

**待决（非阻塞，有默认值）**：将来是否升级为「邮箱 + 密码 + 找回」。给默认：等受邀者超过 10 人
或出现"要自己改密码"的真实诉求时再补，届时 D 的令牌仍然兼容（登录后发同一种令牌）。

### 2.2 账号状态

`users.status` 增加一个值：

| 值 | 含义 | 可登录 | 可读历史 |
|---|---|---|---|
| `invited` | 邀请码已签发、尚未兑换 | 否 | 否 |
| `active` | 正常 | 是 | 是 |
| `disabled` | 管理员封禁 | 否（403 `account_disabled`） | 否 |

`disabled` 是**软封禁**：数据保留，令牌全部撤销（`auth_sessions.revoked_at`），不删数据。删除数据
另走 §11 的"删除账户"。

---

## 3. 数据模型

沿用主规格 §6.1 的通用约定（UUID 主键、`TIMESTAMPTZ NOT NULL DEFAULT now()`、业务表带
`created_at`、可变实体带 `updated_at`）。以下 DDL 与当前实现对齐（注意：实现里 `email` 是
`String(320)` 而不是规格写的 `CITEXT`，本文按实现写；若要改回 CITEXT 需单独迁移，与本草案无关）。

### 3.1 `users`（增列）

```sql
ALTER TABLE users ADD COLUMN last_seen_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN monthly_token_budget INTEGER;   -- NULL = 用全局默认
ALTER TABLE users DROP CONSTRAINT ck_users_status;
ALTER TABLE users ADD CONSTRAINT ck_users_status
    CHECK (status IN ('invited', 'active', 'disabled'));
```

- `last_seen_at`：任何带令牌的请求都刷新它（"最后在线时间"，用于你自己看谁还在用）。
- `monthly_token_budget`：per-user 覆盖值，NULL 表示取 `settings.default_monthly_token_budget`。

### 3.2 `auth_sessions`（设备令牌，新表）

```sql
CREATE TABLE auth_sessions (
    id            UUID PRIMARY KEY,
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash    CHAR(64) NOT NULL UNIQUE,      -- sha256(token) 的 hex，明文永不落库
    device_label  VARCHAR(60),                   -- 客户端自报，仅用于展示与撤销
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL,
    revoked_at    TIMESTAMPTZ
);
CREATE INDEX ix_auth_sessions_user_active ON auth_sessions (user_id) WHERE revoked_at IS NULL;
```

**已定**：

- 令牌是 **32 字节随机数的 base64url**（`secrets.token_urlsafe(32)`），不是 JWT。理由：需要能撤销
  （禁用账号、丢手机）、能看到"谁在用"；JWT 的过期语义反而要求再建一张黑名单表，等于绕回来。
- **只存哈希**（sha256，不带盐：令牌本身是 256 位随机数，不需要抗字典；加盐会阻止按哈希查表，
  所以查询用 `token_hash = sha256(明文)`）。日志、错误信息里绝不出现明文令牌。
- 有效期默认 90 天，**滑动续期**：`last_used_at` 每次刷新，且当 `expires_at - now() < 30 天` 时把
  `expires_at` 推到 `now() + 90 天`。理由：一台手机正常用起来不该每 90 天重新登录一次。
- 每设备一行，可多设备并存。撤销单台不影响其他设备。
- 每用户活跃令牌上限默认 5（超过时报 429 `too_many_devices`，先撤销旧的才能加新设备）——防止
  一个泄漏的令牌被无限复制。

### 3.3 `invite_codes`（新表）

```sql
CREATE TABLE invite_codes (
    id                UUID PRIMARY KEY,
    code_hash         CHAR(64) NOT NULL UNIQUE,   -- sha256(码) 的 hex
    display_name      VARCHAR(80) NOT NULL,       -- 兑换后写入 users.display_name
    created_by        UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at        TIMESTAMPTZ NOT NULL,
    used_at           TIMESTAMPTZ,
    used_by_user_id   UUID REFERENCES users(id) ON DELETE SET NULL,
    revoked_at        TIMESTAMPTZ
);
```

- 码本体是 8 组 4 字符的可读音段（`secrets.token_hex` + 去掉易混字符），方便在微信里手抄；
  熵仍然远高于暴力猜解（≥ 80 bit）。
- `used_at` 非空即失效；`revoked_at` 用于"发错了，作废"。

### 3.4 `ai_usage`（计量，新表）

```sql
CREATE TABLE ai_usage (
    id                UUID PRIMARY KEY,
    user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind              VARCHAR(24) NOT NULL,   -- roleplay | advance | evaluation | synthesis | transcription
    provider          VARCHAR(40) NOT NULL,   -- deepseek | faster_whisper | piper | mock
    model             VARCHAR(60),
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    audio_seconds     NUMERIC(8,2) NOT NULL DEFAULT 0,   -- 转写/合成用，tokens 为 0
    session_id        UUID REFERENCES practice_sessions(id) ON DELETE SET NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (kind IN ('roleplay','advance','evaluation','synthesis','transcription'))
);
CREATE INDEX ix_ai_usage_user_created ON ai_usage (user_id, created_at);
```

- **月度用量 = `SUM(prompt_tokens + completion_tokens) WHERE user_id = ? AND created_at >= date_trunc('month', now())`**。
  不预聚合：个人规模的量级（每人每月几十条）不值得多一张会漂移的汇总表。
- 写入时机：拿到 provider 的 usage 之后，**与业务写入同事务**（roleplay/评价/推进都在自己的事务里）；
  转写没有 usage，就记 `audio_seconds`。计量写失败不能把用户的请求打成 500 —— 见 §7.4。
- `transcription` / `synthesis` 也记，但**不计入 token 预算**（它们不花钱，只有 CPU）。它们存在的
  意义是滥用排查与"谁在传 300 秒音频"。

---

## 4. 认证流程

### 4.1 签发（引导账号的唯一特殊之处）

第一个用户由种子产生：`python -m app.db.seed` 建 `users` 行（沿用 `LOCAL_USER_ID` 那个固定 UUID，
这样现有历史数据天然属于他本人），状态 `active`。**引导账号用一次性安装令牌激活**：

- 首次迁移后，`run-api.sh` 若发现"没有任何活跃 `auth_sessions`"，就在日志里打印一行
  `bootstrap: <一次性码>`（同时写 `/var/lib/voxora/bootstrap-code` 或仓库外的 `infra/.bootstrap`，
  权限 0600）。用它换出第一台设备令牌；换完即作废。
- 环境变量 `API_ACCESS_TOKEN` 保留，但语义收窄为**开发用**：仅在 `APP_ENV=local` **且** loopback
  客户端下免令牌（现有测试与本地调试依赖它，见 §6.2）。公网路径不再接受它。

### 4.2 兑换邀请码

```http
POST /api/v1/auth/redeem
Content-Type: application/json

{ "code": "K7PM-2XQF-...", "device_label": "Pixel 7" }
```

成功（201）：

```json
{
  "token": "8sQ...base64url...",
  "expires_at": "2027-01-01T00:00:00Z",
  "user": { "id": "…", "display_name": "小林", "status": "active" }
}
```

失败：410 `invite_code_used` / `invite_code_expired`（码本身不区分"不存在"与"别人的"，统一 404
`resource_not_found`，避免探码）。

### 4.3 使用

```http
Authorization: Bearer <token>
```

服务端：`sha256(明文) → auth_sessions` 查行 → 校验 `revoked_at IS NULL AND expires_at > now()` →
取 `users`（`status='active'` 才放行）→ 刷新 `last_used_at`（以及条件性 `expires_at`）→
把 `User` 交给业务层。

失败语义（**已定**）：

| 情况 | HTTP | code |
|---|---|---|
| 没有 Authorization 头 | 401 | `authentication_required` |
| 令牌格式合法但查不到 / 已撤销 / 已过期 | 401 | `invalid_token` |
| 用户 `disabled` | 403 | `account_disabled` |
| 令牌有效但超出配额/限速 | 429 | `quota_exceeded` / `rate_limited` |

**401 不带任何细节**（不区分"过期"与"不存在"），否则等于给攻击者一个探针；`invalid_token` 的
含义就是"这个令牌不能用，请重新登录"。

### 4.4 登出与撤销

- `POST /api/v1/auth/logout`：撤销**当前**令牌（`revoked_at = now()`），返回 204。
- `GET /api/v1/auth/me`：返回当前用户 + 设备列表（`id`、`device_label`、`last_used_at`），客户端
  "设置"页用它。
- `DELETE /api/v1/auth/sessions/{id}`：撤销指定设备（只能撤销自己的）。
- 管理员动作（封禁、发码、看用量）用 CLI/SQL，不建后台：`app/admin.py` 提供
  `invite <name>` / `disable <email>` / `usage [--month]` 三个子命令，走同一套 settings 与数据库。

---

## 5. API 契约变更清单

| 端点 | 变更 |
|---|---|
| `POST /auth/redeem` | 新增（§4.2） |
| `POST /auth/logout` | 新增（§4.4） |
| `GET /auth/me` | 新增（§4.4） |
| `POST /auth/invite-codes` | 新增（已登录用户可发；§2.1） |
| `GET /health` | 不变：永远免认证，不含业务数据（主规格 §3.1） |
| 其余全部业务端点 | **认证方式变更**：`require_practice_access`（共享 token 比较）→ `current_user`（令牌 → User 行）；请求/响应体不变 |

**已定**：不新增"用户 id 参数"。所有资源归属一律取自令牌对应用户，客户端传的 `user_id` 一律忽略
（主规格 §12 已规定，这里是实现口径）。

---

## 6. 授权与隔离

### 6.1 逐处触点（这就是全部工作量）

`settings.local_user_id` 目前出现在 4 个源文件、15 处；替换为入参传入的 `user_id`：

| 文件 | 现在的样子 | 改成 |
|---|---|---|
| `app/core/config.py` | `local_user_id` 是身份 | 降级为**引导账号 ID**，仅 seed 与本地开发用 |
| `app/services/practice.py` | 建会话/查会话按 `settings.local_user_id` | 形参 `user_id: UUID` |
| `app/services/evaluation.py` | 评价读写按 `settings.local_user_id` | 形参 `user_id` |
| `app/services/review.py` | 5 处过滤与写入 | 形参 `user_id` |
| `app/api/deps.py` | `require_practice_access` 只做"放行/401" | 新增 `current_user`，返回 `User`；测试环境用 `get_db_session` 的同一模式注入 |
| `tests/` | 6 处 | 夹具里显式建两个用户，默认用 A |

**关键约束**：`app/api/deps.py` 里 `current_user` 是唯一产出 `User` 的地方；service 层继续不依赖
FastAPI（主规格 §3.1），也就不依赖 `Request`。这保持了现有的可测性。

### 6.2 所有权规则

- 私有资源：`practice_sessions`、`messages`（经 session）、`evaluations`（经 session）、`review_items`。
- 规则：查询条件永远带 `user_id == current_user.id`；他人资源返回 **404 `resource_not_found`**
  （不返回 403，避免"存在但不属于你"的信息泄漏）。这条规则已经在 `review-items/{id}` 上实现过，
  现在要覆盖全部资源。
- 公共资源：`scenarios`（只有 `status='active'` 可建会话）。场景不归属用户，多用户共享。
- 管理员**没有**读他人数据的特权路径。他若要看别人练得怎样，让对方自己导出或截屏 —— 这不是技术
  限制，是隐私承诺的一部分（§11）。

---

## 7. 配额、计量与限速

### 7.1 为什么必须有

一轮 roleplay 大约 300–700 completion tokens，一次完整评价 2000–2800（本机实测，见 `progress.md`
的成本一节）。一个人一天练 20 轮 + 几次评价约 1–1.5 万 tokens；10 个人一个月就是数百万量级。
多人共用时，**没有上限等于把 DeepSeek 账单交给别人的手指**。

### 7.2 已定的默认值（写进 config，可改）

| 配置项 | 默认 | 说明 |
|---|---|---|
| `default_monthly_token_budget` | 300000 | 每人每自然月（UTC）token 上限；`users.monthly_token_budget` 可覆盖 |
| `rate_limit_requests_per_minute` | 30 | 每用户每分钟请求数（含转写、合成） |
| `rate_limit_transcriptions_per_day` | 60 | 每天上传音频次数上限（CPU 保护） |
| `max_active_sessions_per_user` | 30 | 活跃会话上限，防"忘了结束"堆积 |
| `transcription_concurrency` | 2 | 全局同时转写数（§8） |
| `max_active_auth_sessions` | 5 | 每用户设备令牌上限（§3.2） |

### 7.3 判定与语义

- 配额检查在**业务动作开始前**：当前月 `SUM(prompt+completion)` ≥ 预算 → 429 `quota_exceeded`，
  `details` 里带 `used` / `budget` / `resets_at`，客户端渲染成"本月额度用完了，X 号重置"。
- 限速用**进程内滑动窗口**（单进程部署，没有 Redis，也不引入）。若将来跑多 worker，必须把计数器
  挪到数据库或 Redis —— 这一条写进代码注释，避免有人加 `--workers` 之后限速静默失效。
- 配额用尽**不中断进行中的会话**：可以继续读历史、看评价、复习列表（读不花钱）；只有会触发模型调用
  的动作（发消息、推进、生成评价、转写）被拒。这一条是为了不让学习者卡在半场会话里。

### 7.4 计量写入不能毁掉请求

- 拿到 usage 后就地写 `ai_usage`，与业务写入同事务（失败一起回滚，语义干净）。
- **例外**：转写结束时业务上什么都没写，此时计量写失败只记 warning（`logger.warning`），不改变已经
  成功的转写响应。理由：让"记一次用量"失败去毁掉一个已经完成 26 秒 CPU 工作的请求，是错的权衡。
- 供应商没返回 usage（例如 mock provider）时也要记一行，token 记 0 —— 便于区分"没调用"与"调用但没计到"。

---

## 8. 并发与资源

### 8.1 现状与风险（实测）

- 转写走 `asyncio.to_thread`（`faster_whisper_speech.py`），**不阻塞事件循环**，但**没有并发上限**。
  3 个人同时传 300 秒音频 = 3 个 CPU 满载线程互相抢核，单段耗时从 27 秒（本机 i5-10300H 实测）
  掉到 80–100 秒以上，逼近 `SPEECH_TIMEOUT_SECONDS=180` 会变成 504。
- 常驻内存：本机实测 API 进程 RSS 约 2 GB（whisper small.en int8 + piper 会话）。多用户不会让它
  线性增长（模型是共享的），但**并发转写的峰值内存**会上去。
- piper 合成按音色懒加载（已有实现），0.2 秒/句，可忽略。

### 8.2 已定

- **全局转写信号量**（`transcription_concurrency=2`）：第 3 个请求排队等待，而不是并发执行。
- **每用户同时 1 个转写**：自己的第二段排队即可，避免一个人占满全局名额。
- **排队语义**：等待超过 `speech_queue_wait_seconds`（默认 60）→ 429 `transcription_busy`，
  `details` 带 `retry_after`；客户端提示"前面还有一段在转写，稍后再试"，而不是超时 504。
- **每用户同时 1 个生成中轮次**：已由既有的 `turn_in_progress`（409）覆盖，不改。
- 会话级并发（同一 session 两个 turn）仍由 `with_for_update()` 的行锁保证（主规格 §9.3），不改。

---

## 9. 客户端

### 9.1 页面与状态

- 新增 `app/login.tsx`：输入邀请码 → `POST /auth/redeem` → 存令牌 → `router.replace("/")`。
- 启动流程：读 `expo-secure-store` → 有令牌就先 `GET /auth/me` 验证（顺带拿 `display_name`）；
  401 就跳登录页。**不在离线时假设令牌有效**，离线直接进首页、等第一个请求 401 再跳。
- 设置页新增：显示名、当前设备、其他设备列表（可撤销）、登出。
- **删除** `EXPO_PUBLIC_API_ACCESS_TOKEN`：`app.json`/eas.json 的 `preview` 环境变量、`.env.local`、
  以及 `src/api/client.ts` 里读它的那几行。构建产物里必须搜不到任何长期凭据（M1 的验收项）。

### 9.2 API 客户端

- `src/api/client.ts`：token 来源改为内存缓存 + `expo-secure-store` 持久化；`buildHeaders()` 用当前
  令牌；收到 401 `invalid_token` 时清空令牌并把用户送回登录页（一次性，避免循环）。
- 429：`quota_exceeded` / `rate_limited` / `transcription_busy` 三个 code 各自有中文文案（现有
  `describeError` 扩展），且**不**清空令牌、**不**跳登录页。

---

## 10. 迁移路径（现有数据怎么办）

1. 迁移只加表/加列，不删不改现有数据（现有行 `user_id` 已经是引导账号的 UUID，天然正确）。
2. `python -m app.db.seed` 保持幂等：仍以 `LOCAL_USER_ID` 建/复用引导账号。
3. 首次启动若没有任何活跃令牌 → 打印引导码（§4.1）。
4. `API_ACCESS_TOKEN` 的既有用法在 `APP_ENV=local` 下继续可用（loopback 免令牌不变），测试套件不需要
   改认证夹具就能先跑起来；跨用户隔离测试是**新增**的，不是改写既有断言。
5. 回滚：所有新增都是增量；回滚到上一版本代码后，多出来的表不影响旧代码（旧代码不认识它们）。

---

## 11. 运维与隐私

- **备份**：多用户后从"想要"变"必须有"。`infra/backup.sh`：`pg_dump` → 按天保留 14 份 + 每月 3 份；
  备份文件里包含所有人的 transcript，权限 0600，不进 git。
- **健康检查**：`GET /health` 保持免认证；另加一个只在本机可用的 `/health/deep`（查数据库 + 最近
  一次模型调用时间）。多用户后别人的手机依赖这台机器，**挂了要有人知道**：复用现有的微信通道，
  由 cron 每 10 分钟打一次公网 `/health`，连续两次失败才通知（避免抖动刷屏）。
- **账户删除**：`app/admin.py delete-account <email>` → 级联删除其 sessions/messages/evaluations/
  review_items/ai_usage/auth_sessions（主规格 §6.1 的删除行为），保留 `scenarios`。
- **日志脱敏**：Authorization 头、令牌明文、邀请码明文一律不进日志；`ai_usage` 只存用量不存内容。
- **隐私说明必须同步更新**：现在的文档写的是"单人本机使用"。多用户后要写清楚：谁的 transcript 谁能
  看到（只有本人；管理员无特权读路径）、数据存在哪、删除怎么做、AI 供应商能看到什么（对话内容会
  发给 DeepSeek）。**这条不写完，M1 不算完成。**
- **ADR**：M1 开始前把 `docs/adr/ADR-001-auth-boundary.md` 落成文件（主规格 §18 已列待建），
  内容即本文 §2/§4/§12 的决策摘要。

---

## 12. 测试要求（新增）

在现有 294 条之上补充，全部用临时 SQLite + 假 provider，不需要真实 Postgres 或密钥：

1. 非 loopback 且无令牌 → 401 `authentication_required`（扩展现有 `test_access_coverage.py`）。
2. 伪造/过期/已撤销令牌 → 401 `invalid_token`；`disabled` 用户 → 403 `account_disabled`。
3. 跨用户矩阵：A 的 `practice_sessions` / `messages` / `evaluations` / `review_items` 对 B 全部 404，
   逐个端点断言（不只是列表，含详情、finish、evaluation、advance、review PATCH）。
4. 邀请码：单次使用（第二次 410）、过期（410）、乱码（404）、兑换后建出的用户状态是 `active`、
   `display_name` 来自码。
5. 令牌滑动续期：`last_used_at` 被刷新；`expires_at` 只在 30 天内时延长；撤销后立即失效。
6. 每用户设备上限：第 6 次兑换 → 429 `too_many_devices`。
7. 配额：月初干净 → 用掉预算后 `POST /messages` 等写动作 429，而 `GET /sessions`、`GET /review-items`
   仍 200。
8. 限速：同一用户第 31 个请求/分钟 → 429 `rate_limited`；换一个用户不受影响。
9. 转写并发：第三个并发转写在信号量处排队，超时窗口内返回 429 `transcription_busy`（用假 provider
   人为占住名额）。
10. 计量：一次 roleplay + 一次评价后 `ai_usage` 有对应行且 token 数来自 provider 的 usage；
    mock provider 记 0。
11. Alembic 从空库迁移成功，且四个新表/新列存在（扩展现有第 10 条）。
12. **构建产物检查脚本**：对打包后的 `index.android.bundle` 断言搜不到旧共享 token 的哈希前缀 ——
    这是唯一能证明"包里没有长期凭据"的方式（`~/.hermes/cache/scratch` 里的那套 grep 手法可以固化成
    `apps/mobile/scripts/check_bundle_secrets.sh`）。

---

## 13. 实施拆解（Phase 7）

四个纵向切片，每个都能独立交付并验收。

### M1 — 身份接线（预计 2 天）

交付：`users` 增列、`auth_sessions`、`invite_codes`、`current_user` 依赖、三个 auth 端点、
`admin.py invite`、客户端登录页 + secure-store、**移除内嵌 token**。
验收：两台设备各自兑换邀请码登录，互相看不到对方的会话；打包产物里搜不到旧 token；
现有 294 条测试全绿（新认证夹具就位后）。

### M2 — 成本与滥用（预计 1.5 天）

交付：`ai_usage` 表与写入、配额与限速中间件、`admin.py usage`、客户端 429 文案。
验收：把预算调到 1000 tokens 跑一场练习 → 第 N 轮被 429 拒绝且读接口仍可用；
`admin.py usage` 能按用户/按月列出用量，与 provider 返回的 usage 对得上。

### M3 — 并发（预计 0.5 天）

交付：转写信号量 + 每用户 1 并发 + `transcription_busy` 语义与客户端提示。
验收：脚本并发发起 3 段 60 秒音频 → 第三个在排队窗口内收到 429 且带 `retry_after`，不出现 504；
两段串行总耗时不超过单段 ×2.2。

### M4 — 运维与隐私（预计 1 天）

交付：`infra/backup.sh`、外部健康检查 cron、`admin.py disable/delete-account`、隐私说明更新、
ADR-001 落文件。
验收：备份能恢复到一个空库并读出全部会话；拔掉 API 后 20 分钟内微信收到告警；
隐私说明逐条与实现对齐（逐条勾）。

**总计约 5 天**（我个人估算是 4–6 天，含验收）。若走"一人一个实例"替代路线（§14），成本是 0.5 小时。

---

## 14. 决策、假设与替代路线

### 14.1 已定

1. 身份用「邀请码 → 设备令牌」，不引入密码与邮件（§2.1）。
2. 令牌是 opaque + sha256 存哈希，可撤销，90 天滑动（§3.2）。
3. 所有权一律取自令牌，客户端传的 user_id 一律忽略；越权返回 404（§6.2）。
4. 必须有每用户 token 预算与限速，默认 300k/月、30 次/分（§7.2）。
5. 转写有全局与每用户并发上限（§8.2）。
6. 管理员没有读他人训练数据的路径（§6.2、§11）。

### 14.2 假设（若被推翻要重新评估）

- 受邀者 ≤10 人、都通过微信拿到邀请码。若变成陌生人自助注册，§2 整套需要重做（回到方案 A）。
- 单进程部署。多 worker 会让进程内限速失效（§7.3）。
- 单个转写 ≤300 秒、≤32 MB（主规格 §7.11）。若放宽，§8 的并发上限必须按新上限重算。

### 14.3 待决（非阻塞，已有默认值）

| 事项 | 默认 | 影响 |
|---|---|---|
| 邀请码有效期 | 7 天 | 发码太早会过期，重发成本＝一条命令 |
| 令牌有效期 | 90 天滑动 | 更长更省事，泄漏窗口更大 |
| 每月 token 预算初值 | 300000 | 拍脑袋值，第一周看账单再定 |
| 是否需要 `user_profiles` | 不做 | 规格里有、代码里没有；与本草案无关的独立缺口（§0 表） |

### 14.4 替代路线：一人一个实例（如果只是 2–3 个人想用）

**不做任何代码改动**：同一份代码部署多份（不同端口/域名/数据库/.env），每人一份，各自一个共享
token。半小时能上，代价是你要替他们管机器，且"谁用了多少"由机器隔离天然成立。

**选哪条**：人数 ≤3 且都认识 → 走这条，本文封存；人数 >3 或你不想替每个人修机器 → 按 M1–M4 做。
这个判断不需要现在做，本文放在这里就是为了到时候不用重新想。

---

## 15. ADR 与主规格改动清单

- 新建 `docs/adr/ADR-001-auth-boundary.md`（§11 末尾要求）。
- 主规格：§0.1 决策表新增一行「认证边界」；§3.1 改写为令牌模型；§7.12 增补 401/403/429；
  §11.2 删除 `EXPO_PUBLIC_API_ACCESS_TOKEN`；§12 收口公网条件；§14.2 增补第 16–22 条（本文 §12）；
  §17 增加 Phase 7；§19 第 1 条（是否只由本人使用）按本文的 M1–M4 结论勾掉。
- 本草案实现后，本文与主规格**同时**更新，不能只改一处（主规格的成对修订规则）。
