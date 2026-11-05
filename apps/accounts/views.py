from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib import messages
from django.conf import settings
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods
from .forms import UserLoginForm, UserRegistrationForm


def login_view(request):
    """
    Handles user login supporting authentication with username or email,
    'Remember Me' session duration, and secure redirect handling.
    """
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    next_url = request.GET.get('next') or request.POST.get('next') or ''

    if request.method == 'POST':
        form = UserLoginForm(data=request.POST, request=request)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            remember_me = form.cleaned_data.get('remember_me')
            if remember_me:
                request.session.set_expiry(1209600)  # 2 weeks
            else:
                request.session.set_expiry(0)  # Browser close

            user_display_name = user.first_name or user.username
            messages.success(request, f"Welcome back, {user_display_name}!")

            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure()
            ):
                return redirect(next_url)

            return redirect(settings.LOGIN_REDIRECT_URL)
        else:
            messages.error(request, "Unable to sign in. Please verify your credentials.")
    else:
        form = UserLoginForm(request=request)

    context = {
        'form': form,
        'next': next_url,
    }
    return render(request, 'accounts/login.html', context)


def register_view(request):
    """
    Handles public customer registration with comprehensive input validation.
    New accounts are registered strictly as standard CUSTOMER accounts.
    Preserves redirect target via ?next= parameter to return customer to their selected car.
    """
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    next_url = request.GET.get('next') or request.POST.get('next') or ''

    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(
                request,
                user,
                backend='apps.accounts.backends.EmailOrUsernameModelBackend'
            )
            user_display_name = user.first_name or user.username
            messages.success(
                request,
                f"Welcome to CarVistaHub, {user_display_name}! Your account has been created."
            )
            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure()
            ):
                return redirect(next_url)

            return redirect(settings.LOGIN_REDIRECT_URL)
        else:
            messages.error(request, "Please correct the highlighted errors below.")
    else:
        form = UserRegistrationForm()

    context = {
        'form': form,
        'next': next_url,
    }
    return render(request, 'accounts/register.html', context)


@require_http_methods(["GET", "POST"])
def logout_view(request):
    """
    Signs out the authenticated user and clears session state.
    Supports secure POST submissions and redirects to home.
    """
    if request.user.is_authenticated:
        storage = messages.get_messages(request)
        for _ in storage:
            pass
        logout(request)
        messages.info(request, "You have been successfully signed out.")
    return redirect(settings.LOGOUT_REDIRECT_URL)
