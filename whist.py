# whist.py
# 配合 Flask 后端使用，状态保存在 session 中。

import random
from playcard import make_deck, get_suit, get_rank_ace_high, SUITS, get_suit_name
import userlog


# 游戏常量

# 顺时针出牌顺序：北 → 东 → 南 → 西
TURN_ORDER = ['north', 'east', 'south', 'west']

# 各位置对应的玩家名称
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


def get_led_suit(trick, leader=None):
    # Return the led suit of the trick. If leader is provided, use it directly
    # to avoid incorrect results when the leader is not North.
    if leader:
        card = trick.get(leader)
        if card is not None:
            return card[1]
    for pos in TURN_ORDER:
        card = trick.get(pos)
        if card is not None:
            return card[1]
    return None


def sort_hand(hand):
    """
    对一手牌进行排序：先按花色（H > S > D > C），再按点数降序。
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
def determine_trick_winner(trick, trump_suit, leader=None):
    """
    判定一个已完成的墩由谁赢下。
    规则（优先级从高到低）：
        1. 若有人出王牌，则出最高将牌者获胜；
        2. 否则，出引牌花色中点数最高者获胜；
        3. 其他花色（非王牌、非引牌花色）不能赢。
    参数:
        trick: 完整的墩字典（四个位置都有牌）
        trump_suit: 本局王牌花色
        leader: 引牌者位置（可选，用于正确判断引牌花色）
    返回:
        赢家位置字符串
    """
    led_suit = get_led_suit(trick, leader)
    best_pos = None
    best_card = None
    best_rank = -1
    best_is_trump = False

    for pos in TURN_ORDER:
        card = trick.get(pos)
        if card is None:
            continue

        is_trump = (card[1] == trump_suit)
        rank = get_rank_ace_high(card)

        if best_pos is None:
            best_pos, best_card, best_rank, best_is_trump = pos, card, rank, is_trump
        elif is_trump and not best_is_trump:
            # trump always beats non-trump
            best_pos, best_card, best_rank, best_is_trump = pos, card, rank, True
        elif is_trump and best_is_trump:
            # both trump — higher rank wins
            if rank > best_rank:
                best_pos, best_card, best_rank = pos, card, rank
        elif not is_trump and not best_is_trump:
            # neither is trump — only led-suit cards compete
            # if current best is off-suit, a led-suit card wins regardless of rank
            if card[1] == led_suit and (best_card[1] != led_suit or rank > best_rank):
                best_pos, best_card, best_rank = pos, card, rank
        # else: non-trump vs best_is_trump — cannot win, ignored

    return best_pos


# AI 出牌逻辑 

def ai_choose_card(hand, trick, trump_suit, position, difficulty='easy',
                   played_cards=None, leader=None):
    """AI 出牌调度器：根据难度分发到不同策略。

    参数:
        hand: AI 当前手牌
        trick: 当前墩的字典（可能有 None）
        trump_suit: 王牌花色
        position: AI 的位置
        difficulty: 'easy'（原版保守策略）或 'hard'（优化策略）
        played_cards: 已出过的牌的集合（Hard 难度使用）
        leader: 引牌者位置（用于正确判断引牌花色）
    返回:
        选中的牌 [rank, suit]
    """
    if difficulty == 'hard':
        return _ai_choose_card_hard(hand, trick, trump_suit, position, played_cards, leader)
    return _ai_choose_card_easy(hand, trick, trump_suit, position, leader)


def _ai_choose_card_easy(hand, trick, trump_suit, position, leader=None):
    """AI 玩家的出牌策略（简单版 / Easy 难度）：
        - 若为引牌者：出点数最小的牌（保守）。
        - 若为跟牌者：
            * 若有引牌花色，则出该花色中点数最小的牌；
            * 若没有引牌花色，则出最小的王牌（如果有）；
            * 否则出点数最小的牌作为垫牌。
    """
    led_suit = get_led_suit(trick, leader)

    if led_suit is None:
        return min(hand, key=lambda c: get_rank_ace_high(c))

    same_suit = cards_of_suit(hand, led_suit)
    if same_suit:
        return min(same_suit, key=lambda c: get_rank_ace_high(c))

    trumps = cards_of_suit(hand, trump_suit)
    if trumps:
        return min(trumps, key=lambda c: get_rank_ace_high(c))

    return min(hand, key=lambda c: get_rank_ace_high(c))



#  Hard AI 辅助函数


def _play_count(trick):
    """当前墩已出了几张牌（0~3）。"""
    return sum(1 for p in TURN_ORDER if trick.get(p) is not None)


def _current_winner(trick, trump_suit, leader=None):
    """判断未完成墩中当前谁赢。
    返回 (position, card) 或 (None, None) 若墩为空。
    """
    led_suit = get_led_suit(trick, leader)
    if led_suit is None:
        return None, None

    best_pos, best_card = None, None
    best_rank, best_is_trump = -1, False

    for pos in TURN_ORDER:
        card = trick.get(pos)
        if card is None:
            continue
        is_trump = (card[1] == trump_suit)
        rank = get_rank_ace_high(card)

        if best_pos is None:
            best_pos, best_card, best_rank, best_is_trump = pos, card, rank, is_trump
        elif is_trump and (not best_is_trump or rank > best_rank):
            best_pos, best_card, best_rank, best_is_trump = pos, card, rank, True
        elif not is_trump and not best_is_trump:
            # neither is trump — if current best is off-suit, led-suit wins regardless of rank
            if card[1] == led_suit and (best_card[1] != led_suit or rank > best_rank):
                best_pos, best_card, best_rank = pos, card, rank

    return best_pos, best_card


def _beats(card, current_best, led_suit, trump_suit):
    """判断 card 是否击败 current_best（在当前墩上下文中）。"""
    c_trump = (card[1] == trump_suit)
    b_trump = (current_best[1] == trump_suit)

    if c_trump != b_trump:
        return c_trump  

    if c_trump:
        return get_rank_ace_high(card) > get_rank_ace_high(current_best)

    # 都不是王牌：只有引牌花色可以竞争
    if card[1] != led_suit:
        return False
    if current_best[1] != led_suit:
        return True
    return get_rank_ace_high(card) > get_rank_ace_high(current_best)



#  Hard AI 子策略函数


def _ai_lead(hand, trump_suit):
    """引牌策略（Hard 难度）：
    - 若持有 ≥4 张将牌 → 吊将（出最小的王牌）
    - 否则从最长非将套引第 4 大（标准桥牌约定）
    """
    trumps = cards_of_suit(hand, trump_suit)

    # 王牌多时出小的王牌，消耗对手王牌
    if len(trumps) >= 4:
        return min(trumps, key=get_rank_ace_high)

    # 找最长非王牌花色
    best_suit, best_len = None, -1
    for s in SUITS:
        if s == trump_suit:
            continue
        cnt = len(cards_of_suit(hand, s))
        if cnt > best_len:
            best_len = cnt
            best_suit = s

    if best_suit and best_len > 0:
        suit_cards = cards_of_suit(hand, best_suit)
        descending = sorted(suit_cards, key=get_rank_ace_high, reverse=True)
        # 引第 4 大（不够 4 张则引最小）
        idx = min(3, len(descending) - 1)
        return descending[idx]

    # 只有王牌且 <4 张 → 引最小
    return min(hand, key=get_rank_ace_high)


def _ai_follow(same_suit_cards, trick, trump_suit, position, leader=None):
    """跟牌策略（Hard 难度）：
    - 第 2 位出牌 → second hand low（出小）
    - 第 3 位出牌 → 队友赢则出小，否则尝试反超
    - 第 4 位出牌 → 队友赢则出小，对手赢则尝试反超
    """
    my_team = get_team(position)
    curr_winner, curr_best = _current_winner(trick, trump_suit, leader)
    played = _play_count(trick)
    led_suit = get_led_suit(trick, leader)

    partner_win = (curr_winner is not None and get_team(curr_winner) == my_team)
    opponent_win = (curr_winner is not None and get_team(curr_winner) != my_team)

    descending = sorted(same_suit_cards, key=get_rank_ace_high, reverse=True)
    low = descending[-1]
    high = descending[0]

    # 第 2 位：second hand low
    if played == 1:
        return low

    # 第 3 位：third hand high
    if played == 2:
        if partner_win:
            return low
        # 尝试用最小能赢的牌反超
        for c in reversed(descending):  # 低→高
            if curr_best is None or _beats(c, curr_best, led_suit, trump_suit):
                return c
        return high  # 无法反超则出大牌施压

    # 第 4 位：最后出手
    if played == 3:
        if partner_win:
            return low
        if opponent_win and curr_best:
            for c in reversed(descending):
                if _beats(c, curr_best, led_suit, trump_suit):
                    return c
            return low  # 反超不了
        return low

    return low


def _ai_trump(hand, trumps, trick, trump_suit, position, leader=None):
    """将吃策略（Hard 难度）：
    - 队友赢 → 不将吃！垫牌代替（节省将牌）
    - 对手赢 → 出最小能赢的将牌
    """
    my_team = get_team(position)
    curr_winner, curr_best = _current_winner(trick, trump_suit, leader)

    # 队友已经赢了 → 不要浪费将牌
    if curr_winner is not None and get_team(curr_winner) == my_team:
        return _ai_discard(hand, trump_suit)

    # 对手赢了 → 尝试将吃反超
    if curr_winner is not None and curr_best is not None:
        led_suit = get_led_suit(trick, leader)
        sorted_trumps = sorted(trumps, key=get_rank_ace_high)  # 低→高
        for c in sorted_trumps:
            if _beats(c, curr_best, led_suit, trump_suit):
                return c
        # 所有将牌都无法反超 → 出最小将牌，保留大牌
        return sorted_trumps[0]

    # 无人赢
    return min(trumps, key=get_rank_ace_high)


def _ai_discard(hand, trump_suit):
    """垫牌策略（Hard 难度）：
    从最短的非将牌花色出牌，尽快清空该花色以创造缺门（方便后续将吃）。
    """
    best_card, best_len = None, 999
    for s in SUITS:
        if s == trump_suit:
            continue
        cards = cards_of_suit(hand, s)
        if 0 < len(cards) < best_len:
            best_len = len(cards)
            # 从最短花色出最大的牌（加速清空）
            best_card = max(cards, key=get_rank_ace_high)
    if best_card:
        return best_card
    # 只有将牌 — 出最小的
    return min(hand, key=get_rank_ace_high)


def _ai_choose_card_hard(hand, trick, trump_suit, position, played_cards=None, leader=None):
    """Hard 难度 AI 主调度器。
    根据墩的状态分发到引牌/跟牌/将吃/垫牌子策略。
    """
    led_suit = get_led_suit(trick, leader)

    # ── 引牌 ──
    if led_suit is None:
        return _ai_lead(hand, trump_suit)

    # ── 必须跟引牌花色 ──
    same_suit = cards_of_suit(hand, led_suit)
    if same_suit:
        return _ai_follow(same_suit, trick, trump_suit, position, leader)

    # ── 无引牌花色：将吃或垫牌 ──
    trumps = cards_of_suit(hand, trump_suit)
    if trumps:
        return _ai_trump(hand, trumps, trick, trump_suit, position, leader)

    return _ai_discard(hand, trump_suit)


#  游戏状态机
def _finish_trick(game_state, session=None):
    """
    完成当前墩：判定赢家、更新分数、设置信息并决定下一步状态（新墩或结束）。
    此函数会直接修改 game_state 字典。
    参数:
        game_state: 游戏状态字典（引用）
        session: Flask session
    """
    current_trick = game_state['tricks'][-1]
    leader = game_state.get('leader', '')
    winner = determine_trick_winner(current_trick, game_state['trump_suit'], leader)
    team = get_team(winner)

    # 更新该队伍的得分
    game_state['scores'][team] += 1

    # Log
    if session is not None:
        winner_name = PLAYER_NAMES.get(winner, winner)
        userlog.add_log_entry(session, f'{winner_name} wins the trick.')

    # 设置本轮结果消息
    if winner == 'south':
        game_state['message'] = "South wins the trick!"
    else:
        game_state['message'] = f"{PLAYER_NAMES[winner]} wins the trick!"
    game_state['message_class'] = 'trick-message'

    # 检查是否有一方达到 7 墩 → 游戏结束
    if game_state['scores']['south_north'] >= WINNING_TRICKS:
        game_state['stop_type'] = 'game_over'
        game_state['message'] = "South-North wins the game!"
        game_state['message_class'] = 'win-message'
        if session is not None:
            userlog.add_log_entry(session, 'Game over! South-North wins!')
    elif game_state['scores']['east_west'] >= WINNING_TRICKS:
        game_state['stop_type'] = 'game_over'
        game_state['message'] = "East-West wins the game."
        game_state['message_class'] = 'lose-message'
        if session is not None:
            userlog.add_log_entry(session, 'Game over! East-West wins!')
    elif sum(game_state['scores'].values()) >= 13:
        # 若所有 13 墩打完但无人达到 7 分，按总分判定胜负
        game_state['stop_type'] = 'game_over'
        if game_state['scores']['south_north'] > game_state['scores']['east_west']:
            game_state['message'] = "South-North wins the game!"
            game_state['message_class'] = 'win-message'
        else:
            game_state['message'] = "East-West wins the game."
            game_state['message_class'] = 'lose-message'
        if session is not None:
            userlog.add_log_entry(session, 'Game over!')
    else:
        # 继续下一墩，赢家作为下一墩的引牌者
        game_state['stop_type'] = 'new_trick'
        game_state['leader'] = winner


def _advance_game(game_state, session=None):
    """
    推进游戏：自动处理 AI 的回合，直到轮到南（人类玩家）出牌，
    或当前墩结束，或游戏结束。
    此函数会在每次状态变更后被调用（新墩开始、南出牌后）。
    参数:
        game_state: 游戏状态字典（引用）
        session: Flask session
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
            _finish_trick(game_state, session)
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

        difficulty = game_state.get('difficulty', 'easy')
        leader = game_state.get('leader', '')
        card = ai_choose_card(hand, current_trick,
                              game_state['trump_suit'], next_pos, difficulty,
                              leader=leader)
        hand.remove(card)
        current_trick[next_pos] = card

        # Log AI play
        if session is not None:
            card_name = f'{card[0]}{card[1]}'
            player_name = PLAYER_NAMES.get(next_pos, next_pos)
            userlog.add_log_entry(session, f'{player_name} plays {card_name}.')

        if all_played(current_trick):
            _finish_trick(game_state, session)
            return


