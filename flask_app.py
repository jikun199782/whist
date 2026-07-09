import os
import uuid
import random
from flask import Flask, render_template, redirect, url_for, session, jsonify, request
from playcard import get_card_name, make_deck

# Inline suit-name lookup so we don't depend on playcard.get_suit_name

_SUIT_NAME_MAP = {'H': 'heart', 'S': 'spade', 'D': 'diamond', 'C': 'club'}
# from userlog import add_log_entry, get_user_log
import blackjack, blackjack_eu, whist
import game_store
import userlog

# Whist utility functions needed by multiplayer mode
from whist import (
    sort_hand, get_led_suit, get_team, all_played,
    determine_trick_winner, ai_choose_card,
    TURN_ORDER, WINNING_TRICKS
)

# Position-to-display-slot mapping for per-player perspective.
# Each player sees their own hand at the bottom (south slot),
# partner opposite at top (north slot),
# left neighbour in west slot, right neighbour in east slot.
SLOT_MAP = {
    'south': {'south': 'south', 'north': 'north', 'west': 'west', 'east': 'east'},
    'north': {'south': 'north', 'north': 'south', 'west': 'east', 'east': 'west'},
    'east':  {'south': 'east',  'north': 'west',  'west': 'north', 'east': 'south'},
    'west':  {'south': 'west',  'north': 'east',   'west': 'south', 'east': 'north'},
}

# Reverse direction labels — used for the slot labels
DIRECTION_LABEL = {
    'south': 'South', 'north': 'North', 'east': 'East', 'west': 'West',
}

SUPPORTED_GAMES = {'blackjack': blackjack, 'blackjack_eu': blackjack_eu, 'whist': whist}
app = Flask(__name__)
# Generate a random secret key for the session
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

# Initialise the multiplayer database on startup
try:
    game_store.init_db()
except Exception as e:
    import sys
    print(f"WARNING: Could not init multiplayer DB: {e}", file=sys.stderr)
    print(f"DB path: {game_store.DB_PATH}", file=sys.stderr)



#  Existing single-player


@app.route('/')
def index():
    return redirect(url_for('game'))


@app.route('/select')
def select():
    session.setdefault('session_id', uuid.uuid4().hex)
    return render_template('select.html', cur_game=session.get('cur_game', ''))


@app.route('/new_game')
def new_game():
    cur_game = session.get('cur_game', '')
    if cur_game in SUPPORTED_GAMES:
        SUPPORTED_GAMES[cur_game].new_game(session)
        session.modified = True
        return redirect(url_for('game'))
    else:
        return redirect(url_for('select'))


@app.route('/game')
def game():
    session.setdefault('session_id', uuid.uuid4().hex)
    # If player is in a multiplayer game, redirect to it
    multi_game_id = session.get('multi_game_id', '')
    if multi_game_id:
        pos = session.get('multi_position', '')
        token = session.get('multi_token', '')
        gs = game_store.get_game_state(multi_game_id)
        if gs:
            # Verify seat is still valid
            seat = game_store.get_seat(multi_game_id, pos)
            if seat and seat['player_type'] == 'human' and seat['session_token'] == token:
                return redirect(url_for('multi_game', game_id=multi_game_id,
                                        pos=pos, token=token))
            else:
                # Seat lost — search for token elsewhere
                for p in ['north', 'east', 'south', 'west']:
                    s = game_store.get_seat(multi_game_id, p)
                    if s and s['player_type'] == 'human' and s['session_token'] == token:
                        return redirect(url_for('multi_game', game_id=multi_game_id,
                                                pos=p, token=token))
    cur_game = session.get('cur_game', '')
    game_state = session.get('game_state', {})
    if cur_game in SUPPORTED_GAMES and game_state:
        return render_template(f'{cur_game}.html', game_state=game_state)
    else:
        return redirect(url_for('select'))


@app.route('/game_update/<path:action>')
def game_update(action):
    cur_game = session.get('cur_game', '')
    if cur_game in SUPPORTED_GAMES:
        SUPPORTED_GAMES[cur_game].game_update(session, action)
        session.modified = True
        return redirect(url_for('game'))
    else:
        return redirect(url_for('select'))


@app.route('/select_game/<target_game>')
def select_game(target_game):
    if target_game in SUPPORTED_GAMES:
        session['cur_game'] = target_game
        # Clear multiplayer state so /game doesn't redirect to old multi game
        session.pop('multi_game_id', None)
        session.pop('multi_position', None)
        session.pop('multi_token', None)
        userlog.add_log_entry(session, f'Select {target_game}.')
        SUPPORTED_GAMES[target_game].new_game(session)
        return redirect(url_for('game'))
    else:
        return render_template('about.html', supported=False)


