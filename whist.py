# whist.py 
# 配合 Flask 后端使用，状态保存在 session 中。

import random
from playcard import make_deck, get_suit, get_rank_ace_high, SUITS, get_suit_name


# 游戏常量

# 顺时针出牌顺序：北 → 东 → 南 → 西
TURN_ORDER = ['north', 'east', 'south', 'west']

# 各位置对应的玩家名称（显示用）
PLAYER_NAMES = {
    'north': 'AI Alice',
    'south': 'You',
    'east': 'AI Bob',
    'west': 'AI Charlie',
}

# 率先赢得 7 墩的一方获胜（总共 13 墩）
WINNING_TRICKS = 7


#  辅助函数

def get_team(pos):
    """
    根据玩家位置返回所属队伍。
    北、南为一方（'south_north'），东、西为一方（'east_west'）。
    参数:
        pos: 位置字符串 'north','east','south','west'
    返回:
        队伍键名
    """
    if pos in ('north', 'south'):
        return 'south_north'
    else:
        return 'east_west'


def next_player(pos):
    """
    返回顺时针方向的下一位玩家。
    参数:
        pos: 当前位置
    返回:
        下一位的位置字符串
    """
    idx = TURN_ORDER.index(pos)
    return TURN_ORDER[(idx + 1) % 4]


def get_led_suit(trick):
    """
    获取当前墩的“引牌花色”（第一张打出的牌的花色）。
    若该墩尚未有牌打出，则返回 None。
    参数:
        trick: 当前墩的字典 {位置: 牌}，牌为 [rank, suit] 或 None
    返回:
        花色字符 'H','S','D','C' 或 None
    """
    for pos in TURN_ORDER:
        card = trick.get(pos)
        if card is not None:
            return card[1]
    return None


def sort_hand(hand):
    """
    对一手牌进行排序：先按花色（H > S > D > C），再按点数降序（A 最大）。
    返回新列表，不改变原手牌。
    参数:
        hand: 牌的列表
    返回:
        排序后的新列表
    """
    suit_order = {s: i for i, s in enumerate(SUITS)}  # H:0, S:1, D:2, C:3
    return sorted(hand, key=lambda c: (suit_order[c[1]], -get_rank_ace_high(c)))


def cards_of_suit(hand, suit):
    """
    从手牌中筛选出指定花色的所有牌。
    参数:
        hand: 手牌列表
        suit: 花色字符
    返回:
        符合花色的牌列表
    """
    return [c for c in hand if c[1] == suit]


def all_played(trick):
    """
    检查当前墩是否所有四名玩家都已出牌。
    参数:
        trick: 当前墩字典
    返回:
        True 表示全部出完，False 表示还有空位
    """
    return all(trick.get(pos) is not None for pos in TURN_ORDER)


# 墩赢家判定 
def determine_trick_winner(trick, trump_suit):
    """
    判定一个已完成的墩由谁赢下。
    规则（优先级从高到低）：
        1. 若有人出将牌（王牌），则出最高将牌者获胜；
        2. 否则，出引牌花色中点数最高者获胜；
        3. 其他花色（非将牌、非引牌花色）不能赢。
    参数:
        trick: 完整的墩字典（四个位置都有牌）
        trump_suit: 本局将牌花色
    返回:
        赢家位置字符串
    """
    led_suit = get_led_suit(trick)
    best_pos = None
    best_rank = -1
    best_is_trump = False

    for pos in TURN_ORDER:
        card = trick.get(pos)
        if card is None:
            continue

        is_trump = (card[1] == trump_suit)
        rank = get_rank_ace_high(card)  # 点数 0~13，A=13

        if best_pos is None:
            # 第一个有效牌
            best_pos = pos
            best_rank = rank
            best_is_trump = is_trump
        elif is_trump and not best_is_trump:
            # 将牌优先于非将牌
            best_pos = pos
            best_rank = rank
            best_is_trump = True
        elif is_trump and best_is_trump:
            # 都是将牌，点数高者胜
            if rank > best_rank:
                best_pos = pos
                best_rank = rank
        elif not is_trump and not best_is_trump:
            # 都不是将牌，只允许引牌花色竞争
            if card[1] == led_suit and rank > best_rank:
                best_pos = pos
                best_rank = rank
        # 否则（非将牌 vs 最佳是将牌）此牌无法获胜，忽略

    return best_pos


# AI 出牌逻辑 

