import os
import sys
import sqlite3
import secrets
import smtplib
import json
import psycopg2

from psycopg2.extras import DictCursor
from email.message import EmailMessage
from dotenv import load_dotenv
from pathlib import Path
from functools import wraps
from datetime import datetime, timedelta
from io import BytesIO

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, abort, jsonify, send_file
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "instance" / "pickford.db"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}

app = Flask(__name__)
app.config["SECRET_KEY"] = (
    os.environ.get("PICKFORD_SECRET_KEY")
    or "dev-only-change-this-secret-before-deployment"
)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# ============================================================
# DATABASE CONNECTION
# ============================================================

def using_postgresql():
    return bool(os.environ.get("DATABASE_URL"))


class PostgreSQLDatabase:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, parameters=()):
        sql = sql.replace("?", "%s")
        cursor = self.connection.cursor(cursor_factory=DictCursor)
        cursor.execute(sql, parameters)
        return cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if exc_type is None:
                self.connection.commit()
            else:
                self.connection.rollback()
        finally:
            self.connection.close()


def connect_db():
    database_url = os.environ.get("DATABASE_URL")

    if database_url:
        if database_url.startswith("postgres://"):
            database_url = database_url.replace(
                "postgres://", "postgresql://", 1
            )

        connection = psycopg2.connect(database_url)
        return PostgreSQLDatabase(connection)

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():

    if using_postgresql():

        with connect_db() as db:

            db.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    id BIGSERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    id BIGSERIAL PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            db.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS
                idx_customers_email_lower
                ON customers (LOWER(email))
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS gallery (
                    id BIGSERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    category TEXT,
                    location TEXT,
                    completed_date TEXT,
                    image_filename TEXT NOT NULL,
                    published INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS bookings (
                    id BIGSERIAL PRIMARY KEY,
                    reference TEXT UNIQUE NOT NULL,
                    full_name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    email TEXT,
                    service TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    move_date TEXT,
                    notes TEXT,
                    status TEXT NOT NULL DEFAULT 'New request',
                    admin_notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    customer_id BIGINT REFERENCES customers(id)
                )
            """)

            db.execute("""
                ALTER TABLE bookings
                ADD COLUMN IF NOT EXISTS customer_id BIGINT
                REFERENCES customers(id)
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS quotes (
                    id BIGSERIAL PRIMARY KEY,
                    booking_id BIGINT NOT NULL REFERENCES bookings(id),
                    token TEXT UNIQUE NOT NULL,
                    quote_number TEXT UNIQUE NOT NULL,
                    items_json TEXT NOT NULL,
                    subtotal DOUBLE PRECISION NOT NULL,
                    discount DOUBLE PRECISION NOT NULL DEFAULT 0,
                    total DOUBLE PRECISION NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'KES',
                    terms TEXT,
                    valid_until TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Sent',
                    payment_instructions TEXT,
                    payment_status TEXT NOT NULL DEFAULT 'Not recorded',
                    payment_reference TEXT,
                    created_at TEXT NOT NULL
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS assistant_messages (
                    id BIGSERIAL PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id BIGSERIAL PRIMARY KEY,
                    customer_id BIGINT NOT NULL REFERENCES customers(id),
                    sender TEXT NOT NULL
                        CHECK(sender IN ('customer', 'admin')),
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    is_read INTEGER NOT NULL DEFAULT 0
                )
            """)

            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_customer
                ON messages(customer_id, id)
            """)

    else:

        with connect_db() as db:

            db.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    id INTEGER PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    phone TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS gallery (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    category TEXT,
                    location TEXT,
                    completed_date TEXT,
                    image_filename TEXT NOT NULL,
                    published INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reference TEXT UNIQUE NOT NULL,
                    full_name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    email TEXT,
                    service TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    move_date TEXT,
                    notes TEXT,
                    status TEXT NOT NULL DEFAULT 'New request',
                    admin_notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    customer_id INTEGER
                )
            """)

            booking_columns = [
                row["name"]
                for row in db.execute(
                    "PRAGMA table_info(bookings)"
                ).fetchall()
            ]

            if "customer_id" not in booking_columns:
                db.execute(
                    "ALTER TABLE bookings ADD COLUMN customer_id INTEGER"
                )

            db.execute("""
                CREATE TABLE IF NOT EXISTS quotes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    booking_id INTEGER NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    quote_number TEXT UNIQUE NOT NULL,
                    items_json TEXT NOT NULL,
                    subtotal REAL NOT NULL,
                    discount REAL NOT NULL DEFAULT 0,
                    total REAL NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'KES',
                    terms TEXT,
                    valid_until TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Sent',
                    payment_instructions TEXT,
                    payment_status TEXT NOT NULL DEFAULT 'Not recorded',
                    payment_reference TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(booking_id) REFERENCES bookings(id)
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS assistant_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER NOT NULL,
                    sender TEXT NOT NULL
                        CHECK(sender IN ('customer', 'admin')),
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    is_read INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(customer_id) REFERENCES customers(id)
                )
            """)

            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_customer
                ON messages(customer_id, id)
            """)