@app.route('/rules')
def rules():
    return render_template('rules.html',
                           cur_game=session.get('cur_game', ''))


@app.route('/log')
def log():
    session_id = session.setdefault('session_id', uuid.uuid4().hex)
    return render_template('userlog.html',
                           log=userlog.get_user_log(session))


@app.route('/about')
def about():
    return render_template('about.html', supported=True)



#  Multiplayer routes


def _deal_cards():
    """Create a shuffled deck and deal 13 cards to each player.
    Returns (hands_dict, trump_suit, trump_suit_name).
    """
    deck = [[c[0], c[1]] for c in make_deck()]
    random.shuffle(deck)
    hands = {
        'north': sort_hand(deck[0:13]),
        'east': sort_hand(deck[13:26]),
        'south': sort_hand(deck[26:39]),
        'west': sort_hand(deck[39:52]),
    }
    trump_suit = deck[51][1]
    trump_suit_name = _SUIT_NAME_MAP[trump_suit]
    return hands, trump_suit, trump_suit_name


def _resolve_trick(game_id):
    """Called when all four cards in the current trick have been played.
    Determines the winner, updates scores, checks for game-over.
    Returns the updated game_state dict.
    """
    gs = game_store.get_game_state(game_id)
    trick = gs['tricks'][-1]
    leader = gs.get('leader', '')
    winner = determine_trick_winner(trick, gs['trump_suit'], leader)
    team = get_team(winner)

    scores_sn = gs['scores']['south_north']
    scores_ew = gs['scores']['east_west']
    if team == 'south_north':
        scores_sn += 1
    else:
        scores_ew += 1

    # Build message (shown to all players, avoid perspective-specific "You")
    if winner == 'south':
        msg = "Host wins the trick!"
    else:
        player_name = gs['players'][winner]
        msg = f"{player_name} wins the trick!"

    # Determine next state
    if scores_sn >= WINNING_TRICKS:
        stop_type = 'game_over'
        msg = "South-North wins the game!"
        msg_class = 'win-message'
        new_leader = None
    elif scores_ew >= WINNING_TRICKS:
        stop_type = 'game_over'
        msg = "East-West wins the game."
        msg_class = 'lose-message'
        new_leader = None
    elif (scores_sn + scores_ew) >= 13:
        stop_type = 'game_over'
        if scores_sn > scores_ew:
            msg = "South-North wins the game!"
            msg_class = 'win-message'
        else:
            msg = "East-West wins the game."
            msg_class = 'lose-message'
        new_leader = None
    else:
        stop_type = 'new_trick'
        msg_class = 'trick-message'
        new_leader = winner

    game_store.update_game_after_trick(
        game_id, winner, scores_sn, scores_ew,
        msg, msg_class, stop_type, new_leader
    )
    return game_store.get_game_state(game_id)


def _auto_play_ai(game_id):
    """After a human plays, auto-play consecutive AI seats within the
    CURRENT trick only.  When the trick completes, resolve it and STOP
    so all players can review the four cards before the host continues.
    Returns the updated game_state dict.
    """
    while True:
        # --- Trick complete → resolve and stop (cards stay visible) ---
        if game_store.is_trick_complete(game_id):
            return _resolve_trick(game_id)

        next_pos = game_store.find_next_player(game_id)
        if next_pos is None:
            return _resolve_trick(game_id)

        seat = game_store.get_seat(game_id, next_pos)
        if seat and seat['player_type'] == 'human' and seat['is_connected']:
            # Human's turn — stop and wait
            leader = game_store.get_game(game_id)['leader']
            current_trick = game_store.get_current_trick(game_id)
            if current_trick.get(leader) is None and next_pos == leader:
                game_store.set_stop_type(game_id, 'lead_card')
            else:
                game_store.set_stop_type(game_id, 'follow_card')
            break

        # AI turn — auto-play (within current trick)
        hand = game_store.get_player_hand(game_id, next_pos)
        if not hand:
            break  # defensive

        trick = game_store.get_current_trick(game_id)
        game = game_store.get_game(game_id)
        card = ai_choose_card(hand, trick, game['trump_suit'], next_pos,
                              game.get('difficulty', 'easy'),
                              leader=game.get('leader', ''))

        game_store.remove_card(game_id, next_pos, card)
        game_store.play_card_to_trick(game_id, next_pos, card)

    return game_store.get_game_state(game_id)


