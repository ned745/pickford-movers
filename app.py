import os, sys, sqlite3, secrets
from pathlib import Path
from functools import wraps
from datetime import datetime, timedelta
from io import BytesIO
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "instance" / "pickford.db"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("PICKFORD_SECRET_KEY") or "dev-only-change-this-secret-before-deployment"
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def connect_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with connect_db() as db:
        db.execute("CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS gallery (id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT, category TEXT, location TEXT, completed_date TEXT, image_filename TEXT NOT NULL, published INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)")
        db.execute("""CREATE TABLE IF NOT EXISTS quotes (
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
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS bookings (
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
            updated_at TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL COLLATE NOCASE,
            phone TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        booking_columns = {row["name"] for row in db.execute("PRAGMA table_info(bookings)").fetchall()}
        if "customer_id" not in booking_columns:
            db.execute("ALTER TABLE bookings ADD COLUMN customer_id INTEGER REFERENCES customers(id)")

init_db()

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin_login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# Public website
@app.route("/")
def home(): return render_template("index.html")
@app.route("/services")
def services(): return render_template("services.html")
@app.route("/about")
def about(): return render_template("about.html")
@app.route("/gallery")
def gallery():
    with connect_db() as db: projects = db.execute("SELECT * FROM gallery WHERE published=1 ORDER BY id DESC").fetchall()
    return render_template("gallery.html", projects=projects)
@app.route("/contact")
def contact(): return render_template("contact.html")
@app.route("/request-quote", methods=["GET", "POST"])
def request_quote():
    if request.method == "POST":
        fields = {key: request.form.get(key, "").strip() for key in ("name", "phone", "email", "service", "origin", "destination", "move_date", "notes")}
        if not all(fields[k] for k in ("name", "phone", "service", "origin", "destination")):
            flash("Please complete your name, phone, service, pickup and destination fields.", "error")
            return render_template("quote.html", form_data=fields), 400
        reference = "PM-" + secrets.token_hex(4).upper()
        now = datetime.now().isoformat(timespec="seconds")
        with connect_db() as db:
            db.execute("""INSERT INTO bookings (reference,full_name,phone,email,service,origin,destination,move_date,notes,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,'New request',?,?)""", (reference, fields["name"], fields["phone"], fields["email"], fields["service"], fields["origin"], fields["destination"], fields["move_date"], fields["notes"], now, now))
        return render_template("booking_received.html", reference=reference, customer_name=fields["name"])
    return render_template("quote.html", form_data={})

# Phase 5: customer accounts and booking tracking

def customer_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("customer_id"):
            return redirect(url_for("customer_login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper

@app.route("/customer/register", methods=["GET", "POST"])
def customer_register():
    if request.method == "POST":
        name=request.form.get("full_name","").strip(); email=request.form.get("email","").strip().lower()
        phone=request.form.get("phone","").strip(); password=request.form.get("password",""); confirm=request.form.get("confirm_password","")
        if not all([name,email,phone,password,confirm]): flash("Complete all fields to create your account.","error")
        elif len(password)<10: flash("Use a password with at least 10 characters.","error")
        elif password!=confirm: flash("The passwords do not match.","error")
        else:
            try:
                with connect_db() as db:
                    db.execute("INSERT INTO customers (full_name,email,phone,password_hash,created_at) VALUES (?,?,?,?,?)",(name,email,phone,generate_password_hash(password),datetime.now().isoformat(timespec="seconds")))
                    customer=db.execute("SELECT id FROM customers WHERE email=?",(email,)).fetchone()
                    db.execute("UPDATE bookings SET customer_id=? WHERE lower(email)=? AND phone=? AND customer_id IS NULL",(customer["id"],email,phone))
                flash("Account created. Sign in to view any matching bookings.","success"); return redirect(url_for("customer_login"))
            except sqlite3.IntegrityError: flash("An account with that email already exists. Please log in.","error")
    return render_template("customer/register.html")

@app.route("/customer/login", methods=["GET", "POST"])
def customer_login():
    if request.method == "POST":
        email=request.form.get("email","").strip().lower(); password=request.form.get("password","")
        with connect_db() as db: customer=db.execute("SELECT * FROM customers WHERE email=?",(email,)).fetchone()
        if customer and check_password_hash(customer["password_hash"],password):
            session.clear(); session["customer_id"]=customer["id"]; session["customer_name"]=customer["full_name"]
            return redirect(request.args.get("next") or url_for("customer_dashboard"))
        flash("Email or password is incorrect.","error")
    return render_template("customer/login.html")

@app.post("/customer/logout")
@customer_required
def customer_logout():
    session.clear(); flash("You have been logged out.","success"); return redirect(url_for("home"))

@app.route("/customer/dashboard")
@customer_required
def customer_dashboard():
    with connect_db() as db:
        bookings=db.execute("""SELECT b.*,
        (SELECT quote_number FROM quotes q WHERE q.booking_id=b.id ORDER BY q.id DESC LIMIT 1) quote_number,
        (SELECT total FROM quotes q WHERE q.booking_id=b.id ORDER BY q.id DESC LIMIT 1) quote_total
        FROM bookings b WHERE b.customer_id=? ORDER BY b.id DESC""",(session["customer_id"],)).fetchall()
    return render_template("customer/dashboard.html",bookings=bookings)

@app.route("/customer/bookings/<int:booking_id>")
@customer_required
def customer_booking_detail(booking_id):
    with connect_db() as db:
        booking=db.execute("SELECT * FROM bookings WHERE id=? AND customer_id=?",(booking_id,session["customer_id"])).fetchone()
        if not booking: abort(404)
        quote=db.execute("SELECT * FROM quotes WHERE booking_id=? ORDER BY id DESC LIMIT 1",(booking_id,)).fetchone()
    return render_template("customer/booking_detail.html",booking=booking,quote=quote,items=json.loads(quote["items_json"]) if quote else [])

# Admin authentication and dashboard
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_id"): return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with connect_db() as db: admin = db.execute("SELECT * FROM admins WHERE username=?", (username,)).fetchone()
        if admin and check_password_hash(admin["password_hash"], password):
            session.clear(); session["admin_id"] = admin["id"]; session["admin_username"] = admin["username"]
            return redirect(request.args.get("next") or url_for("admin_dashboard"))
        flash("The username or password is incorrect.", "error")
    return render_template("admin/login.html")

@app.post("/admin/logout")
@admin_required
def admin_logout():
    session.clear(); flash("You have been logged out.", "success"); return redirect(url_for("admin_login"))

@app.route("/admin")
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    with connect_db() as db:
        total = db.execute("SELECT COUNT(*) FROM gallery").fetchone()[0]
        published = db.execute("SELECT COUNT(*) FROM gallery WHERE published=1").fetchone()[0]
        drafts = total - published
        recent = db.execute("SELECT * FROM gallery ORDER BY id DESC LIMIT 5").fetchall()
        booking_total = db.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
        new_bookings = db.execute("SELECT COUNT(*) FROM bookings WHERE status='New request'").fetchone()[0]
        latest_bookings = db.execute("SELECT * FROM bookings ORDER BY id DESC LIMIT 5").fetchall()
    return render_template("admin/dashboard.html", total=total, published=published, drafts=drafts, recent=recent, booking_total=booking_total, new_bookings=new_bookings, latest_bookings=latest_bookings)

@app.route("/admin/gallery")
@admin_required
def admin_gallery():
    with connect_db() as db: projects = db.execute("SELECT * FROM gallery ORDER BY id DESC").fetchall()
    return render_template("admin/gallery.html", projects=projects)

@app.route("/admin/gallery/new", methods=["GET", "POST"])
@admin_required
def admin_gallery_new():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        image = request.files.get("image")
        if not title or not image or not image.filename:
            flash("Please add a project title and choose an image.", "error")
            return render_template("admin/gallery_form.html", project=None)
        if not allowed_file(image.filename):
            flash("Please upload JPG, JPEG, PNG, WEBP or GIF images only.", "error")
            return render_template("admin/gallery_form.html", project=None)
        safe_name = secure_filename(image.filename)
        ext = safe_name.rsplit(".", 1)[1].lower()
        filename = f"{secrets.token_hex(12)}.{ext}"
        image.save(UPLOAD_DIR / filename)
        published = 1 if request.form.get("published") == "on" else 0
        with connect_db() as db:
            db.execute("INSERT INTO gallery (title,description,category,location,completed_date,image_filename,published,created_at) VALUES (?,?,?,?,?,?,?,?)", (title, request.form.get("description", "").strip(), request.form.get("category", "").strip(), request.form.get("location", "").strip(), request.form.get("completed_date", ""), filename, published, datetime.now().isoformat(timespec="seconds")))
        flash("Project saved to the gallery.", "success")
        return redirect(url_for("admin_gallery"))
    return render_template("admin/gallery_form.html", project=None)

@app.post("/admin/gallery/<int:project_id>/toggle")
@admin_required
def admin_gallery_toggle(project_id):
    with connect_db() as db:
        item = db.execute("SELECT published FROM gallery WHERE id=?", (project_id,)).fetchone()
        if not item: abort(404)
        db.execute("UPDATE gallery SET published=? WHERE id=?", (0 if item["published"] else 1, project_id))
    flash("Gallery visibility updated.", "success"); return redirect(url_for("admin_gallery"))

@app.post("/admin/gallery/<int:project_id>/delete")
@admin_required
def admin_gallery_delete(project_id):
    with connect_db() as db:
        item = db.execute("SELECT image_filename FROM gallery WHERE id=?", (project_id,)).fetchone()
        if not item: abort(404)
        db.execute("DELETE FROM gallery WHERE id=?", (project_id,))
    try: (UPLOAD_DIR / item["image_filename"]).unlink(missing_ok=True)
    except OSError: pass
    flash("Project deleted.", "success"); return redirect(url_for("admin_gallery"))


BOOKING_STATUSES = ["New request", "Under review", "Awaiting quotation", "Quotation sent", "Awaiting approval", "Awaiting payment", "Confirmed", "Team assigned", "In progress", "Completed", "Cancelled"]

@app.route("/admin/bookings")
@admin_required
def admin_bookings():
    status = request.args.get("status", "").strip()
    with connect_db() as db:
        if status in BOOKING_STATUSES:
            bookings = db.execute("SELECT * FROM bookings WHERE status=? ORDER BY id DESC", (status,)).fetchall()
        else:
            status = ""
            bookings = db.execute("SELECT * FROM bookings ORDER BY id DESC").fetchall()
    return render_template("admin/bookings.html", bookings=bookings, statuses=BOOKING_STATUSES, selected_status=status)

@app.route("/admin/bookings/<int:booking_id>", methods=["GET", "POST"])
@admin_required
def admin_booking_detail(booking_id):
    if request.method == "POST":
        status = request.form.get("status", "")
        admin_notes = request.form.get("admin_notes", "").strip()
        if status not in BOOKING_STATUSES:
            abort(400)
        with connect_db() as db:
            exists = db.execute("SELECT id FROM bookings WHERE id=?", (booking_id,)).fetchone()
            if not exists: abort(404)
            db.execute("UPDATE bookings SET status=?, admin_notes=?, updated_at=? WHERE id=?", (status, admin_notes, datetime.now().isoformat(timespec="seconds"), booking_id))
        flash("Enquiry record updated. This does not send a message to the customer or confirm payment.", "success")
        return redirect(url_for("admin_booking_detail", booking_id=booking_id))
    with connect_db() as db:
        booking = db.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
    if not booking: abort(404)
    return render_template("admin/booking_detail.html", booking=booking, statuses=BOOKING_STATUSES)


# Phase 4: quotations and payment administration
import json

@app.route("/admin/bookings/<int:booking_id>/quote", methods=["GET", "POST"])
@admin_required
def admin_quote_new(booking_id):
    with connect_db() as db:
        booking = db.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
    if not booking: abort(404)
    if request.method == "POST":
        descriptions = request.form.getlist("description[]")
        quantities = request.form.getlist("quantity[]")
        prices = request.form.getlist("unit_price[]")
        items=[]
        try:
            for desc, qty, price in zip(descriptions, quantities, prices):
                desc=desc.strip(); q=float(qty); price=float(price)
                if desc and q > 0 and price >= 0:
                    items.append({"description":desc,"quantity":q,"unit_price":price,"amount":round(q*price,2)})
            discount=float(request.form.get("discount", "0") or 0)
        except ValueError:
            flash("Enter valid numeric quantities, prices and discount.", "error")
            return render_template("admin/quote_form.html", booking=booking)
        subtotal=round(sum(i["amount"] for i in items),2)
        if not items or discount < 0 or discount > subtotal:
            flash("Add at least one valid line item. Discount cannot exceed subtotal.", "error")
            return render_template("admin/quote_form.html", booking=booking)
        total=round(subtotal-discount,2)
        now=datetime.now(); valid=(now+timedelta(days=7)).date().isoformat()
        token=secrets.token_urlsafe(24); quote_number="PMQ-"+secrets.token_hex(4).upper()
        terms=request.form.get("terms", "").strip()
        with connect_db() as db:
            db.execute("INSERT INTO quotes (booking_id,token,quote_number,items_json,subtotal,discount,total,terms,valid_until,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,'Sent',?)",
                       (booking_id,token,quote_number,json.dumps(items),subtotal,discount,total,terms,valid,now.isoformat(timespec="seconds")))
            db.execute("UPDATE bookings SET status='Quotation sent',updated_at=? WHERE id=?",(now.isoformat(timespec="seconds"),booking_id))
        flash("Quotation created. Copy the customer link and share it with them.", "success")
        return redirect(url_for("admin_quote_detail", quote_id=get_quote_id(quote_number)))
    return render_template("admin/quote_form.html", booking=booking)

def get_quote_id(number):
    with connect_db() as db:
        row=db.execute("SELECT id FROM quotes WHERE quote_number=?",(number,)).fetchone()
    return row["id"]

@app.route("/admin/quotes/<int:quote_id>")
@admin_required
def admin_quote_detail(quote_id):
    with connect_db() as db:
        q=db.execute("SELECT q.*,b.reference,b.full_name,b.phone,b.email,b.service FROM quotes q JOIN bookings b ON b.id=q.booking_id WHERE q.id=?",(quote_id,)).fetchone()
    if not q: abort(404)
    return render_template("admin/quote_detail.html", quote=q, items=json.loads(q["items_json"]))

@app.post("/admin/quotes/<int:quote_id>/payment")
@admin_required
def admin_quote_payment(quote_id):
    instructions=request.form.get("payment_instructions","").strip()
    reference=request.form.get("payment_reference","").strip()
    action=request.form.get("payment_action")
    if action not in {"instructions","verify","reset"}: abort(400)
    with connect_db() as db:
        q=db.execute("SELECT booking_id FROM quotes WHERE id=?",(quote_id,)).fetchone()
        if not q: abort(404)
        if action=="instructions":
            db.execute("UPDATE quotes SET payment_instructions=? WHERE id=?",(instructions,quote_id))
            msg="Payment instructions saved. Share the customer quote link manually."
        elif action=="verify":
            if not reference:
                flash("Enter the payment reference before verifying.","error")
                return redirect(url_for("admin_quote_detail",quote_id=quote_id))
            db.execute("UPDATE quotes SET payment_status='Verified',payment_reference=? WHERE id=?",(reference,quote_id))
            db.execute("UPDATE bookings SET status='Confirmed',updated_at=? WHERE id=?",(datetime.now().isoformat(timespec="seconds"),q["booking_id"]))
            msg="Payment marked verified by admin; booking status updated to Confirmed."
        else:
            db.execute("UPDATE quotes SET payment_status='Not recorded',payment_reference=NULL WHERE id=?",(quote_id,))
            msg="Payment record reset."
    flash(msg,"success"); return redirect(url_for("admin_quote_detail",quote_id=quote_id))

@app.route("/quote/<token>", methods=["GET","POST"])
def customer_quote(token):
    with connect_db() as db:
        q=db.execute("SELECT q.*,b.reference,b.full_name,b.service,b.origin,b.destination FROM quotes q JOIN bookings b ON b.id=q.booking_id WHERE q.token=?",(token,)).fetchone()
    if not q: abort(404)
    if request.method=="POST":
        choice=request.form.get("choice")
        if choice not in {"Accepted","Declined","Revision requested"}: abort(400)
        with connect_db() as db:
            db.execute("UPDATE quotes SET status=? WHERE id=?",(choice,q["id"]))
            if choice=="Accepted":
                db.execute("UPDATE bookings SET status='Awaiting payment',updated_at=? WHERE id=?",(datetime.now().isoformat(timespec="seconds"),q["booking_id"]))
        flash("Your response has been recorded. The Pickford Movers team will follow up.","success")
        return redirect(url_for("customer_quote",token=token))
    return render_template("customer_quote.html",quote=q,items=json.loads(q["items_json"]))

@app.route("/quote/<token>/pdf")
def customer_quote_pdf(token):
    with connect_db() as db:
        q=db.execute("SELECT q.*,b.reference,b.full_name,b.phone,b.email,b.service,b.origin,b.destination FROM quotes q JOIN bookings b ON b.id=q.booking_id WHERE q.token=?",(token,)).fetchone()
    if not q: abort(404)
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError:
        return "PDF support is not installed. Run: py -m pip install -r requirements.txt", 500
    output=BytesIO(); c=canvas.Canvas(output,pagesize=A4); width,height=A4; y=height-55
    c.setFillColorRGB(.06,.11,.20); c.rect(0,height-105,width,105,fill=1,stroke=0)
    c.setFillColorRGB(.84,.68,.40); c.setFont("Helvetica-Bold",20); c.drawString(48,height-55,"PICKFORD MOVERS")
    c.setFillColorRGB(1,1,1); c.setFont("Helvetica",10); c.drawString(48,height-75,"Moving People. Moving Possibilities.")
    y=height-140; c.setFillColorRGB(.08,.12,.19); c.setFont("Helvetica-Bold",16); c.drawString(48,y,"QUOTATION")
    y-=28; c.setFont("Helvetica",10)
    for line in [f"Quote: {q['quote_number']}    Booking: {q['reference']}",f"Customer: {q['full_name']}",f"Service: {q['service']}",f"Route: {q['origin']} to {q['destination']}",f"Valid until: {q['valid_until']}"]:
        c.drawString(48,y,line); y-=18
    y-=12; c.setFont("Helvetica-Bold",10); c.drawString(48,y,"DESCRIPTION"); c.drawRightString(390,y,"QTY"); c.drawRightString(470,y,"UNIT (KES)"); c.drawRightString(550,y,"AMOUNT")
    y-=12; c.line(48,y,550,y); y-=20; c.setFont("Helvetica",9)
    for item in json.loads(q["items_json"]):
        if y<100: c.showPage(); y=height-60
        desc=item['description'][:48]; c.drawString(48,y,desc); c.drawRightString(390,y,str(item['quantity'])); c.drawRightString(470,y,f"{item['unit_price']:,.2f}"); c.drawRightString(550,y,f"{item['amount']:,.2f}"); y-=18
    y-=10; c.line(350,y,550,y); y-=20; c.setFont("Helvetica",10); c.drawRightString(470,y,"Subtotal:"); c.drawRightString(550,y,f"KES {q['subtotal']:,.2f}"); y-=18
    c.drawRightString(470,y,"Discount:"); c.drawRightString(550,y,f"KES {q['discount']:,.2f}"); y-=22
    c.setFont("Helvetica-Bold",12); c.drawRightString(470,y,"TOTAL:"); c.drawRightString(550,y,f"KES {q['total']:,.2f}")
    y-=38; c.setFont("Helvetica",9); c.drawString(48,y,"Terms: "+(q["terms"] or "Please contact Pickford Movers for clarification."))
    c.save(); output.seek(0)
    from flask import send_file
    return send_file(output,as_attachment=True,download_name=f"{q['quote_number']}.pdf",mimetype="application/pdf")

@app.errorhandler(413)
def too_large(_error):
    flash("That image is too large. Maximum upload size is 8 MB.", "error")
    return redirect(url_for("admin_gallery_new"))

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "create-admin":
        import getpass
        username = input("Choose admin username: ").strip()
        password = getpass.getpass("Choose admin password (minimum 12 characters): ")
        if not username or len(password) < 12:
            print("Username is required and password must be at least 12 characters."); raise SystemExit(1)
        try:
            with connect_db() as db:
                db.execute("INSERT INTO admins (username,password_hash,created_at) VALUES (?,?,?)", (username, generate_password_hash(password), datetime.now().isoformat(timespec="seconds")))
            print("Admin account created. Start the website with: py app.py")
        except sqlite3.IntegrityError: print("That username already exists.")
    else:
        app.run(debug=True)
