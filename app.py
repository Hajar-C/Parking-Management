import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from datetime import datetime
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from database import init_db, register_user, authenticate_user, get_user_reservations, cancel_reservation, get_available_slots, reserve_slot
from database import DB_NAME
import glob
from datetime import timedelta

app = Flask(__name__)
app.secret_key = "secret_key"

# Initialisation de la base de données
init_db()

def update_expired_reservations():
    """
    Libère les places pour lesquelles la date de fin est dépassée.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE parkings
        SET is_occupied = 0
        WHERE parking_id IN (
            SELECT parking_id
            FROM reservations
            WHERE datetime(end_time) < datetime('now')
        )
    """)
    cursor.execute("""
        DELETE FROM reservations
        WHERE datetime(end_time) < datetime('now')
    """)
    conn.commit()
    conn.close()

def get_zones_by_type(type_zone):
    """
    Retourne les zones disponibles pour un type donné (VIP, Handicap, Standard).
    """
    conn = sqlite3.connect("parking.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT zone FROM parkings 
        WHERE type_zone = ? AND is_occupied = 0
    """, (type_zone,))
    zones = [row[0] for row in cursor.fetchall()]
    conn.close()
    return zones

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("slots"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["username"]
        password = request.form["password"]
        user_id = authenticate_user(email, password)
        if user_id:
            session["user_id"] = user_id
            session["username"] = email
            flash("Connexion réussie.", "success")
            return redirect(url_for("slots"))
        else:
            flash("Nom d'utilisateur ou mot de passe incorrect.", "error")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        repeat_password = request.form["repeat_password"]

        if password != repeat_password:
            flash("Les mots de passe ne correspondent pas.", "error")
            return redirect(url_for("register"))

        try:
            if register_user(email, password):
                flash("Inscription réussie. Vous pouvez maintenant vous connecter.", "success")
                return redirect(url_for("login"))
            else:
                flash("Cet e-mail est déjà utilisé.", "error")
        except Exception as e:
            flash(f"Erreur : {e}", "error")
            return redirect(url_for("register"))

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("username", None)
    flash("Déconnexion réussie.", "success")
    return redirect(url_for("login"))

@app.route("/slots")
def slots():
    if "user_id" not in session:
        return redirect(url_for("login"))
    update_expired_reservations()
    slots = get_available_slots()
    return render_template("slots.html", slots=slots)

@app.route("/reserve", methods=["GET", "POST"])
def reserve():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        matricule = request.form["matricule"]
        zone = request.form["zone"]
        start_time = request.form["start_time"]
        end_time = request.form["end_time"]
        user_id = session["user_id"]

        if not matricule or not zone or not start_time or not end_time:
            flash("Tous les champs sont requis.", "error")
            return redirect(url_for("reserve"))

        try:
            reservation_id, parking_id = reserve_slot(user_id, matricule, zone, start_time, end_time)
            
            # Préparer les détails de la réservation
            reservation_details = (reservation_id, matricule, zone, start_time, end_time, parking_id)
            
            # Générer le reçu PDF
            generate_pdf_receipt(reservation_details)
            
            flash(f"Réservation réussie !", "success")
            return redirect(url_for("reservations"))
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("reserve"))

    vip_zones = get_zones_by_type("VIP")
    handicap_zones = get_zones_by_type("Handicap")
    standard_zones = get_zones_by_type("Standard")

    return render_template(
        "reserve.html", 
        vip_zones=vip_zones, 
        handicap_zones=handicap_zones, 
        standard_zones=standard_zones
    )


@app.route("/reservations")
def reservations():
    if "user_id" not in session:
        return redirect(url_for("login"))
    update_expired_reservations()
    user_id = session["user_id"]
    reservations = get_user_reservations(user_id)
    return render_template("reservations.html", reservations=reservations)

@app.route("/cancel/<int:reservation_id>", methods=["POST"])
def cancel(reservation_id):
    if "user_id" not in session:
        flash("Vous devez être connecté pour annuler une réservation.", "error")
        return redirect(url_for("login"))

    try:
        cancel_reservation(reservation_id)
        flash("Réservation annulée avec succès.", "success")
    except Exception as e:
        flash(f"Erreur lors de l'annulation : {e}", "error")

    return redirect(url_for("reservations"))


def generate_pdf_receipt(reservation, is_download=False):
    """
    Génère un reçu PDF pour une réservation donnée.
    Si is_download est True, gère les suffixes pour éviter les conflits de noms de fichiers.
    """
    base_filename = f"ticket_{reservation[5]}"  # Utilisez l'ID de la réservation pour le nom de base
    receipt_dir = "receipts"
    if not os.path.exists(receipt_dir):
        os.makedirs(receipt_dir)

    # Déterminer le nom du fichier
    if is_download:
        filename = find_unique_filename(base_filename, receipt_dir)
    else:
        filename = f"{base_filename}.pdf"

    filepath = os.path.join(receipt_dir, filename)

    # Calculer le tarif
    start_time = reservation[3]
    end_time = reservation[4]
    tariff = calculate_tariff(start_time, end_time)

    # Générer le PDF
    c = canvas.Canvas(filepath, pagesize=letter)
    c.drawString(100, 750, f"Reçu de Réservation - Parking")
    c.drawString(100, 720, f"ID de la Place: {reservation[5]}")  # ID de la réservation
    c.drawString(100, 700, f"Matricule: {reservation[1]}")
    c.drawString(100, 680, f"Zone: {reservation[2]}")
    c.drawString(100, 660, f"Début: {start_time}")
    c.drawString(100, 640, f"Fin: {end_time}")
    c.drawString(100, 620, f"Tarif: {tariff} DH")
    c.drawString(100, 600, f"Merci d'avoir réservé avec nous!")

    c.save()
    return filepath


def find_unique_filename(base_filename, directory):
    """
    Trouve un nom de fichier unique en ajoutant un suffixe incrémental si nécessaire.
    """
    filepath = os.path.join(directory, f"{base_filename}.pdf")
    counter = 1

    # Boucle pour trouver un nom unique
    while os.path.exists(filepath):
        filepath = os.path.join(directory, f"{base_filename} ({counter}).pdf")
        counter += 1

    return os.path.basename(filepath)


def calculate_tariff(start_time, end_time):
    """
    Calcule le tarif basé sur la durée entre start_time et end_time.
    """
    from datetime import datetime

    # Fonction pour parser différents formats de dates
    def parse_time(time_str):
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S']:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue
        raise ValueError(f"Format de date invalide : {time_str}")

    # Parser les dates
    start = parse_time(start_time)
    end = parse_time(end_time)
    duration = end - start

    # Conversion de la durée en minutes et heures
    total_minutes = duration.total_seconds() / 60
    total_hours = total_minutes / 60

    # Tarification
    if total_minutes <= 15:
        return 3  # 3 dh pour 15 minutes ou moins
    elif total_hours <= 1:
        return 15  # 15 dh pour jusqu'à 1 heure
    elif total_hours <= 5:
        return 35  # 35 dh pour jusqu'à 5 heures
    elif total_hours <= 24:
        return 50  # 50 dh pour plus de 5 heures et moins de 24 heures
    else:
        return 100  # 100 dh pour 1 jour ou plus



@app.route("/download_receipt/<int:reservation_id>")
def download_receipt(reservation_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Récupérer les détails de la réservation
    user_id = session["user_id"]
    reservations = get_user_reservations(user_id)
    reservation = next((res for res in reservations if res[0] == reservation_id), None)

    if reservation:
        # Générer un fichier unique pour le téléchargement
        filepath = generate_pdf_receipt(reservation, is_download=True)
        return send_file(filepath, as_attachment=True)
    else:
        flash("Réservation introuvable.", "error")
        return redirect(url_for("reservations"))




@app.template_filter('format_date')
def format_date(value, format='%d/%m/%Y %H:%M'):
    """
    Filtre personnalisé pour formater les dates.
    """
    try:
        date_obj = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        return date_obj.strftime(format)
    except ValueError:
        return value

def calculate_tariff(start_time, end_time):
    """
    Calcule le tarif basé sur la durée entre start_time et end_time.
    """
    # Fonction pour tenter différents formats
    def parse_time(time_str):
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S']:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue
        raise ValueError(f"Format de date invalide : {time_str}")
    
    # Parser les dates avec le bon format
    start = parse_time(start_time)
    end = parse_time(end_time)
    duration = end - start

    # Conversion de la durée en minutes et heures
    total_minutes = duration.total_seconds() / 60
    total_hours = total_minutes / 60

    # Tarification
    if total_minutes <= 15:
        return 3  # 3 dh pour 15 minutes ou moins
    elif total_hours <= 1:
        return 15  # 15 dh pour jusqu'à 1 heure
    elif total_hours <= 5:
        return 35  # 35 dh pour jusqu'à 5 heures
    elif total_hours <= 24:
        return 50  # 50 dh pour plus de 5 heures et moins de 24 heures
    else:
        return 100  # 100 dh pour 1 jour ou plus



if __name__ == "__main__":
    app.run(debug=True)
 