# 对外 API，flask_app.py 
def new_game(session, difficulty='easy'):
    """
    初始化一局新的 Whist 游戏。
    创建并洗牌，发牌（每人13张），将牌由最后一张牌决定，
    并将初始游戏状态存入 Flask session。
    参数:
        session: Flask 的 session 字典
        difficulty: AI 难度 'easy' 或 'hard'
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

    # Log game start
    userlog.add_log_entry(session, f'New Whist game started. Trump is {trump_suit_name}.')
    for pos in TURN_ORDER:
        cards_str = ', '.join(f'{c[0]}{c[1]}' for c in hands[pos])
        player_name = PLAYER_NAMES[pos]
        userlog.add_log_entry(session, f'{player_name} gets [{cards_str}].')

    # 初始游戏状态：北先引牌
    session['game_state'] = {
        'stop_type': 'new_trick',
        'hands': hands,
        'players': dict(PLAYER_NAMES),
        'leader': 'north',
        'tricks': [],          # 已完成的墩列表
        'scores': {'south_north': 0, 'east_west': 0},
        'trump_suit': trump_suit,
        'trump_suit_name': trump_suit_name,
        'message': None,
        'message_class': 'info-message',
        'difficulty': difficulty,
    }
    # Flask 会自动将 session 的修改保存


def game_update(session, action):
    """
    处理人类玩家发出的动作。
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

    if action.startswith('difficulty/'):
        diff = action.split('/', 1)[1]
        if diff in ('easy', 'hard'):
            # Only allow changes before the first trick starts
            if game_state.get('stop_type') == 'new_trick' and not game_state.get('tricks'):
                game_state['difficulty'] = diff
        return

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
        _advance_game(game_state, session)

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
            leader = game_state.get('leader', '')
            led_suit = get_led_suit(current_trick, leader)
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

        # Log human play
        card_name = f'{card[0]}{card[1]}'
        userlog.add_log_entry(session, f'You play {card_name}.')

        # 让 AI 自动响应
        _advance_game(game_state, session)

