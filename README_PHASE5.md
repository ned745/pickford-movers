# Pickford Movers — Phase 5: Customer Portal & Booking Tracking

## Keep Phase 4 safe
This is a separate test copy. Do not overwrite your working Phase 4 folder.

## Start the app
1. Extract this ZIP.
2. Open the extracted `Pickford_Movers_Phase1` folder in VS Code.
3. Open Terminal > New Terminal.
4. Run `py -m pip install -r requirements.txt`
5. Run `py app.py`
6. Visit `http://127.0.0.1:5000`.

## Customer portal
- Register at `/customer/register`.
- Use the same email AND phone number as an existing booking to link it.
- Sign in at `/customer/login`.
- View bookings at `/customer/dashboard`.

## Admin account
This separate test copy has its own database. If you need an admin here, run `py app.py create-admin` and create a strong password of at least 12 characters. Your Phase 4 admin account and records remain in the Phase 4 folder.

## Important limitations
Account linking currently matches exact email and phone together; email/SMS verification is not yet implemented, so treat this as a local pilot. Customers can view only linked bookings. Admins remain responsible for status changes and payment verification. Automated notifications, online payments and GPS tracking are not included. Before public deployment, configure a strong `PICKFORD_SECRET_KEY`, disable debug mode, and use HTTPS.