init_db()


# ============================================================
# EMAIL NOTIFICATIONS
# ============================================================

def send_notification_email(recipient, subject, body):

    username = os.getenv("MAIL_USERNAME")
    password = os.getenv("MAIL_PASSWORD")
    server = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    port = int(os.getenv("MAIL_PORT", "587"))

    if not username or not password or not recipient:
        print("Email notification skipped: configuration incomplete.")
        return False

    email = EmailMessage()
    email["From"] = username
    email["To"] = recipient
    email["Subject"] = subject
    email.set_content(body)

    try:
        with smtplib.SMTP(server, port, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(email)

        print("Email notification sent successfully.")
        return True

    except Exception as error:
        print(f"Email notification failed: {type(error).__name__}")
        return False


# ============================================================
# AUTHENTICATION HELPERS
# ============================================================

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(
                url_for("admin_login", next=request.path)
            )
        return fn(*args, **kwargs)
    return wrapper


def customer_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("customer_id"):
            flash(
                "Please sign in to view your customer account.",
                "error"
            )
            return redirect(
                url_for("customer_login", next=request.path)
            )
        return fn(*args, **kwargs)
    return wrapper


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


# ============================================================
# PHASE 6: GUIDED WEBSITE ASSISTANT
# ============================================================

@app.route("/assistant/chat", methods=["POST"])
def assistant_chat():

    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()[:1000]

    if not message:
        return jsonify({
            "reply": "Please type a question so I can help."
        }), 400

    conversation_id = session.get("assistant_conversation")

    if not conversation_id:
        conversation_id = secrets.token_urlsafe(18)
        session["assistant_conversation"] = conversation_id

    now = datetime.now().isoformat(timespec="seconds")

    with connect_db() as db:
        db.execute("""
            INSERT INTO assistant_messages
            (conversation_id, sender, message, created_at)
            VALUES (?, ?, ?, ?)
        """, (conversation_id, "customer", message, now))

    q = message.lower()

    if any(w in q for w in (
        "price", "cost", "how much", "quote", "quotation"
    )):
        reply = (
            "Moving costs depend on the service, route, volume, "
            "access and any special handling. I cannot make up a "
            "price, but you can submit your details for a "
            "personalised quotation."
        )
        action = {
            "label": "Request a quotation",
            "url": url_for("request_quote")
        }

    elif any(w in q for w in (
        "track", "status", "booking", "reference", "my move"
    )):
        reply = (
            "You can check your relocation requests and updates "
            "in the customer portal. Sign in to view bookings "
            "linked to your account."
        )
        action = {
            "label": "Open customer portal",
            "url": url_for("customer_login")
        }

    elif any(w in q for w in (
        "pay", "payment", "mpesa", "deposit"
    )):
        reply = (
            "Payment instructions are provided by the Pickford "
            "Movers team after your quotation is issued and "
            "accepted. Payments are verified manually by an "
            "administrator. Please do not send money to an "
            "unverified number."
        )
        action = {
            "label": "Contact support on WhatsApp",
            "url": "https://wa.me/254726775604?text=Hello%20Pickford%20Movers%2C%20I%20need%20help%20with%20payment."
        }

    elif any(w in q for w in (
        "international", "abroad", "overseas", "country"
    )):
        reply = (
            "We handle international relocation enquiries. "
            "Tell us your origin, destination country, preferred "
            "date and what you plan to move so the team can "
            "review the requirements."
        )
        action = {
            "label": "Start an enquiry",
            "url": url_for("request_quote")
        }

    elif any(w in q for w in (
        "storage", "warehouse", "store"
    )):
        reply = (
            "Pickford Movers offers storage and warehousing "
            "enquiries. Share the items, approximate volume, "
            "location and expected storage period for a "
            "tailored response."
        )
        action = {
            "label": "Request a storage quote",
            "url": url_for("request_quote")
        }

    elif any(w in q for w in (
        "vehicle", "car", "motorcycle", "bike"
    )):
        reply = (
            "We accept vehicle transportation enquiries. "
            "Please provide the vehicle type, collection point, "
            "destination and preferred transport date."
        )
        action = {
            "label": "Vehicle transport enquiry",
            "url": url_for("request_quote")
        }

    elif any(w in q for w in (
        "service", "move", "moving", "relocation", "office",
        "house", "furniture", "packing", "cargo", "freight"
    )):
        reply = (
            "Our services include household and office relocation, "
            "local and long-distance moving, international relocation, "
            "furniture dismantling and installation, packing and "
            "unpacking, storage and warehousing, vehicle transportation, "
            "and cargo and freight logistics."
        )
        action = {
            "label": "Explore all services",
            "url": url_for("services")
        }

    elif any(w in q for w in (
        "human", "person", "agent", "staff", "talk", "contact", "help"
    )):
        reply = (
            "Of course. Our support team can assist you directly "
            "on WhatsApp or by phone at 0726775604."
        )
        action = {
            "label": "Chat with support",
            "url": "https://wa.me/254726775604?text=Hello%20Pickford%20Movers%2C%20I%20need%20assistance."
        }

    else:
        reply = (
            "I can help with services, quotations, booking tracking, "
            "storage, vehicle transport and payment guidance. For a "
            "question that needs a team member, contact us on "
            "WhatsApp or call 0726775604."
        )
        action = {
            "label": "Speak to our team",
            "url": "https://wa.me/254726775604?text=Hello%20Pickford%20Movers%2C%20I%20have%20a%20question."
        }

    with connect_db() as db:
        db.execute("""
            INSERT INTO assistant_messages
            (conversation_id, sender, message, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            conversation_id,
            "assistant",
            reply,
            datetime.now().isoformat(timespec="seconds")
        ))

    return jsonify({"reply": reply, "action": action})


# ============================================================
# PUBLIC WEBSITE
# ============================================================

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/services")
def services():
    return render_template("services.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/gallery")
def gallery():
    with connect_db() as db:
        projects = db.execute("""
            SELECT * FROM gallery
            WHERE published=1
            ORDER BY id DESC
        """).fetchall()

    return render_template("gallery.html", projects=projects)


@app.route("/contact")
def contact():
    return render_template("contact.html")


@app.route("/request-quote", methods=["GET", "POST"])
def request_quote():

    if request.method == "POST":

        fields = {
            key: request.form.get(key, "").strip()
            for key in (
                "name", "phone", "email", "service",
                "origin", "destination", "move_date", "notes"
            )
        }

        if not all(fields[k] for k in (
            "name", "phone", "service", "origin", "destination"
        )):
            flash(
                "Please complete your name, phone, service, "
                "pickup and destination fields.",
                "error"
            )
            return render_template(
                "quote.html", form_data=fields
            ), 400

        reference = "PM-" + secrets.token_hex(4).upper()
        now = datetime.now().isoformat(timespec="seconds")

        with connect_db() as db:
            db.execute("""
                INSERT INTO bookings (
                    reference, full_name, phone, email, service,
                    origin, destination, move_date, notes, status,
                    created_at, updated_at, customer_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                        'New request', ?, ?, ?)
            """, (
                reference,
                fields["name"],
                fields["phone"],
                fields["email"],
                fields["service"],
                fields["origin"],
                fields["destination"],
                fields["move_date"],
                fields["notes"],
                now,
                now,
                session.get("customer_id")
            ))

        return render_template(
            "booking_received.html",
            reference=reference,
            customer_name=fields["name"]
        )

    return render_template("quote.html", form_data={})


# ============================================================
# CUSTOMER REGISTRATION
# ============================================================

@app.route("/customer/register", methods=["GET", "POST"])
def customer_register():

    if session.get("customer_id"):
        return redirect(url_for("customer_dashboard"))

    if request.method == "POST":

        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not all([name, email, phone, password, confirm]):
            flash("Complete every field to create your account.", "error")

        elif password != confirm:
            flash("The passwords do not match.", "error")

        elif len(password) < 8:
            flash("Use a password with at least 8 characters.", "error")

        else:
            try:
                with connect_db() as db:

                    if using_postgresql():
                        cur = db.execute("""
                            INSERT INTO customers (
                                full_name, email, phone,
                                password_hash, created_at
                            )
                            VALUES (?, ?, ?, ?, ?)
                            RETURNING id
                        """, (
                            name,
                            email,
                            phone,
                            generate_password_hash(password),
                            datetime.now().isoformat(timespec="seconds")
                        ))

                        customer_id = cur.fetchone()["id"]

                    else:
                        cur = db.execute("""
                            INSERT INTO customers (
                                full_name, email, phone,
                                password_hash, created_at
                            )
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            name,
                            email,
                            phone,
                            generate_password_hash(password),
                            datetime.now().isoformat(timespec="seconds")
                        ))

                        customer_id = cur.lastrowid

                    db.execute("""
                        UPDATE bookings
                        SET customer_id=?
                        WHERE lower(email)=?
                        AND phone=?
                        AND customer_id IS NULL
                    """, (customer_id, email, phone))

                session["customer_id"] = customer_id
                session["customer_name"] = name

                flash("Your account is ready.", "success")
                return redirect(url_for("customer_dashboard"))

            except (sqlite3.IntegrityError, psycopg2.IntegrityError):
                flash(
                    "An account with that email already exists. "
                    "Please sign in.",
                    "error"
                )

    return render_template("customer/register.html")


