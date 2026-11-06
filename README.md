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
- Dedicated dashboard to access and manage showroom activities.
- View and manage customer test-drive appointment requests.
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

### 1. Go to the Project Directory

```powershell
cd CarVistaHub-Django-Car-Showroom
```

### 2. Create a Virtual Environment

```powershell
python -m venv venv
```

### 3. Activate the Virtual Environment

**Windows PowerShell:**

```powershell
.\venv\Scripts\Activate.ps1
```

If PowerShell blocks script execution, use Command Prompt:

```cmd
venv\Scripts\activate.bat
```

### 4. Install Dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Configure Environment Variables

Create a local `.env` file using the example file:

```powershell
Copy-Item .env.example .env
```

### 6. Apply Database Migrations

```powershell
python manage.py migrate
```

### 7. Import Car Inventory

The repository includes the inventory research workbook:

`CarVistaHub_32_Car_Inventory_Research.xlsx`

To import the prepared vehicle inventory, run:

```powershell
python manage.py import_car_inventory
```

### 8. Run the Development Server

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
| Home Page | `http://127.0.0.1:8000/` |
| Car Inventory | `http://127.0.0.1:8000/cars` |
| Login | `http://127.0.0.1:8000/accounts/login/` |
| Register | `http://127.0.0.1:8000/accounts/register/` |
| Compare Cars | `http://127.0.0.1:8000/compare/` |
| Wishlist | `http://127.0.0.1:8000/wishlist/` |

Other customer and manager pages are available through the application's navigation after signing in.

## Payment Integration

CarVistaHub uses **Razorpay Test Mode** for the car reservation payment workflow.

- Test Mode is intended for development and demonstration.
- Configure the required Razorpay test credentials through the local environment file.
- Test-drive appointments are a separate workflow and do not require payment.
- This repository is not configured as a live payment service.

## Database and Media

- **Database:** SQLite (`db.sqlite3`) is created locally when migrations are applied.
- **Car images:** Public vehicle catalogue images are stored under `media/cars/`.
- **Private uploads and local database files:** These are not included in the public repository.
- **Image credits:** Refer to [`ATTRIBUTION.md`](ATTRIBUTION.md) for image attribution and licence details.