def ai_choose_card(hand, trick, trump_suit, position):
    """
    AI 玩家的出牌策略（简单版）：
        - 若为引牌者：出点数最小的牌（保守）。
        - 若为跟牌者：
            * 若有引牌花色，则出该花色中点数最小的牌；
            * 若没有引牌花色，则出最小的将牌（如果有）；
            * 否则出点数最小的牌作为垫牌。
    参数:
        hand: AI 当前手牌
        trick: 当前墩的字典（可能有 None）
        trump_suit: 将牌花色
        position: AI 的位置（本版本未使用，预留扩展）
    返回:
        选中的牌 [rank, suit]
    """
    led_suit = get_led_suit(trick)

    if led_suit is None:
        # AI 是引牌者 → 出最小牌
        return min(hand, key=lambda c: get_rank_ace_high(c))

    # 跟牌：必须跟引牌花色（如果手中有）
    same_suit = cards_of_suit(hand, led_suit)
    if same_suit:
        return min(same_suit, key=lambda c: get_rank_ace_high(c))

    # 没有引牌花色 → 出将牌（如有）
    trumps = cards_of_suit(hand, trump_suit)
    if trumps:
        return min(trumps, key=lambda c: get_rank_ace_high(c))

    # 既无引牌花色也无将牌 → 出最小牌垫掉
    return min(hand, key=lambda c: get_rank_ace_high(c))


#  游戏状态机
def _finish_trick(game_state):
    """
    完成当前墩：判定赢家、更新分数、设置信息并决定下一步状态（新墩或结束）。
    此函数会直接修改 game_state 字典。
    参数:
        game_state: 游戏状态字典（引用）
    """
    current_trick = game_state['tricks'][-1]
    winner = determine_trick_winner(current_trick, game_state['trump_suit'])
    team = get_team(winner)

    # 更新该队伍的得分
    game_state['scores'][team] += 1

    # 设置本轮结果消息
    if winner == 'south':
        game_state['message'] = "You win the trick!"
    else:
        game_state['message'] = f"{PLAYER_NAMES[winner]} wins the trick!"
    game_state['message_class'] = 'trick-message'

    # 检查是否有一方达到 7 墩 → 游戏结束
    if game_state['scores']['south_north'] >= WINNING_TRICKS:
        game_state['stop_type'] = 'game_over'
        game_state['message'] = "Congratulations! South-North wins the game!"
        game_state['message_class'] = 'win-message'
    elif game_state['scores']['east_west'] >= WINNING_TRICKS:
        game_state['stop_type'] = 'game_over'
        game_state['message'] = "East-West wins the game. Better luck next time!"
        game_state['message_class'] = 'lose-message'
    elif sum(game_state['scores'].values()) >= 13:
        # 若所有 13 墩打完但无人达到 7 分（极端情况），按总分判定胜负
        game_state['stop_type'] = 'game_over'
        if game_state['scores']['south_north'] > game_state['scores']['east_west']:
            game_state['message'] = "Game over! South-North wins!"
            game_state['message_class'] = 'win-message'
        else:
            game_state['message'] = "Game over! East-West wins!"
            game_state['message_class'] = 'lose-message'
    else:
        # 继续下一墩，赢家作为下一墩的引牌者
        game_state['stop_type'] = 'new_trick'
        game_state['leader'] = winner


def _advance_game(game_state):
    """
    推进游戏：自动处理 AI 的回合，直到轮到南（人类玩家）出牌，
    或当前墩结束，或游戏结束。
    此函数会在每次状态变更后被调用（新墩开始、南出牌后）。
    参数:
        game_state: 游戏状态字典（引用）
    """
    while True:
        current_trick = game_state['tricks'][-1]
        leader = game_state['leader']
        leader_idx = TURN_ORDER.index(leader)

        # 从引牌者开始，找到第一个未出牌的玩家
        next_pos = None
        for i in range(4):
            pos = TURN_ORDER[(leader_idx + i) % 4]
            if current_trick.get(pos) is None:
                next_pos = pos
                break

        if next_pos is None:
            # 所有人都已出牌 → 解决本墩
            _finish_trick(game_state)
            return

        if next_pos == 'south':
            # 轮到人类玩家，停止循环等待外部输入
            if current_trick.get(leader) is None and next_pos == leader:
                # 南是引牌者且尚未出牌
                game_state['stop_type'] = 'lead_card'
            else:
                game_state['stop_type'] = 'follow_card'
            return

        # AI 回合：自动选择并出牌
        hand = game_state['hands'][next_pos]
        if not hand:  # 防御性代码
            return

        card = ai_choose_card(hand, current_trick,
                              game_state['trump_suit'], next_pos)
        hand.remove(card)
        current_trick[next_pos] = card

        if all_played(current_trick):
            _finish_trick(game_state)
            return


