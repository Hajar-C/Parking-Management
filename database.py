import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import random

DB_NAME = "parking.db"


def init_db():
    """
    Initialise la base de données en créant les tables nécessaires si elles n'existent pas déjà.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Création des tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS parkings (
            parking_id INTEGER PRIMARY KEY,
            zone TEXT NOT NULL,
            type_zone TEXT NOT NULL,
            is_occupied INTEGER NOT NULL DEFAULT 0,
            statut TEXT DEFAULT 'Disponible'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            reservation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            matricule TEXT NOT NULL,
            zone TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    """)


    # Réinitialiser les données de la table parkings
    cursor.execute("DELETE FROM parkings")

    # Préparer les zones et les types de places
    zones = ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]
    types = ["VIP"] * 10 + ["Handicap"] * 10 + ["Standard"] * 30

    random.shuffle(types)
    parking_slots = []
    for i in range(1, 51):
        parking_slots.append((i, zones[(i - 1) % len(zones)], types[i - 1], 0))

    cursor.executemany(
        "INSERT INTO parkings (parking_id, zone, type_zone, is_occupied) VALUES (?, ?, ?, ?)", 
        parking_slots
    )
    conn.commit()
    conn.close()

def register_user(username, password):
    """
    Enregistre un utilisateur dans la base de données.
    Retourne True si l'utilisateur est enregistré avec succès, sinon False.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    hashed_password = generate_password_hash(password)
    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def authenticate_user(username, password):
    """
    Authentifie un utilisateur.
    Retourne l'ID de l'utilisateur si les informations sont correctes.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    if user and check_password_hash(user[2], password):
        return user[0]
    return None

def get_user_reservations(user_id):
    """
    Retourne les réservations d'un utilisateur avec le parking_id associé.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT reservation_id, matricule, zone, start_time, end_time, parking_id
        FROM reservations
        WHERE user_id = ?
    """, (user_id,))
    reservations = cursor.fetchall()
    conn.close()
    return reservations


def get_available_slots():
    """
    Retourne toutes les places de parking avec leurs statuts.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT parking_id, zone, type_zone, is_occupied 
        FROM parkings
    """)
    slots = cursor.fetchall()
    conn.close()
    return slots



def reserve_slot(user_id, matricule, zone, start_time, end_time):
    """
    Réserve une place pour un utilisateur.
    Retourne un tuple contenant l'ID de la réservation et l'ID de la place.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Vérifier si une réservation active existe déjà pour le matricule donné
    cursor.execute("""
        SELECT COUNT(*) FROM reservations 
        WHERE matricule = ? AND datetime(end_time) > datetime('now')
    """, (matricule,))
    existing_reservations = cursor.fetchone()[0]

    if existing_reservations > 0:
        conn.close()
        raise ValueError("Une réservation existe déjà pour ce matricule.")

    # Trouver la place disponible pour la zone sélectionnée
    cursor.execute("SELECT parking_id FROM parkings WHERE zone = ? AND is_occupied = 0 LIMIT 1", (zone,))
    available_slot = cursor.fetchone()

    if available_slot:
        parking_id = available_slot[0]
        # Mettre à jour la place comme occupée
        cursor.execute("UPDATE parkings SET is_occupied = 1 WHERE parking_id = ?", (parking_id,))
        # Créer la réservation en associant le parking_id
        cursor.execute("""
            INSERT INTO reservations (user_id, matricule, zone, start_time, end_time, parking_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, matricule, zone, start_time, end_time, parking_id))
        reservation_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return reservation_id, parking_id
    else:
        conn.close()
        raise ValueError("Aucune place disponible dans la zone sélectionnée.")



def cancel_reservation(reservation_id):
    """
    Annule une réservation et libère la place correspondante.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Libérer la place associée à la réservation
    cursor.execute("""
        UPDATE parkings
        SET is_occupied = 0
        WHERE parking_id = (
            SELECT parking_id FROM reservations WHERE reservation_id = ?
        )
    """, (reservation_id,))
    # Supprimer la réservation
    cursor.execute("DELETE FROM reservations WHERE reservation_id = ?", (reservation_id,))
    conn.commit()
    conn.close()
 
