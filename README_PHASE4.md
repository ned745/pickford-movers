# PICKFORD MOVERS — Phase 4: Quotations & Payment Administration

This package builds on Phase 3 and adds:
- Admin-created quotations with multiple line items, quantities, unit prices and discounts.
- Automatic KES totals and a 7-day validity date.
- A private, unguessable customer quotation link to review, download a PDF, accept, decline or request a revision.
- Admin-managed payment instructions and an explicit manual payment verification action.
- Booking status changes to Awaiting payment when a customer accepts, and Confirmed only when an admin verifies payment.

## Install / update
1. Extract this ZIP.
2. Open the inner `Pickford_Movers_Phase1` folder in VS Code.
3. In the terminal, run `py -m pip install -r requirements.txt`.
4. If this is a fresh folder, create an admin with `py app.py create-admin`.
5. Start with `py app.py`.

For a fresh Phase 4 test installation, create a new folder and use the included code. The database is created automatically in `instance/pickford.db`. If migrating from Phase 3, stop the server and copy the Phase 3 `instance` folder and `static/uploads` folder into this Phase 4 project before starting it. Keep a backup first.

## Workflow
1. Sign in at `/admin/login`.
2. Open Booking enquiries and select a booking.
3. Select Create quotation, add one or more line items, and submit.
4. On the quotation detail page, copy the customer link and share it manually.
5. The customer can review the quote, download its PDF and record a response.
6. Add payment instructions in the admin page and share the same quote link again.
7. Verify receipt of funds independently, enter the payment reference, and click Verify payment & confirm booking.

## Important limitations
- Email and WhatsApp delivery are not connected; the admin copies and sends the link manually.
- Payment is not processed by this application. Never mark a payment verified until you have independently confirmed receipt.
- A customer response does not automatically confirm a booking. Only the admin verification action changes the booking to Confirmed.
- Use a strong secret key and a production WSGI server before public deployment. The Flask debug server is for local development only.