# 对外 API，flask_app.py 
def new_game(session):
    """
    初始化一局新的 Whist 游戏。
    创建并洗牌，发牌（每人13张），将牌由最后一张牌决定，
    并将初始游戏状态存入 Flask session。
    参数:
        session: Flask 的 session 字典（会被修改）
    """
    session_id = session.get('session_id', '')

    # 生成一副 52 张牌并洗牌
    deck = [[c[0], c[1]] for c in make_deck()]
    random.shuffle(deck)

    # 按顺序发牌：北、东、南、西（每人 13 张）
    north_hand = deck[0:13]
    east_hand  = deck[13:26]
    south_hand = deck[26:39]
    west_hand  = deck[39:52]

    # 最后一张牌（西的最后一张）确定将牌花色
    trump_card = deck[51]
    trump_suit = trump_card[1]
    trump_suit_name = get_suit_name(trump_suit)

    # 排序手牌
    hands = {
        'north': sort_hand(north_hand),
        'east':  sort_hand(east_hand),
        'south': sort_hand(south_hand),
        'west':  sort_hand(west_hand),
    }

    # 初始游戏状态：北先引牌
    session['game_state'] = {
        'stop_type': 'new_trick',
        'hands': hands,
        'players': dict(PLAYER_NAMES),
        'leader': 'north',
        'tricks': [],          # 已完成的墩列表（每墩是一个字典）
        'scores': {'south_north': 0, 'east_west': 0},
        'trump_suit': trump_suit,
        'trump_suit_name': trump_suit_name,
        'message': None,
        'message_class': 'info-message',
    }
    # Flask 会自动将 session 的修改保存


def game_update(session, action):
    """
    处理人类玩家（南）发出的动作。
    支持的动作：
        - 'new_trick' : 请求开始新一墩
        - 'play/<rank>,<suit>' : 南出牌
    参数:
        session: Flask session 字典（包含 game_state）
        action: 动作字符串（从 URL 路径捕获）
    """
    game_state = session.get('game_state')
    if not game_state:
        new_game(session)
        return

    # 若游戏已结束，忽略所有动作
    if game_state.get('stop_type') == 'game_over':
        return

    session_id = session.get('session_id', '')

    if action == 'new_trick':
        # 检查当前墩是否已完成（无牌或已全部出完）
        if game_state['tricks']:
            current_trick = game_state['tricks'][-1]
            any_played = any(current_trick.get(pos) is not None
                             for pos in TURN_ORDER)
            if any_played and not all_played(current_trick):
                # 当前墩正在进行，不能开始新墩
                return

        # 创建空墩
        new_trick = {pos: None for pos in TURN_ORDER}
        game_state['tricks'].append(new_trick)
        game_state['message'] = None
        game_state['message_class'] = 'info-message'

        # 让 AI 先走，直到轮到南或墩结束
        _advance_game(game_state)

    elif action.startswith('play/'):
        # 解析出牌动作，格式 'play/<rank>,<suit>'
        card_str = action.split('/', 1)[1]  # 例如 'A,H'
        parts = card_str.split(',', 1)
        if len(parts) != 2:
            return
        rank, suit = parts[0], parts[1]
        card = [rank, suit]

        south_hand = game_state['hands']['south']
        if card not in south_hand:
            return  # 手中无此牌，非法

        # 根据当前 stop_type 检查出牌合法性
        stop_type = game_state.get('stop_type')
        if stop_type == 'lead_card':
            # 引牌：任何牌都合法
            pass
        elif stop_type == 'follow_card':
            # 跟牌：必须跟引牌花色（若手中有）
            current_trick = game_state['tricks'][-1]
            led_suit = get_led_suit(current_trick)
            if led_suit is not None:
                has_led_suit = any(c[1] == led_suit for c in south_hand)
                if has_led_suit and card[1] != led_suit:
                    return  # 违规，忽略
        else:
            return  # 当前状态不能出牌

        # 执行出牌
        south_hand.remove(card)
        current_trick = game_state['tricks'][-1]
        current_trick['south'] = card
        game_state['message'] = None

        # 让 AI 自动响应
        _advance_game(game_state)

