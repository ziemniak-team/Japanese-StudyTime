
\"\"\"flashcards_app.py - lightweight Tkinter flashcard app for Japanese study.

Features implemented:
- Loads CSV "japanese_flashcards.csv" automatically (expects id,word_phrase,translation)
- SQLite DB "flashcards.db" to store SRS fields and user-provided kana readings & progress
- Dark-themed Tkinter UI (custom styling)
- Loading splash screen while assets load
- Large centered Japanese word/phrase, translation below (toggleable)
- 'Show Kana' button: if kana not present, prompts user to enter it and saves
- Difficulty buttons (Easy / Medium / Hard) that map to review quality and update SRS
- Auto-save progress to DB
- Uses SRS.py module (SM-2 implementation) for scheduling logic

Run this script with: python3 flashcards_app.py
\"\"\"

import os, sqlite3, csv, threading, time, sys
from datetime import datetime
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, font

# Import local SRS utilities (SRS.py must be in same directory)
try:
    from SRS import init_card, update_review, days_until_due
except Exception as e:
    print('Could not import SRS module:', e)
    init_card = lambda cid: {'id': str(cid), 'efactor':2.5,'interval':0,'repetition':0,'due_date':datetime.utcnow().date().isoformat(),'correct_count':0,'wrong_count':0,'kana':None}
    def update_review(card, quality, today=None):
        card['due_date'] = datetime.utcnow().date().isoformat()
        return card
    def days_until_due(card, today=None):
        return 0

BASE = os.path.dirname(__file__)
CSV_PATH = os.path.join(BASE, 'japanese_flashcards.csv')
DB_PATH = os.path.join(BASE, 'flashcards.db')

# --- Database helpers ---
def get_db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS cards (
            id TEXT PRIMARY KEY,
            word_phrase TEXT,
            translation TEXT,
            kana TEXT,
            efactor REAL,
            interval INTEGER,
            repetition INTEGER,
            due_date TEXT,
            correct_count INTEGER DEFAULT 0,
            wrong_count INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def load_csv_into_db(csv_path):
    if not os.path.exists(csv_path):
        return 0
    conn = get_db_conn()
    cur = conn.cursor()
    added = 0
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f, fieldnames=['id','word_phrase','translation'])
        for row in reader:
            card_id = str(row['id']).strip()
            word = row['word_phrase'].strip() if row['word_phrase'] else ''
            translation = row['translation'].strip() if row['translation'] else ''
            cur.execute('SELECT id FROM cards WHERE id=?', (card_id,))
            if cur.fetchone() is None:
                # initialize SRS fields
                s = init_card(card_id)
                cur.execute('INSERT INTO cards (id,word_phrase,translation,kana,efactor,interval,repetition,due_date,correct_count,wrong_count) VALUES (?,?,?,?,?,?,?,?,?,?)',
                            (card_id, word, translation, None, s.get('efactor',2.5), s.get('interval',0), s.get('repetition',0), s.get('due_date', datetime.utcnow().date().isoformat()), 0, 0))
                added += 1
    conn.commit()
    conn.close()
    return added

