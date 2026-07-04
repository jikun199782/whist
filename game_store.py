"""
game_store.py — SQLite-backed game state management for Whist multiplayer.

Replaces Flask session (cookie-based) with server-side persistent storage.
Uses WAL mode so concurrent reads/writes from multiple HTTP workers are safe.

Every function opens a fresh connection and closes it before returning;
there are no long-lived connections or shared state between requests.
"""

import json
import os
import sqlite3
import uuid
from typing import Optional

# ---------------------------------------------------------------------------
# Constants (mirrored from whist.py to keep modules independent)
# ---------------------------------------------------------------------------
TURN_ORDER = ['north', 'east', 'south', 'west']
PLAYER_NAMES = {
    'north': 'AI Alice',
    'east': 'AI Bob',
    'south': 'You',
    'west': 'AI Charlie',
}
# Names used when a human claims a seat
HUMAN_NAMES = {
    'north': 'Guest Alice',
    'east': 'Guest Bob',
    'south': 'Host',
    'west': 'Guest Charlie',
}
WINNING_TRICKS = 7

# Database path – same directory as this file.
# On PythonAnywhere, __file__ resolves correctly in WSGI mode, but we fall back
# to the current working directory just in case.
try:
    _base = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _base = os.getcwd()
DB_PATH = os.path.join(_base, 'whist_multi.db')


# ===========================================================================
# DATABASE INITIALISATION
# ===========================================================================

def _get_conn() -> sqlite3.Connection:
    """Open a connection with WAL mode enabled and foreign keys on."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if they don't exist (idempotent – safe to call on every startup)."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS games (
            id              TEXT PRIMARY KEY,
            trump_suit      TEXT NOT NULL,
            trump_suit_name TEXT NOT NULL,
            leader          TEXT NOT NULL DEFAULT 'north',
            stop_type       TEXT NOT NULL DEFAULT 'waiting',
            scores_sn       INTEGER DEFAULT 0,
            scores_ew       INTEGER DEFAULT 0,
            message         TEXT,
            message_class   TEXT DEFAULT 'info-message',
            tricks_json     TEXT DEFAULT '[]',
            version         INTEGER DEFAULT 0,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS seats (
            game_id      TEXT NOT NULL,
            position     TEXT NOT NULL,
            player_type  TEXT DEFAULT 'ai',
            player_name  TEXT,
            session_token TEXT,
            is_connected INTEGER DEFAULT 0,
            PRIMARY KEY (game_id, position),
            FOREIGN KEY (game_id) REFERENCES games(id)
        );

        CREATE TABLE IF NOT EXISTS hands (
            game_id    TEXT NOT NULL,
            position   TEXT NOT NULL,
            cards_json TEXT NOT NULL,
            PRIMARY KEY (game_id, position),
            FOREIGN KEY (game_id) REFERENCES games(id)
        );
    """)
    conn.commit()
    conn.close()


# ===========================================================================
# GAME LIFECYCLE
# ===========================================================================

def create_game(game_id: str, hands: dict, trump_suit: str,
                trump_suit_name: str) -> None:
    """Insert a brand-new game with dealt hands and four AI seats.

    Args:
        game_id: UUID string identifying the game.
        hands: dict position → list of [rank, suit] cards (13 each).
        trump_suit: e.g. 'H'.
        trump_suit_name: e.g. 'heart'.
    """
    conn = _get_conn()
    conn.execute("""
        INSERT INTO games (id, trump_suit, trump_suit_name)
        VALUES (?, ?, ?)
    """, (game_id, trump_suit, trump_suit_name))

    for pos in TURN_ORDER:
        conn.execute("""
            INSERT INTO seats (game_id, position, player_type, player_name)
            VALUES (?, ?, 'ai', ?)
        """, (game_id, pos, PLAYER_NAMES[pos]))
        conn.execute("""
            INSERT INTO hands (game_id, position, cards_json)
            VALUES (?, ?, ?)
        """, (game_id, pos, json.dumps(hands[pos])))

    conn.commit()
    conn.close()


def has_game(game_id: str) -> bool:
    """Return True if the game exists."""
    conn = _get_conn()
    row = conn.execute("SELECT 1 FROM games WHERE id = ?", (game_id,)).fetchone()
    conn.close()
    return row is not None


def get_game(game_id: str) -> Optional[dict]:
    """Return the raw games table row as a dict, or None."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def bump_version(game_id: str) -> None:
    """Increment the version column so pollers know state changed."""
    conn = _get_conn()
    conn.execute("UPDATE games SET version = version + 1 WHERE id = ?", (game_id,))
    conn.commit()
    conn.close()


# ===========================================================================
# SEAT MANAGEMENT
# ===========================================================================

def get_seats(game_id: str) -> dict:
    """Return {position: {player_type, player_name, session_token, is_connected}}."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT position, player_type, player_name, session_token, is_connected "
        "FROM seats WHERE game_id = ?", (game_id,)
    ).fetchall()
    conn.close()
    return {r['position']: dict(r) for r in rows}