# ---- helpers for reading per-tab identity ----

def _get_player_id():
    """Return (pos, token) from URL query params, falling back to session."""
    pos = request.args.get('pos') or session.get('multi_position', '')
    token = request.args.get('token') or session.get('multi_token', '')
    return pos, token


def _redirect_game(game_id, pos, token):
    """Redirect to the game page, preserving per-tab identity in the URL."""
    return redirect(url_for('multi_game', game_id=game_id,
                            pos=pos, token=token))


# ---- route: create a multiplayer game ----

@app.route('/multi/create')
def multi_create():
    """Create a new multiplayer Whist game.  South (the creator) is human;
    the other three seats start as AI and can be claimed by friends.
    """
    game_id = uuid.uuid4().hex[:8]
    hands, trump_suit, trump_suit_name = _deal_cards()
    game_store.create_game(game_id, hands, trump_suit, trump_suit_name)

    # Mark South as the human host
    token = uuid.uuid4().hex
    game_store.set_south_human(game_id, token)

    # Store identity in session AND pass via URL query params
    # (query params prevent cross-tab session overwrite in same browser)
    session['multi_game_id'] = game_id
    session['multi_position'] = 'south'
    session['multi_token'] = token
    session['cur_game'] = 'whist_multi'  # so select page highlights the right mode
    session.modified = True

    userlog.add_log_entry(session, 'New multiplayer Whist game created. '
                          f'Trump is {trump_suit_name}.')

    return redirect(url_for('multi_game', game_id=game_id,
                            pos='south', token=token))


# ---- route: join an existing game ----

@app.route('/multi/join/<game_id>')
def multi_join(game_id):
    """Assign the visitor to an available seat.
    Supports ?seat=north|east|west to request a specific seat.
    Falls back to auto-assign if the seat is taken or not specified.
    """
    if not game_store.has_game(game_id):
        return render_template('about.html', supported=False), 404

    requested_seat = request.args.get('seat', '').lower()
    pos = None
    if requested_seat in ('north', 'east', 'west'):
        seat_info = game_store.get_seat(game_id, requested_seat)
        if seat_info and seat_info['player_type'] == 'ai':
            # Try to claim the specific seat
            if game_store.assign_specific_seat(game_id, requested_seat):
                pos = requested_seat

    if pos is None:
        # Fall back to auto-assign
        pos = game_store.assign_human_seat(game_id)

    if pos is None:
        return "<h2>Sorry, this game is full.</h2>", 403

    # Get the token that was assigned
    seat = game_store.get_seat(game_id, pos)
    token = seat['session_token']
    session['multi_game_id'] = game_id
    session['multi_position'] = pos
    session['multi_token'] = token
    session['cur_game'] = 'whist_multi'  # so select page highlights the right mode
    session.modified = True

    return redirect(url_for('multi_game', game_id=game_id,
                            pos=pos, token=token))


# ---- route: render the multiplayer game page ----

