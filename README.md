# Parking Management

Application web de gestion de parking développée avec **Python / Flask**.

## Fonctionnalités
- Authentification (inscription / connexion) avec mots de passe hashés (Werkzeug)
- Réservation de places par zone (VIP, Handicap, Standard)
- Suivi des places occupées / disponibles en temps réel (SQLite)
- Libération automatique des places dont la réservation a expiré
- Génération de reçus de réservation en PDF (ReportLab)

## Stack
- Flask, SQLite3, Werkzeug (hash de mots de passe), ReportLab (génération PDF)

## Lancer le projet
```bash
pip install -r requirements.txt  # flask, reportlab, werkzeug
python app.py
```

## Auteurs
Projet réalisé à deux.
