# Whist 卡牌游戏

> 从课程项目初始代码到完整多人联机 Whist 游戏的技术演进

---

## 一、技术栈

| 层次 | 技术 | 用途 |
|------|------|------|
| **后端框架** | Flask (Python) | HTTP 路由、Session 管理、模板渲染 |
| **模板引擎** | Jinja2 | 服务端渲染游戏页面，`\|tojson` 传递 Python 数据到 JS |
| **数据库** | SQLite + WAL 模式 | 多人游戏状态持久化、并发安全 |
| **前端** | 原生 JavaScript + SVG | 卡牌渲染、轮询更新、交互动画 |
| **样式** | CSS Grid + Flexbox | 牌桌布局、卡牌定位、响应式适配 |
| **卡牌图形** | SVG Sprite Sheet | 52 张牌共用一个 SVG 文件，按 ID 引用 |

### 为什么不选 WebSocket / AJAX POST？

- **轮询 (Polling)** 而非 WebSocket：PythonAnywhere 免费版不支持 WebSocket；2 秒轮询对 4 人卡牌游戏延迟可接受
- **GET 请求 + 重定向** 而非 AJAX POST：课程项目的 Flask 原始代码使用页面重定向模式，保持一致性

---

## 二、架构设计

### 2.1 模块分层

```
flask_app.py        ← HTTP 路由 / 请求分发
    ↓
whist.py            ← 单人游戏逻辑 + AI 策略 + 状态机
game_store.py       ← SQLite CRUD（仅联机模式使用）
playcard.py         ← 卡牌工具函数（花色、点数、牌组）
userlog.py          ← 游戏日志（session 存储）
    ↓
templates/          ← Jinja2 模板（whist.html, whist_multi.html, ...）
static/             ← CSS / JS / SVG 资源
```

**设计原则**：`whist.py` 不依赖 Flask，仅接收 dict-like 对象（session / game_state），可独立测试。

---

### 2.2 游戏状态机

```
waiting ──→ new_trick ──→ lead_card ──→ follow_card ──→ new_trick ──→ ... ──→ game_over
  ↑                        ↑              ↑                              ↑
  └── 联机等人              └── 引牌者出牌   └── 跟牌者出牌（循环3次）     └── 一方达7墩
```

- 状态存储：单人模式 → `session['game_state']`；联机模式 → SQLite `games` 表
- 状态驱动 UI：`stop_type` 决定按钮文字（"New Trick" / "Lead Card" / "Follow Card"）和可用性

---

### 2.3 联机架构：无状态 HTTP + 数据库 + 轮询

```
┌─ Host 浏览器 ─┐     ┌─ Flask 服务器 ─┐     ┌─ Guest 浏览器 ─┐
│ pollStatus()  │────→│ /multi/status  │←────│ pollStatus()   │
│  (2s interval)│←────│  → 查询 SQLite  │────→│  (2s interval) │
│               │     └────────────────┘     │               │
│ 出牌点击      │────→│ /multi/play    │     │               │
│               │     │  → 验证身份    │     │               │
│               │     │  → 执行出牌    │     │               │
│               │     │  → AI 自动响应 │     │               │
│               │←────│  → 重定向回页面│     │               │
└───────────────┘     └────────────────┘     └───────────────┘
```

**版本号机制**：每次状态变更 `bump_version()`，客户端轮询比对 `lastVersion`，变化时触发更新。三类响应：
- `majorChange`（new_trick / game_over / waiting）：整页重载
- `becameMyTurn`：整页重载（需渲染可点击手牌）
- 其他：增量更新 DOM（分数、消息、牌桌卡牌）

---

### 2.4 跨标签页身份隔离

```
┌─────────────────────────────────────────────────┐
│ 用户身份来源（优先级从高到低）                     │
│                                                 │
│ 1. URL query params  (?pos=south&token=abc123)  │
│ 2. sessionStorage    (whist_pos_<GAME_ID>)      │
│ 3. Flask session     (multi_position)           │
└─────────────────────────────────────────────────┘
```

- URL 参数是权威来源，每个标签页独立
- `sessionStorage` 做跨重载持久化（同名变量按 `GAME_ID` 隔离）
- Flask session 仅作初始兜底

---

## 三、关键功能实现

### 3.1 视角旋转（SLOT_MAP）

```python
# 每个玩家看到的桌子布局：
#   Self → 底部 (south 槽)
#   Partner → 顶部 (north 槽)
#   Left opponent → 左侧 (west 槽)
#   Right opponent → 右侧 (east 槽)

SLOT_MAP = {
    'south': {'south':'south', 'north':'north', 'west':'west', 'east':'east'},
    'north': {'south':'north', 'north':'south', 'west':'east', 'east':'west'},
    'east':  {'south':'east',  'north':'west',  'west':'north', 'east':'south'},
    'west':  {'south':'west',  'north':'east',   'west':'south', 'east':'north'},
}
```

**实现**：
1. 服务器在 `multi_game()` 和 `multi_status()` 中附加 `slot` 映射
2. Jinja 模板用 `{% set bottom = slot.south %}` 确定每个显示槽对应哪个游戏位置
3. JS `updateTrickCards()` 用 `data.slot` 做同样映射（增量更新路径）

---

### 3.2 AI 难度系统

```
ai_choose_card(hand, trick, trump, position, difficulty, leader)
    │
    ├── difficulty == 'easy'
    │       └── _ai_choose_card_easy()
    │           ├── 引牌: min(hand)           // 永远最小
    │           ├── 跟牌: min(same_suit)
    │           ├── 将吃: min(trumps)
    │           └── 垫牌: min(hand)
    │
    └── difficulty == 'hard'
            └── _ai_choose_card_hard()
                ├── 引牌: _ai_lead()          // ≥4将牌吊将, 否则长套引
                ├── 跟牌: _ai_follow()        // 队友赢→小, 对手赢→反超
                ├── 将吃: _ai_trump()         // 队友赢不将吃, 对手赢最小赢墩
                └── 垫牌: _ai_discard()       // 清最短花色创缺门
```