@app.route('/multi/game/<game_id>')
def multi_game(game_id):
    """Render the Whist table for a multiplayer game.
    Each player sees their own hand at the bottom (斗地主-style perspective).
    """
    gs = game_store.get_game_state(game_id)
    if not gs:
        return redirect(url_for('select'))

    # Ensure nav bar shows the correct current game
    session['cur_game'] = 'whist_multi'

    # Read identity from URL query params FIRST (per-tab),
    # fall back to session (backward compat).
    my_pos = request.args.get('pos') or session.get('multi_position', '')
    my_token = request.args.get('token') or session.get('multi_token', '')
    # Keep session in sync for this tab
    session['multi_position'] = my_pos
    session['multi_token'] = my_token

    # Auto-detect if player was moved to a different seat by the host.
    # If the seat at my_pos doesn't have this human+token, search all seats.
    if my_pos and my_token:
        seat_now = game_store.get_seat(game_id, my_pos)
        seat_valid = (seat_now and seat_now['player_type'] == 'human'
                      and seat_now['session_token'] == my_token)
        if not seat_valid:
            # Player may have been moved — search for their token elsewhere
            found_pos = None
            for p in ['north', 'east', 'south', 'west']:
                if p == my_pos:
                    continue
                s = game_store.get_seat(game_id, p)
                if s and s['player_type'] == 'human' and s['session_token'] == my_token:
                    found_pos = p
                    break
            if found_pos:
                # Redirect to the correct seat URL
                return redirect(url_for('multi_game', game_id=game_id,
                                        pos=found_pos, token=my_token))
            # Token not found anywhere — player needs to re-join

    # Attach info about *this* viewer
    gs['my_position'] = my_pos
    gs['my_token'] = my_token
    gs['share_link'] = url_for('multi_join', game_id=game_id, _external=True)

    # Per-player perspective: which game position goes in each display slot
    gs['slot'] = SLOT_MAP.get(my_pos, SLOT_MAP['south'])
    # Pass version so JS initializes lastVersion correctly (avoids spurious first-poll reload)
    gs['version'] = game_store.get_version(game_id)
    # Pass AI difficulty so the template can display it
    game = game_store.get_game(game_id)
    gs['difficulty'] = game.get('difficulty', 'easy') if game else 'easy'
    # Pass seat types so the template can distinguish human vs AI
    gs['seat_types'] = {}
    for pos in ['north', 'east', 'south', 'west']:
        seat = game_store.get_seat(game_id, pos)
        gs['seat_types'][pos] = seat['player_type'] if seat else 'ai'

    # Precise turn detection
    next_pos = game_store.find_next_player(game_id)
    leader = gs.get('leader', '')
    if gs['stop_type'] in ('lead_card', 'follow_card'):
        gs['is_my_turn'] = (next_pos == my_pos)
    elif gs['stop_type'] == 'new_trick':
        gs['is_my_turn'] = (my_pos == 'south')  # only host can proceed
    elif gs['stop_type'] == 'waiting':
        gs['is_my_turn'] = (my_pos == 'south')  # only host can start
    else:
        gs['is_my_turn'] = False

    gs['next_player'] = next_pos
    gs['next_player_name'] = gs['players'].get(next_pos, '') if next_pos else ''

    return render_template('whist_multi.html', game_state=gs)


# ---- route: AJAX polling endpoint ----

@app.route('/multi/status/<game_id>')
def multi_status(game_id):
    """Return lightweight JSON telling the client whether to reload.
    Called every second by the polling JS.
    """
    game = game_store.get_game(game_id)
    if not game:
        return jsonify({'error': 'game not found'}), 404

    gs = game_store.get_game_state(game_id)
    my_pos, my_token = _get_player_id()
    next_pos = game_store.find_next_player(game_id)

    # Check if the game needs this player's attention
    is_my_turn = False
    leader = gs.get('leader', '')
    if gs['stop_type'] in ('lead_card', 'follow_card'):
        # It's my turn only if I'm the next player to act
        is_my_turn = (next_pos == my_pos)
    elif gs['stop_type'] == 'new_trick':
        # Only the host can click "Next Trick"
        is_my_turn = (my_pos == 'south')

    return jsonify({
        'version': game['version'],
        'stop_type': gs['stop_type'],
        'is_my_turn': is_my_turn,
        'next_player': next_pos,
        'scores': gs['scores'],
        'message': gs.get('message'),
        'message_class': gs.get('message_class', 'info-message'),
        'leader': gs.get('leader', ''),
        'trick': gs['tricks'][-1] if gs.get('tricks') else {},
        'trump_suit': gs.get('trump_suit', ''),
        'hands': gs.get('hands', {}),
        'players': gs.get('players', {}),
        'slot': SLOT_MAP.get(my_pos, SLOT_MAP['south']),
    })


# ---- route: play a card (human action) ----

@app.route('/multi/play/<game_id>/<path:card_str>')
def multi_play(game_id, card_str):
    """Process a human player's card play.
    Validates the player's identity and turn, then auto-plays AI seats.
    """
    my_pos, my_token = _get_player_id()

    # Verify game exists
    if not game_store.has_game(game_id):
        return redirect(url_for('select'))

    gs = game_store.get_game_state(game_id)
    if gs['stop_type'] == 'game_over':
        return _redirect_game(game_id, my_pos, my_token)

    # Verify this player's identity
    seat = game_store.get_seat(game_id, my_pos)
    if not seat or seat['session_token'] != my_token:
        return "Not your seat.", 403

    # Verify it's this player's turn
    next_pos = game_store.find_next_player(game_id)
    if next_pos != my_pos:
        return _redirect_game(game_id, my_pos, my_token)

    # Parse card  (format: "A,H" or "T,S")
    parts = card_str.split(',')
    if len(parts) != 2:
        return _redirect_game(game_id, my_pos, my_token)
    card = [parts[0], parts[1]]

    # Validate: card in hand
    hand = game_store.get_player_hand(game_id, my_pos)
    if card not in hand:
        return _redirect_game(game_id, my_pos, my_token)

    # Validate: follow-suit rule
    stop_type = gs['stop_type']
    if stop_type == 'follow_card':
        trick = game_store.get_current_trick(game_id)
        leader = gs.get('leader', '')
        led_suit = get_led_suit(trick, leader)
        if led_suit:
            has_led = any(c[1] == led_suit for c in hand)
            if has_led and card[1] != led_suit:
                return _redirect_game(game_id, my_pos, my_token)

    # All checks passed — play the card
    game_store.remove_card(game_id, my_pos, card)
    game_store.play_card_to_trick(game_id, my_pos, card)

    card_name = f'{card[0]}{card[1]}'
    userlog.add_log_entry(session, f'You play {card_name}.')

    # Auto-play AI seats until next human or trick complete
    _auto_play_ai(game_id)

    return _redirect_game(game_id, my_pos, my_token)


