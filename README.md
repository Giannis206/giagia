# Ελληνικό Σταυρόλεξο — Τοπικός Γεννήτορας

Μικρό Python πρόγραμμα για δημιουργία αμερικάνικου τύπου σταυρόλεξου (με μαύρα τετράγωνα, συμμετρία 180°) και εκτύπωση σε PDF μέσω browser.

## Απαιτήσεις

- Python 3.11+
- Jinja2 + Flask (μόνο για HTML templating και τοπικό UI)

## Εγκατάσταση

```bash
cd c:\giagia
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Χρήση

### Συντόμευση επιφάνειας εργασίας (Windows — χωρίς terminal)

1. Κάνε διπλό κλικ στο `start_silent.vbs` για δοκιμή (ξεκινά server + ανοίγει Microsoft Edge).
2. **Δημιουργία συντόμευσης:**
   - Right-click στο `start_silent.vbs` → **Create shortcut**
   - Σύρε τη συντόμευση στην Επιφάνεια Εργασίας
   - (Προαιρετικά) Right-click στη συντόμευση → **Properties** → **Change Icon** για αναγνωρίσιμο εικονίδιο
3. Από εδώ και πέρα: **διπλό κλικ** → Edge → UI στο `http://localhost:5000` (ή `5001` αν η 5000 είναι κατειλημμένη).

Το UI έχει μεγάλα κουμπιά:
- **Δημιουργία νέου σταυρόλεξου**
- **Επανάληψη** (νέο τυχαίο)
- **Άνοιγμα για εκτύπωση** (ανοίγει `/print` με dialog εκτύπωσης)
- **Κλείσιμο server**

Αρχεία εκκίνησης:
- `start_silent.vbs` — χωρίς ορατό παράθυρο CMD (για τη συντόμευση)
- `start.bat` — ίδια λειτουργία, ελάχιστο minimized CMD

### Διαδραστικό μενού (CLI)

```bash
python main.py
```

Επιλογές:
1. **Generate new crossword** — νέο σταυρόλεξο
2. **Open printable preview** — άνοιγμα HTML στον browser
3. **Regenerate** — νέο τυχαίο σταυρόλεξο
4. **Exit**

### Γρήγορη δημιουργία (CLI)

```bash
# Τυχαίο σταυρόλεξο + άνοιγμα preview
python main.py --generate --open

# Με deterministic seed
python main.py --generate --seed 42 --open

# Μεγαλύτερο πλέγμα
python main.py --generate --size 13 --open
```

## Εκτύπωση σε PDF

1. Τρέξε `python main.py --generate --open` ή επίλεξε **Open printable preview**
2. Στον browser: **Ctrl+P** (ή Cmd+P στο macOS)
3. Προορισμός: **Save as PDF**
4. Βεβαιώσου ότι είναι **Portrait A4** — το CSS ορίζει ακριβώς 2 σελίδες:
   - **Σελίδα 1:** Μόνο το πλέγμα (κενά κελιά, υψηλή αντίθεση)
   - **Σελίδα 2:** Λέξεις ομαδοποιημένες ανά μήκος, μεγάλη γραμματοσειρά

## Δομή project

```
main.py
app.py              # τοπικό Flask UI (localhost:5000)
start.bat
start_silent.vbs    # launcher χωρίς CMD — για συντόμευση
crossword/
  grid.py       # πλέγμα + συμμετρικό pattern
  slots.py      # εξαγωγή across/down slots
  validate.py   # κανόνες επικύρωσης
  dictionary.py # normalization + validation rules
  word_store.py # SQLite word DB + in-memory index
  solver.py     # backtracking + MRV heuristic
  render.py     # HTML output
data/
  greek_words.db      # build via scripts/build_word_db.py
  words_3.txt … words_12.txt
  sources/el_50k.txt
templates/
  print.html
static/
  print.css
output/
  crossword.html
```

## Λεξικό (Plan B — SQLite)

Η βάση λέξεων είναι τοπικό SQLite αρχείο `data/greek_words.db` (~48.000+ πραγματικές ελληνικές λέξεις, μήκη 3–12).

### Χτίσιμο βάσης

```bash
python scripts/build_word_db.py --download
python scripts/validate_word_db.py
```

Πηγές: `SUBTLEX-GR_restricted.txt`, `data/sources/el_50k.txt`, `curated_el.txt`, `words_*.txt`, και οποιοδήποτε `data/sources/*.{txt,csv,json}`.

### Δοκιμές generation

```bash
python scripts/test_generation.py
```

## Σημειώσεις

- Προεπιλογή πλέγματος: **7×7** (~39mm κελιά στο Α4 — ιδανικό για χαμηλή όραση)
- Αν αποτύχει η γέμιση, εμφανίζεται καθαρό μήνυμα σφάλματος (χωρίς ψεύτικες λέξεις)
- Το `--seed` δίνει επαναλήψιμη δημιουργία
- Μεγέθη: 7×7 και 10×10 είναι αξιόπιστα· 8×8 μερικώς· 12×12 ακόμα ασταθές
