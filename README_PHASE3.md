PICKFORD MOVERS — PHASE 3: BOOKING ENQUIRIES

This is a complete replacement project folder based on Phase 2. It adds a working local SQLite enquiry workflow.

INSTALL
1. Back up your existing project folder first.
2. Extract this ZIP. Open the inner Pickford_Movers_Phase1 folder in VS Code (the one containing app.py and requirements.txt).
3. Keep your existing venv if desired. In the VS Code terminal run: py -m pip install -r requirements.txt
4. Your existing admin account/database is stored in instance/pickford.db. To preserve it, copy your existing instance folder into this extracted project before starting. If you do not copy it, run py app.py create-admin to create a fresh admin account.
5. Run: py app.py
6. Public quote form: http://127.0.0.1:5000/request-quote
7. Admin enquiries: http://127.0.0.1:5000/admin/bookings

FEATURES
- Customer enquiries are saved to SQLite and assigned a PM reference.
- Admin can list/filter enquiries, inspect details, set workflow status and write internal notes.
- Status changes are internal only. Email/WhatsApp notifications, quotations, payment processing and live tracking are not connected in this phase.
- A submitted enquiry is not a confirmed booking.

SECURITY BEFORE PUBLIC DEPLOYMENT
Set PICKFORD_SECRET_KEY to a long random secret, disable Flask debug mode, add CSRF protection and HTTPS, validate uploads more rigorously, configure backups, and use PostgreSQL for production.
