/**
 * CarVistaHub - Customer Live In-App Notification Poller & Handler
 * Handles real-time polling for test-drive confirmation & rejection popups.
 */

(function () {
    function getCookie(name) {
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
        return cookieValue;
    }

    function attachDismissHandlers(modalElem, notifId) {
        if (!modalElem || !notifId) return;
        const dismissUrl = `/bookings/api/notifications/${notifId}/dismiss/`;
        const dismissNotification = () => {
            fetch(dismissUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken') || '',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            }).catch(() => {});
        };

        const btnAck = modalElem.querySelector('#btnDismissNotificationAck');
        const btnX = modalElem.querySelector('#btnDismissNotificationX');
        const btnHistory = modalElem.querySelector('#btnNotificationViewHistory');

        if (btnAck) btnAck.addEventListener('click', dismissNotification);
        if (btnX) btnX.addEventListener('click', dismissNotification);
        if (btnHistory) btnHistory.addEventListener('click', dismissNotification);
    }

    document.addEventListener('DOMContentLoaded', function () {
        // 1. Initial server-rendered modal handling
        const existingModal = document.getElementById('modalCustomerRejectionNotice');
        let isModalVisible = false;

        if (existingModal && typeof bootstrap !== 'undefined') {
            isModalVisible = true;
            const notifId = existingModal.getAttribute('data-notification-id');
            const bsModal = new bootstrap.Modal(existingModal);
            bsModal.show();
            attachDismissHandlers(existingModal, notifId);
            existingModal.addEventListener('hidden.bs.modal', function () {
                isModalVisible = false;
            });
        }

        // 2. Client-side polling for live notifications while logged in
        let container = document.getElementById('dynamicNotificationContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'dynamicNotificationContainer';
            document.body.appendChild(container);
        }

        async function checkUnreadNotification() {
            if (isModalVisible) return;

            // Never display test drive modals on payment, receipt, or vehicle reservation pages
            const path = window.location.pathname;
            if (path.includes('/payments/') || path.includes('/dashboard/vehicle-reservations/')) {
                return;
            }

            try {
                const res = await fetch('/bookings/api/notifications/unread/', {
                    headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
                });
                if (!res.ok) return;
                const data = await res.json().catch(() => ({}));
                if (data && data.has_unread && data.notification) {
                    // Do not show test drive modal for car reservations (BK-)
                    if (data.notification.booking_reference && data.notification.booking_reference.startsWith('BK-')) {
                        return;
                    }
                    showDynamicNotificationModal(data.notification);
                }
            } catch (_) {}
        }

        function showDynamicNotificationModal(n) {
            if (!container || typeof bootstrap === 'undefined') return;

            const isConfirmed = (n.type === 'BOOKING_CONFIRMED');
            const headerBg = isConfirmed ? 'bg-success' : 'bg-danger';
            const headerIcon = isConfirmed ? 'task_alt' : 'event_busy';
            const subtitle = isConfirmed ? 'Appointment Status: Confirmed' : 'Appointment Request Status: Rejected';
            const bodyIcon = isConfirmed ? 'check_circle' : 'cancel';
            const bodyBg = isConfirmed ? 'bg-success-subtle text-success' : 'bg-danger-subtle text-danger';
            const heading = isConfirmed ? 'Test Drive Confirmed!' : 'Appointment Request Rejected';
            const statusBadge = isConfirmed
                ? '<span class="badge bg-success text-white">CONFIRMED</span>'
                : '<span class="badge bg-danger text-white">REJECTED</span>';

            let extraContent = '';
            if (isConfirmed) {
                extraContent = `
                    <div class="alert alert-success py-2 px-3 fs-8 mb-0 d-flex align-items-start gap-2">
                        <span class="material-symbols-outlined fs-6 text-success flex-shrink-0 mt-1">verified</span>
                        <div>
                            <strong>Appointment Locked:</strong> Your showroom test-drive appointment is locked. Please arrive 10 minutes prior to your slot and bring your original driving licence.
                        </div>
                    </div>
                `;
            } else {
                extraContent = `
                    <div class="mt-2 mb-3">
                        <span class="text-muted fs-8 d-block mb-1">Showroom Manager Rejection Reason:</span>
                        <div class="p-2 bg-white rounded border border-danger-subtle text-danger fs-8 fw-semibold">
                            ${n.rejection_reason || 'Document does not satisfy verification criteria.'}
                        </div>
                    </div>
                    <div class="alert alert-warning py-2 px-3 fs-8 mb-0 d-flex align-items-start gap-2">
                        <span class="material-symbols-outlined fs-6 text-warning flex-shrink-0 mt-1">info</span>
                        <div>
                            <strong>Appointment Slot Released:</strong> The 1-hour showroom test drive slot reserved for this appointment has been immediately released back to the shared showroom schedule.
                        </div>
                    </div>
                `;
            }

            container.innerHTML = `
                <div class="modal fade" id="modalCustomerRejectionNotice" tabindex="-1" aria-labelledby="modalCustomerRejectionNoticeLabel" aria-hidden="true" data-bs-backdrop="static" data-bs-keyboard="false" data-notification-id="${n.id}">
                    <div class="modal-dialog modal-dialog-centered">
                        <div class="modal-content border-0 shadow-lg rounded-4 overflow-hidden">
                            <div class="modal-header ${headerBg} text-white py-3 px-4">
                                <div class="d-flex align-items-center gap-2">
                                    <span class="material-symbols-outlined fs-3">${headerIcon}</span>
                                    <div>
                                        <h5 class="modal-title fs-6 fw-bold mb-0" id="modalCustomerRejectionNoticeLabel">${n.title || (isConfirmed ? 'Test Drive Confirmed!' : 'Test Drive Request Update')}</h5>
                                        <span class="fs-9 text-white-50">${subtitle}</span>
                                    </div>
                                </div>
                                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close" id="btnDismissNotificationX"></button>
                            </div>
                            <div class="modal-body p-4">
                                <div class="text-center mb-3">
                                    <div class="d-inline-flex align-items-center justify-content-center ${bodyBg} rounded-circle p-3 mb-2">
                                        <span class="material-symbols-outlined fs-1">${bodyIcon}</span>
                                    </div>
                                    <h5 class="fw-bold text-dark mb-1">${heading}</h5>
                                    <p class="fs-8 text-muted mb-0">${n.message}</p>
                                </div>

                                <div class="bg-light rounded-3 p-3 mb-3 border">
                                    <div class="d-flex justify-content-between align-items-center border-bottom pb-2 mb-2 fs-8">
                                        <span class="text-muted">Booking Reference:</span>
                                        <strong class="font-monospace text-dark">${n.booking_reference || '--'}</strong>
                                    </div>
                                    <div class="d-flex justify-content-between align-items-center border-bottom pb-2 mb-2 fs-8">
                                        <span class="text-muted">Vehicle Name:</span>
                                        <strong class="text-dark">${n.car_title || '--'}</strong>
                                    </div>
                                    <div class="d-flex justify-content-between align-items-center border-bottom pb-2 mb-2 fs-8">
                                        <span class="text-muted">Appointment Date &amp; Slot:</span>
                                        <strong class="text-dark">
                                            ${n.slot_date_display || n.slot_date} (${n.slot_time || '--'})
                                        </strong>
                                    </div>
                                    <div class="d-flex justify-content-between align-items-center border-bottom pb-2 mb-2 fs-8">
                                        <span class="text-muted">Showroom Location:</span>
                                        <strong class="text-dark">${n.showroom_location || 'CarVistaHub Showroom'}</strong>
                                    </div>
                                    <div class="d-flex justify-content-between align-items-center fs-8">
                                        <span class="text-muted">Confirmation Status:</span>
                                        ${statusBadge}
                                    </div>
                                    ${!isConfirmed ? extraContent : ''}
                                </div>
                                ${isConfirmed ? extraContent : ''}
                            </div>
                            <div class="modal-footer py-3 px-4 bg-light border-top d-flex justify-content-between">
                                <a href="/dashboard/test-drive-appointments/" class="btn btn-outline-secondary btn-sm fs-8 py-2 px-3" id="btnNotificationViewHistory">
                                    <span class="material-symbols-outlined fs-7 align-middle">calendar_month</span>
                                    <span>View Test Drive Appointments</span>
                                </a>
                                <button type="button" class="btn btn-primary btn-sm fs-8 py-2 px-4 shadow-xs" data-bs-dismiss="modal" id="btnDismissNotificationAck">
                                    <span>Acknowledge &amp; Close</span>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            const newModalElem = document.getElementById('modalCustomerRejectionNotice');
            if (newModalElem) {
                isModalVisible = true;
                const bs = new bootstrap.Modal(newModalElem);
                bs.show();
                attachDismissHandlers(newModalElem, n.id);
                newModalElem.addEventListener('hidden.bs.modal', function () {
                    isModalVisible = false;
                });
            }
        }

        // Live polling every 12 seconds
        setInterval(checkUnreadNotification, 12000);
    });
})();

