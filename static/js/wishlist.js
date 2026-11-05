/**
 * CarVistaHub - Client-Side Wishlist Management
 * Seamless AJAX add/remove micro-interactions with CSRF protection,
 * optimistic/safe state toggling, navigation count sync, and toast feedback.
 */

(function () {
    'use strict';

    // Helper: Retrieve CSRF Token from cookie
    function getCsrfToken() {
        const name = 'csrftoken';
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        if (!cookieValue) {
            const csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
            if (csrfInput) cookieValue = csrfInput.value;
        }
        return cookieValue;
    }

    // Helper: Display Toast Notification
    function showWishlistToast(message, type = 'info') {
        let container = document.getElementById('wishlistToastContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'wishlistToastContainer';
            container.className = 'position-fixed top-0 end-0 p-3';
            container.style.zIndex = '1090';
            document.body.appendChild(container);
        }

        const toastId = 'toast-' + Date.now();
        const iconName = type === 'success' ? 'favorite' : (type === 'danger' ? 'delete' : 'info');
        const iconColor = type === 'success' ? 'text-danger' : (type === 'danger' ? 'text-secondary' : 'text-primary');

        const toastHtml = `
            <div id="${toastId}" class="toast align-items-center bg-white border-0 shadow-lg rounded-3 mb-2 show" role="alert" aria-live="assertive" aria-atomic="true">
                <div class="d-flex">
                    <div class="toast-body d-flex align-items-center gap-2 py-3 px-3">
                        <span class="material-symbols-outlined fs-5 ${iconColor}">${iconName}</span>
                        <span class="fs-7 text-dark fw-medium">${message}</span>
                    </div>
                    <button type="button" class="btn-close me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
                </div>
            </div>
        `;

        container.insertAdjacentHTML('beforeend', toastHtml);
        const toastEl = document.getElementById(toastId);

        // Auto dismiss after 3.5 seconds
        setTimeout(() => {
            if (toastEl && toastEl.parentNode) {
                toastEl.classList.remove('show');
                setTimeout(() => toastEl.remove(), 300);
            }
        }, 3500);

        const closeBtn = toastEl.querySelector('.btn-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                toastEl.classList.remove('show');
                setTimeout(() => toastEl.remove(), 300);
            });
        }
    }

    // Helper: Update Navigation & Header Wishlist Count Badges
    function updateWishlistBadges(count) {
        const badges = document.querySelectorAll('.wishlist-nav-badge');
        badges.forEach((badge) => {
            badge.textContent = count;
            if (count > 0) {
                badge.style.display = 'inline-block';
            } else {
                badge.style.display = 'none';
            }
        });

        const headerCount = document.getElementById('wishlistHeaderCount');
        if (headerCount) {
            headerCount.textContent = count;
        }
    }

    // Main Toggle Wishlist Function
    async function toggleWishlist(carId, carTitle, triggerBtn) {
        if (!carId) return;

        // Prevent double submit
        if (triggerBtn) triggerBtn.disabled = true;

        const csrfToken = getCsrfToken();
        const endpoint = '/wishlist/api/toggle/';

        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: new URLSearchParams({ car_id: carId })
            });

            // Handle unauthenticated user redirect
            if (response.status === 401) {
                const data = await response.json();
                const redirectTarget = data.login_url || `/accounts/login/?next=${encodeURIComponent(window.location.pathname)}`;
                window.location.href = redirectTarget;
                return;
            }

            if (!response.ok) {
                throw new Error(`HTTP error ${response.status}`);
            }

            const data = await response.json();

            if (data.status === 'success') {
                const isWishlisted = data.is_wishlisted;
                const newCount = data.wishlist_count;

                // Sync all buttons on page for this specific car
                const allMatchingBtns = document.querySelectorAll(`[data-car-id="${carId}"]`);
                allMatchingBtns.forEach((btn) => {
                    const icon = btn.querySelector('.wishlist-icon');
                    const textSpan = btn.querySelector('.wishlist-btn-text');

                    if (isWishlisted) {
                        if (icon) {
                            icon.classList.add('filled', 'text-danger');
                            icon.classList.remove('text-muted');
                            // Micro-interaction bounce
                            icon.style.transform = 'scale(1.25)';
                            setTimeout(() => { icon.style.transform = ''; }, 200);
                        }
                        if (textSpan) textSpan.textContent = 'Saved in Wishlist';
                        btn.setAttribute('title', 'Remove from Wishlist');
                        btn.setAttribute('aria-label', `Remove ${carTitle || 'car'} from Wishlist`);
                    } else {
                        if (icon) {
                            icon.classList.remove('filled', 'text-danger');
                            icon.classList.add('text-muted');
                            icon.style.transform = 'scale(0.85)';
                            setTimeout(() => { icon.style.transform = ''; }, 200);
                        }
                        if (textSpan) textSpan.textContent = 'Add to Wishlist';
                        btn.setAttribute('title', 'Add to Wishlist');
                        btn.setAttribute('aria-label', `Add ${carTitle || 'car'} to Wishlist`);
                    }
                });

                // Update navigation badge
                updateWishlistBadges(newCount);

                // Toast notification
                showWishlistToast(data.message, isWishlisted ? 'success' : 'danger');

                // If on /wishlist/ page and item was removed, animate and remove card
                if (!isWishlisted && window.location.pathname.includes('/wishlist/')) {
                    const cardItem = document.getElementById(`wishlist-item-${carId}`);
                    if (cardItem) {
                        cardItem.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                        cardItem.style.opacity = '0';
                        cardItem.style.transform = 'scale(0.95)';
                        setTimeout(() => {
                            cardItem.remove();
                            // If no more items, display empty state
                            const remaining = document.querySelectorAll('.wishlist-card-item');
                            if (remaining.length === 0) {
                                const grid = document.getElementById('wishlistGrid');
                                const emptyState = document.getElementById('wishlistEmptyState');
                                if (grid) grid.style.display = 'none';
                                if (emptyState) emptyState.style.display = 'block';
                            }
                        }, 300);
                    }
                }
            } else {
                showWishlistToast(data.message || 'Unable to update wishlist.', 'danger');
            }
        } catch (err) {
            console.error('Wishlist toggle error:', err);
            showWishlistToast('Network or server error while updating wishlist.', 'danger');
        } finally {
            if (triggerBtn) triggerBtn.disabled = false;
        }
    }

    // Direct Removal from Wishlist Page
    async function removeWishlistDirect(carId, carTitle, triggerBtn) {
        if (!carId) return;
        if (triggerBtn) triggerBtn.disabled = true;

        const csrfToken = getCsrfToken();
        const endpoint = `/wishlist/api/remove/${carId}/`;

        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (response.status === 401) {
                window.location.href = `/accounts/login/?next=${encodeURIComponent(window.location.pathname)}`;
                return;
            }

            const data = await response.json();
            if (data.status === 'success') {
                updateWishlistBadges(data.wishlist_count);
                showWishlistToast(data.message, 'danger');

                const cardItem = document.getElementById(`wishlist-item-${carId}`);
                if (cardItem) {
                    cardItem.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                    cardItem.style.opacity = '0';
                    cardItem.style.transform = 'scale(0.95)';
                    setTimeout(() => {
                        cardItem.remove();
                        const remaining = document.querySelectorAll('.wishlist-card-item');
                        if (remaining.length === 0) {
                            const grid = document.getElementById('wishlistGrid');
                            const emptyState = document.getElementById('wishlistEmptyState');
                            if (grid) grid.style.display = 'none';
                            if (emptyState) emptyState.style.display = 'block';
                        }
                    }, 300);
                }
            }
        } catch (err) {
            console.error('Wishlist removal error:', err);
            showWishlistToast('Error removing car from wishlist.', 'danger');
        } finally {
            if (triggerBtn) triggerBtn.disabled = false;
        }
    }

    // Initialize Event Listeners
    document.addEventListener('DOMContentLoaded', () => {
        // Event delegation for all wishlist action buttons
        document.body.addEventListener('click', (e) => {
            // Check for toggle button or icon click
            const btn = e.target.closest('.wishlist-btn') || e.target.closest('.wishlist-detail-btn');
            if (btn) {
                e.preventDefault();
                e.stopPropagation();
                const carId = btn.getAttribute('data-car-id');
                const carTitle = btn.getAttribute('data-car-title') || '';
                toggleWishlist(carId, carTitle, btn);
                return;
            }

            // Check for direct remove button on wishlist page
            const removeBtn = e.target.closest('.wishlist-remove-btn');
            if (removeBtn) {
                e.preventDefault();
                e.stopPropagation();
                const carId = removeBtn.getAttribute('data-car-id');
                const carTitle = removeBtn.getAttribute('data-car-title') || '';
                removeWishlistDirect(carId, carTitle, removeBtn);
                return;
            }
        });
    });
})();

