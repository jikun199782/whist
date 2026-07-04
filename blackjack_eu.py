import random
from playcard import make_deck

# from userlog import add_log_entry

CARD_VALUES = {
    'A': 11,
    '2': 2,
    '3': 3,
    '4': 4,
    '5': 5,
    '6': 6,
    '7': 7,
    '8': 8,
    '9': 9,
    'T': 10,
    'J': 10,
    'Q': 10,
    'K': 10,
}


def calculate_hand_value(hand):
    # 计算手牌点数：A 默认 11，必要时降为 1
    value, aces = 0, 0
    for card in hand:
        rank = card[0]
        value += CARD_VALUES[rank]
        aces += rank == 'A'

    while value > 21 and aces:
        value -= 10
        aces -= 1

    return value


def is_natural_blackjack(hand):
    # 自然 Blackjack：恰好 2 张牌且点数为 21
    return len(hand) == 2 and calculate_hand_value(hand) == 21


def new_game(session):
    # 欧版Blackjack的发牌：玩家 2 张明牌，庄家只发 1 张明牌（无 Hole Card）
    session_id = session.get('session_id', '')
    deck = make_deck()
    random.shuffle(deck)


    card_p1 = deck.pop()
    card_d1 = deck.pop()
    card_p2 = deck.pop()

    player_hand = [card_p1, card_p2]
    dealer_hand = [card_d1]

    player_value = calculate_hand_value(player_hand)
    dealer_value = calculate_hand_value(dealer_hand)

    # 欧洲版不在发牌阶段检查庄家 Blackjack（庄家此时只有一张牌，不可能 BJ）
    # 但如果玩家本身是自然 Blackjack，仍然进入正常流程，等到 stand 时由庄家补牌后再判
    message = None
    message_class = ""

    session['game_state'] = {
        'deck': deck,
        'dealer_hand': dealer_hand,
        'player_hand': player_hand,
        'dealer_value': dealer_value,
        'player_value': player_value,
        'message': message,
        'message_class': message_class,
    }


def game_update(session, action):
    game_state = session.get('game_state', {})
    if not game_state:
        return new_game(session)

    session_id = session.get('session_id', '')
    deck = game_state['deck']
    dealer_hand = game_state['dealer_hand']
    player_hand = game_state['player_hand']

    if action == 'hit':
        # 玩家要牌
        card = deck.pop()
        player_hand.append(card)
        player_value = calculate_hand_value(player_hand)
        game_state['player_value'] = player_value

        # 玩家爆牌：直接结算（庄家此时仍只有一张明牌，欧洲版无需翻暗牌）
        if player_value > 21:
            game_state['dealer_value'] = calculate_hand_value(dealer_hand)
            game_state['message'] = 'You busted! Dealer wins.'
            game_state['message_class'] = 'lose-message'

    elif action == 'stand':
        # 玩家停牌 ，庄家回合开始
        player_value = game_state['player_value']

        # 庄家先补第二张牌
        card = deck.pop()
        dealer_hand.append(card)
        dealer_value = calculate_hand_value(dealer_hand)

        # 补完第二张后立即检查庄家是否自然 Blackjack
        if is_natural_blackjack(dealer_hand):
            game_state['dealer_value'] = dealer_value
            if is_natural_blackjack(player_hand):
                # 玩家也是 2 张牌的自然 Blackjack ，平局
                game_state['message'] = "It's a tie of double blackjack!"
                game_state['message_class'] = 'tie-message'
            else:
                # 玩家不是自然 Blackjack（包括 3 张及以上凑成的 21），庄家胜
                game_state['message'] = 'Dealer has Blackjack! Dealer wins.'
                game_state['message_class'] = 'lose-message'
        else:
            # 庄家不是自然 Blackjack，则按常规继续要牌（< 17 必须要牌）
            while dealer_value < 17:
                card = deck.pop()
                dealer_hand.append(card)
                dealer_value = calculate_hand_value(dealer_hand)

            game_state['dealer_value'] = dealer_value

            # 比较点数
            if dealer_value > 21:
                game_state['message'] = 'Dealer busted! You win!'
                game_state['message_class'] = 'win-message'
            elif dealer_value > player_value:
                game_state['message'] = 'Dealer wins!'
                game_state['message_class'] = 'lose-message'
            elif dealer_value < player_value:
                game_state['message'] = 'You win!'
                game_state['message_class'] = 'win-message'
            else:
                game_state['message'] = "It's a tie!"
                game_state['message_class'] = 'tie-message'
    else:
        return

    session.modified = True
