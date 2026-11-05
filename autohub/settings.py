"""
Django settings for AutoHub project.
Generated for Phase 1 architecture setup.
Compatible with Django 5.x and Python 3.12+
"""

import os
from pathlib import Path
import sys
from decouple import config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Add 'apps' directory to Python path for clean app imports
sys.path.insert(0, str(BASE_DIR / 'apps'))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='django-insecure-autohub-default-dev-key-2026')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='127.0.0.1,localhost').split(',')


# Application definition

INSTALLED_APPS = [
    # Default Django Apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-Party Libraries
    'rest_framework',

    # AutoHub Custom Application Modules (6 Approved Apps)
    'apps.accounts',
    'apps.cars',
    'apps.bookings',
    'apps.payments',
    'apps.interactions',
    'apps.dashboard',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'autohub.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.bookings.context_processors.customer_notifications',
                'apps.interactions.context_processors.wishlist_data',
            ],
        },
    },
]

WSGI_APPLICATION = 'autohub.wsgi.application'


# Database Configuration
# Primary: MySQL Database using environment variables
# Fallback: SQLite for local developer setup if USE_SQLITE is enabled in .env

# Enable PyMySQL driver for MySQL compatibility
try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    pass

USE_SQLITE = config('USE_SQLITE', default=True, cast=bool)

if USE_SQLITE:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': config('DB_ENGINE', default='django.db.backends.mysql'),
            'NAME': config('DB_NAME', default='autohub_db'),
            'USER': config('DB_USER', default='root'),
            'PASSWORD': config('DB_PASSWORD', default='root'),
            'HOST': config('DB_HOST', default='127.0.0.1'),
            'PORT': config('DB_PORT', default='3306'),
            'OPTIONS': {
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
                'charset': 'utf8mb4',
            },
        }
    }


# Custom User Model Support
AUTH_USER_MODEL = 'accounts.User'


# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Kolkata'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
STATIC_ROOT = BASE_DIR / 'staticfiles'


# Media files (User Uploads, Car Images, License Uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Authentication Settings & Redirects
AUTHENTICATION_BACKENDS = [
    'apps.accounts.backends.EmailOrUsernameModelBackend',
    'django.contrib.auth.backends.ModelBackend',
]

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'cars:home'
LOGOUT_REDIRECT_URL = 'cars:home'


# Razorpay Payment Gateway Credentials (Loaded from environment variables)
RAZORPAY_KEY_ID = config('RAZORPAY_KEY_ID', default='')
RAZORPAY_KEY_SECRET = config('RAZORPAY_KEY_SECRET', default='')


# ==============================================================================
# Phase 2: Session & Cookie Configuration
# ==============================================================================
# Database-backed session engine
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# Standard session lifetime: 2 weeks (1,209,600 seconds)
SESSION_COOKIE_AGE = 1209600

# Prevent client-side JavaScript access to session cookie (mitigates XSS)
SESSION_COOKIE_HTTPONLY = True

# SameSite attribute for session cookie to protect against CSRF
SESSION_COOKIE_SAMESITE = 'Lax'

# Default session expiry: False (persistent until SESSION_COOKIE_AGE)
# Per-session expiry is dynamically set in login_view based on Remember Me
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# SameSite attribute for CSRF cookie
CSRF_COOKIE_SAMESITE = 'Lax'

# Secure Cookies: Only transmitted over HTTPS in production (disabled in local HTTP development)
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=not DEBUG, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=not DEBUG, cast=bool)

# Cross-Origin Opener Policy (COOP):
# Standard Django 4.0+ defaults to 'same-origin', which prevents payment gateways
# (e.g. Razorpay Standard Checkout Netbanking & 3DS bank popups) from opening their
# redirect URLs in Chromium browsers (Edge, Chrome), leaving popup windows on 'about:blank'.
# 'same-origin-allow-popups' isolates the top document while permitting outgoing bank redirects.
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin-allow-popups'


