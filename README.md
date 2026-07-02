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
  solver.py     # backtracking + MRV heuristic
  render.py     # HTML output
data/
  words_3.txt … words_8.txt
templates/
  print.html
static/
  print.css
output/
  crossword.html
```

## Λεξικό

Πρόσθεσε δικές σου λέξεις στα `data/words_N.txt` (μία λέξη ανά γραμμή, κεφαλαία ελληνικά, χωρίς τόνους). Κάθε αρχείο πρέπει να περιέχει λέξεις μήκους `N` μόνο. Τα sample αρχεία περιλαμβάνουν και κοινούς ελληνικούς συνδυασμούς γραμμάτων ώστε να ολοκληρώνεται ευκολότερα η γέμιση — μπορείς να τα αντικαταστήσεις σταδιακά με πραγματικό λεξικό.

## Σημειώσεις

- Προεπιλογή πλέγματος: **7×7** (~39mm κελιά στο Α4 — ιδανικό για χαμηλή όραση)
- Αν αποτύχει η γέμιση, ο γεννήτορας ξαναδοκιμάζει αυτόματα με νέο pattern/seed
- Το `--seed` δίνει επαναλήψιμη δημιουργία
