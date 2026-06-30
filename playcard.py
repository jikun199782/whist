# constants and functions for playing cards
# Short name of the cards is to comply with the community
# card is 2-character string, card[0] is rank and card[1] is suit

# ====================== CARD RANKING HELPERS ======================

RANK_ORDER_ACE_HIGH = '23456789TJQKA'   # Ace highest (for Whist)
RANK_ORDER_ACE_LOW  = 'A23456789TJQK'   # Ace lowest  (for Freecell)
SUITS = 'HSDC'

def get_rank_ace_high(card: str) -> int:
    # Return numerical rank with Ace high (A=14). Used in Whist.
    return RANK_ORDER_ACE_HIGH.index(card[0])

def get_rank_ace_low(card: str) -> int:
    # Return numerical rank with Ace low (A=1). Used in Freecell.
    return RANK_ORDER_ACE_LOW.index(card[0])

def get_suit(card: str) -> str:
    # Return the suit of the card (H, S, D, C).
    return card[1]

def make_deck():
    return [rank+suit for suit in SUITS for rank in RANK_ORDER_ACE_LOW]

def is_red(card):
    return card[1] in 'HD'

# Full name of the cards is to comply with HTDebeer's so that we can reference his svg
SUIT_NAME_MAP = {'H':'heart', 'S':'spade', 'D':'diamond', 'C':'club'}
RANK_NAME_MAP = {'A':'1', '2':'2', '3':'3', '4':'4', '5':'5', '6':'6', '7':'7', '8':'8', '9':'9',
         'T':'10', 'J': 'jack', 'Q': 'queen', 'K': 'king'}
UNICODE_SUITS = '♡♤♢♧'

def get_card_name(card):
    return f'{SUIT_NAME_MAP[card[1]]}_{RANK_NAME_MAP[card[0]]}'

def get_suit_name(suit: str) -> str:
    # Return Unicode suit symbol for the card.
    return SUIT_NAME_MAP[suit]

def get_unicode_suit(suit: str) -> str:
    # Return Unicode suit symbol for the card.
    return UNICODE_SUITS[SUITS.index(suit)]