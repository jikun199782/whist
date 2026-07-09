"""Game event logger stored in Flask session."""

from datetime import datetime

MAX_ENTRIES = 500


def add_log_entry(session, message):
    """Add a timestamped [ts, msg] pair to the session log."""
    if 'game_log' not in session:
        session['game_log'] = []
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    session['game_log'].append([ts, message])
    # Prevent unbounded growth
    if len(session['game_log']) > MAX_ENTRIES:
        session['game_log'] = session['game_log'][-MAX_ENTRIES:]
    session.modified = True


def get_user_log(session):
    """Return the log list (list of [timestamp, message] pairs)."""
    return session.get('game_log', [])
