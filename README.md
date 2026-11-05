::: {align="center"}
# CarVistaHub

### A Django-Based Car Showroom Management Platform

A web application for exploring and managing car inventory, comparing
vehicles, saving favourites, scheduling test drives, and reserving cars
through a secure payment workflow.

**Built with Python · Django · SQLite · HTML · CSS · JavaScript ·
Bootstrap**
:::

------------------------------------------------------------------------

## 📌 Overview

**CarVistaHub** is a full-stack car showroom management website
developed using the Django framework. It brings essential showroom
operations together in one platform, with dedicated experiences for
customers and showroom managers.

Customers can browse available vehicles, compare specifications, add
cars to their wishlist, schedule test drives, and make car reservations.
Managers can access dashboard features to oversee showroom activity and
review vehicle reservation records.

The project was developed as an academic full-stack web development
project, with an emphasis on Django's Model--View--Template (MVT)
architecture, database operations, authentication, and practical
frontend integration.

## ✨ Key Features

### Customer Features

-   **User Authentication** -- Register, log in, and access a customer
    account.
-   **Car Inventory** -- Browse vehicles with details, specifications,
    brands, and images.
-   **Vehicle Comparison** -- Compare selected cars to evaluate their
    features.
-   **Wishlist** -- Save favourite vehicles for later.
-   **Test Drive Booking** -- Schedule test-drive appointments.
-   **Car Reservation** -- Reserve a vehicle through the online booking
    workflow.
-   **Online Payment** -- Razorpay integration configured for Test Mode.
-   **Customer Dashboard** -- Access vehicle reservations and test-drive
    appointments.

### Manager Features

-   **Manager Dashboard** -- Access showroom management information.
-   **Vehicle Reservation Records** -- Review customer vehicle
    reservation details through a read-only view.

## 🧰 Technology Stack

  Area                Technology
  ------------------- --------------------------------------------------
  Backend             Python, Django
  Frontend            HTML5, CSS3, JavaScript, Bootstrap
  Database            SQLite
  Authentication      Django Authentication
  Payment Gateway     Razorpay (Test Mode)
  Configuration       python-decouple
  Development Tools   Visual Studio Code / compatible IDE, Git, GitHub

## 🏗️ Project Structure

``` text
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
│   └── Django project configuration
│
├── media/
│   └── cars/                 # Public car catalogue images
│
├── static/                   # CSS, JavaScript and static assets
├── templates/                # Django HTML templates
│
├── .env.example              # Environment variable template
├── .gitignore
├── ATTRIBUTION.md            # Image credits and licence information
├── requirements.txt
└── manage.py
```

> The local SQLite database, environment file, private customer uploads,
> and development backups are intentionally excluded from the
> repository.

## ⚙️ Getting Started

Follow these steps to run CarVistaHub on your local machine.

### 1. Clone the Repository

``` bash
git clone https://github.com/OmSoni739/CarVistaHub-Django-Car-Showroom.git
```

### 2. Open the Project Folder

``` bash
cd CarVistaHub-Django-Car-Showroom
```

### 3. Create a Virtual Environment

``` bash
python -m venv venv
```

### 4. Activate the Virtual Environment

**Windows PowerShell:**

``` powershell
.\venv\Scripts\Activate.ps1
```

If PowerShell blocks script execution, you can use Command Prompt
instead:

``` cmd
venv\Scripts\activate.bat
```

### 5. Install Dependencies

``` bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 6. Configure Environment Variables

Create your local `.env` file from the provided example:

**Windows PowerShell:**

``` powershell
Copy-Item .env.example .env
```

Open `.env` and enter your own local configuration values. Follow the
variable names and format in `.env.example`.

**Important:** Never commit your `.env` file or publish real Django
secret keys, Razorpay credentials, passwords, or other private values.

### 7. Apply Database Migrations

``` bash
python manage.py migrate
```

### 8. Create an Admin Account

``` bash
python manage.py createsuperuser
```

Follow the prompts to create your Django administrator account.

### 9. Run the Development Server

``` bash
python manage.py runserver
```

Open the following address in your browser:

``` text
http://127.0.0.1:8000/
```

## 🗃️ Car Inventory Data

The repository includes the `CarVistaHub_26_Car_Inventory_Research.xlsx`
workbook used during the vehicle inventory preparation process.

The original development database is not included in this repository. A
fresh setup creates a new local SQLite database when migrations are
applied. If you want to populate the catalogue, use the project's car
inventory import management command:

``` bash
python manage.py import_car_inventory
```

Run the command from the project root. Review the command implementation
and workbook requirements if your local setup needs additional input or
configuration.

## 💳 Payment Integration

CarVistaHub integrates **Razorpay in Test Mode** for the car reservation
payment workflow.

-   Test Mode is intended for development and demonstration.
-   Test credentials must be configured locally through environment
    variables.
-   Test Drive bookings are separate from paid car reservations.
-   The project is not configured as a live payment service.

Do not add live payment credentials to source code or commit them to
GitHub.

## 🔐 Security and Configuration

-   Sensitive environment files and local database files are excluded
    using `.gitignore`.
-   `.env.example` provides a template without real credentials.
-   Private customer uploads and local backups are not part of the
    public source repository.
-   Public vehicle catalogue images are included with attribution
    details in [`ATTRIBUTION.md`](ATTRIBUTION.md).

Before deploying this project, configure a strong, unique Django
`SECRET_KEY`, set `DEBUG=False`, configure `ALLOWED_HOSTS`, use
production-grade database and static/media storage settings, and review
all security settings and credentials. Do not use development fallback
secrets in production.

## 🧠 What I Learned

Working on CarVistaHub provided practical experience with:

-   Building a web application using Django's MVT architecture.
-   Designing Django models and managing database migrations.
-   Implementing user authentication and role-based access.
-   Connecting frontend templates with backend views.
-   Handling vehicle inventory and image uploads.
-   Building booking, wishlist, and comparison workflows.
-   Integrating a payment gateway in Test Mode.
-   Organising a multi-app Django project.
-   Using Git and GitHub for source-code version control.

## 🚀 Future Improvements

Potential areas for future development include:

-   Production deployment with secure environment configuration.
-   Improved search, filtering, and sorting for vehicle inventory.
-   Enhanced mobile responsiveness and accessibility.
-   Automated testing for core customer and manager workflows.
-   Production-ready payment configuration and transaction monitoring.

## 👨‍💻 Author

**Om Soni**

-   GitHub: [@OmSoni739](https://github.com/OmSoni739)

------------------------------------------------------------------------

::: {align="center"}
**CarVistaHub --- Explore. Compare. Book.**

*Developed as an academic project.*
:::
