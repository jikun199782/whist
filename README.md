# 棋牌游戏中心 — Whist

基于 Flask 的 Web 卡牌游戏中心，实现经典四人惠斯特桥牌（Whist）游戏。人类玩家（South）与三名 AI 玩家（North / East / West）进行固定搭档对战。


## 快速开始

### 环境要求

- Python 3.9+
- Flask 3.x

### 安装与运行

```bash
# 安装依赖
pip install flask

# 启动服务器
cd games_center_work2_org
python flask_app.py
```

浏览器访问hotocean.pythonanywhere.com，选择 **Whist** 即可开始游戏。

---

## 项目结构

```
games_center_work2_org/
├── flask_app.py            # Flask 主应用（路由、session、游戏分发）
├── playcard.py             # 卡牌工具模块（排序、命名、SVG 映射）
├── blackjack.py            # 21点游戏
├── blackjack_eu.py         # 欧式21点
├── whist.py                # Whist 游戏逻辑
├── static/
│   ├── base.css            # 全局样式
│   ├── whist.css           # Whist 牌桌布局
│   ├── whist.js            # Whist 前端交互
│   ├── svg-cards.svg       # 卡牌精灵图（52张 + 背面）
│   └── *.svg               # 花色图标（heart/spade/diamond/club）
└── templates/
    ├── base.html           # 基础模板（导航栏、标题）
    ├── select.html         # 游戏选择页
    ├── whist.html          # Whist 游戏页面
    ├── rules.html          # 规则说明页
    └── ...                 # 其他页面
```

---

## 游戏规则

### 基本设定

| 项目 | 说明 |
|------|------|
| 玩家人数 | 4人（South = 你，North/East/West = AI） |
| 搭档 | South + North **vs** East + West |
| 牌数 | 标准52张（无大小王） |
| 发牌 | 每人13张 |
| 牌大小 | A > K > Q > J > 10 > 9 > ... > 2 |

### 王牌（Trump）

最后一张发出的牌翻开，其花色即为本局**王牌花色**。王牌大于任何非王牌。

### 出牌流程

1. **领牌**：每墩由领牌者先出任意一张牌，该牌的花色即为本墩的**引导花色**
2. **跟牌**：其余玩家顺时针出牌，**必须出同花色**（如有）；若缺门，可出任意牌（含王牌）
3. **胜负**：王牌最大者赢 → 无王牌时引导花色最大者赢
4. **下一墩**：赢家成为下一墩的领牌者

### 胜利条件

13墩中率先赢得 **≥7 墩** 的队伍获胜。

---

## 技术架构

### 后端

- **框架**：Flask + Jinja2
- **状态存储**：Flask Session（Cookie-based）
- **模块接口**：每个游戏导出 `new_game(session)` 和 `game_update(session, action)` 两个函数

### 前端

- **交互模式**：服务端渲染 + 原生 JavaScript
- **数据桥接**：Jinja2 `|tojson` 将 Python dict 序列化为 JS 对象
- **状态机**：`stop_type` 字段驱动 UI（`new_trick` → `lead_card` → `follow_card` → `game_over`）

### AI 策略

| 情形 | 策略 |
|------|------|
| 领牌 | 出点数最小的牌 |
| 跟牌（有同花色） | 出最小的同花色牌 |
| 跟牌（缺门，有王牌） | 出最小的王牌（将吃） |
| 跟牌（缺门，无王牌） | 出最小的牌（垫牌） |

### Whist 模块架构（whist.py）

```
┌──────────────────────────────────────┐
│         Public API                    │
│  new_game()    game_update()         │
├──────────────────────────────────────┤
│         State Machine                 │
│  _advance_game()   _finish_trick()   │
├──────────────────────────────────────┤
│         Game Rules                    │
│  determine_trick_winner()            │
│  ai_choose_card()                    │
├──────────────────────────────────────┤
│         Helpers                       │
│  get_team()  next_player()           │
│  get_led_suit()  sort_hand()         │
│  cards_of_suit()  all_played()       │
└──────────────────────────────────────┘
```

---

## 关键设计决策

### 卡牌内部表示

卡牌使用 **2元素列表** `["A", "H"]` 而非字符串 `"AH"`。`playcard.py` 所有函数通过 `card[0]`/`card[1]` 下标访问，对两种格式完全兼容；而模板 `|tojson` 过滤器需要列表格式才能正确序列化为 JS 数组。

### AI 自动推进

Flask 为同步请求-响应模型，无法使用 WebSocket。`_advance_game()` 函数在单次 HTTP 请求中批量处理所有 AI 回合，直到需要人类操作，在无状态协议上模拟了多玩家回合制游戏。



---

## 许可证

本项目为课程作业，仅供学习参考。
