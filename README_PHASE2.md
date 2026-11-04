# Pickford Movers — Phase 2 Admin Dashboard

This update adds a private admin login, dashboard and project gallery manager. It keeps the public Flask website and adds a local SQLite database.

## 1. Replace your project files
Extract this ZIP and copy its contents into your existing `Pickford_Movers_Phase1` project folder, choosing **Replace** when Windows asks. Keep your existing `venv` folder.

## 2. Create your first admin account
Open VS Code in the project folder. In the terminal, activate your existing environment if it is not already active:

```powershell
.\venv\Scripts\Activate.ps1
```

Then run this once:

```powershell
py app.py create-admin
```

Choose an admin username and a strong password of at least 12 characters. The password is stored as a secure hash, not plain text. Keep it private.

## 3. Start the website
```powershell
py app.py
```

Public website: `http://127.0.0.1:5000`
Admin login: `http://127.0.0.1:5000/admin/login`

## Gallery manager
From the dashboard choose **Project gallery** then **Add project**. You can upload a photo (JPG, JPEG, PNG, WEBP or GIF, maximum 8 MB), add details, save it as a draft or publish it. Only published projects appear on the public gallery. You can unpublish or delete projects later.

## Important security notes
- This is for local development/testing. Before public deployment, set a long random `PICKFORD_SECRET_KEY` environment variable and turn off Flask debug mode.
- The database is created in `instance/pickford.db`; uploaded photos are in `static/uploads/`. Back up both.
- Use a strong unique admin password. Do not share your admin login.
- Publish only genuine project photos you have permission to share. Avoid exposing faces, private home details, documents or number plates without consent.
- Booking management, quotations, payment verification, customer accounts, AI chat and WhatsApp/email automation are not implemented yet.
