/**
 * CarVistaHub - Showroom Test Drive Availability Calendar Engine (Phase 2)
 * Provides real-time dynamic calendar rendering, automatic polling, date navigation,
 * and role-appropriate slot inspection for both Customer and Manager interfaces.
 */

(function (window, document) {
    'use strict';

    const API_ENDPOINT = '/bookings/api/calendar/';
    let customerTimer = null;
    let managerTimer = null;
    let activeCustomerRequestId = 0;
    let activeManagerRequestId = 0;

    /**
     * Format a Date object to YYYY-MM-DD local string
     */
    function formatDateISO(dateObj) {
        const year = dateObj.getFullYear();
        const month = String(dateObj.getMonth() + 1).padStart(2, '0');
        const day = String(dateObj.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    /**
     * Add days to a Date object safely
     */
    function addDays(dateObj, days) {
        const result = new Date(dateObj);
        result.setDate(result.getDate() + days);
        return result;
    }

    /**
     * Helper to get CSRF token from cookie if needed
     */
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

    /**
     * Unified AJAX availability fetcher with cancellation of stale responses
     */
    async function fetchCalendarAvailability(startDateStr, endDateStr, carId = null) {
        let url = `${API_ENDPOINT}?start_date=${encodeURIComponent(startDateStr)}&end_date=${encodeURIComponent(endDateStr)}`;
        if (carId) {
            url += `&car_id=${encodeURIComponent(carId)}`;
        }

        const response = await fetch(url, {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
            },
        });

        if (!response.ok) {
            let errorMsg = `Server returned HTTP ${response.status}`;
            try {
                const errData = await response.json();
                if (errData && errData.error) {
                    errorMsg = errData.error;
                }
            } catch (_) { }
            throw new Error(errorMsg);
        }

        return await response.json();
    }

    // =========================================================================
    // 1. Customer Modal Calendar Controller
    // =========================================================================
    const CustomerCalendar = {
        modalElem: null,
        pillsContainer: null,
        slotsContainer: null,
        dateLabel: null,
        alertContainer: null,
        loadingSpinner: null,
        lastSyncText: null,
        previewCard: null,
        previewSummaryText: null,
        continueBtn: null,

        // Step containers & footer
        stepSelectSlot: null,
        stepBookingForm: null,
        stepSuccess: null,
        modalFooter: null,
        modalHeaderContent: null,

        // Step 2 Form elements
        bookingForm: null,
        formSummaryCarTitle: null,
        formSummarySlotTime: null,
        formAlertContainer: null,
        inputFullName: null,
        inputEmail: null,
        inputContactPhone: null,
        inputDrivingLicense: null,
        dlFeedback: null,
        inputCustomerNotes: null,
        inputTermsAgreed: null,
        termsFeedback: null,
        btnBackToCalendar: null,
        btnSubmitBooking: null,
        submitSpinner: null,
        submitIcon: null,
        submitText: null,

        // Step 3 Success elements
        successBookingNumber: null,
        successCarTitle: null,
        successDate: null,
        successTime: null,
        btnSuccessDone: null,
        btnSuccessViewCalendar: null,

        carId: null,
        carTitle: '',
        windowStartDate: new Date(),
        selectedDateStr: '',
        selectedSlot: null,
        cachedDays: {},
        isGuest: false,

        init() {
            this.modalElem = document.getElementById('showroomCalendarModal');
            if (!this.modalElem) return;

            this.isGuest = (this.modalElem.getAttribute('data-is-authenticated') === 'false');

            this.pillsContainer = document.getElementById('calendarDatePillsContainer');
            this.slotsContainer = document.getElementById('customerSlotsContainer');
            this.dateLabel = document.getElementById('calendarSelectedDateLabel');
            this.alertContainer = document.getElementById('calendarAlertContainer');
            this.loadingSpinner = document.getElementById('calendarLoadingSpinner');
            this.lastSyncText = document.getElementById('calendarLastSyncText');
            this.previewCard = document.getElementById('customerSelectedSlotCard');
            this.previewSummaryText = document.getElementById('selectedSlotSummaryText');
            this.continueBtn = document.getElementById('calContinueBtn');

            // Steps & Footer
            this.stepSelectSlot = document.getElementById('calStepSelectSlot');
            this.stepBookingForm = document.getElementById('calStepBookingForm');
            this.stepSuccess = document.getElementById('calStepSuccess');
            this.modalFooter = document.getElementById('calModalFooter');
            this.modalHeaderContent = document.getElementById('calModalHeaderContent');

            // Form inputs
            this.bookingForm = document.getElementById('customerBookingSubmissionForm');
            this.formSummaryCarTitle = document.getElementById('formSummaryCarTitle');
            this.formSummarySlotTime = document.getElementById('formSummarySlotTime');
            this.formAlertContainer = document.getElementById('bookingFormAlertContainer');

            this.inputFullName = document.getElementById('inputFullName');
            this.inputEmail = document.getElementById('inputEmail');
            this.inputContactPhone = document.getElementById('inputContactPhone');
            this.inputDrivingLicenseImage = document.getElementById('inputDrivingLicenseImage');
            this.dlFeedback = document.getElementById('drivingLicenseFeedback');
            this.inputCustomerNotes = document.getElementById('inputCustomerNotes');
            this.inputTermsAgreed = document.getElementById('inputTermsAgreed');
            this.termsFeedback = document.getElementById('termsFeedback');

            this.btnBackToCalendar = document.getElementById('btnBackToCalendar');
            this.btnSubmitBooking = document.getElementById('btnSubmitBooking');
            this.submitSpinner = document.getElementById('submitBookingSpinner');
            this.submitIcon = document.getElementById('submitBookingIcon');
            this.submitText = document.getElementById('submitBookingText');

            // Success elements
            this.successBookingNumber = document.getElementById('successBookingNumber');
            this.successCarTitle = document.getElementById('successCarTitle');
            this.successDate = document.getElementById('successDate');
            this.successTime = document.getElementById('successTime');
            this.btnSuccessDone = document.getElementById('btnSuccessDone');
            this.btnSuccessViewCalendar = document.getElementById('btnSuccessViewCalendar');

            const carStrip = document.getElementById('calendarCarSummaryStrip');
            if (carStrip) {
                this.carId = carStrip.getAttribute('data-car-id') || null;
                this.carTitle = carStrip.getAttribute('data-car-title') || '';
            }

            // Refresh button
            const refreshBtn = document.getElementById('calManualRefreshBtn');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', () => {
                    this.loadAvailabilityWindow(true);
                });
            }

            // Customer Cancellation Buttons & Modals (Phase B & C)
            const btnCancelBooking = document.getElementById('btnCustomerCancelBooking');
            const modalCancelConfirmElem = document.getElementById('modalCustomerCancelConfirm');
            const btnSubmitCancel = document.getElementById('btnSubmitCustomerCancel');
            const cancelReasonInput = document.getElementById('custCancelReasonInput');
            const cancelErrorAlert = document.getElementById('custCancelErrorAlert');

            let cancelConfirmModal = null;
            if (modalCancelConfirmElem && typeof bootstrap !== 'undefined') {
                cancelConfirmModal = bootstrap.Modal.getOrCreateInstance(modalCancelConfirmElem);
            }

            if (btnCancelBooking) {
                btnCancelBooking.addEventListener('click', () => {
                    const detailsModalElem = document.getElementById('modalCustomerBookingDetails');
                    if (detailsModalElem && typeof bootstrap !== 'undefined') {
                        const detailsModal = bootstrap.Modal.getOrCreateInstance(detailsModalElem);
                        detailsModal.hide();
                    }
                    if (cancelReasonInput) cancelReasonInput.value = '';
                    if (cancelErrorAlert) {
                        cancelErrorAlert.classList.add('d-none');
                        cancelErrorAlert.textContent = '';
                    }
                    if (cancelConfirmModal) cancelConfirmModal.show();
                });
            }

            if (btnSubmitCancel) {
                btnSubmitCancel.addEventListener('click', async () => {
                    const booking = this.activeCustomerBooking;
                    const bookingId = booking ? (booking.booking_id || booking.id) : null;
                    if (!bookingId) return;

                    const reason = cancelReasonInput ? cancelReasonInput.value.trim() : '';

                    btnSubmitCancel.disabled = true;
                    if (cancelErrorAlert) cancelErrorAlert.classList.add('d-none');

                    try {
                        const res = await fetch(`/bookings/api/bookings/${bookingId}/cancel/`, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'Accept': 'application/json',
                                'X-CSRFToken': getCookie('csrftoken'),
                                'X-Requested-With': 'XMLHttpRequest'
                            },
                            body: JSON.stringify({ reason })
                        });
                        const data = await res.json().catch(() => ({}));
                        if (res.ok && data.success) {
                            if (cancelConfirmModal) cancelConfirmModal.hide();
                            this.showAlert(data.message || 'Your test-drive appointment has been cancelled successfully. The time slot is now available for other customers.', 'success');
                            // Live sync: refresh calendar so slot immediately becomes AVAILABLE
                            this.loadAvailabilityWindow(true);
                        } else {
                            if (cancelErrorAlert) {
                                cancelErrorAlert.textContent = data.error || 'Failed to cancel appointment. Please try again.';
                                cancelErrorAlert.classList.remove('d-none');
                            }
                        }
                    } catch (err) {
                        if (cancelErrorAlert) {
                            cancelErrorAlert.textContent = err.message || 'Network error.';
                            cancelErrorAlert.classList.remove('d-none');
                        }
                    } finally {
                        btnSubmitCancel.disabled = false;
                    }
                });
            }

            // Continue to Step 2 Form
            if (this.continueBtn) {
                this.continueBtn.addEventListener('click', () => {
                    if (!this.selectedSlot || this.isGuest) return;
                    this.showFormAlert(null);
                    if (this.formSummaryCarTitle) {
                        this.formSummaryCarTitle.textContent = this.carTitle;
                    }
                    if (this.formSummarySlotTime) {
                        const dayDate = new Date(this.selectedSlot.date + 'T00:00:00');
                        const dateFormatted = dayDate.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
                        this.formSummarySlotTime.textContent = `${dateFormatted} • ${this.selectedSlot.start_time} - ${this.selectedSlot.end_time}`;
                    }
                    this.showStep('form');
                });
            }

            // Back to Calendar Button
            if (this.btnBackToCalendar) {
                this.btnBackToCalendar.addEventListener('click', () => {
                    this.showStep('select');
                });
            }

            // Success screen buttons
            if (this.btnSuccessViewCalendar) {
                this.btnSuccessViewCalendar.addEventListener('click', () => {
                    this.selectedSlot = null;
                    if (this.continueBtn) this.continueBtn.disabled = true;
                    if (this.previewCard) this.previewCard.classList.add('d-none');
                    this.showStep('select');
                    this.loadAvailabilityWindow(true);
                });
            }

            // Form submission event
            if (this.bookingForm) {
                this.bookingForm.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    if (!this.selectedSlot || this.isGuest) return;

                    this.showFormAlert(null);

                    // 1. Validate Driving Licence Image (mandatory front side)
                    if (!this.inputDrivingLicenseImage || !this.inputDrivingLicenseImage.files || this.inputDrivingLicenseImage.files.length === 0) {
                        if (this.inputDrivingLicenseImage) this.inputDrivingLicenseImage.classList.add('is-invalid');
                        if (this.dlFeedback) this.dlFeedback.textContent = "Driving licence photograph is compulsory. Please upload the front side of your licence.";
                        if (this.inputDrivingLicenseImage) this.inputDrivingLicenseImage.focus();
                        return;
                    }

                    const file = this.inputDrivingLicenseImage.files[0];
                    const maxSize = 5 * 1024 * 1024; // 5 MB

                    if (file.size > maxSize) {
                        if (this.inputDrivingLicenseImage) this.inputDrivingLicenseImage.classList.add('is-invalid');
                        if (this.dlFeedback) this.dlFeedback.textContent = "File size exceeds 5 MB limit. Please upload an image under 5 MB in size.";
                        if (this.inputDrivingLicenseImage) this.inputDrivingLicenseImage.focus();
                        return;
                    }

                    const fileName = file.name.toLowerCase();
                    const validExts = ['.jpg', '.jpeg', '.png'];
                    const hasValidExt = validExts.some(ext => fileName.endsWith(ext));
                    if (!hasValidExt) {
                        if (this.inputDrivingLicenseImage) this.inputDrivingLicenseImage.classList.add('is-invalid');
                        if (this.dlFeedback) this.dlFeedback.textContent = "Invalid file type. Only JPG, JPEG, and PNG images are accepted.";
                        if (this.inputDrivingLicenseImage) this.inputDrivingLicenseImage.focus();
                        return;
                    }

                    if (this.inputDrivingLicenseImage) this.inputDrivingLicenseImage.classList.remove('is-invalid');

                    // 2. Validate Terms & Conditions agreement
                    if (!this.inputTermsAgreed || !this.inputTermsAgreed.checked) {
                        if (this.inputTermsAgreed) this.inputTermsAgreed.classList.add('is-invalid');
                        if (this.termsFeedback) this.termsFeedback.textContent = "You must agree to the terms and conditions.";
                        return;
                    } else {
                        if (this.inputTermsAgreed) this.inputTermsAgreed.classList.remove('is-invalid');
                    }

                    // 3. Prevent duplicate submission with button loading/disabled state
                    this.setSubmittingState(true);

                    // 4. Construct FormData payload for multipart/form-data upload
                    const formData = new FormData();
                    formData.append('car_id', parseInt(this.carId, 10));
                    formData.append('preferred_date', this.selectedSlot.date);
                    formData.append('start_time', this.selectedSlot.start_time);
                    formData.append('license_image', file);
                    if (this.inputCustomerNotes) {
                        formData.append('customer_notes', this.inputCustomerNotes.value.trim());
                    }
                    if (this.inputContactPhone) {
                        formData.append('contact_phone', this.inputContactPhone.value.trim());
                    }
                    formData.append('terms_agreed', 'true');

                    try {
                        const response = await fetch('/bookings/api/book/', {
                            method: 'POST',
                            headers: {
                                'Accept': 'application/json',
                                'X-CSRFToken': getCookie('csrftoken'),
                                'X-Requested-With': 'XMLHttpRequest',
                            },
                            body: formData
                        });

                        const resData = await response.json().catch(() => ({}));

                        if (response.status === 201 && resData.success) {
                            // Populate success step
                            if (this.successBookingNumber) this.successBookingNumber.textContent = resData.booking_number;
                            if (this.successCarTitle) this.successCarTitle.textContent = resData.car_title || this.carTitle;
                            if (this.successDate) this.successDate.textContent = resData.date;
                            if (this.successTime) this.successTime.textContent = `${resData.start_time} - ${resData.end_time}`;

                            this.showStep('success');

                            // Live sync: refresh calendar so slot immediately appears as PENDING / "Your Booking"
                            this.loadAvailabilityWindow(true);
                        } else {
                            const errorMsg = resData.error || `Booking submission failed (HTTP ${response.status}). Please try again.`;
                            this.showFormAlert(errorMsg, response.status === 409 ? 'warning' : 'danger');

                            if (response.status === 409) {
                                // Slot conflict: refresh calendar so user sees updated slot state
                                this.loadAvailabilityWindow(true);
                            }
                        }
                    } catch (netErr) {
                        this.showFormAlert(`Network error: ${netErr.message || 'Unable to submit booking request.'}`, 'danger');
                    } finally {
                        this.setSubmittingState(false);
                    }
                });
            }

            // Modal lifecycle events
            this.modalElem.addEventListener('shown.bs.modal', () => {
                this.showStep('select');
                this.windowStartDate = new Date();
                this.windowStartDate.setHours(0, 0, 0, 0);
                this.selectedDateStr = formatDateISO(this.windowStartDate);
                this.selectedSlot = null;
                if (this.previewCard) this.previewCard.classList.add('d-none');
                if (this.continueBtn) this.continueBtn.disabled = true;

                this.loadAvailabilityWindow();
                this.startPolling();
            });

            this.modalElem.addEventListener('hidden.bs.modal', () => {
                this.stopPolling();
                this.showStep('select');
            });

            // Focus refresh
            window.addEventListener('focus', () => {
                if (this.modalElem.classList.contains('show')) {
                    this.loadAvailabilityWindow(false);
                }
            });

            document.addEventListener('visibilitychange', () => {
                if (document.visibilityState === 'visible' && this.modalElem.classList.contains('show')) {
                    this.loadAvailabilityWindow(false);
                }
            });
        },

        showStep(stepName) {
            if (this.stepSelectSlot) {
                this.stepSelectSlot.classList.toggle('d-none', stepName !== 'select');
            }
            if (this.stepBookingForm) {
                this.stepBookingForm.classList.toggle('d-none', stepName !== 'form');
            }
            if (this.stepSuccess) {
                this.stepSuccess.classList.toggle('d-none', stepName !== 'success');
            }
            if (this.modalHeaderContent) {
                this.modalHeaderContent.classList.toggle('d-none', stepName === 'success');
            }
            if (this.modalFooter) {
                if (stepName === 'select') {
                    this.modalFooter.classList.remove('d-none');
                    this.modalFooter.classList.add('d-flex');
                } else {
                    this.modalFooter.classList.add('d-none');
                    this.modalFooter.classList.remove('d-flex');
                }
            }
        },

        setSubmittingState(isSubmitting) {
            if (this.btnSubmitBooking) this.btnSubmitBooking.disabled = isSubmitting;
            if (this.btnBackToCalendar) this.btnBackToCalendar.disabled = isSubmitting;
            if (this.submitSpinner) this.submitSpinner.classList.toggle('d-none', !isSubmitting);
            if (this.submitIcon) this.submitIcon.classList.toggle('d-none', isSubmitting);
            if (this.submitText) {
                this.submitText.textContent = isSubmitting ? 'Submitting Request...' : 'Confirm & Book Test Drive';
            }
        },

        showFormAlert(msg, type = 'danger') {
            if (!this.formAlertContainer) return;
            if (!msg) {
                this.formAlertContainer.classList.add('d-none');
                this.formAlertContainer.innerHTML = '';
                return;
            }
            this.formAlertContainer.className = `alert alert-${type} py-2 px-3 fs-8 mb-3 d-flex align-items-center gap-2`;
            this.formAlertContainer.innerHTML = `
                <span class="material-symbols-outlined fs-5 flex-shrink-0">error</span>
                <div>${msg}</div>
            `;
            this.formAlertContainer.classList.remove('d-none');
        },

        validateDLFormat(rawDL) {
            if (!rawDL || !rawDL.trim()) return false;
            const cleaned = rawDL.trim().toUpperCase().replace(/[\s\-\/]+/g, '');
            if (cleaned.length < 12 || cleaned.length > 15) return false;
            const stateCode = cleaned.substring(0, 2);
            const validStates = [
                'AN','AP','AR','AS','BR','CG','CH','DD','DL','DN','GA','GJ','HP','HR',
                'JH','JK','KA','KL','LA','LD','MH','ML','MN','MP','MZ','NL','OD','PB',
                'PY','RJ','SK','TN','TR','TS','UK','UP','WB','OR','UA'
            ];
            if (!validStates.includes(stateCode)) return false;
            const rto = cleaned.substring(2, 4);
            if (!/^\d{2}$/.test(rto)) return false;
            const yearStr = cleaned.substring(4, 8);
            if (!/^\d{4}$/.test(yearStr)) return false;
            const year = parseInt(yearStr, 10);
            const currentYear = new Date().getFullYear();
            if (year < 1950 || year > currentYear) return false;
            const remaining = cleaned.substring(8);
            if (!/^\d{4,7}$/.test(remaining)) return false;
            return true;
        },

        startPolling() {
            this.stopPolling();
            // Refresh customer availability every 60 seconds
            customerTimer = setInterval(() => {
                if (this.modalElem && this.modalElem.classList.contains('show')) {
                    this.loadAvailabilityWindow(false);
                }
            }, 60000);
        },

        stopPolling() {
            if (customerTimer) {
                clearInterval(customerTimer);
                customerTimer = null;
            }
        },

        showLoading(show) {
            if (this.loadingSpinner) {
                this.loadingSpinner.classList.toggle('d-none', !show);
            }
        },

        showAlert(msg, type = 'danger') {
            if (!this.alertContainer) return;
            if (!msg) {
                this.alertContainer.classList.add('d-none');
                this.alertContainer.innerHTML = '';
                return;
            }
            this.alertContainer.className = `alert alert-${type} py-2 px-3 fs-8 mb-3`;
            this.alertContainer.innerHTML = msg;
            this.alertContainer.classList.remove('d-none');
        },

        async loadAvailabilityWindow(forceFeedback = false) {
            const reqId = ++activeCustomerRequestId;
            this.showLoading(true);
            this.showAlert(null);

            const startStr = formatDateISO(this.windowStartDate);
            const endStr = formatDateISO(addDays(this.windowStartDate, 6)); // Exactly 7 days: today through today + 6

            try {
                const data = await fetchCalendarAvailability(startStr, endStr, this.carId);
                if (reqId !== activeCustomerRequestId) {
                    return; // Stale request discard
                }

                if (data.is_guest_view !== undefined) {
                    this.isGuest = Boolean(data.is_guest_view);
                }

                // Cache days by date string
                this.cachedDays = {};
                if (data.days && Array.isArray(data.days)) {
                    data.days.forEach(day => {
                        this.cachedDays[day.date] = day;
                    });
                }

                // Render horizontal date pills (rolling 7-day window)
                this.renderDatePills(data.days || []);

                // If currently selected date is not in the window, select today (first day)
                if (!this.cachedDays[this.selectedDateStr] && data.days && data.days.length > 0) {
                    this.selectedDateStr = data.days[0].date;
                }

                // Render slots for selected date
                this.renderSlotsForSelectedDate();

                if (this.lastSyncText) {
                    if (this.isGuest) {
                        this.lastSyncText.textContent = 'Preview Mode (Locked)';
                    } else {
                        const nowTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                        this.lastSyncText.textContent = `Synced at ${nowTime}`;
                    }
                }
            } catch (err) {
                if (reqId === activeCustomerRequestId) {
                    this.showAlert(`Failed to fetch showroom calendar: ${err.message}`);
                }
            } finally {
                if (reqId === activeCustomerRequestId) {
                    this.showLoading(false);
                }
            }
        },

        renderDatePills(days) {
            if (!this.pillsContainer) return;
            this.pillsContainer.innerHTML = '';

            const todayStr = formatDateISO(new Date());

            days.forEach(day => {
                const pillBtn = document.createElement('button');
                pillBtn.type = 'button';
                const isSelected = (day.date === this.selectedDateStr);

                let btnStyle = isSelected ? 'btn-primary text-white shadow-sm' : 'btn-outline-secondary bg-white text-dark';
                if (this.isGuest) {
                    btnStyle = isSelected ? 'btn-secondary text-white shadow-sm' : 'btn-light border-secondary-subtle text-muted';
                }

                pillBtn.className = `btn btn-sm d-flex flex-column align-items-center py-2 px-3 rounded-3 text-nowrap transition-all border ${btnStyle}`;

                const dayDate = new Date(day.date + 'T00:00:00');
                const dayName = dayDate.toLocaleDateString([], { weekday: 'short' });
                const dayMonth = dayDate.toLocaleDateString([], { month: 'short', day: 'numeric' });

                let subBadge = '';
                if (!this.isGuest) {
                    if (day.date === todayStr) {
                        subBadge = '<span class="badge bg-secondary-subtle text-secondary fs-9 mt-1">Today</span>';
                    } else if (!day.is_open) {
                        subBadge = '<span class="badge bg-danger-subtle text-danger fs-9 mt-1">Closed</span>';
                    }
                } else {
                    subBadge = '<span class="badge bg-secondary-subtle text-secondary fs-9 mt-1 d-inline-flex align-items-center gap-1"><span class="material-symbols-outlined fs-9" style="font-size: 11px !important;">lock</span><span>Locked</span></span>';
                }

                pillBtn.innerHTML = `
                    <span class="fs-8 text-uppercase fw-bold opacity-75">${dayName}</span>
                    <span class="fs-7 fw-bold">${dayMonth}</span>
                    ${subBadge}
                `;

                if (this.isGuest) {
                    pillBtn.disabled = true;
                    pillBtn.style.cursor = 'not-allowed';
                    pillBtn.title = 'Sign in to select dates';
                } else {
                    pillBtn.addEventListener('click', () => {
                        this.selectedDateStr = day.date;
                        this.renderDatePills(days);
                        this.renderSlotsForSelectedDate();
                    });
                }

                this.pillsContainer.appendChild(pillBtn);
            });
        },

        renderSlotsForSelectedDate() {
            if (!this.slotsContainer) return;
            this.slotsContainer.innerHTML = '';

            const day = this.cachedDays[this.selectedDateStr];
            if (!day) {
                this.slotsContainer.innerHTML = `
                    <div class="col-12 text-center py-4 text-muted fs-8">
                        No appointment schedule available for this date.
                    </div>
                `;
                return;
            }

            // Update header date label
            if (this.dateLabel) {
                const dayDate = new Date(day.date + 'T00:00:00');
                const fullDateStr = dayDate.toLocaleDateString([], { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
                if (this.isGuest) {
                    this.dateLabel.textContent = `${fullDateStr} (Locked Preview)`;
                } else {
                    this.dateLabel.textContent = fullDateStr;
                }
            }

            // Check if showroom is closed (only for authenticated users)
            if (!this.isGuest && !day.is_open) {
                this.slotsContainer.innerHTML = `
                    <div class="col-12">
                        <div class="card border-0 bg-light p-4 text-center rounded-3">
                            <span class="material-symbols-outlined text-muted fs-1 mb-2">event_busy</span>
                            <h6 class="fw-bold text-dark mb-1">Showroom Closed</h6>
                            <p class="fs-8 text-muted mb-0">${day.closure_reason || 'No appointments are scheduled for this date.'}</p>
                        </div>
                    </div>
                `;
                return;
            }

            if (!day.slots || day.slots.length === 0) {
                this.slotsContainer.innerHTML = `
                    <div class="col-12 text-center py-4 text-muted fs-8">
                        No 1-hour appointment slots generated for this day.
                    </div>
                `;
                return;
            }

            // Render slot items
            day.slots.forEach(slot => {
                const col = document.createElement('div');
                col.className = 'col';

                let statusBadge = '';
                let btnClass = '';
                let isClickable = false;
                let isCustomerConfirmedBooking = false;

                if (this.isGuest || slot.status === 'LOCKED' || slot.status === 'UNAVAILABLE') {
                    btnClass = 'btn-light border-secondary-subtle bg-light text-muted opacity-75';
                    statusBadge = '<span class="badge bg-secondary-subtle text-secondary fs-9 d-inline-flex align-items-center gap-1"><span class="material-symbols-outlined fs-9" style="font-size: 12px !important;">lock</span><span>Locked</span></span>';
                    isClickable = false;
                } else if (slot.status === 'AVAILABLE') {
                    btnClass = 'btn-outline-success border-success-subtle bg-white hover-success shadow-xs';
                    statusBadge = '<span class="badge bg-success-subtle text-success fs-9">Available</span>';
                    isClickable = true;
                } else if (slot.status === 'PENDING') {
                    btnClass = 'btn-light border-warning text-dark disabled opacity-75';
                    statusBadge = '<span class="badge bg-warning-subtle text-warning-emphasis fs-9">Pending Approval</span>';
                } else if (slot.status === 'BOOKED') {
                    btnClass = 'btn-light border-primary text-dark disabled opacity-75';
                    statusBadge = '<span class="badge bg-primary-subtle text-primary fs-9">Booked</span>';
                } else if (slot.status === 'PROPOSED') {
                    btnClass = 'btn-light border-info text-dark disabled opacity-75';
                    statusBadge = '<span class="badge bg-info-subtle text-info-emphasis fs-9">Proposed Hold</span>';
                } else { // CLOSED
                    btnClass = 'btn-light border-secondary text-muted disabled opacity-50';
                    const reasonShort = slot.reason ? (slot.reason.includes('Break') ? 'Break' : 'Closed') : 'Closed';
                    statusBadge = `<span class="badge bg-secondary-subtle text-secondary fs-9">${reasonShort}</span>`;
                }

                // If customer's own booking, highlight visually and allow confirmed booking interaction
                if (!this.isGuest && slot.booking_details && slot.booking_details.is_my_booking) {
                    if (slot.booking_details.status === 'CONFIRMED' || slot.status === 'BOOKED') {
                        isCustomerConfirmedBooking = true;
                        isClickable = true;
                        btnClass = 'btn-outline-primary border-primary bg-primary-subtle text-primary shadow-xs cursor-pointer';
                        statusBadge = '<span class="badge bg-primary text-white fs-9 d-inline-flex align-items-center gap-1"><span class="material-symbols-outlined fs-9" style="font-size: 11px !important;">task_alt</span><span>Your Booking</span></span>';
                    } else {
                        statusBadge = '<span class="badge bg-primary text-white fs-9">Your Booking</span>';
                    }
                }

                const isSelected = !this.isGuest && this.selectedSlot && this.selectedSlot.slot_key === slot.slot_key;
                if (isSelected) {
                    btnClass = 'btn-success text-white shadow-sm ring-2 ring-success';
                }

                const slotBtn = document.createElement('button');
                slotBtn.type = 'button';
                slotBtn.className = `btn calendar-slot-btn w-100 py-3 px-2 d-flex flex-column align-items-center justify-content-center rounded-3 transition-all ${btnClass}`;
                if (this.isGuest || slot.status === 'LOCKED' || slot.status === 'UNAVAILABLE') {
                    slotBtn.disabled = true;
                    slotBtn.style.cursor = 'not-allowed';
                    slotBtn.title = 'Sign in to reserve showroom slots';
                    slotBtn.innerHTML = `
                        <span class="material-symbols-outlined text-secondary fs-6 mb-1">lock</span>
                        <span class="fw-bold fs-7 mb-1 text-secondary">${slot.start_time} - ${slot.end_time}</span>
                        ${statusBadge}
                    `;
                } else {
                    slotBtn.innerHTML = `
                        <span class="fw-bold fs-7 mb-1">${slot.start_time} - ${slot.end_time}</span>
                        ${statusBadge}
                    `;

                    if (isCustomerConfirmedBooking) {
                        slotBtn.title = 'Click to view confirmed appointment details or manage booking';
                        slotBtn.addEventListener('click', () => {
                            this.openCustomerBookingDetails(slot);
                        });
                    } else if (isClickable) {
                        slotBtn.addEventListener('click', () => {
                            this.selectedSlot = slot;
                            this.renderSlotsForSelectedDate();
                            this.updateSelectedPreview();
                        });
                    } else {
                        slotBtn.disabled = true;
                    }
                }

                col.appendChild(slotBtn);
                this.slotsContainer.appendChild(col);
            });
        },

        updateSelectedPreview() {
            if (this.isGuest || !this.selectedSlot) {
                if (this.previewCard) this.previewCard.classList.add('d-none');
                if (this.continueBtn) this.continueBtn.disabled = true;
                return;
            }

            if (this.previewCard && this.previewSummaryText) {
                const dayDate = new Date(this.selectedSlot.date + 'T00:00:00');
                const dateStr = dayDate.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
                this.previewSummaryText.textContent = `${dateStr} @ ${this.selectedSlot.start_time} - ${this.selectedSlot.end_time}`;
                this.previewCard.classList.remove('d-none');
            }

            if (this.continueBtn) {
                this.continueBtn.disabled = false;
            }
        },

        async openCustomerBookingDetails(slot) {
            if (!slot || !slot.booking_details) return;
            const b = slot.booking_details;
            this.activeCustomerBooking = b;

            const modalElem = document.getElementById('modalCustomerBookingDetails');
            if (!modalElem || typeof bootstrap === 'undefined') return;

            const refElem = document.getElementById('custBookingRef');
            const carElem = document.getElementById('custBookingCar');
            const dateElem = document.getElementById('custBookingDate');
            const timeElem = document.getElementById('custBookingTime');
            const locElem = document.getElementById('custBookingLocation');
            const statusElem = document.getElementById('custBookingStatus');
            const alertElem = document.getElementById('custBookingAlert');
            const cancelBtn = document.getElementById('btnCustomerCancelBooking');

            if (refElem) refElem.textContent = b.booking_number || '--';
            if (carElem) carElem.textContent = b.car_title || '--';
            if (dateElem) dateElem.textContent = b.date_display || b.date || slot.date || '--';
            if (timeElem) timeElem.textContent = b.slot_time || `${slot.start_time} - ${slot.end_time}`;
            if (locElem) locElem.textContent = b.showroom_location || 'CarVistaHub Showroom';
            if (statusElem) {
                statusElem.textContent = b.status || 'CONFIRMED';
                statusElem.className = 'badge bg-success text-white';
            }
            if (alertElem) alertElem.classList.add('d-none');
            if (cancelBtn) {
                cancelBtn.disabled = !(b.can_cancel !== false);
            }

            const modal = bootstrap.Modal.getOrCreateInstance(modalElem);
            modal.show();

            // Fetch latest confirmed details from backend (Phase B)
            const bookingId = b.booking_id || b.id;
            if (bookingId) {
                try {
                    const res = await fetch(`/bookings/api/bookings/${bookingId}/details/`, {
                        headers: {
                            'Accept': 'application/json',
                            'X-Requested-With': 'XMLHttpRequest'
                        }
                    });
                    if (res.ok) {
                        const data = await res.json();
                        if (data.success && data.booking) {
                            const fresh = data.booking;
                            this.activeCustomerBooking = fresh;
                            if (refElem) refElem.textContent = fresh.booking_number;
                            if (carElem) carElem.textContent = fresh.car_title;
                            if (dateElem) dateElem.textContent = fresh.date_display || fresh.date;
                            if (timeElem) timeElem.textContent = fresh.slot_time;
                            if (locElem) locElem.textContent = fresh.showroom_location;
                            if (statusElem) statusElem.textContent = fresh.status;
                            if (cancelBtn) cancelBtn.disabled = !fresh.can_cancel;
                        }
                    }
                } catch (_) {}
            }
        }
    };

    // =========================================================================
    // 2. Manager Calendar Controller
    // =========================================================================
    const ManagerCalendar = {
        slotsContainer: null,
        inspectorContent: null,
        inspectorPlaceholder: null,
        activeDayHeader: null,
        activeDaySubheader: null,
        dayStatsPills: null,
        alertContainer: null,
        dateInput: null,
        syncStatusText: null,

        currentDate: new Date(),
        activeDayData: null,
        selectedSlotKey: null,
        currentBookingId: null,
        pendingActionType: null,

        init(options = {}) {
            this.slotsContainer = document.getElementById('mgrSlotsContainer');
            this.inspectorContent = document.getElementById('mgrInspectorContent');
            this.inspectorPlaceholder = document.getElementById('mgrInspectorPlaceholder');
            this.activeDayHeader = document.getElementById('mgrActiveDayHeader');
            this.activeDaySubheader = document.getElementById('mgrActiveDaySubheader');
            this.dayStatsPills = document.getElementById('mgrDayStatsPills');
            this.alertContainer = document.getElementById('mgrAlertContainer');
            this.dateInput = document.getElementById('mgrDateInput');
            this.syncStatusText = document.getElementById('mgrSyncStatusText');

            if (!this.slotsContainer) return;

            // Enlarge Driving Licence modal trigger
            const btnEnlarge = document.getElementById('btnEnlargeLicense');
            const previewImg = document.getElementById('inspectLicenseImg');
            const enlargeModalElem = document.getElementById('modalEnlargeLicense');
            if (enlargeModalElem && typeof bootstrap !== 'undefined') {
                const enlargeModal = new bootstrap.Modal(enlargeModalElem);
                const openEnlarge = () => {
                    const enlargedImg = document.getElementById('enlargedLicenseImg');
                    if (previewImg && enlargedImg && previewImg.src) {
                        enlargedImg.src = previewImg.src;
                    }
                    enlargeModal.show();
                };
                if (btnEnlarge) btnEnlarge.addEventListener('click', openEnlarge);
                if (previewImg) previewImg.addEventListener('click', openEnlarge);
            }

            // Manager Review Action Buttons (Verify Document & Reject Document)
            const btnVerify = document.getElementById('btnVerifyDoc');
            const btnReject = document.getElementById('btnRejectDoc');
            const reasonModalElem = document.getElementById('modalLicenseReason');
            const reasonInput = document.getElementById('mgrActionReasonInput');
            const reasonFeedback = document.getElementById('mgrReasonFeedback');
            const reasonLabel = document.getElementById('mgrReasonLabel');
            const reasonTitle = document.getElementById('modalLicenseReasonLabel');
            const btnSubmitReason = document.getElementById('btnSubmitLicenseReason');

            let reasonModal = null;
            if (reasonModalElem && typeof bootstrap !== 'undefined') {
                reasonModal = new bootstrap.Modal(reasonModalElem);
            }

            if (btnVerify) {
                btnVerify.addEventListener('click', () => {
                    if (!this.currentBookingId) return;
                    this.performLicenseAction(this.currentBookingId, 'VERIFY', '');
                });
            }

            if (btnReject) {
                btnReject.addEventListener('click', () => {
                    if (!this.currentBookingId) return;
                    this.pendingActionType = 'REJECT';
                    if (reasonTitle) reasonTitle.textContent = 'Reject Driving Licence & Appointment';
                    if (reasonLabel) reasonLabel.textContent = 'Mandatory Rejection Reason *';
                    if (reasonInput) {
                        reasonInput.value = '';
                        reasonInput.placeholder = 'Provide clear reason for rejection (e.g. invalid document, expired licence, category mismatch)...';
                        reasonInput.classList.remove('is-invalid');
                    }
                    if (reasonModal) reasonModal.show();
                });
            }

            if (btnSubmitReason) {
                btnSubmitReason.addEventListener('click', () => {
                    if (!this.currentBookingId || !this.pendingActionType) return;
                    const reason = reasonInput ? reasonInput.value.trim() : '';
                    if (!reason) {
                        if (reasonInput) reasonInput.classList.add('is-invalid');
                        if (reasonFeedback) reasonFeedback.textContent = 'A rejection reason is mandatory to reject the document and appointment.';
                        return;
                    }
                    if (reasonInput) reasonInput.classList.remove('is-invalid');
                    if (reasonModal) reasonModal.hide();
                    this.performLicenseAction(this.currentBookingId, this.pendingActionType, reason);
                });
            }

            // Final Confirm Driving Test Button & Modal (Stage 2)
            const btnConfirm = document.getElementById('btnConfirmTestDrive');
            const confirmModalElem = document.getElementById('modalConfirmTestDrive');
            const btnSubmitConfirm = document.getElementById('btnSubmitConfirmBooking');

            let confirmModal = null;
            if (confirmModalElem && typeof bootstrap !== 'undefined') {
                confirmModal = new bootstrap.Modal(confirmModalElem);
            }

            if (btnConfirm) {
                btnConfirm.addEventListener('click', () => {
                    if (!this.currentBookingId || !this.activeInspectedSlot) return;
                    const b = this.activeInspectedSlot.booking_details;
                    const slot = this.activeInspectedSlot;

                    const ref = document.getElementById('modalConfirmBookingRef');
                    const cust = document.getElementById('modalConfirmCustName');
                    const car = document.getElementById('modalConfirmCarTitle');
                    const time = document.getElementById('modalConfirmSlotTime');
                    const lic = document.getElementById('modalConfirmLicenseStatus');

                    if (ref) ref.textContent = b ? b.booking_number : '--';
                    if (cust) cust.textContent = b ? b.customer_name : '--';
                    if (car) car.textContent = b ? b.car_title : '--';
                    if (time) time.textContent = `${slot.date} (${slot.start_time} - ${slot.end_time})`;
                    if (lic) lic.textContent = b ? (b.license_verification_status || 'VERIFIED') : 'VERIFIED';

                    if (confirmModal) confirmModal.show();
                });
            }

            if (btnSubmitConfirm) {
                btnSubmitConfirm.addEventListener('click', () => {
                    if (!this.currentBookingId) return;
                    if (confirmModal) confirmModal.hide();
                    this.performConfirmBooking(this.currentBookingId);
                });
            }

            // Mark as Completed Button & Modal (Phase E)
            const btnComplete = document.getElementById('btnCompleteTestDrive');
            const completeModalElem = document.getElementById('modalCompleteTestDrive');
            const btnSubmitComplete = document.getElementById('btnSubmitCompleteBooking');

            let completeModal = null;
            if (completeModalElem && typeof bootstrap !== 'undefined') {
                completeModal = new bootstrap.Modal(completeModalElem);
            }

            if (btnComplete) {
                btnComplete.addEventListener('click', () => {
                    if (!this.currentBookingId || !this.activeInspectedSlot) return;
                    const b = this.activeInspectedSlot.booking_details;
                    const slot = this.activeInspectedSlot;

                    const ref = document.getElementById('modalCompleteBookingRef');
                    const cust = document.getElementById('modalCompleteCustName');
                    const car = document.getElementById('modalCompleteCarTitle');
                    const time = document.getElementById('modalCompleteSlotTime');

                    if (ref) ref.textContent = b ? b.booking_number : '--';
                    if (cust) cust.textContent = b ? b.customer_name : '--';
                    if (car) car.textContent = b ? b.car_title : '--';
                    if (time) time.textContent = `${slot.date} (${slot.start_time} - ${slot.end_time})`;

                    if (completeModal) completeModal.show();
                });
            }

            if (btnSubmitComplete) {
                btnSubmitComplete.addEventListener('click', () => {
                    if (!this.currentBookingId) return;
                    if (completeModal) completeModal.hide();
                    this.performCompleteBooking(this.currentBookingId);
                });
            }

            if (options.initialDate) {
                try {
                    this.currentDate = new Date(options.initialDate + 'T00:00:00');
                } catch (_) {
                    this.currentDate = new Date();
                }
            }

            // Steppers
            const prevBtn = document.getElementById('mgrPrevDayBtn');
            const nextBtn = document.getElementById('mgrNextDayBtn');
            const todayBtn = document.getElementById('mgrTodayBtn');
            const refreshBtn = document.getElementById('mgrManualRefreshBtn');

            if (prevBtn) {
                prevBtn.addEventListener('click', () => {
                    this.currentDate = addDays(this.currentDate, -1);
                    this.syncDateInput();
                    this.loadManagerDay();
                });
            }

            if (nextBtn) {
                nextBtn.addEventListener('click', () => {
                    this.currentDate = addDays(this.currentDate, 1);
                    this.syncDateInput();
                    this.loadManagerDay();
                });
            }

            if (todayBtn) {
                todayBtn.addEventListener('click', () => {
                    this.currentDate = new Date();
                    this.syncDateInput();
                    this.loadManagerDay();
                });
            }

            if (this.dateInput) {
                this.dateInput.addEventListener('change', (e) => {
                    if (e.target.value) {
                        this.currentDate = new Date(e.target.value + 'T00:00:00');
                        this.loadManagerDay();
                    }
                });
            }

            if (refreshBtn) {
                refreshBtn.addEventListener('click', () => {
                    this.loadManagerDay(true);
                });
            }

            // Automatic polling every 30 seconds
            this.startPolling();

            // Refresh immediately when tab gains focus
            window.addEventListener('focus', () => {
                this.loadManagerDay(false);
            });
            document.addEventListener('visibilitychange', () => {
                if (document.visibilityState === 'visible') {
                    this.loadManagerDay(false);
                }
            });

            this.syncDateInput();
            this.loadManagerDay();
        },

        syncDateInput() {
            if (this.dateInput) {
                this.dateInput.value = formatDateISO(this.currentDate);
            }
            this.render7DayQuickStrip();
        },

        render7DayQuickStrip() {
            const container = document.getElementById('mgr7DayQuickStrip');
            if (!container) return;
            container.innerHTML = '';

            const today = new Date();
            today.setHours(0, 0, 0, 0);
            const currDateStr = formatDateISO(this.currentDate);

            for (let i = 0; i < 7; i++) {
                const day = addDays(today, i);
                const dayStr = formatDateISO(day);
                const isSelected = (dayStr === currDateStr);
                const dayLabel = (i === 0) ? 'Today' : day.toLocaleDateString([], { weekday: 'short' });
                const dateLabel = day.toLocaleDateString([], { month: 'short', day: 'numeric' });

                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = `btn btn-sm py-1 px-2 fs-8 rounded-2 border d-flex align-items-center gap-1 ${
                    isSelected ? 'btn-primary text-white shadow-xs' : 'btn-outline-secondary bg-white text-dark'
                }`;
                btn.innerHTML = `<span class="fw-bold">${dayLabel}</span> <span class="opacity-75 fs-9">(${dateLabel})</span>`;
                btn.addEventListener('click', () => {
                    this.currentDate = day;
                    this.syncDateInput();
                    this.loadManagerDay();
                });
                container.appendChild(btn);
            }
        },

        startPolling() {
            this.stopPolling();
            managerTimer = setInterval(() => {
                this.loadManagerDay(false);
            }, 30000); // 30 seconds for Manager
        },

        stopPolling() {
            if (managerTimer) {
                clearInterval(managerTimer);
                managerTimer = null;
            }
        },

        showAlert(msg) {
            if (!this.alertContainer) return;
            if (!msg) {
                this.alertContainer.classList.add('d-none');
                this.alertContainer.innerHTML = '';
                return;
            }
            this.alertContainer.className = 'alert alert-danger py-2 px-3 fs-8';
            this.alertContainer.innerHTML = msg;
            this.alertContainer.classList.remove('d-none');
        },

        async loadManagerDay(forceFeedback = false) {
            const reqId = ++activeManagerRequestId;
            this.showAlert(null);

            const dateStr = formatDateISO(this.currentDate);

            try {
                // Query calendar endpoint with date range [dateStr, dateStr]
                const data = await fetchCalendarAvailability(dateStr, dateStr);
                if (reqId !== activeManagerRequestId) return; // Stale request discard

                const dayData = (data.days && data.days.length > 0) ? data.days[0] : null;
                this.activeDayData = dayData;
                this.renderManagerSlots(dayData);

                if (this.syncStatusText) {
                    const nowTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                    this.syncStatusText.textContent = `Live: ${nowTime}`;
                }
            } catch (err) {
                if (reqId === activeManagerRequestId) {
                    this.showAlert(`Failed to fetch manager calendar data: ${err.message}`);
                }
            }
        },

        renderManagerSlots(dayData) {
            if (!this.slotsContainer) return;
            this.slotsContainer.innerHTML = '';

            const dayDate = new Date(formatDateISO(this.currentDate) + 'T00:00:00');
            const fullDateStr = dayDate.toLocaleDateString([], { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });

            if (this.activeDayHeader) {
                this.activeDayHeader.textContent = fullDateStr;
            }

            if (!dayData) {
                this.slotsContainer.innerHTML = `
                    <div class="text-center py-5 text-muted">
                        No schedule returned for this date.
                    </div>
                `;
                return;
            }

            if (!dayData.is_open) {
                this.slotsContainer.innerHTML = `
                    <div class="card border-0 bg-light p-4 text-center rounded-3">
                        <span class="material-symbols-outlined text-muted fs-1 mb-2">event_busy</span>
                        <h6 class="fw-bold text-dark mb-1">Showroom Closed</h6>
                        <p class="fs-8 text-muted mb-0">${dayData.closure_reason || 'Showroom is closed on this day.'}</p>
                    </div>
                `;
                if (this.dayStatsPills) this.dayStatsPills.innerHTML = '<span class="badge bg-danger">Closed</span>';
                return;
            }

            const slots = dayData.slots || [];
            let availableCount = 0;
            let bookedCount = 0;
            let pendingCount = 0;
            let closedCount = 0;

            slots.forEach(slot => {
                if (slot.status === 'AVAILABLE') availableCount++;
                else if (slot.status === 'BOOKED') bookedCount++;
                else if (slot.status === 'PENDING') pendingCount++;
                else closedCount++;
            });

            // Update stats badge pills
            if (this.dayStatsPills) {
                this.dayStatsPills.innerHTML = `
                    <span class="badge bg-success-subtle text-success border border-success-subtle fs-8">${availableCount} Available</span>
                    <span class="badge bg-warning-subtle text-warning-emphasis border border-warning-subtle fs-8">${pendingCount} Pending</span>
                    <span class="badge bg-primary-subtle text-primary border border-primary-subtle fs-8">${bookedCount} Booked</span>
                `;
            }

            slots.forEach(slot => {
                const card = document.createElement('div');
                const isSelected = (this.selectedSlotKey === slot.slot_key);

                let borderClass = 'border';
                let bgClass = 'bg-white';
                let statusBadge = '';
                let occupantSummary = '';

                if (slot.status === 'AVAILABLE') {
                    borderClass = 'border-success-subtle border-start-success';
                    statusBadge = '<span class="badge bg-success text-white fs-8">Available</span>';
                    occupantSummary = '<span class="fs-8 text-muted">Open for customer appointment</span>';
                } else if (slot.status === 'PENDING') {
                    borderClass = 'border-warning-subtle border-start-warning';
                    bgClass = 'bg-warning-subtle';
                    statusBadge = '<span class="badge bg-warning text-dark fs-8">Pending Approval</span>';
                    if (slot.booking_details) {
                        occupantSummary = `<span class="fw-bold text-dark fs-8">${slot.booking_details.customer_name}</span> &bull; <span class="text-muted fs-8">${slot.booking_details.car_title}</span>`;
                    }
                } else if (slot.status === 'BOOKED') {
                    borderClass = 'border-primary-subtle border-start-primary';
                    bgClass = 'bg-light';
                    statusBadge = '<span class="badge bg-primary text-white fs-8">Confirmed Booking</span>';
                    if (slot.booking_details) {
                        occupantSummary = `<span class="fw-bold text-dark fs-8">${slot.booking_details.customer_name}</span> &bull; <span class="text-muted fs-8">${slot.booking_details.car_title}</span>`;
                    }
                } else if (slot.status === 'PROPOSED') {
                    borderClass = 'border-info-subtle border-start-info';
                    bgClass = 'bg-info-subtle';
                    statusBadge = '<span class="badge bg-info text-dark fs-8">Manager Alternative Proposed</span>';
                    if (slot.booking_details) {
                        occupantSummary = `<span class="fw-bold text-dark fs-8">${slot.booking_details.customer_name}</span> &bull; <span class="text-muted fs-8">${slot.booking_details.car_title}</span>`;
                    }
                } else { // CLOSED
                    borderClass = 'border-secondary-subtle';
                    bgClass = 'bg-light text-muted opacity-75';
                    statusBadge = `<span class="badge bg-secondary text-white fs-8">${slot.reason || 'Closed'}</span>`;
                    occupantSummary = `<span class="fs-8 text-muted">${slot.reason || 'Showroom break / closed'}</span>`;
                }

                card.className = `card ${borderClass} ${bgClass} rounded-3 p-3 transition-all cursor-pointer ${isSelected ? 'shadow-sm ring-2 ring-primary' : 'shadow-xs'
                    }`;
                card.style.borderLeftWidth = '5px';
                card.style.cursor = 'pointer';

                card.innerHTML = `
                    <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
                        <div class="d-flex align-items-center gap-3">
                            <div class="d-flex align-items-center gap-1 text-dark fw-bold fs-6">
                                <span class="material-symbols-outlined fs-5 text-primary">schedule</span>
                                <span>${slot.start_time} - ${slot.end_time}</span>
                            </div>
                            <div class="vr d-none d-sm-block" style="height: 20px;"></div>
                            <div>${occupantSummary}</div>
                        </div>
                        <div class="d-flex align-items-center gap-2">
                            ${statusBadge}
                            <span class="material-symbols-outlined text-muted fs-6">chevron_right</span>
                        </div>
                    </div>
                `;

                card.addEventListener('click', () => {
                    this.selectedSlotKey = slot.slot_key;
                    this.renderManagerSlots(this.activeDayData);
                    this.inspectSlot(slot);
                });

                this.slotsContainer.appendChild(card);
            });
        },

        inspectSlot(slot) {
            if (!this.inspectorContent || !this.inspectorPlaceholder) return;

            if (!slot || !slot.booking_details) {
                this.inspectorContent.classList.add('d-none');
                this.inspectorPlaceholder.classList.remove('d-none');
                this.currentBookingId = null;
                return;
            }

            const b = slot.booking_details;
            this.currentBookingId = b.booking_id;
            this.activeInspectedSlot = slot;
            this.inspectorPlaceholder.classList.add('d-none');
            this.inspectorContent.classList.remove('d-none');

            const refElem = document.getElementById('inspectBookingNumber');
            const statusBadge = document.getElementById('inspectStatusBadge');
            const custName = document.getElementById('inspectCustomerName');
            const custEmail = document.getElementById('inspectCustomerEmail');
            const custPhone = document.getElementById('inspectCustomerPhone');
            const custLicenseStatus = document.getElementById('inspectCustomerLicenseStatus');
            const carTitle = document.getElementById('inspectCarTitle');
            const slotTime = document.getElementById('inspectSlotTime');
            const slotDate = document.getElementById('inspectSlotDate');
            const notesText = document.getElementById('inspectNotesText');

            if (refElem) refElem.textContent = b.booking_number || 'N/A';
            if (statusBadge) {
                statusBadge.textContent = slot.status;
                if (slot.status === 'BOOKED' || b.status === 'CONFIRMED') statusBadge.className = 'badge bg-primary text-white px-2 py-1 fs-8';
                else if (slot.status === 'PENDING') statusBadge.className = 'badge bg-warning text-dark px-2 py-1 fs-8';
                else if (slot.status === 'PROPOSED') statusBadge.className = 'badge bg-info text-dark px-2 py-1 fs-8';
                else if (slot.status === 'REJECTED' || b.status === 'REJECTED') statusBadge.className = 'badge bg-danger text-white px-2 py-1 fs-8';
                else statusBadge.className = 'badge bg-secondary text-white px-2 py-1 fs-8';
            }
            if (custName) custName.textContent = b.customer_name || 'Anonymous Customer';
            if (custEmail) custEmail.textContent = b.customer_email || 'Not provided';
            if (custPhone) custPhone.textContent = b.customer_phone || 'Not provided';
            if (custLicenseStatus) custLicenseStatus.textContent = b.license_verification_display || b.license_verification_status || 'Pending Review';
            if (carTitle) carTitle.textContent = b.car_title || 'Vehicle';
            if (slotTime) slotTime.textContent = `${slot.start_time} - ${slot.end_time}`;
            if (slotDate) slotDate.textContent = slot.date;
            if (notesText) {
                let noteMsg = b.customer_notes || 'No customer notes.';
                if (b.manager_notes) {
                    noteMsg += `\nInternal Manager Note: ${b.manager_notes}`;
                }
                if (b.rejection_reason) {
                    noteMsg += `\nRejection Reason: ${b.rejection_reason}`;
                }
                notesText.textContent = noteMsg;
            }

            // Driving Licence Document Section
            const licenseBadge = document.getElementById('inspectLicenseBadge');
            const imgContainer = document.getElementById('inspectLicenseImgContainer');
            const noDocNotice = document.getElementById('inspectNoLicenseNotice');
            const previewImg = document.getElementById('inspectLicenseImg');
            const enlargedImg = document.getElementById('enlargedLicenseImg');
            const alertElem = document.getElementById('licenseActionAlert');
            const confirmAlertElem = document.getElementById('confirmActionAlert');

            if (alertElem) alertElem.classList.add('d-none');
            if (confirmAlertElem) confirmAlertElem.classList.add('d-none');

            // Verification status badge
            const vStatus = b.license_verification_status || 'PENDING';
            const bStatus = b.status || 'PENDING';

            if (licenseBadge) {
                licenseBadge.textContent = b.license_verification_display || (vStatus === 'VERIFIED' ? 'Document Verified by Manager' : (vStatus === 'REJECTED' ? 'Document Rejected' : 'Pending Review'));
                if (vStatus === 'VERIFIED') {
                    licenseBadge.className = 'badge bg-success text-white px-2 py-1 fs-9';
                } else if (vStatus === 'REJECTED') {
                    licenseBadge.className = 'badge bg-danger text-white px-2 py-1 fs-9';
                } else {
                    licenseBadge.className = 'badge bg-warning text-dark px-2 py-1 fs-9';
                }
            }

            // Manage State Action Sections:
            // 1. PENDING / PENDING -> Verify & Reject buttons visible
            // 2. VERIFIED / PENDING -> Confirm Driving Test button visible
            // 3. Any / CONFIRMED -> Confirmed notice badge and Mark as Completed button visible
            // 4. Any / COMPLETED -> Completed notice badge visible
            // 5. Any / REJECTED -> Rejected notice badge visible
            const licenseActions = document.getElementById('inspectLicenseActions');
            const confirmSection = document.getElementById('inspectConfirmSection');
            const confirmedNotice = document.getElementById('inspectConfirmedNotice');
            const completedNotice = document.getElementById('inspectCompletedNotice');
            const rejectedNotice = document.getElementById('inspectRejectedNotice');
            const btnComplete = document.getElementById('btnCompleteTestDrive');
            const completeHint = document.getElementById('completeActionHint');

            if (licenseActions) licenseActions.classList.add('d-none');
            if (confirmSection) confirmSection.classList.add('d-none');
            if (confirmedNotice) confirmedNotice.classList.add('d-none');
            if (completedNotice) completedNotice.classList.add('d-none');
            if (rejectedNotice) rejectedNotice.classList.add('d-none');

            if (bStatus === 'COMPLETED') {
                if (completedNotice) completedNotice.classList.remove('d-none');
            } else if (bStatus === 'CONFIRMED') {
                if (confirmedNotice) confirmedNotice.classList.remove('d-none');
                if (btnComplete) {
                    if (b.can_complete) {
                        btnComplete.disabled = false;
                        btnComplete.classList.remove('disabled');
                        if (completeHint) completeHint.textContent = 'Appointment slot has concluded. Ready to mark as completed.';
                    } else {
                        btnComplete.disabled = true;
                        btnComplete.classList.add('disabled');
                        if (completeHint) completeHint.textContent = 'Available after the scheduled appointment time concludes.';
                    }
                }
            } else if (bStatus === 'REJECTED' || vStatus === 'REJECTED') {
                if (rejectedNotice) rejectedNotice.classList.remove('d-none');
            } else if (vStatus === 'VERIFIED' && bStatus === 'PENDING') {
                if (confirmSection) confirmSection.classList.remove('d-none');
            } else if (vStatus === 'PENDING' && bStatus === 'PENDING') {
                if (licenseActions) licenseActions.classList.remove('d-none');
            }

            // Document Image display
            if (b.has_license_image && b.license_image_url) {
                if (imgContainer) imgContainer.classList.remove('d-none');
                if (noDocNotice) noDocNotice.classList.add('d-none');
                if (previewImg) previewImg.src = b.license_image_url;
                if (enlargedImg) enlargedImg.src = b.license_image_url;
            } else {
                if (imgContainer) imgContainer.classList.add('d-none');
                if (noDocNotice) noDocNotice.classList.remove('d-none');
                if (previewImg) previewImg.src = '';
                if (enlargedImg) enlargedImg.src = '';
            }
        },

        async performLicenseAction(bookingId, action, reason = '') {
            const alertElem = document.getElementById('licenseActionAlert');
            if (alertElem) {
                alertElem.className = 'mt-2 fs-8 alert alert-info py-1 px-2';
                alertElem.textContent = 'Updating verification status...';
                alertElem.classList.remove('d-none');
            }
            try {
                const res = await fetch(`/bookings/api/manager/bookings/${bookingId}/license-action/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken'),
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify({ action, reason })
                });
                const data = await res.json().catch(() => ({}));
                if (res.ok && data.success) {
                    if (alertElem) {
                        alertElem.className = 'mt-2 fs-8 alert alert-success py-1 px-2';
                        alertElem.textContent = data.message || 'Status updated successfully.';
                    }
                    if (this.activeInspectedSlot && this.activeInspectedSlot.booking_details) {
                        this.activeInspectedSlot.booking_details.license_verification_status = data.status;
                        this.activeInspectedSlot.booking_details.license_verification_display = data.display;
                        if (data.booking_status) {
                            this.activeInspectedSlot.booking_details.status = data.booking_status;
                        }
                        this.inspectSlot(this.activeInspectedSlot);
                    }
                    // Live sync: refresh day slots
                    this.loadManagerDay();
                } else {
                    if (alertElem) {
                        alertElem.className = 'mt-2 fs-8 alert alert-danger py-1 px-2';
                        alertElem.textContent = data.error || 'Failed to update verification status.';
                    }
                }
            } catch (err) {
                if (alertElem) {
                    alertElem.className = 'mt-2 fs-8 alert alert-danger py-1 px-2';
                    alertElem.textContent = err.message || 'Network error.';
                }
            }
        },

        async performConfirmBooking(bookingId) {
            const alertElem = document.getElementById('confirmActionAlert');
            if (alertElem) {
                alertElem.className = 'mt-2 fs-8 alert alert-info py-1 px-2';
                alertElem.textContent = 'Confirming appointment and locking showroom slot...';
                alertElem.classList.remove('d-none');
            }
            try {
                const res = await fetch(`/bookings/api/manager/bookings/${bookingId}/confirm/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken'),
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });
                const data = await res.json().catch(() => ({}));
                if (res.ok && data.success) {
                    if (alertElem) {
                        alertElem.className = 'mt-2 fs-8 alert alert-success py-1 px-2';
                        alertElem.textContent = data.message || 'Appointment confirmed successfully.';
                    }
                    if (this.activeInspectedSlot && this.activeInspectedSlot.booking_details) {
                        this.activeInspectedSlot.booking_details.status = 'CONFIRMED';
                        this.activeInspectedSlot.status = 'BOOKED';
                        this.inspectSlot(this.activeInspectedSlot);
                    }
                    // Live sync: refresh day slots
                    this.loadManagerDay();
                } else {
                    if (alertElem) {
                        alertElem.className = 'mt-2 fs-8 alert alert-danger py-1 px-2';
                        alertElem.textContent = data.error || 'Failed to confirm booking.';
                    }
                }
            } catch (err) {
                if (alertElem) {
                    alertElem.className = 'mt-2 fs-8 alert alert-danger py-1 px-2';
                    alertElem.textContent = err.message || 'Network error.';
                }
            }
        },

        async performCompleteBooking(bookingId) {
            const alertElem = document.getElementById('confirmActionAlert');
            if (alertElem) {
                alertElem.className = 'mt-2 fs-8 alert alert-info py-1 px-2';
                alertElem.textContent = 'Marking appointment as completed...';
                alertElem.classList.remove('d-none');
            }
            try {
                const res = await fetch(`/bookings/api/manager/bookings/${bookingId}/complete/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken'),
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });
                const data = await res.json().catch(() => ({}));
                if (res.ok && data.success) {
                    if (alertElem) {
                        alertElem.className = 'mt-2 fs-8 alert alert-success py-1 px-2';
                        alertElem.textContent = data.message || 'Appointment marked as completed successfully.';
                    }
                    if (this.activeInspectedSlot && this.activeInspectedSlot.booking_details) {
                        this.activeInspectedSlot.booking_details.status = 'COMPLETED';
                        this.inspectSlot(this.activeInspectedSlot);
                    }
                    // Live sync: refresh day slots
                    this.loadManagerDay();
                } else {
                    if (alertElem) {
                        alertElem.className = 'mt-2 fs-8 alert alert-danger py-1 px-2';
                        alertElem.textContent = data.error || 'Failed to mark appointment completed.';
                    }
                }
            } catch (err) {
                if (alertElem) {
                    alertElem.className = 'mt-2 fs-8 alert alert-danger py-1 px-2';
                    alertElem.textContent = err.message || 'Network error.';
                }
            }
        }
    };

    // Expose globally
    window.CarVistaCalendar = {
        initCustomerModal: () => CustomerCalendar.init(),
        initManagerCalendar: (opts) => ManagerCalendar.init(opts),
    };

    // Auto-init on page load if elements are present
    document.addEventListener('DOMContentLoaded', () => {
        if (document.getElementById('showroomCalendarModal')) {
            CustomerCalendar.init();
        }
    });

})(window, document);

