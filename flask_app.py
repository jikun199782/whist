import os
import uuid
from flask import Flask, render_template, redirect, url_for, session
from playcard import get_card_name
#from userlog import add_log_entry, get_user_log
import blackjack, blackjack_eu, whist

SUPPORTED_GAMES = {'blackjack': blackjack, 'blackjack_eu': blackjack_eu, 'whist': whist}
app = Flask(__name__)
# Generate a random secret key for the session
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

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
    cur_game = session.get('cur_game', '')
    game_state = session.get('game_state', {})
    if cur_game in SUPPORTED_GAMES and game_state:
        return render_template(f'{cur_game}.html',
                               game_state=game_state)
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
        session_id = session.get('session_id', '')
        # add_log_entry(session_id, f'Select {target_game}.')
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
                           log=get_user_log(session_id))

@app.route('/about')
def about():
    return render_template('about.html', supported=True)


@app.context_processor
def utility_processor():
    # Make the `get_card_name` function available in all templates
    return dict(enumerate=enumerate, get_card_name=get_card_name)


if __name__ == '__main__':
    app.run(port=80)