**设计模式**：策略模式 + 调度器。`ai_choose_card` 是入口，根据 `difficulty` 字符串分发到不同实现。新增难度只需添加新子策略函数 + 注册到调度器。

---

### 3.3 SQLite 持久化

```sql
-- 核心表结构
games (id, trump_suit, leader, stop_type, scores_sn, scores_ew,
       message, tricks_json, version, difficulty, created_at)

seats (game_id, position, player_type, player_name,
       session_token, is_connected)   -- PRIMARY KEY (game_id, position)

hands (game_id, position, cards_json) -- PRIMARY KEY (game_id, position)
```

**设计要点**：
- 卡牌以 JSON 存储（`[["A","H"],["K","S"],...]`）
- `version` 字段做乐观锁：每次写操作 `bump_version()`，客户端轮询比版本号
- WAL 模式：读写不互斥，支持 HTTP 多 worker 并发
- 每个函数开闭连接：无长连接、无连接池泄漏
- `init_db()` 用 `ALTER TABLE ... ADD COLUMN` 做向后兼容 migration

---

### 3.4 增量 DOM 更新

为减少页面闪烁，JS 尽量增量更新而非整页刷新：

| 数据变化 | 更新方式 |
|---------|---------|
| 分数变化 | `updateScores()` 直接修改 `.score-number` textContent |
| 消息变化 | `updateMessage()` 创建/更新 `.message` div |
| AI 出牌 | `updateTrickCards()` 更新 SVG `<use>` href 属性 |
| 回合切换 | `becameMyTurn` → 整页重载（需重新渲染手牌和按钮） |
| 新墩开始 | `majorChange` → 整页重载 |

手牌选择状态用 `sessionStorage` 持久化，重载后自动恢复。

---

### 3.5 游戏日志

```python
# userlog.py
def add_log_entry(session, message):
    session['game_log'].append([timestamp_str, message])
```

- 存储：`session['game_log']` 列表，每项 `[timestamp, message]`
- 容量控制：最大 500 条，超出裁剪旧记录
- 集成点：`new_game()`（发牌）、`_advance_game()`（AI 出牌）、`_finish_trick()`（赢墩）、`game_update()`（人类出牌）
- 渲染：Jinja 模板遍历 `log` 列表，每行一个 `.log-entry` div

---

## 四、CSS 布局设计

### 4.1 牌桌 Grid 布局

```
┌──────────┬───────────────┬──────────┐
│          │    NORTH      │          │
│  WEST    │  ┌─────────┐  │   EAST   │
│  (左手)  │  │ 牌桌中央  │  │  (右手)  │
│          │  │ trick区  │  │          │
│          │  └─────────┘  │          │
├──────────┴───────────────┴──────────┤
│              SOUTH (我的手)           │
└──────────────────────────────────────┘
```

```css
.whist-table {
    display: grid;
    grid-template-columns: minmax(190px,240px) minmax(780px,860px) minmax(190px,240px);
    grid-template-rows: 1fr auto;
}
```

- 三列两行：左（West）、中（North+牌桌）、右（East）；底行跨三列（South）
- 卡牌重叠：负 margin 实现扇形展开
- `.card.eligible:hover` 上浮 + 放大 + 阴影
- `.card.selected` 更大上浮 + 金色边框 + 发光阴影

### 4.2 卡牌 SVG 引用

```html
<svg class="card" viewBox="0 0 169 244">
    <use href="/static/svg-cards.svg#heart_1"/>
</svg>
```

全部 52 张卡牌集中在一个 SVG sprite 文件中，按 ID 引用（如 `heart_1` = 红心 A），客户端只需加载一次。

---

## 五、代码规模

| 模块 | 行数 | 职责 |
|------|------|------|
| `flask_app.py` | ~600 | HTTP 路由、请求验证、联机游戏流程 |
| `whist.py` | ~680 | 游戏状态机、单人模式、AI 策略（Easy + Hard） |
| `game_store.py` | ~520 | SQLite CRUD、座位管理、手牌/墩数据 |
| `playcard.py` | ~44 | 卡牌工具（花色、点数、名称） |
| `userlog.py` | ~20 | 游戏日志 |
| `whist_multi.html` | ~650 | 联机模板 + JS 轮询 + DOM 更新 |
| `whist.html` | ~175 | 单人模板 |
| `whist.js` | ~165 | 单人 JS（卡牌选择、按钮控制） |
| CSS 文件 | ~410 | 牌桌布局 + 基础样式 + 难度切换 |


---

## 六、核心设计决策回顾

| 决策 | 选型 | 理由 |
|------|------|------|
| 状态存储 | Session（单人）/ SQLite（联机） | 单人简单够用，联机需跨用户共享 |
| 实时同步 | 轮询 + 版本号 | PythonAnywhere 无 WebSocket；2s 延迟可接受 |
| 身份传递 | URL query param | 解决 cookie 跨标签共享问题 |
| AI 扩展 | 策略模式 + 调度器 | 新增难度不改调用方 |
| 前端更新 | 增量 DOM + 选择性重载 | 减少闪烁，保持交互流畅 |
| 卡牌格式 | `[rank, suit]` 列表 | Jinja `\|tojson` 兼容，Python/JS 通用 |
| 数据库 | SQLite + WAL | 零配置，单文件，支持并发读 |
| 模板 | Jinja2 服务端渲染 | 与原始课程代码一致，减少 JS 复杂度 |