def get_seat(game_id: str, position: str) -> Optional[dict]:
    """Return a single seat dict or None."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM seats WHERE game_id = ? AND position = ?",
        (game_id, position)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def assign_human_seat(game_id: str) -> Optional[str]:
    """Claim the first available AI seat (N→E→W, skipping South).
    The player name is set from HUMAN_NAMES based on the seat position.
    Returns the position string, or None if all seats are taken.
    """
    conn = _get_conn()
    for pos in ['north', 'east', 'west']:
        row = conn.execute(
            "SELECT player_type FROM seats WHERE game_id = ? AND position = ?",
            (game_id, pos)
        ).fetchone()
        if row and row['player_type'] == 'ai':
            token = uuid.uuid4().hex
            player_name = HUMAN_NAMES[pos]
            conn.execute("""
                UPDATE seats
                SET player_type = 'human', player_name = ?,
                    session_token = ?, is_connected = 1
                WHERE game_id = ? AND position = ?
            """, (player_name, token, game_id, pos))
            conn.commit()
            conn.close()
            bump_version(game_id)
            return pos
    conn.close()
    return None


def set_south_human(game_id: str, token: str) -> None:
    """Mark the South seat as human with name 'Host' (called when creating the game)."""
    conn = _get_conn()
    conn.execute("""
        UPDATE seats
        SET player_type = 'human', player_name = ?,
            session_token = ?, is_connected = 1
        WHERE game_id = ? AND position = 'south'
    """, (HUMAN_NAMES['south'], token, game_id))
    conn.commit()
    conn.close()


def assign_specific_seat(game_id: str, pos: str) -> bool:
    """Try to claim a specific seat. Returns True on success."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT player_type FROM seats WHERE game_id = ? AND position = ?",
        (game_id, pos)
    ).fetchone()
    if not row or row['player_type'] != 'ai':
        conn.close()
        return False
    token = uuid.uuid4().hex
    player_name = HUMAN_NAMES[pos]
    conn.execute("""
        UPDATE seats SET player_type = 'human', player_name = ?,
            session_token = ?, is_connected = 1
        WHERE game_id = ? AND position = ?
    """, (player_name, token, game_id, pos))
    conn.commit()
    conn.close()
    bump_version(game_id)
    return True


def swap_seats(game_id: str, pos1: str, pos2: str) -> bool:
    """Swap the player identities of two seats.
    Works for any combination (human↔AI, human↔human, AI↔AI).
    Hands stay with seats (cards are dealt to positions, not players).
    Returns True on success.
    """
    if pos1 == pos2:
        return False
    conn = _get_conn()
    seat1 = conn.execute(
        "SELECT * FROM seats WHERE game_id = ? AND position = ?",
        (game_id, pos1)
    ).fetchone()
    seat2 = conn.execute(
        "SELECT * FROM seats WHERE game_id = ? AND position = ?",
        (game_id, pos2)
    ).fetchone()

    if not seat1 or not seat2:
        conn.close()
        return False

    # Swap: pos1 ← seat2's identity, pos2 ← seat1's identity
    conn.execute("""
        UPDATE seats
        SET player_type = ?, player_name = ?,
            session_token = ?, is_connected = ?
        WHERE game_id = ? AND position = ?
    """, (seat2['player_type'], seat2['player_name'],
          seat2['session_token'], seat2['is_connected'],
          game_id, pos1))

    conn.execute("""
        UPDATE seats
        SET player_type = ?, player_name = ?,
            session_token = ?, is_connected = ?
        WHERE game_id = ? AND position = ?
    """, (seat1['player_type'], seat1['player_name'],
          seat1['session_token'], seat1['is_connected'],
          game_id, pos2))

    conn.commit()
    conn.close()
    bump_version(game_id)
    return True


# ===========================================================================
# HAND MANAGEMENT
# ===========================================================================

def get_hands(game_id: str) -> dict:
    """Return {position: [[rank, suit], ...]} for all four players."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT position, cards_json FROM hands WHERE game_id = ?", (game_id,)
    ).fetchall()
    conn.close()
    return {r['position']: json.loads(r['cards_json']) for r in rows}


def get_player_hand(game_id: str, position: str) -> list:
    """Return the hand for a single player as a list of [rank, suit] cards."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT cards_json FROM hands WHERE game_id = ? AND position = ?",
        (game_id, position)
    ).fetchone()
    conn.close()
    return json.loads(row['cards_json']) if row else []


def remove_card(game_id: str, position: str, card: list) -> None:
    """Remove *card* ([rank, suit]) from the player's hand in the database."""
    hand = get_player_hand(game_id, position)
    # Remove the first occurrence (there should be exactly one)
    for i, c in enumerate(hand):
        if c[0] == card[0] and c[1] == card[1]:
            hand.pop(i)
            break
    conn = _get_conn()
    conn.execute(
        "UPDATE hands SET cards_json = ? WHERE game_id = ? AND position = ?",
        (json.dumps(hand), game_id, position)
    )
    conn.commit()
    conn.close()
    bump_version(game_id)


# ===========================================================================
# TRICK MANAGEMENT
# ===========================================================================

