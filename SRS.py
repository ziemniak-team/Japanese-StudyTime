
\"\"\"SRS.py - simple SM-2 spaced repetition utilities

This module implements a compact version of the SM-2 algorithm used in many SRS systems.
It exposes helper functions to initialize a card and to update scheduling after a review.

Card object (dict-like) expected fields (some optional):
- id: unique id (string/int)
- efactor: float (ease factor)
- interval: int (days)
- repetition: int (consecutive correct repetitions)
- due_date: ISO date string (YYYY-MM-DD)
- correct_count: int
- wrong_count: int

Functions:
- init_card(id): returns defaults for a new card
- update_review(card, quality, today=None): update card in-place and return it
- days_until_due(card, today=None): returns int number of days until due (<=0 => due now)
\"\"\"

from datetime import datetime, timedelta

DEFAULT_EFACTOR = 2.5

def iso_today(today=None):
    if today is None:
        return datetime.utcnow().date().isoformat()
    if isinstance(today, str):
        return today
    return today.date().isoformat()

def init_card(card_id):
    \"\"\"Return a new card dict with SRS fields initialized.\"\"\"
    return {
        'id': str(card_id),
        'efactor': DEFAULT_EFACTOR,
        'interval': 0,
        'repetition': 0,
        'due_date': iso_today(),
        'correct_count': 0,
        'wrong_count': 0,
        'kana': None,  # optional user-provided kana reading
    }

def update_review(card, quality, today=None):
    \"\"\"Update the card's scheduling based on the SM-2 algorithm.
    quality: integer 0-5 (5 excellent, 0 complete blackout)
    Returns the updated card (also mutates the dict in-place).
    \"\"\"
    if quality < 0 or quality > 5:
        raise ValueError('quality must be between 0 and 5')
    if today is None:
        today = datetime.utcnow().date()

    # If the quality is less than 3, reset repetition count.
    if quality < 3:
        card['repetition'] = 0
        card['interval'] = 1
        card['wrong_count'] = card.get('wrong_count', 0) + 1
    else:
        card['correct_count'] = card.get('correct_count', 0) + 1
        card['repetition'] = card.get('repetition', 0) + 1
        if card['repetition'] == 1:
            card['interval'] = 1
        elif card['repetition'] == 2:
            card['interval'] = 6
        else:
            # next interval = previous_interval * efactor
            card['interval'] = int(round(card['interval'] * card.get('efactor', DEFAULT_EFACTOR)))

    # Update ease factor
    ef = card.get('efactor', DEFAULT_EFACTOR)
    ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    if ef < 1.3:
        ef = 1.3
    card['efactor'] = round(ef, 4)

    # Set next due date
    due = today + timedelta(days=max(1, int(card['interval'])))
    card['due_date'] = due.isoformat()

    return card

def days_until_due(card, today=None):
    if today is None:
        today = datetime.utcnow().date()
    else:
        if isinstance(today, str):
            today = datetime.fromisoformat(today).date()
    due = datetime.fromisoformat(card['due_date']).date()
    return (due - today).days