# ============================================================
# CUSTOMER LOGIN AND LOGOUT
# ============================================================

@app.route("/customer/login", methods=["GET", "POST"])
def customer_login():

    if session.get("customer_id"):
        return redirect(url_for("customer_dashboard"))

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        with connect_db() as db:
            customer = db.execute("""
                SELECT * FROM customers
                WHERE lower(email)=?
            """, (email,)).fetchone()

        if customer and check_password_hash(
            customer["password_hash"], password
        ):
            session["customer_id"] = customer["id"]
            session["customer_name"] = customer["full_name"]

            destination = request.args.get("next", "")

            if not destination.startswith("/customer/"):
                destination = url_for("customer_dashboard")

            return redirect(destination)

        flash("Invalid email or password.", "error")

    return render_template("customer/login.html")


@app.route("/customer/logout", methods=["POST"])
def customer_logout():

    session.pop("customer_id", None)
    session.pop("customer_name", None)

    flash("You have signed out.", "success")
    return redirect(url_for("home"))


# ============================================================
# CUSTOMER DASHBOARD
# ============================================================

@app.route("/customer/dashboard")
@customer_required
def customer_dashboard():

    with connect_db() as db:
        bookings = db.execute("""
            SELECT b.*,
                (SELECT q.token FROM quotes q
                 WHERE q.booking_id=b.id
                 ORDER BY q.id DESC LIMIT 1) AS quote_token,

                (SELECT q.quote_number FROM quotes q
                 WHERE q.booking_id=b.id
                 ORDER BY q.id DESC LIMIT 1) AS quote_number,

                (SELECT q.total FROM quotes q
                 WHERE q.booking_id=b.id
                 ORDER BY q.id DESC LIMIT 1) AS quote_total,

                (SELECT q.currency FROM quotes q
                 WHERE q.booking_id=b.id
                 ORDER BY q.id DESC LIMIT 1) AS quote_currency,

                (SELECT q.status FROM quotes q
                 WHERE q.booking_id=b.id
                 ORDER BY q.id DESC LIMIT 1) AS quote_status,

                (SELECT q.payment_status FROM quotes q
                 WHERE q.booking_id=b.id
                 ORDER BY q.id DESC LIMIT 1) AS payment_status

            FROM bookings b
            WHERE b.customer_id=?
            ORDER BY b.id DESC
        """, (session["customer_id"],)).fetchall()

    return render_template(
        "customer/dashboard.html",
        bookings=bookings
    )