# ---- route: start the game (host only) ----

@app.route('/multi/start/<game_id>')
def multi_start(game_id):
    """Start a waiting game — only South (host) can do this."""
    gs = game_store.get_game_state(game_id)
    if not gs:
        return redirect(url_for('select'))

    my_pos, my_token = _get_player_id()
    if my_pos != 'south':
        return _redirect_game(game_id, my_pos, my_token)

    if gs['stop_type'] != 'waiting':
        return _redirect_game(game_id, my_pos, my_token)

    game_store.add_trick(game_id)
    game_store.clear_message(game_id)
    _auto_play_ai(game_id)

    return _redirect_game(game_id, my_pos, my_token)


# ---- route: swap two seats (host only, waiting only) ----

@app.route('/multi/swap/<game_id>/<pos1>/<pos2>')
def multi_swap(game_id, pos1, pos2):
    """Swap the players in two seats. Host (South) only, waiting only."""
    my_pos, my_token = _get_player_id()
    if my_pos != 'south':
        return _redirect_game(game_id, my_pos, my_token)

    gs = game_store.get_game_state(game_id)
    if not gs or gs['stop_type'] != 'waiting':
        return _redirect_game(game_id, my_pos, my_token)

    game_store.swap_seats(game_id, pos1, pos2)
    return _redirect_game(game_id, my_pos, my_token)


# ---- route: change AI difficulty (single-player) ----


@app.route('/game_update/difficulty/<difficulty>')
def game_update_difficulty(difficulty):
    """Switch AI difficulty before the first trick starts."""
    if difficulty in ('easy', 'hard'):
        game_state = session.get('game_state', {})
        if game_state.get('stop_type') == 'new_trick' and not game_state.get('tricks'):
            game_state['difficulty'] = difficulty
            session.modified = True
    return redirect(url_for('game'))


# ---- route: change AI difficulty (multiplayer, host only) ----


@app.route('/multi/difficulty/<game_id>/<difficulty>')
def multi_difficulty(game_id, difficulty):
    """Host switches AI difficulty during waiting phase."""
    my_pos, my_token = _get_player_id()
    if my_pos != 'south':
        return _redirect_game(game_id, my_pos, my_token)
    game = game_store.get_game(game_id)
    if not game or game['stop_type'] != 'waiting':
        return _redirect_game(game_id, my_pos, my_token)
    if difficulty in ('easy', 'hard'):
        game_store.set_difficulty(game_id, difficulty)
    return _redirect_game(game_id, my_pos, my_token)


# ---- route: start a new trick in multiplayer mode ----

@app.route('/multi/new_trick/<game_id>')
def multi_new_trick(game_id):
    """Start the next trick — only the leader of the new trick can do this."""
    gs = game_store.get_game_state(game_id)
    if not gs:
        return redirect(url_for('select'))

    my_pos, my_token = _get_player_id()

    # Verify identity
    seat = game_store.get_seat(game_id, my_pos)
    if not seat or seat['session_token'] != my_token:
        return "Not your seat.", 403

    # Only allowed during new_trick state
    if gs['stop_type'] != 'new_trick':
        return _redirect_game(game_id, my_pos, my_token)

    # Only the host (South) can start the next trick
    if my_pos != 'south':
        return _redirect_game(game_id, my_pos, my_token)

    game_store.add_trick(game_id)
    game_store.clear_message(game_id)

    # Kick off: auto-play AI until human or trick complete
    _auto_play_ai(game_id)

    return _redirect_game(game_id, my_pos, my_token)



#  Template utilities


@app.context_processor
def utility_processor():
    # Make the `get_card_name` function available in all templates
    return dict(enumerate=enumerate, get_card_name=get_card_name)


if __name__ == '__main__':
    app.run(port=80, debug=True)
