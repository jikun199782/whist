// ==================== GLOBAL STATE ====================
let selectedCard = null;
let gameState = null;

// ==================== HELPER FUNCTIONS ====================
function getLeadSuit() {
    if (!gameState?.current_trick || gameState.current_trick.length === 0) {
        return null;
    }
    const leadCard = gameState.current_trick[gameState.leader];
    return leadCard ? leadCard[1] : null;
}

function isCardEligible(card) {
    if (!gameState
        || gameState.stop_type === 'new_trick'
        || gameState.stop_type === 'game_over') {
        return false;
    }

    if (gameState.stop_type === 'lead_card') {
        return true;
    }

    const leadSuit = getLeadSuit();
    if (!gameState.player_hand.some(c => c[1] === leadSuit)) {
        return true; // void
    }

    return card[1] === leadSuit;
}

const SUIT_NAME_MAP = {
    'H': 'heart', 'S': 'spade', 'D': 'diamond', 'C': 'club'
};

const RANK_NAME_MAP = {
    'A': '1', '2': '2', '3': '3', '4': '4', '5': '5', '6': '6',
    '7': '7', '8': '8', '9': '9', 'T': '10',
    'J': 'jack', 'Q': 'queen', 'K': 'king'
};

function get_card_name(card) {
    if (!card || card.length < 2) return '';
    return `${SUIT_NAME_MAP[card[1]]}_${RANK_NAME_MAP[card[0]]}`;
}

// ==================== CARD SELECTION ====================
function selectCard(cardElement, cardData) {
    // Clear previous selection (only in South's hand)
    document.querySelectorAll('.south .card').forEach(c => {
        c.classList.remove('selected');
    });

    // Select the new card
    cardElement.classList.add('selected');
    selectedCard = cardData;
    enableProceedButton();
}

// ==================== BUTTON FUNCTIONS ====================
function enableProceedButton() {
    const btn = document.getElementById('proceed-btn');
    if (btn) {
        btn.disabled = false;
        btn.classList.remove('disabled');
    }
}

// ==================== PROCEED ACTION ====================
function proceedAction() {
    const btn = document.getElementById('proceed-btn');
    if (!btn || btn.disabled) return;

    // Disable immediately
    btn.disabled = true;
    btn.classList.add('disabled');

    if (!gameState || gameState.stop_type === 'game_over') {
        return;
    }

    if (gameState.stop_type === 'new_trick') {
        window.location.href = '/game_update/new_trick';
        return;
    }

    if (selectedCard) {
        window.location.href = `/game_update/play/${selectedCard}`;
    }
}


// ==================== BUTTON INITIALIZATION ====================
function initProceedButton() {
    const btn = document.getElementById('proceed-btn');
    if (!btn) return;

    if (!gameState || !gameState.stop_type) {
        btn.classList.remove('visible');
        return;
    }

    switch (gameState.stop_type) {
        case 'new_trick':
            btn.textContent = 'New Trick';
            btn.disabled = false;
            btn.classList.add('visible');
            break;

        case 'lead_card':
            btn.textContent = 'Lead Card';
            btn.disabled = true;
            btn.classList.add('visible');
            break;

        case 'follow_card':
            btn.textContent = 'Follow Card';
            btn.disabled = true;
            btn.classList.add('visible');
            break;

        default:
            btn.classList.remove('visible');
            return;
    }

    btn.classList.toggle('disabled', btn.disabled);
    btn.addEventListener('click', proceedAction);
}

// ==================== RENDER SOUTH HAND ====================
function renderSouthHand() {
    const container = document.getElementById('south-hand');
    if (!container || !gameState?.player_hand) return;

    container.innerHTML = '';

    gameState.player_hand.forEach(card => {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("class", "card");
        svg.setAttribute("viewBox", "0 0 169 244");

        const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
        use.setAttribute("href", `/static/svg-cards.svg#${get_card_name(card)}`);
        svg.appendChild(use);

        if (isCardEligible(card)) {
            svg.classList.add('eligible');
            svg.addEventListener('click', () => selectCard(svg, card));
        }

        container.appendChild(svg);
    });
}

// ==================== INITIALIZE ====================
function initializeGame() {
    gameState = window.gameState || {};
    renderSouthHand();
    initProceedButton();
}

// Start
document.addEventListener('DOMContentLoaded', initializeGame);