@app.route("/customer/bookings/<int:booking_id>")
@customer_required
def customer_booking_detail(booking_id):

    with connect_db() as db:

        booking = db.execute("""
            SELECT * FROM bookings
            WHERE id=? AND customer_id=?
        """, (
            booking_id,
            session["customer_id"]
        )).fetchone()

        if not booking:
            abort(404)

        quote = db.execute("""
            SELECT * FROM quotes
            WHERE booking_id=?
            ORDER BY id DESC
            LIMIT 1
        """, (booking_id,)).fetchone()

    return render_template(
        "customer/booking_detail.html",
        booking=booking,
        quote=quote
    )


# ============================================================
# CUSTOMER MESSAGING
# ============================================================

@app.route("/customer/messages", methods=["GET", "POST"])
@customer_required
def customer_messages():

    customer_id = session["customer_id"]

    if request.method == "POST":

        message = request.form.get("message", "").strip()

        if not message:
            flash("Please enter a message.", "error")

        elif len(message) > 2000:
            flash(
                "Your message is too long. Maximum is 2000 characters.",
                "error"
            )

        else:
            now = datetime.now().isoformat(timespec="seconds")

            with connect_db() as db:
                db.execute("""
                    INSERT INTO messages
                    (customer_id, sender, message, created_at)
                    VALUES (?, 'customer', ?, ?)
                """, (customer_id, message, now))

            flash("Your message has been sent successfully.", "success")

        return redirect(url_for("customer_messages"))

    with connect_db() as db:

        db.execute("""
            UPDATE messages
            SET is_read=1
            WHERE customer_id=?
            AND sender='admin'
        """, (customer_id,))

        messages = db.execute("""
            SELECT * FROM messages
            WHERE customer_id=?
            ORDER BY id ASC
        """, (customer_id,)).fetchall()

    return render_template(
        "customer/messages.html",
        messages=messages
    )


# ============================================================
# ADMIN LOGIN
# ============================================================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if session.get("admin_id"):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        with connect_db() as db:
            admin = db.execute("""
                SELECT * FROM admins
                WHERE username=?
            """, (username,)).fetchone()

        if admin and check_password_hash(
            admin["password_hash"], password
        ):
            session.clear()
            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]

            return redirect(
                request.args.get("next")
                or url_for("admin_dashboard")
            )

        flash("The username or password is incorrect.", "error")

    return render_template("admin/login.html")