# --- Flashcard selection ---
def get_due_cards(limit=100):
    conn = get_db_conn()
    cur = conn.cursor()
    today = datetime.utcnow().date().isoformat()
    cur.execute('SELECT * FROM cards ORDER BY due_date ASC LIMIT ?', (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_card_in_db(card):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute('''UPDATE cards SET kana=?, efactor=?, interval=?, repetition=?, due_date=?, correct_count=?, wrong_count=? WHERE id=?''',
                (card.get('kana'), card.get('efactor'), card.get('interval'), card.get('repetition'), card.get('due_date'), card.get('correct_count',0), card.get('wrong_count',0), card.get('id')))
    conn.commit()
    conn.close()

# --- UI ---
class FlashcardApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Japanese Flashcards — Dark SRS')
        self.geometry('800x520')
        self.configure(bg='#111217')
        self.style = ttk.Style(self)
        self._setup_style()
        self.current_index = 0
        self.cards = []
        self.build_ui()
        # Load cards in background so splash screen can show if needed
        self.after(100, self.load_cards_and_start)

    def _setup_style(self):
        # Basic dark theme styling for ttk widgets & fonts
        default_font = font.nametofont('TkDefaultFont')
        default_font.configure(size=11, family='Segoe UI' if os.name == 'nt' else 'Helvetica')
        self.option_add('*Font', default_font)
        self.style.theme_use('clam')
        self.style.configure('TButton', background='#22252b', foreground='#e6eef8', padding=8, relief='flat', borderwidth=0)
        self.style.map('TButton', background=[('active', '#2b3038')])
        self.style.configure('Card.TFrame', background='#0f1113')
        self.style.configure('Big.TLabel', background='#0f1113', foreground='#f6f8ff', font=(None, 40, 'bold'))
        self.style.configure('Small.TLabel', background='#0f1113', foreground='#cbd5e1', font=(None, 14))
        self.style.configure('Difficulty.TButton', padding=10)
        self.style.configure('TEntry', fieldbackground='#15161a', foreground='#ffffff')

    def build_ui(self):
        # Top area: menu buttons
        top = ttk.Frame(self, style='Card.TFrame')
        top.pack(fill='x', padx=12, pady=8)
        ttk.Button(top, text='Shuffle', command=self.shuffle_cards).pack(side='left', padx=6)
        ttk.Button(top, text='Add Kana', command=self.prompt_add_kana).pack(side='left', padx=6)
        ttk.Button(top, text='Export Progress', command=self.export_progress).pack(side='left', padx=6)
        ttk.Button(top, text='Quit', command=self.quit).pack(side='right', padx=6)

        # Card area
        card_frame = ttk.Frame(self, style='Card.TFrame')
        card_frame.pack(expand=True, fill='both', padx=16, pady=8)
        self.card_label = ttk.Label(card_frame, text='—', style='Big.TLabel', anchor='center', justify='center', wraplength=720)
        self.card_label.pack(expand=True)
        self.translation_label = ttk.Label(card_frame, text='', style='Small.TLabel', anchor='n', justify='center', wraplength=720)
        self.translation_label.pack(pady=(6,12))

        # Bottom area: controls
        bottom = ttk.Frame(self, style='Card.TFrame')
        bottom.pack(fill='x', padx=12, pady=10)
        ttk.Button(bottom, text='Show/Hide Translation', command=self.toggle_translation).pack(side='left', padx=6)
        ttk.Button(bottom, text='Show Kana', command=self.show_or_ask_kana).pack(side='left', padx=6)

        # Difficulty buttons grouped
        diff_frame = ttk.Frame(bottom, style='Card.TFrame')
        diff_frame.pack(side='right', padx=4)
        ttk.Button(diff_frame, text='Easy', style='Difficulty.TButton', command=lambda: self.review_with_quality(5)).pack(side='left', padx=6)
        ttk.Button(diff_frame, text='Medium', style='Difficulty.TButton', command=lambda: self.review_with_quality(4)).pack(side='left', padx=6)
        ttk.Button(diff_frame, text='Hard', style='Difficulty.TButton', command=lambda: self.review_with_quality(2)).pack(side='left', padx=6)
        ttk.Button(diff_frame, text='Skip', style='Difficulty.TButton', command=self.next_card).pack(side='left', padx=6)

    # --- Loading & data ---
    def load_cards_and_start(self):
        # Show a short loading/splash if loading heavy assets (simulate)
        splash = SplashScreen(self)
        self.update()
        def worker():
            init_db()
            added = load_csv_into_db(CSV_PATH)
            self.cards = get_due_cards(500)
            time.sleep(0.6)  # small delay so splash can be seen
            splash.close()
            self.after(10, self.show_current_card)
        threading.Thread(target=worker, daemon=True).start()

    def show_current_card(self):
        if not self.cards:
            self.card_label.config(text='No cards found.\nPlace japanese_flashcards.csv next to this script and restart.')
            self.translation_label.config(text='')
            return
        card = self.cards[self.current_index % len(self.cards)]
        self.current_card = card
        self.card_label.config(text=card.get('word_phrase', '—'))
        self.translation_label.config(text=card.get('translation', ''))
        self.translation_visible = True

    def next_card(self):
        if not self.cards:
            return
        self.current_index = (self.current_index + 1) % len(self.cards)
        self.show_current_card()

    def shuffle_cards(self):
        import random
        random.shuffle(self.cards)
        self.current_index = 0
        self.show_current_card()

    # --- Actions ---
    def toggle_translation(self):
        if not hasattr(self, 'translation_visible'):
            self.translation_visible = True
        self.translation_visible = not self.translation_visible
        self.translation_label.config(text=self.current_card.get('translation') if self.translation_visible else '')

    def show_or_ask_kana(self):
        card = self.current_card
        if not card:
            return
        if card.get('kana'):
            # toggle between kana and original phrase
            currently = self.card_label.cget('text')
            if currently == card.get('word_phrase'):
                self.card_label.config(text=card.get('kana'))
            else:
                self.card_label.config(text=card.get('word_phrase'))
        else:
            # ask user to provide kana; save to DB
            self.prompt_kana_for_card(card)

    def prompt_kana_for_card(self, card):
        ans = simpledialog.askstring('Add Kana', f'No kana saved for this card (id={card.get("id")}).\\nEnter kana reading now:')
        if ans:
            card['kana'] = ans.strip()
            update_card_in_db(card)
            messagebox.showinfo('Saved', 'Kana saved for this card.')

    def prompt_add_kana(self):
        # general utility to pick a card by id and add kana
        cid = simpledialog.askstring('Add Kana by ID', 'Enter card id:')
        if not cid:
            return
        matches = [c for c in self.cards if c.get('id') == cid]
        if not matches:
            messagebox.showwarning('Not found', 'Card id not found among loaded cards.')
            return
        self.prompt_kana_for_card(matches[0])
        self.show_current_card()

    def review_with_quality(self, quality):
        # Map quality (0-5) expected by SRS.update_review
        card = self.current_card
        if not card:
            return
        # Ensure SRS fields exist in the dict
        c = dict(card)  # shallow copy
        # normalize fields expected by SRS
        if c.get('efactor') is None:
            c['efactor'] = 2.5
        if c.get('interval') is None:
            c['interval'] = 0
        if c.get('repetition') is None:
            c['repetition'] = 0
        c = update_review(c, quality)
        # write SRS fields back to db and local list
        # preserve kana if present in local card
        if card.get('kana'):
            c['kana'] = card.get('kana')
        update_card_in_db(c)
        # update the in-memory list
        self.cards[self.current_index % len(self.cards)] = {**card, **c}
        # feedback then jump to next card
        self.show_score_feedback(quality)
        self.next_card()

    def show_score_feedback(self, quality):
        if quality >= 5:
            msg = 'Great! Marked Easy.'
        elif quality >= 4:
            msg = 'Nice — Medium.'
        else:
            msg = 'Tough one — will review sooner.'
        # subtle transient notification
        self.title(f'Japanese Flashcards — {msg}')

    def export_progress(self):
        # Exports a CSV with progress/state
        path = os.path.join(BASE, 'flashcard_progress_export.csv')
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute('SELECT * FROM cards')
        rows = cur.fetchall()
        conn.close()
        with open(path, 'w', encoding='utf-8', newline='') as f:
            w = csv.writer(f)
            w.writerow(['id','word_phrase','translation','kana','efactor','interval','repetition','due_date','correct_count','wrong_count'])
            for r in rows:
                w.writerow([r['id'], r['word_phrase'], r['translation'], r['kana'], r['efactor'], r['interval'], r['repetition'], r['due_date'], r['correct_count'], r['wrong_count']])
        messagebox.showinfo('Exported', f'Progress exported to: {path}')

# --- Splash screen ---
class SplashScreen(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.overrideredirect(True)
        self.geometry('420x220+{}+{}'.format(int(parent.winfo_screenwidth()/2-210), int(parent.winfo_screenheight()/2-110)))
        self.configure(bg='#0b0c0e')
        lbl = tk.Label(self, text='Loading Japanese Flashcards', bg='#0b0c0e', fg='#e8eef8', font=('Helvetica', 16, 'bold'))
        lbl.pack(expand=True)
        sub = tk.Label(self, text='Preparing database and assets...', bg='#0b0c0e', fg='#aab3c6', font=('Helvetica', 10))
        sub.pack(pady=(0,20))
        self.update()

    def close(self):
        self.destroy()

# --- Entry point for script ---
def main():
    app = FlashcardApp()
    app.mainloop()

if __name__ == '__main__':
    main()
