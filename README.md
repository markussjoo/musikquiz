# Musikquiz – Webbapp

En komplett webbapp för att skapa och genomföra musikquiz med:
- **Deltagarvy (`/quiz/<slug>` eller `/`)**: Deltagarna börjar med att skriva sitt användarnamn/lagnamn och fyller sedan i svarsformuläret.
- **Admin-panel (`/admin`)**: Skapa quiz, lägg in frågor (Artist + Låt, Fritext eller Flerval), kopiera delningslänk, rätta svar, se topplista och exportera resultat som CSV.

## Starta appen

```bash
python3 server.py
```

Öppna sedan i webbläsaren:
- **Deltagarformulär:** `http://localhost:8000` (eller direktlänk `http://localhost:8000/quiz/fredagsquiz`)
- **Admin-panel:** `http://localhost:8000/admin` (standard-PIN: `1234`)

## Anpassa port eller Admin-PIN

```bash
PORT=8080 ADMIN_PIN=9999 python3 server.py
```

All data sparas automatiskt i SQLite-databasen `quiz.db`.