@app.post("/admin/logout")
@admin_required
def admin_logout():

    session.clear()
    flash("You have been logged out.", "success")

    return redirect(url_for("admin_login"))


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():

    with connect_db() as db:

        total = db.execute(
            "SELECT COUNT(*) FROM gallery"
        ).fetchone()[0]

        published = db.execute("""
            SELECT COUNT(*) FROM gallery
            WHERE published=1
        """).fetchone()[0]

        drafts = total - published

        recent = db.execute("""
            SELECT * FROM gallery
            ORDER BY id DESC LIMIT 5
        """).fetchall()

        booking_total = db.execute(
            "SELECT COUNT(*) FROM bookings"
        ).fetchone()[0]

        new_bookings = db.execute("""
            SELECT COUNT(*) FROM bookings
            WHERE status='New request'
        """).fetchone()[0]

        latest_bookings = db.execute("""
            SELECT * FROM bookings
            ORDER BY id DESC LIMIT 5
        """).fetchall()

    return render_template(
        "admin/dashboard.html",
        total=total,
        published=published,
        drafts=drafts,
        recent=recent,
        booking_total=booking_total,
        new_bookings=new_bookings,
        latest_bookings=latest_bookings
    )


# ============================================================
# ADMIN MESSAGING INBOX
# ============================================================

@app.route("/admin/messages")
@admin_required
def admin_messages():

    with connect_db() as db:

        conversations = db.execute("""
            SELECT
                c.id AS customer_id,
                c.full_name,
                c.email,
                c.phone,
                MAX(m.id) AS last_message_id,

                SUM(
                    CASE
                        WHEN m.sender='customer' AND m.is_read=0
                        THEN 1 ELSE 0
                    END
                ) AS unread_count

            FROM customers c
            JOIN messages m ON m.customer_id=c.id
            GROUP BY c.id
            ORDER BY last_message_id DESC
        """).fetchall()

        conversations = [
            dict(row) | {
                "last_message": db.execute("""
                    SELECT message FROM messages
                    WHERE id=?
                """, (row["last_message_id"],)).fetchone()["message"]
            }
            for row in conversations
        ]

    return render_template(
        "admin/messages.html",
        conversations=conversations
    )


