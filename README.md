# CarVistaHub

CarVistaHub is a Django-based car showroom management web application. It allows customers to explore vehicles, compare cars, manage wishlists, schedule test drives, and reserve vehicles through a Razorpay Test Mode payment workflow. It also provides dashboard functionality for customers and showroom managers.

## Features

### Customer Features
- User registration, login, and logout
- Browse car inventory with vehicle details, specifications, brands, and images
- Compare multiple vehicles
- Add and remove cars from a wishlist
- Schedule test-drive appointments
- Reserve vehicles through the car booking workflow
- Razorpay integration for car reservation payments (Test Mode)
- Customer dashboard
- Separate pages for vehicle reservations and test-drive appointments

### Manager Features
- Manager dashboard
- View vehicle reservation records
- Read-only access to customer vehicle reservation information

### Inventory
- Car catalogue containing 32 vehicles across 8 brands
- Vehicle data managed through Django models
- Public catalogue images stored in the media directory
- Inventory import through a custom Django management command

## Tech Stack

- Python 3
- Django
- SQLite
- HTML5, CSS3, JavaScript
- Bootstrap
- Razorpay Payment Gateway (Test Mode)
- python-decouple for environment-based configuration

## Project Structure

```text
CarVistaHub/
│
├── apps/
│   ├── accounts/
│   ├── cars/
│   ├── bookings/
│   ├── payments/
│   ├── interactions/
│   └── dashboard/
│
├── autohub/
│   ├── settings.py
│   ├── urls.py
│   └── ...
│
├── media/
│   └── cars/
│
├── static/
├── templates/
│
├── .env.example
├── .gitignore
├── ATTRIBUTION.md
├── requirements.txt
├── CarVistaHub_26_Car_Inventory_Research.xlsx
└── manage.py
```

## Local Setup

### 1. Clone the Repository

```powershell
git clone https://github.com/OmSoni739/CarVistaHub-Django-Car-Showroom.git
```

### 2. Go to the Project Directory

```powershell
cd CarVistaHub-Django-Car-Showroom
```

Make sure the terminal is in the directory containing `manage.py`.

### 3. Create a Virtual Environment

```powershell
python -m venv venv
```

### 4. Activate the Virtual Environment

**Windows PowerShell:**

```powershell
.\venv\Scripts\Activate.ps1
```

If PowerShell blocks script execution, use Command Prompt:

```cmd
venv\Scripts\activate.bat
```

### 5. Install Dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 6. Configure Environment Variables

Create a local `.env` file using the example file:

```powershell
Copy-Item .env.example .env
```

Open `.env` and configure the required values using the variable names provided in `.env.example`.


### 7. Apply Database Migrations

```powershell
python manage.py migrate
```

This creates and updates the local SQLite database using the project's migrations.

### 8. Create a Superuser (Optional)

To access the Django admin site, create an administrator account:

```powershell
python manage.py createsuperuser
```

Follow the prompts in the terminal.

### 9. Import Car Inventory

The repository includes the inventory research workbook:

`CarVistaHub_26_Car_Inventory_Research.xlsx`

To import the prepared vehicle inventory, run:

```powershell
python manage.py import_car_inventory
```

Run this command from the project root, after applying migrations. The command uses the project's inventory import logic and expected workbook/input location.

### 10. Run the Development Server

```powershell
python manage.py runserver
```

Open the application in your browser:

```text
http://127.0.0.1:8000/
```

## Default URLs

| Page | URL |
|---|---|
| Application | `http://127.0.0.1:8000/` |
| Django Admin | `http://127.0.0.1:8000/admin/` |

Other customer and manager pages are available through the application's navigation after signing in.

## Payment Integration

CarVistaHub uses **Razorpay Test Mode** for the car reservation payment workflow.

- Test Mode is intended for development and demonstration.
- Configure the required Razorpay test credentials through the local environment file.
- Do not place API keys directly in source code.
- Test-drive appointments are a separate workflow and do not require payment.
- This repository is not configured as a live payment service.

## Database and Media

- **Database:** SQLite (`db.sqlite3`) is created locally when migrations are applied.
- **Car images:** Public vehicle catalogue images are stored under `media/cars/`.
- **Private uploads and local database files:** These are not included in the public repository.
- **Image credits:** Refer to [`ATTRIBUTION.md`](ATTRIBUTION.md) for image attribution and licence details.

The original development database is intentionally excluded. A fresh clone starts with a new local database.

## Useful Django Commands

Check the project configuration:

```powershell
python manage.py check
```

Check whether model changes require migrations:

```powershell
python manage.py makemigrations --check --dry-run
```

Create migrations after making model changes:

```powershell
python manage.py makemigrations
```

Apply migrations:

```powershell
python manage.py migrate
```

Start the development server:

```powershell
python manage.py runserver
```

## Security Notes

- Keep `.env` files and real credentials private.
- Use a unique, strong Django `SECRET_KEY` from the environment.
- Do not use development fallback secrets in production.
- Set `DEBUG=False` and configure `ALLOWED_HOSTS` before deployment.
- Configure production-grade database, static-file, and media-file handling before hosting.
- Review payment and authentication settings before making the application publicly available.

## Future Improvements

- Deploy the application with production-ready Django settings.
- Add automated tests for authentication, bookings, and payment workflows.
- Improve vehicle search, filtering, and sorting.
- Further enhance responsive layouts and accessibility.
- Add production payment configuration and transaction monitoring.

## Author

**Om Soni**

- GitHub: [@OmSoni739](https://github.com/OmSoni739)
- Repository: [CarVistaHub-Django-Car-Showroom](https://github.com/OmSoni739/CarVistaHub-Django-Car-Showroom)

---

**CarVistaHub — Explore. Compare. Book.**

*Developed as an academic project.*