def get_tricks(game_id: str) -> list:
    """Return the tricks list: [{pos: [r,s] or None}, ...]."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT tricks_json FROM games WHERE id = ?", (game_id,)
    ).fetchone()
    conn.close()
    return json.loads(row['tricks_json']) if row else []


def add_trick(game_id: str) -> None:
    """Append a new empty trick (all four positions None)."""
    tricks = get_tricks(game_id)
    tricks.append({'north': None, 'east': None, 'south': None, 'west': None})
    conn = _get_conn()
    conn.execute(
        "UPDATE games SET tricks_json = ? WHERE id = ?",
        (json.dumps(tricks), game_id)
    )
    conn.commit()
    conn.close()
    bump_version(game_id)


def play_card_to_trick(game_id: str, position: str, card: list) -> None:
    """Record *card* in the *position* slot of the current (last) trick."""
    tricks = get_tricks(game_id)
    tricks[-1][position] = card
    conn = _get_conn()
    conn.execute(
        "UPDATE games SET tricks_json = ? WHERE id = ?",
        (json.dumps(tricks), game_id)
    )
    conn.commit()
    conn.close()
    bump_version(game_id)


def get_current_trick(game_id: str) -> dict:
    """Return the current (last) trick dict, or empty dict."""
    tricks = get_tricks(game_id)
    return tricks[-1] if tricks else {}


def is_trick_complete(game_id: str) -> bool:
    """True when all four seats have played a card in the current trick."""
    trick = get_current_trick(game_id)
    if not trick:
        return False
    return all(trick.get(pos) is not None for pos in TURN_ORDER)


# ===========================================================================
# TURN MANAGEMENT
# ===========================================================================

def find_next_player(game_id: str) -> Optional[str]:
    """Return the position of the player who should act next,
    or None if the current trick is complete.
    """
    trick = get_current_trick(game_id)
    if not trick:
        return None
    game = get_game(game_id)
    if not game:
        return None
    leader = game['leader']
    leader_idx = TURN_ORDER.index(leader)
    for i in range(4):
        pos = TURN_ORDER[(leader_idx + i) % 4]
        if trick.get(pos) is None:
            return pos
    return None


def update_game_after_trick(game_id: str, winner: str, scores_sn: int,
                            scores_ew: int, message: str, message_class: str,
                            stop_type: str, new_leader: Optional[str] = None) -> None:
    """Update scores, message, stop_type and optionally leader after a trick."""
    conn = _get_conn()
    if new_leader:
        conn.execute("""
            UPDATE games
            SET scores_sn = ?, scores_ew = ?, message = ?, message_class = ?,
                stop_type = ?, leader = ?
            WHERE id = ?
        """, (scores_sn, scores_ew, message, message_class, stop_type,
              new_leader, game_id))
    else:
        conn.execute("""
            UPDATE games
            SET scores_sn = ?, scores_ew = ?, message = ?, message_class = ?,
                stop_type = ?
            WHERE id = ?
        """, (scores_sn, scores_ew, message, message_class, stop_type, game_id))
    conn.commit()
    conn.close()
    bump_version(game_id)


def set_stop_type(game_id: str, stop_type: str) -> None:
    """Update just the stop_type column."""
    conn = _get_conn()
    conn.execute("UPDATE games SET stop_type = ? WHERE id = ?",
                 (stop_type, game_id))
    conn.commit()
    conn.close()
    bump_version(game_id)


def get_version(game_id: str) -> int:
    """Return the current version number (for polling)."""
    conn = _get_conn()
    row = conn.execute("SELECT version FROM games WHERE id = ?",
                       (game_id,)).fetchone()
    conn.close()
    return row['version'] if row else 0


def clear_message(game_id: str) -> None:
    """Clear the message and reset message_class for a new trick."""
    conn = _get_conn()
    conn.execute(
        "UPDATE games SET message = NULL, message_class = 'info-message' WHERE id = ?",
        (game_id,))
    conn.commit()
    conn.close()
    bump_version(game_id)


# ===========================================================================
# FULL STATE ASSEMBLY  (matches the dict shape that whist.html expects)
# ===========================================================================

def get_game_state(game_id: str) -> Optional[dict]:
    """Build the complete game_state dict consumed by the Whist template.

    Returns None when the game does not exist.
    """
    game = get_game(game_id)
    if not game:
        return None
    seats = get_seats(game_id)
    hands = get_hands(game_id)
    tricks = get_tricks(game_id)

    return {
        'stop_type': game['stop_type'],
        'hands': hands,
        'players': {pos: seats[pos]['player_name'] for pos in TURN_ORDER},
        'leader': game['leader'],
        'tricks': tricks,
        'scores': {
            'south_north': game['scores_sn'],
            'east_west': game['scores_ew'],
        },
        'trump_suit': game['trump_suit'],
        'trump_suit_name': game['trump_suit_name'],
        'message': game['message'],
        'message_class': game['message_class'] or 'info-message',
        # Multiplayer-specific extras
        'is_multiplayer': True,
        'game_id': game_id,
    }