@app.route(
    "/admin/messages/<int:customer_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_message_thread(customer_id):

    with connect_db() as db:

        customer = db.execute("""
            SELECT * FROM customers
            WHERE id=?
        """, (customer_id,)).fetchone()

        if not customer:
            abort(404)

        if request.method == "POST":

            message = request.form.get("message", "").strip()

            if not message:
                flash("Please enter a reply.", "error")

            elif len(message) > 2000:
                flash(
                    "Reply is too long. Maximum is 2000 characters.",
                    "error"
                )

            else:
                now = datetime.now().isoformat(timespec="seconds")

                db.execute("""
                    INSERT INTO messages
                    (customer_id, sender, message, created_at)
                    VALUES (?, 'admin', ?, ?)
                """, (customer_id, message, now))

                flash("Your reply has been sent.", "success")

                return redirect(url_for(
                    "admin_message_thread",
                    customer_id=customer_id
                ))

        db.execute("""
            UPDATE messages
            SET is_read=1
            WHERE customer_id=?
            AND sender='customer'
        """, (customer_id,))

        messages = db.execute("""
            SELECT * FROM messages
            WHERE customer_id=?
            ORDER BY id ASC
        """, (customer_id,)).fetchall()

    return render_template(
        "admin/message_thread.html",
        customer=customer,
        messages=messages
    )


# ============================================================
# ADMIN GALLERY
# ============================================================

@app.route("/admin/gallery")
@admin_required
def admin_gallery():

    with connect_db() as db:
        projects = db.execute("""
            SELECT * FROM gallery
            ORDER BY id DESC
        """).fetchall()

    return render_template(
        "admin/gallery.html",
        projects=projects
    )


@app.route("/admin/gallery/new", methods=["GET", "POST"])
@admin_required
def admin_gallery_new():

    if request.method == "POST":

        title = request.form.get("title", "").strip()
        image = request.files.get("image")

        if not title or not image or not image.filename:
            flash(
                "Please add a project title and choose an image.",
                "error"
            )
            return render_template(
                "admin/gallery_form.html",
                project=None
            )

        if not allowed_file(image.filename):
            flash(
                "Please upload JPG, JPEG, PNG, WEBP or GIF images only.",
                "error"
            )
            return render_template(
                "admin/gallery_form.html",
                project=None
            )

        safe_name = secure_filename(image.filename)
        ext = safe_name.rsplit(".", 1)[1].lower()
        filename = f"{secrets.token_hex(12)}.{ext}"

        image.save(UPLOAD_DIR / filename)

        published = (
            1 if request.form.get("published") == "on" else 0
        )

        with connect_db() as db:
            db.execute("""
                INSERT INTO gallery (
                    title, description, category, location,
                    completed_date, image_filename,
                    published, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                title,
                request.form.get("description", "").strip(),
                request.form.get("category", "").strip(),
                request.form.get("location", "").strip(),
                request.form.get("completed_date", ""),
                filename,
                published,
                datetime.now().isoformat(timespec="seconds")
            ))

        flash("Project saved to the gallery.", "success")
        return redirect(url_for("admin_gallery"))

    return render_template(
        "admin/gallery_form.html",
        project=None
    )


@app.post("/admin/gallery/<int:project_id>/toggle")
@admin_required
def admin_gallery_toggle(project_id):

    with connect_db() as db:

        item = db.execute("""
            SELECT published FROM gallery
            WHERE id=?
        """, (project_id,)).fetchone()

        if not item:
            abort(404)

        db.execute("""
            UPDATE gallery
            SET published=?
            WHERE id=?
        """, (
            0 if item["published"] else 1,
            project_id
        ))

    flash("Gallery visibility updated.", "success")
    return redirect(url_for("admin_gallery"))


@app.post("/admin/gallery/<int:project_id>/delete")
@admin_required
def admin_gallery_delete(project_id):

    with connect_db() as db:

        item = db.execute("""
            SELECT image_filename FROM gallery
            WHERE id=?
        """, (project_id,)).fetchone()

        if not item:
            abort(404)

        db.execute("""
            DELETE FROM gallery
            WHERE id=?
        """, (project_id,))

    try:
        (UPLOAD_DIR / item["image_filename"]).unlink(
            missing_ok=True
        )
    except OSError:
        pass

    flash("Project deleted.", "success")
    return redirect(url_for("admin_gallery"))


# ============================================================
# ADMIN BOOKING MANAGEMENT
# ============================================================

BOOKING_STATUSES = [
    "New request",
    "Under review",
    "Awaiting quotation",
    "Quotation sent",
    "Awaiting approval",
    "Awaiting payment",
    "Confirmed",
    "Team assigned",
    "In progress",
    "Completed",
    "Cancelled"
]


@app.route("/admin/bookings")
@admin_required
def admin_bookings():

    status = request.args.get("status", "").strip()

    with connect_db() as db:

        if status in BOOKING_STATUSES:
            bookings = db.execute("""
                SELECT * FROM bookings
                WHERE status=?
                ORDER BY id DESC
            """, (status,)).fetchall()

        else:
            status = ""
            bookings = db.execute("""
                SELECT * FROM bookings
                ORDER BY id DESC
            """).fetchall()

    return render_template(
        "admin/bookings.html",
        bookings=bookings,
        statuses=BOOKING_STATUSES,
        selected_status=status
    )


@app.route(
    "/admin/bookings/<int:booking_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_booking_detail(booking_id):

    if request.method == "POST":

        status = request.form.get("status", "")
        admin_notes = request.form.get(
            "admin_notes", ""
        ).strip()

        if status not in BOOKING_STATUSES:
            abort(400)

        with connect_db() as db:

            exists = db.execute("""
                SELECT id FROM bookings
                WHERE id=?
            """, (booking_id,)).fetchone()

            if not exists:
                abort(404)

            db.execute("""
                UPDATE bookings
                SET status=?, admin_notes=?, updated_at=?
                WHERE id=?
            """, (
                status,
                admin_notes,
                datetime.now().isoformat(timespec="seconds"),
                booking_id
            ))

        flash(
            "Enquiry record updated. This does not send a "
            "message to the customer or confirm payment.",
            "success"
        )

        return redirect(url_for(
            "admin_booking_detail",
            booking_id=booking_id
        ))

    with connect_db() as db:
        booking = db.execute("""
            SELECT * FROM bookings
            WHERE id=?
        """, (booking_id,)).fetchone()

    if not booking:
        abort(404)

    return render_template(
        "admin/booking_detail.html",
        booking=booking,
        statuses=BOOKING_STATUSES
    )


# ============================================================
# PHASE 4: QUOTATIONS AND PAYMENTS
# ============================================================

@app.route(
    "/admin/bookings/<int:booking_id>/quote",
    methods=["GET", "POST"]
)
@admin_required
def admin_quote_new(booking_id):

    with connect_db() as db:
        booking = db.execute("""
            SELECT * FROM bookings
            WHERE id=?
        """, (booking_id,)).fetchone()

    if not booking:
        abort(404)

    if request.method == "POST":

        descriptions = request.form.getlist("description[]")
        quantities = request.form.getlist("quantity[]")
        prices = request.form.getlist("unit_price[]")

        items = []

        try:
            for desc, qty, price in zip(
                descriptions, quantities, prices
            ):
                desc = desc.strip()
                q = float(qty)
                price = float(price)

                if desc and q > 0 and price >= 0:
                    items.append({
                        "description": desc,
                        "quantity": q,
                        "unit_price": price,
                        "amount": round(q * price, 2)
                    })

            discount = float(
                request.form.get("discount", "0") or 0
            )

        except ValueError:
            flash(
                "Enter valid numeric quantities, prices and discount.",
                "error"
            )
            return render_template(
                "admin/quote_form.html",
                booking=booking
            )

        subtotal = round(
            sum(item["amount"] for item in items), 2
        )

        if not items or discount < 0 or discount > subtotal:
            flash(
                "Add at least one valid line item. "
                "Discount cannot exceed subtotal.",
                "error"
            )
            return render_template(
                "admin/quote_form.html",
                booking=booking
            )

        total = round(subtotal - discount, 2)

        now = datetime.now()
        valid = (now + timedelta(days=7)).date().isoformat()

        token = secrets.token_urlsafe(24)
        quote_number = "PMQ-" + secrets.token_hex(4).upper()
        terms = request.form.get("terms", "").strip()

        with connect_db() as db:

            db.execute("""
                INSERT INTO quotes (
                    booking_id, token, quote_number, items_json,
                    subtotal, discount, total, terms,
                    valid_until, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                        'Sent', ?)
            """, (
                booking_id,
                token,
                quote_number,
                json.dumps(items),
                subtotal,
                discount,
                total,
                terms,
                valid,
                now.isoformat(timespec="seconds")
            ))

            db.execute("""
                UPDATE bookings
                SET status='Quotation sent', updated_at=?
                WHERE id=?
            """, (
                now.isoformat(timespec="seconds"),
                booking_id
            ))

        flash(
            "Quotation created. Copy the customer link "
            "and share it with them.",
            "success"
        )

        return redirect(url_for(
            "admin_quote_detail",
            quote_id=get_quote_id(quote_number)
        ))

    return render_template(
        "admin/quote_form.html",
        booking=booking
    )


def get_quote_id(number):

    with connect_db() as db:
        row = db.execute("""
            SELECT id FROM quotes
            WHERE quote_number=?
        """, (number,)).fetchone()

    return row["id"]


@app.route("/admin/quotes/<int:quote_id>")
@admin_required
def admin_quote_detail(quote_id):

    with connect_db() as db:
        q = db.execute("""
            SELECT
                q.*,
                b.reference,
                b.full_name,
                b.phone,
                b.email,
                b.service
            FROM quotes q
            JOIN bookings b ON b.id=q.booking_id
            WHERE q.id=?
        """, (quote_id,)).fetchone()

    if not q:
        abort(404)

    return render_template(
        "admin/quote_detail.html",
        quote=q,
        items=json.loads(q["items_json"])
    )


@app.post("/admin/quotes/<int:quote_id>/payment")
@admin_required
def admin_quote_payment(quote_id):

    instructions = request.form.get(
        "payment_instructions", ""
    ).strip()

    reference = request.form.get(
        "payment_reference", ""
    ).strip()

    action = request.form.get("payment_action")

    if action not in {"instructions", "verify", "reset"}:
        abort(400)

    with connect_db() as db:

        q = db.execute("""
            SELECT booking_id FROM quotes
            WHERE id=?
        """, (quote_id,)).fetchone()

        if not q:
            abort(404)

        if action == "instructions":

            db.execute("""
                UPDATE quotes
                SET payment_instructions=?
                WHERE id=?
            """, (instructions, quote_id))

            msg = (
                "Payment instructions saved. "
                "Share the customer quote link manually."
            )

        elif action == "verify":

            if not reference:
                flash(
                    "Enter the payment reference before verifying.",
                    "error"
                )
                return redirect(url_for(
                    "admin_quote_detail",
                    quote_id=quote_id
                ))

            db.execute("""
                UPDATE quotes
                SET payment_status='Verified',
                    payment_reference=?
                WHERE id=?
            """, (reference, quote_id))

            db.execute("""
                UPDATE bookings
                SET status='Confirmed', updated_at=?
                WHERE id=?
            """, (
                datetime.now().isoformat(timespec="seconds"),
                q["booking_id"]
            ))

            msg = (
                "Payment marked verified by admin; "
                "booking status updated to Confirmed."
            )

        else:

            db.execute("""
                UPDATE quotes
                SET payment_status='Not recorded',
                    payment_reference=NULL
                WHERE id=?
            """, (quote_id,))

            msg = "Payment record reset."

    flash(msg, "success")

    return redirect(url_for(
        "admin_quote_detail",
        quote_id=quote_id
    ))


@app.route("/quote/<token>", methods=["GET", "POST"])
def customer_quote(token):

    with connect_db() as db:
        q = db.execute("""
            SELECT
                q.*,
                b.reference,
                b.full_name,
                b.service,
                b.origin,
                b.destination
            FROM quotes q
            JOIN bookings b ON b.id=q.booking_id
            WHERE q.token=?
        """, (token,)).fetchone()

    if not q:
        abort(404)

    if request.method == "POST":

        choice = request.form.get("choice")

        if choice not in {
            "Accepted", "Declined", "Revision requested"
        }:
            abort(400)

        with connect_db() as db:

            db.execute("""
                UPDATE quotes
                SET status=?
                WHERE id=?
            """, (choice, q["id"]))

            if choice == "Accepted":
                db.execute("""
                    UPDATE bookings
                    SET status='Awaiting payment', updated_at=?
                    WHERE id=?
                """, (
                    datetime.now().isoformat(timespec="seconds"),
                    q["booking_id"]
                ))

        flash(
            "Your response has been recorded. "
            "The Pickford Movers team will follow up.",
            "success"
        )

        return redirect(url_for(
            "customer_quote",
            token=token
        ))

    return render_template(
        "customer_quote.html",
        quote=q,
        items=json.loads(q["items_json"])
    )


# ============================================================
# CUSTOMER QUOTATION PDF
# ============================================================

@app.route("/quote/<token>/pdf")
def customer_quote_pdf(token):

    with connect_db() as db:
        q = db.execute("""
            SELECT
                q.*,
                b.reference,
                b.full_name,
                b.phone,
                b.email,
                b.service,
                b.origin,
                b.destination
            FROM quotes q
            JOIN bookings b ON b.id=q.booking_id
            WHERE q.token=?
        """, (token,)).fetchone()

    if not q:
        abort(404)

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

    except ImportError:
        return (
            "PDF support is not installed. "
            "Run: py -m pip install -r requirements.txt",
            500
        )

    output = BytesIO()
    c = canvas.Canvas(output, pagesize=A4)

    width, height = A4
    y = height - 55

    c.setFillColorRGB(.06, .11, .20)
    c.rect(0, height - 105, width, 105, fill=1, stroke=0)

    c.setFillColorRGB(.84, .68, .40)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(48, height - 55, "PICKFORD MOVERS")

    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica", 10)
    c.drawString(
        48, height - 75,
        "Moving People. Moving Possibilities."
    )

    y = height - 140

    c.setFillColorRGB(.08, .12, .19)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(48, y, "QUOTATION")

    y -= 28
    c.setFont("Helvetica", 10)

    for line in [
        f"Quote: {q['quote_number']}    Booking: {q['reference']}",
        f"Customer: {q['full_name']}",
        f"Service: {q['service']}",
        f"Route: {q['origin']} to {q['destination']}",
        f"Valid until: {q['valid_until']}"
    ]:
        c.drawString(48, y, line)
        y -= 18

    y -= 12

    c.setFont("Helvetica-Bold", 10)
    c.drawString(48, y, "DESCRIPTION")
    c.drawRightString(390, y, "QTY")
    c.drawRightString(470, y, "UNIT (KES)")
    c.drawRightString(550, y, "AMOUNT")

    y -= 12
    c.line(48, y, 550, y)
    y -= 20

    c.setFont("Helvetica", 9)

    for item in json.loads(q["items_json"]):

        if y < 100:
            c.showPage()
            y = height - 60

        desc = item["description"][:48]

        c.drawString(48, y, desc)
        c.drawRightString(390, y, str(item["quantity"]))
        c.drawRightString(
            470, y,
            f"{item['unit_price']:,.2f}"
        )
        c.drawRightString(
            550, y,
            f"{item['amount']:,.2f}"
        )

        y -= 18

    y -= 10
    c.line(350, y, 550, y)
    y -= 20

    c.setFont("Helvetica", 10)

    c.drawRightString(470, y, "Subtotal:")
    c.drawRightString(
        550, y,
        f"KES {q['subtotal']:,.2f}"
    )

    y -= 18

    c.drawRightString(470, y, "Discount:")
    c.drawRightString(
        550, y,
        f"KES {q['discount']:,.2f}"
    )

    y -= 22

    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(470, y, "TOTAL:")
    c.drawRightString(
        550, y,
        f"KES {q['total']:,.2f}"
    )

    y -= 38

    c.setFont("Helvetica", 9)
    c.drawString(
        48, y,
        "Terms: " + (
            q["terms"]
            or "Please contact Pickford Movers for clarification."
        )
    )

    c.save()
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name=f"{q['quote_number']}.pdf",
        mimetype="application/pdf"
    )


# ============================================================
# FILE UPLOAD ERROR HANDLER
# ============================================================

@app.errorhandler(413)
def too_large(_error):

    flash(
        "That image is too large. Maximum upload size is 8 MB.",
        "error"
    )

    return redirect(url_for("admin_gallery_new"))


# ============================================================
# ADMIN ACCOUNT CREATION AND APPLICATION START
# ============================================================

if __name__ == "__main__":

    if len(sys.argv) > 1 and sys.argv[1] == "create-admin":

        import getpass

        username = input("Choose admin username: ").strip()

        password = getpass.getpass(
            "Choose admin password (minimum 12 characters): "
        )

        if not username or len(password) < 12:
            print(
                "Username is required and password must "
                "be at least 12 characters."
            )
            raise SystemExit(1)

        try:

            with connect_db() as db:
                db.execute("""
                    INSERT INTO admins (
                        username, password_hash, created_at
                    )
                    VALUES (?, ?, ?)
                """, (
                    username,
                    generate_password_hash(password),
                    datetime.now().isoformat(timespec="seconds")
                ))

            print("Admin account created.")
            print("Start the website with: py app.py")

        except (sqlite3.IntegrityError, psycopg2.IntegrityError):
            print("That username already exists.")

    else:
        app.run(debug=True)