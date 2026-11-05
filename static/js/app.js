/**
 * CarVistaHub - Client-Side Application Script
 * Minimal, clean UI micro-interactions for the CarVistaHub platform.
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Navbar elevation on scroll
    const navbar = document.querySelector('.autohub-navbar');
    if (navbar) {
        const handleScroll = () => {
            if (window.scrollY > 20) {
                navbar.classList.add('scrolled');
            } else {
                navbar.classList.remove('scrolled');
            }
        };
        window.addEventListener('scroll', handleScroll, { passive: true });
        handleScroll();
    }

    // 2. Featured Cars category filter pill switching (Dynamic database cars)
    const filterTabs = document.querySelectorAll('.category-tab-btn');
    const carCards = document.querySelectorAll('#featured-cars .car-item');

    if (filterTabs.length > 0 && carCards.length > 0) {
        filterTabs.forEach((tab) => {
            tab.addEventListener('click', (e) => {
                e.preventDefault();
                filterTabs.forEach((btn) => {
                    btn.classList.remove('active');
                    btn.setAttribute('aria-selected', 'false');
                });
                tab.classList.add('active');
                tab.setAttribute('aria-selected', 'true');

                const filter = (tab.getAttribute('data-filter') || 'all').toLowerCase();

                carCards.forEach((card) => {
                    const bodyType = (card.getAttribute('data-body-type') || '').toUpperCase();
                    const fuelType = (card.getAttribute('data-fuel-type') || '').toUpperCase();

                    if (filter === 'all') {
                        card.style.display = '';
                    } else if (filter === 'sedan') {
                        card.style.display = (bodyType === 'SEDAN') ? '' : 'none';
                    } else if (filter === 'suv') {
                        card.style.display = (bodyType === 'SUV') ? '' : 'none';
                    } else if (filter === 'electric') {
                        card.style.display = (fuelType === 'ELECTRIC' || bodyType === 'EV') ? '' : 'none';
                    }
                });
            });
        });
    }
});
