import random
from playcard import make_deck
#from userlog import # add_log_entry

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
    # Calculate the value of a hand, considering Aces as 1 or 11.
    value, aces = 0, 0
    for card in hand:
        rank = card[0]
        value += CARD_VALUES[rank]
        aces += rank == 'A'

    # Adjust for Aces if needed
    while value > 21 and aces:
        value -= 10
        aces -= 1

    return value


def new_game(session):
    # Create a standard deck of 52 cards
    session_id = session.get('session_id', '')
    deck = make_deck()
    random.shuffle(deck)
    card1, card2, card3, card4 = deck.pop(), deck.pop(), deck.pop(), deck.pop()
    player_hand = [card1, card3]
    dealer_hand = [card2]
    # Keep dealer's second card's value secret
    dealer_value = calculate_hand_value(dealer_hand)
    player_value = calculate_hand_value(player_hand)
    dealer_hand.append(card4)
    dealer_total_value = calculate_hand_value(dealer_hand)
    game_over = dealer_total_value == 21
    # add_log_entry(session_id, 'New Blackjack game. '
                              # f'Dealer cards: [{card2}, ?]. Player cards: [{card1}, {card3}].')

    if game_over:
        dealer_value = dealer_total_value
        if player_value < 21:
            message = "Dealer wins!"
            message_class = "lose-message"
            # add_log_entry(session_id, 'Dealer wins with an initial blackjack.')
        else:
            message = "It's a tie of double blackjack!"
            message_class = "tie-message"
            # add_log_entry(session_id, 'Dealer and player tie with both initial blackjack.')
    else:
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
    # Flask automatically marks the session as modified when you assign
    # a value to a session key. No need for `session.modified = True`.

def game_update(session, action):
    game_state = session.get('game_state', {})
    if not game_state:
        return new_game(session)

    session_id = session.get('session_id', '')
    deck = game_state['deck']
    dealer_hand = game_state['dealer_hand']
    player_hand = game_state['player_hand']

    if action == 'hit':
        # Deal a card to the player
        card = deck.pop()
        player_hand.append(card)
        player_value = calculate_hand_value(player_hand)
        game_state['player_value'] = player_value
        # add_log_entry(session_id, f'Player hits and gets {card}.')

        # Check if player busts
        if player_value > 21:
            game_state['dealer_value'] = calculate_hand_value(dealer_hand)
            game_state['message'] = 'You busted! Dealer wins.'
            game_state['message_class'] = 'lose-message'
            # add_log_entry(session_id, 'Player busts and loses.')
    elif action == 'stand':
        # Dealer's turn
        # Show secret card's value and count it in
        player_value = game_state['player_value']
        dealer_value = calculate_hand_value(dealer_hand)
        # add_log_entry(session_id, f"Player stands. Dealer's hidden card is {dealer_hand[1]}")
        while dealer_value < 17:
            card = deck.pop()
            dealer_hand.append(card)
            dealer_value = calculate_hand_value(dealer_hand)
            # add_log_entry(session_id, f'Dealer gets {card}.')

        game_state['dealer_value'] = dealer_value

        # Determine the winner
        if dealer_value > 21:
            game_state['message'] = 'Dealer busted! You win!'
            game_state['message_class'] = 'win-message'
            # add_log_entry(session_id, 'Dealer busts. Player wins.')
        elif dealer_value > player_value:
            game_state['message'] = 'Dealer wins!'
            game_state['message_class'] = 'lose-message'
            # add_log_entry(session_id, f'Dealer wins by {dealer_value}:{player_value}.')
        elif dealer_value < player_value:
            game_state['message'] = 'You win!'
            game_state['message_class'] = 'win-message'
            # add_log_entry(session_id, f'Player wins by {player_value}:{dealer_value}.')
        else:
            game_state['message'] = "It's a tie!"
            game_state['message_class'] = 'tie-message'
            # add_log_entry(session_id, f'Dealer and Player tie with {player_value}:{dealer_value}.')
    else:
        # add_log_entry(session_id, f'Unknown action {action}.')
        return