/**
 * CarVistaHub - Compare Cars Feature Script
 * Manages slot selection, searchable modal, duplicate prevention,
 * localStorage persistence, and dynamic side-by-side comparison rendering.
 */

function initComparePage() {
    // -------------------------------------------------------------------------
    // 1. State Management
    // -------------------------------------------------------------------------
    const state = {
        slots: {
            1: null,
            2: null,
            3: null,
        },
        activeSlot3: false,
        currentSelectingSlot: 1,
        allCarsCache: [],
        isLoadingComparison: false,
    };

    const STORAGE_KEY = 'carvistahub_compare_cars';

    // DOM Elements
    const slotCard1 = document.getElementById('slot-card-1');
    const slotCard2 = document.getElementById('slot-card-2');
    const slotCard3 = document.getElementById('slot-card-3');
    const slotCol3 = document.getElementById('slot-col-3');
    const btnAddSlot = document.getElementById('btnAddSlot');
    const btnCompareSubmit = document.getElementById('btnCompareSubmit');
    const btnClearAll = document.getElementById('btnClearAll');
    const compareHelperText = document.getElementById('compareHelperText');

    // Modal Elements
    const carSelectModalEl = document.getElementById('carSelectModal');
    let carSelectModalInstance = null;
    if (carSelectModalEl && window.bootstrap && window.bootstrap.Modal) {
        carSelectModalInstance = window.bootstrap.Modal.getOrCreateInstance(carSelectModalEl);
    }
    const carModalSearchInput = document.getElementById('carModalSearchInput');
    const btnClearModalSearch = document.getElementById('btnClearModalSearch');
    const modalCarList = document.getElementById('modalCarList');
    const modalLoadingSpinner = document.getElementById('modalLoadingSpinner');
    const modalEmptyState = document.getElementById('modalEmptyState');
    const modalResultCount = document.getElementById('modalResultCount');
    const modalSlotIndicator = document.getElementById('modalSlotIndicator');

    // Results Elements
    const comparisonResultsSection = document.getElementById('comparisonResultsSection');
    const compareTableHead = document.getElementById('compareTableHead');
    const compareTableBody = document.getElementById('compareTableBody');
    const comparisonSubtitle = document.getElementById('comparisonSubtitle');
    const btnModifySelection = document.getElementById('btnModifySelection');
    const btnClearComparison = document.getElementById('btnClearComparison');

    // -------------------------------------------------------------------------
    // 2. LocalStorage & Initialization
    // -------------------------------------------------------------------------
    function saveToLocalStorage() {
        const selectedIds = [];
        if (state.slots[1]) selectedIds.push(state.slots[1].id);
        if (state.slots[2]) selectedIds.push(state.slots[2].id);
        if (state.activeSlot3 && state.slots[3]) selectedIds.push(state.slots[3].id);
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(selectedIds));
        } catch (err) {
            console.warn('LocalStorage save error:', err);
        }
    }

    function getFromLocalStorage() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return [];
            const parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed : [];
        } catch (e) {
            return [];
        }
    }

    // -------------------------------------------------------------------------
    // 3. UI Slot Rendering
    // -------------------------------------------------------------------------
    function renderSlot(slotNum) {
        let cardEl;
        if (slotNum === 1) cardEl = slotCard1;
        else if (slotNum === 2) cardEl = slotCard2;
        else if (slotNum === 3) cardEl = slotCard3;
        if (!cardEl) return;

        const car = state.slots[slotNum];

        if (!car) {
            // Render Empty State
            cardEl.className = 'compare-slot-card compare-slot-empty';
            let removeSlotBtnHtml = '';
            if (slotNum === 3) {
                removeSlotBtnHtml = `
                    <button type="button" class="btn btn-sm btn-icon-square text-muted border-0 position-absolute top-0 end-0 m-2 btn-remove-slot" title="Remove 3rd Slot" aria-label="Remove 3rd Slot">
                        <span class="material-symbols-outlined fs-5">close</span>
                    </button>
                `;
            }
            cardEl.innerHTML = `
                ${removeSlotBtnHtml}
                <div class="compare-icon-circle">
                    <span class="material-symbols-outlined fs-2">directions_car</span>
                </div>
                <h3 class="fs-5 fw-bold text-dark mb-1">Choose Car ${slotNum}</h3>
                <p class="text-muted fs-7 mb-4">${slotNum === 3 ? 'Optionally compare a 3rd model.' : 'Select a brand and model to start comparing.'}</p>
                <button type="button" class="btn btn-autohub-primary rounded-pill px-4 py-2 btn-select-car" data-slot="${slotNum}" aria-label="Select Car ${slotNum}">
                    <span class="material-symbols-outlined fs-5 align-middle me-1">add_circle</span>
                    Select Car
                </button>
            `;
        } else {
            // Render Filled State
            cardEl.className = 'compare-slot-card compare-slot-filled';
            const imgHtml = car.image_url
                ? `<img src="${car.image_url}" alt="${car.title}" class="compare-slot-thumb mb-3" loading="lazy">`
                : `<div class="compare-slot-thumb mb-3 d-flex align-items-center justify-content-center text-muted bg-light"><span class="material-symbols-outlined fs-1">directions_car</span></div>`;

            let removeSlotBtnHtml = '';
            if (slotNum === 3) {
                removeSlotBtnHtml = `
                    <button type="button" class="btn btn-sm btn-icon-square text-muted border-0 position-absolute top-0 end-0 m-2 btn-remove-slot" title="Remove 3rd Slot" aria-label="Remove 3rd Slot">
                        <span class="material-symbols-outlined fs-5">close</span>
                    </button>
                `;
            }

            cardEl.innerHTML = `
                ${removeSlotBtnHtml}
                <div class="d-flex align-items-center justify-content-between mb-2">
                    <span class="badge bg-primary text-white text-uppercase px-2 py-1 rounded-pill fs-8 fw-bold">
                        ${car.brand_name}
                    </span>
                    <span class="badge ${car.is_available ? 'bg-success-subtle text-success border border-success-subtle' : 'bg-danger-subtle text-danger border border-danger-subtle'} rounded-pill fs-8">
                        ● ${car.is_available ? 'Available' : 'Unavailable'}
                    </span>
                </div>
                ${imgHtml}
                <h3 class="fs-6 fw-bold text-dark mb-1 text-truncate" title="${car.title}">${car.title}</h3>
                <div class="fs-6 fw-bold text-primary mb-3">
                    ${car.formatted_price} <span class="text-muted fw-normal fs-8">Ex-Showroom</span>
                </div>
                <div class="d-flex gap-2 mt-auto">
                    <button type="button" class="btn btn-sm btn-outline-primary rounded-pill flex-grow-1 btn-replace-car" data-slot="${slotNum}" aria-label="Replace Car ${slotNum}">
                        <span class="material-symbols-outlined fs-6 align-middle me-1">swap_horiz</span>
                        Replace
                    </button>
                    <button type="button" class="btn btn-sm btn-outline-danger rounded-pill px-3 btn-remove-car" data-slot="${slotNum}" aria-label="Remove Car ${slotNum}">
                        <span class="material-symbols-outlined fs-6 align-middle me-1">close</span>
                        Remove
                    </button>
                </div>
            `;
        }
    }

    function updateControls() {
        const filledSlots = [state.slots[1], state.slots[2], (state.activeSlot3 ? state.slots[3] : null)].filter(Boolean);
        const count = filledSlots.length;

        // Compare Submit Button
        if (count >= 2) {
            btnCompareSubmit.removeAttribute('disabled');
            compareHelperText.innerHTML = `<span class="text-success fw-semibold">✓ Ready to compare!</span> Click <strong>Compare Cars</strong> to view detailed side-by-side specifications.`;
        } else {
            btnCompareSubmit.setAttribute('disabled', 'true');
            compareHelperText.textContent = 'Select at least two different cars to compare specifications and features.';
        }

        // Clear All Button
        if (count > 0 || state.activeSlot3) {
            btnClearAll.classList.remove('d-none');
            btnClearAll.classList.add('d-inline-flex');
        } else {
            btnClearAll.classList.add('d-none');
            btnClearAll.classList.remove('d-inline-flex');
        }

        // Add Another Car Control
        if (state.activeSlot3) {
            btnAddSlot.classList.add('d-none');
        } else {
            btnAddSlot.classList.remove('d-none');
        }
    }

    // -------------------------------------------------------------------------
    // 4. Modal Search & Car Selection
    // -------------------------------------------------------------------------
    async function loadAllCars(forceRefresh = false) {
        if (state.allCarsCache.length > 0 && !forceRefresh) {
            return state.allCarsCache;
        }
        if (modalLoadingSpinner) modalLoadingSpinner.classList.remove('d-none');
        if (modalCarList) modalCarList.style.display = 'none';
        if (modalEmptyState) modalEmptyState.classList.add('d-none');

        try {
            const res = await fetch('/api/cars/compare/search/');
            if (!res.ok) throw new Error('Search API returned HTTP ' + res.status);
            const data = await res.json();
            state.allCarsCache = data.cars || [];
            return state.allCarsCache;
        } catch (err) {
            console.error('Error fetching car list:', err);
            return [];
        } finally {
            if (modalLoadingSpinner) modalLoadingSpinner.classList.add('d-none');
            if (modalCarList) modalCarList.style.display = 'flex';
        }
    }

    function renderModalList(cars, query = '') {
        modalCarList.innerHTML = '';
        const currentSlot = state.currentSelectingSlot;

        // Check which car IDs are already occupied in other slots
        const occupiedCarIds = {};
        for (let s = 1; s <= 3; s++) {
            if (s !== currentSlot && state.slots[s]) {
                occupiedCarIds[state.slots[s].id] = s;
            }
        }

        if (cars.length === 0) {
            modalEmptyState.classList.remove('d-none');
            modalResultCount.textContent = '0 cars found';
            return;
        }

        modalEmptyState.classList.add('d-none');
        modalResultCount.textContent = `${cars.length} car${cars.length === 1 ? '' : 's'} available`;

        cars.forEach((car) => {
            const isOccupiedInSlot = occupiedCarIds[car.id];
            const isAlreadyChosenHere = state.slots[currentSlot] && state.slots[currentSlot].id === car.id;

            const card = document.createElement('div');
            card.className = `modal-car-item d-flex flex-column flex-sm-row align-items-sm-center justify-content-between gap-3 ${isOccupiedInSlot ? 'disabled' : ''}`;

            const imgHtml = car.image_url
                ? `<img src="${car.image_url}" alt="${car.title}" class="modal-car-thumb" loading="lazy">`
                : `<div class="modal-car-thumb d-flex align-items-center justify-content-center text-muted bg-light"><span class="material-symbols-outlined fs-2">directions_car</span></div>`;

            let actionHtml = '';
            if (isOccupiedInSlot) {
                actionHtml = `
                    <button type="button" class="btn btn-sm btn-secondary rounded-pill px-3" disabled title="Already in Slot ${isOccupiedInSlot}">
                        Already in Car ${isOccupiedInSlot}
                    </button>
                `;
            } else if (isAlreadyChosenHere) {
                actionHtml = `
                    <button type="button" class="btn btn-sm btn-outline-success rounded-pill px-3" disabled>
                        ✓ Currently Selected
                    </button>
                `;
            } else {
                actionHtml = `
                    <button type="button" class="btn btn-sm btn-autohub-primary rounded-pill px-4 btn-select-this-car" data-car-id="${car.id}">
                        Select
                    </button>
                `;
            }

            card.innerHTML = `
                <div class="d-flex align-items-center gap-3">
                    ${imgHtml}
                    <div>
                        <div class="d-flex align-items-center gap-2 mb-1">
                            <span class="badge bg-primary text-white text-uppercase fs-8">${car.brand_name}</span>
                            <span class="badge bg-light text-muted border fs-8">${car.body_type}</span>
                        </div>
                        <h4 class="fs-6 fw-bold text-dark mb-1">${car.title}</h4>
                        <div class="fw-bold text-primary fs-7">
                            ${car.formatted_price} <span class="text-muted fw-normal fs-8">Ex-Showroom</span>
                        </div>
                    </div>
                </div>
                <div class="d-flex align-items-center gap-2 justify-content-end">
                    ${actionHtml}
                </div>
            `;

            // Attach event listener to select button
            const btn = card.querySelector('.btn-select-this-car');
            if (btn) {
                btn.addEventListener('click', () => {
                    chooseCarForSlot(currentSlot, car);
                });
            }

            modalCarList.appendChild(card);
        });
    }

    function openModalForSlot(slotNum) {
        state.currentSelectingSlot = slotNum;
        modalSlotIndicator.textContent = `Assigning to Car ${slotNum}`;
        carModalSearchInput.value = '';
        btnClearModalSearch.classList.add('d-none');

        if (carSelectModalInstance) {
            carSelectModalInstance.show();
        }

        loadAllCars().then((cars) => {
            renderModalList(cars);
        });
    }

    function chooseCarForSlot(slotNum, car) {
        state.slots[slotNum] = car;
        saveToLocalStorage();
        renderSlot(slotNum);
        updateControls();

        if (carSelectModalInstance) {
            carSelectModalInstance.hide();
        }

        // If >= 2 cars, refresh the comparison table seamlessly
        const filledSlots = [state.slots[1], state.slots[2], (state.activeSlot3 ? state.slots[3] : null)].filter(Boolean);
        if (filledSlots.length >= 2) {
            executeComparison(false); // do not scroll again on auto-update
        }
    }

    function removeCarFromSlot(slotNum) {
        state.slots[slotNum] = null;
        saveToLocalStorage();
        renderSlot(slotNum);
        updateControls();

        const alertContainer = document.getElementById('compareAlertContainer');
        if (alertContainer) alertContainer.classList.add('d-none');

        const filledSlots = [state.slots[1], state.slots[2], (state.activeSlot3 ? state.slots[3] : null)].filter(Boolean);
        if (filledSlots.length < 2) {
            comparisonResultsSection.classList.add('d-none');
        } else if (!comparisonResultsSection.classList.contains('d-none')) {
            executeComparison(false);
        }
    }

    // Modal Search Filtering
    let searchDebounceTimer = null;
    function handleModalSearch() {
        const query = (carModalSearchInput.value || '').trim().toLowerCase();
        if (query) {
            btnClearModalSearch.classList.remove('d-none');
        } else {
            btnClearModalSearch.classList.add('d-none');
        }

        clearTimeout(searchDebounceTimer);
        searchDebounceTimer = setTimeout(() => {
            if (!query) {
                renderModalList(state.allCarsCache);
                return;
            }
            const filtered = state.allCarsCache.filter((car) => {
                const titleMatch = (car.title || '').toLowerCase().includes(query);
                const brandMatch = (car.brand_name || '').toLowerCase().includes(query);
                const bodyMatch = (car.body_type || '').toLowerCase().includes(query);
                return titleMatch || brandMatch || bodyMatch;
            });
            renderModalList(filtered, query);
        }, 150);
    }

    if (carModalSearchInput) {
        carModalSearchInput.addEventListener('input', handleModalSearch);
    }
    if (btnClearModalSearch) {
        btnClearModalSearch.addEventListener('click', () => {
            carModalSearchInput.value = '';
            carModalSearchInput.focus();
            handleModalSearch();
        });
    }

    if (carSelectModalEl) {
        carSelectModalEl.addEventListener('shown.bs.modal', () => {
            if (carModalSearchInput) {
                carModalSearchInput.focus();
            }
        });
    }

    // -------------------------------------------------------------------------
    // 5. Comparison Table Execution & Rendering
    // -------------------------------------------------------------------------
    async function executeComparison(shouldScroll = true) {
        const activeCars = [state.slots[1], state.slots[2], (state.activeSlot3 ? state.slots[3] : null)].filter(Boolean);
        if (activeCars.length < 2) return;

        const ids = activeCars.map((c) => c.id).join(',');
        btnCompareSubmit.setAttribute('disabled', 'true');
        btnCompareSubmit.innerHTML = `
            <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
            Comparing...
        `;

        try {
            const res = await fetch(`/api/cars/compare/details/?ids=${ids}`);
            const data = await res.json();

            if (!res.ok || data.status !== 'success') {
                alert(data.message || 'Unable to retrieve comparison data. Please try again.');
                return;
            }

            renderComparisonResults(data);

            comparisonResultsSection.classList.remove('d-none');
            if (shouldScroll) {
                comparisonResultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        } catch (err) {
            console.error('Comparison error:', err);
            alert('A network error occurred while comparing cars. Please check your connection and try again.');
        } finally {
            btnCompareSubmit.removeAttribute('disabled');
            btnCompareSubmit.innerHTML = `
                <span class="material-symbols-outlined fs-5">compare_arrows</span>
                Compare Cars
            `;
        }
    }

    function renderComparisonResults(data) {
        const cars = data.cars || [];
        const groups = data.groups || [];
        const colCount = cars.length + 1; // 1 label column + N car columns

        comparisonSubtitle.textContent = `Comparing ${cars.length} models side-by-side based on verified database specifications.`;

        // 1. Build THEAD Summary Cards
        let theadHtml = `
            <tr>
                <th scope="col" class="compare-label-col border-bottom-0 pb-3">
                    <span class="fs-7 text-uppercase tracking-wide text-muted fw-bold d-block">Comparison</span>
                    <span class="fs-5 fw-bold text-dark">Selected Models</span>
                </th>
        `;

        cars.forEach((car) => {
            const bestPriceBadge = car.is_lowest_price
                ? `<div class="compare-best-price">★ Lowest Price</div>`
                : '';

            theadHtml += `
                <th scope="col" class="compare-car-col pb-3">
                    <div class="px-2">
                        <img src="${car.image_url || '/static/images/placeholder.svg'}" alt="${car.title}" class="compare-slot-thumb mb-2 shadow-sm" loading="lazy">
                        <span class="badge bg-primary text-white text-uppercase px-2 py-1 rounded-pill fs-8 fw-bold mb-1 d-inline-block">
                            ${car.brand_name}
                        </span>
                        <h4 class="fs-6 fw-bold text-dark mb-1 text-truncate" title="${car.title}">${car.title}</h4>
                        <div class="fs-6 fw-bold text-primary mb-1">
                            ${car.formatted_price}
                        </div>
                        ${bestPriceBadge}
                        <div class="mt-2 mb-2">
                            <span class="badge ${car.is_available ? 'bg-success-subtle text-success border border-success-subtle' : 'bg-danger-subtle text-danger border border-danger-subtle'} rounded-pill fs-8">
                                ● ${car.stock_status}
                            </span>
                        </div>
                        <a href="${car.detail_url}" class="btn btn-sm btn-autohub-primary rounded-pill w-100 py-1 fs-7">
                            View Details
                        </a>
                    </div>
                </th>
            `;
        });

        theadHtml += `</tr>`;
        compareTableHead.innerHTML = theadHtml;

        // 2. Build TBODY Specification Groups
        let tbodyHtml = '';

        groups.forEach((group) => {
            // Group Title Header Row
            tbodyHtml += `
                <tr class="compare-group-header">
                    <td colspan="${colCount}">${group.name}</td>
                </tr>
            `;

            // Field Rows
            (group.fields || []).forEach((field) => {
                const diffClass = field.is_different ? 'compare-row-diff' : '';
                const diffBadge = field.is_different ? `<span class="compare-diff-badge">Differs</span>` : '';

                tbodyHtml += `<tr class="${diffClass}">`;
                tbodyHtml += `
                    <th scope="row" class="compare-label-col">
                        <span>${field.label}</span>
                        ${diffBadge}
                    </th>
                `;

                (field.values || []).forEach((val, idx) => {
                    const car = cars[idx];
                    let displayVal = val;

                    if (val === '—' || val === null || val === undefined || val === '' || val === 'Unknown') {
                        displayVal = `<span class="text-muted" title="Unverified / Information not available">—</span>`;
                    } else if (val === true || val === 'Yes') {
                        displayVal = `<span class="badge bg-success-subtle text-success border border-success-subtle rounded-pill px-2 py-1 fs-8 fw-semibold d-inline-flex align-items-center gap-1" title="Confirmed Available"><span class="material-symbols-outlined fs-7">check</span> Yes</span>`;
                    } else if (val === false || val === 'No') {
                        displayVal = `<span class="badge bg-danger-subtle text-danger border border-danger-subtle rounded-pill px-2 py-1 fs-8 fw-semibold d-inline-flex align-items-center gap-1" title="Confirmed Absent"><span class="material-symbols-outlined fs-7">close</span> No</span>`;
                    } else if (field.is_price && car && car.is_lowest_price) {
                        // For Ex-Showroom Price row, highlight lowest price if different
                        displayVal = `<span class="fw-bold text-success">${val}</span> <span class="compare-best-price">Lowest</span>`;
                    } else if (field.is_price) {
                        displayVal = `<span class="fw-bold text-primary">${val}</span>`;
                    }

                    tbodyHtml += `<td class="compare-car-col">${displayVal}</td>`;
                });

                tbodyHtml += `</tr>`;
            });
        });

        compareTableBody.innerHTML = tbodyHtml;
    }

    // -------------------------------------------------------------------------
    // 6. Global Event Listeners & Delegations
    // -------------------------------------------------------------------------

    // Click "Select Car" or "Replace" or "Remove" on slots
    document.addEventListener('click', (e) => {
        // Select Car Button
        const btnSelect = e.target.closest('.btn-select-car');
        if (btnSelect) {
            e.preventDefault();
            const slot = parseInt(btnSelect.getAttribute('data-slot'), 10);
            openModalForSlot(slot);
            return;
        }

        // Replace Button
        const btnReplace = e.target.closest('.btn-replace-car');
        if (btnReplace) {
            e.preventDefault();
            const slot = parseInt(btnReplace.getAttribute('data-slot'), 10);
            openModalForSlot(slot);
            return;
        }

        // Remove Button
        const btnRemove = e.target.closest('.btn-remove-car');
        if (btnRemove) {
            e.preventDefault();
            const slot = parseInt(btnRemove.getAttribute('data-slot'), 10);
            removeCarFromSlot(slot);
            return;
        }

        // Remove 3rd Slot Button
        const btnRemoveSlot = e.target.closest('.btn-remove-slot');
        if (btnRemoveSlot) {
            e.preventDefault();
            state.activeSlot3 = false;
            state.slots[3] = null;
            slotCol3.classList.add('d-none');
            btnAddSlot.classList.remove('d-none');
            saveToLocalStorage();
            renderSlot(3);
            updateControls();

            const filledSlots = [state.slots[1], state.slots[2]].filter(Boolean);
            if (filledSlots.length < 2) {
                comparisonResultsSection.classList.add('d-none');
            } else if (!comparisonResultsSection.classList.contains('d-none')) {
                executeComparison(false);
            }
            return;
        }
    });

    // Alert Banner Helper
    function showCompareAlert(message, type = 'info') {
        const container = document.getElementById('compareAlertContainer');
        const alertEl = document.getElementById('compareAlert');
        const msgEl = document.getElementById('compareAlertMessage');
        const iconEl = document.getElementById('compareAlertIcon');
        if (!container || !alertEl || !msgEl) return;

        alertEl.className = `alert alert-${type} alert-dismissible fade show d-flex align-items-center gap-2 rounded-3 shadow-sm mb-0`;
        if (iconEl) {
            iconEl.textContent = type === 'warning' ? 'warning' : (type === 'danger' ? 'error' : 'info');
        }
        msgEl.innerHTML = message;
        container.classList.remove('d-none');
    }

    const btnCloseCompareAlert = document.getElementById('btnCloseCompareAlert');
    if (btnCloseCompareAlert) {
        btnCloseCompareAlert.addEventListener('click', () => {
            const container = document.getElementById('compareAlertContainer');
            if (container) container.classList.add('d-none');
        });
    }

    function getFirstAvailableSlot() {
        if (!state.slots[1]) return 1;
        if (!state.slots[2]) return 2;
        if (!state.slots[3]) return 3;
        return null; // All 3 slots occupied
    }

    // Add 3rd Slot
    if (btnAddSlot) {
        btnAddSlot.addEventListener('click', () => {
            state.activeSlot3 = true;
            slotCol3.classList.remove('d-none');
            btnAddSlot.classList.add('d-none');
            renderSlot(3);
            updateControls();
            saveToLocalStorage();
        });
    }

    // Compare Cars Submit
    if (btnCompareSubmit) {
        btnCompareSubmit.addEventListener('click', () => {
            executeComparison(true);
        });
    }

    // Clear All
    function handleClearAll() {
        state.slots[1] = null;
        state.slots[2] = null;
        state.slots[3] = null;
        state.activeSlot3 = false;
        slotCol3.classList.add('d-none');
        btnAddSlot.classList.remove('d-none');

        try {
            localStorage.removeItem(STORAGE_KEY);
        } catch (e) { }

        const alertContainer = document.getElementById('compareAlertContainer');
        if (alertContainer) alertContainer.classList.add('d-none');

        renderSlot(1);
        renderSlot(2);
        renderSlot(3);
        updateControls();
        comparisonResultsSection.classList.add('d-none');
    }

    if (btnClearAll) {
        btnClearAll.addEventListener('click', handleClearAll);
    }
    if (btnClearComparison) {
        btnClearComparison.addEventListener('click', handleClearAll);
    }

    // Modify Selection
    if (btnModifySelection) {
        btnModifySelection.addEventListener('click', () => {
            const section = document.getElementById('selection-section');
            if (section) {
                section.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    }

    // -------------------------------------------------------------------------
    // 7. Initial Restore from Server / LocalStorage
    // -------------------------------------------------------------------------
    async function restoreInitialSelections() {
        // Step 1: Pre-load the catalog of available cars using the existing search API
        const allCars = await loadAllCars();
        const carMap = new Map();
        allCars.forEach((c) => {
            carMap.set(c.id, c);
            carMap.set(String(c.id), c);
            if (c.slug) {
                carMap.set(c.slug.toLowerCase(), c);
            }
        });

        // Step 2: Retrieve existing persisted selections from localStorage
        let savedIds = getFromLocalStorage();
        if (!Array.isArray(savedIds)) savedIds = [];
        savedIds = savedIds.map(Number).filter((id) => carMap.has(id));

        // Step 3: Populate current slots with the persisted cars
        state.slots[1] = null;
        state.slots[2] = null;
        state.slots[3] = null;
        state.activeSlot3 = false;

        savedIds.forEach((id, index) => {
            const slotNum = index + 1;
            if (slotNum <= 3) {
                state.slots[slotNum] = carMap.get(id);
                if (slotNum === 3) {
                    state.activeSlot3 = true;
                }
            }
        });

        // Step 4: Parse incoming query parameter (?car=slug or ?cars=slug1,slug2)
        const urlParams = new URLSearchParams(window.location.search);
        const rawIncoming = urlParams.get('car') || urlParams.get('cars') || '';
        let incomingTokens = [];
        if (rawIncoming) {
            incomingTokens = rawIncoming.split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
        } else if (Array.isArray(window.CARVISTAHUB_INITIAL_CARS) && window.CARVISTAHUB_INITIAL_CARS.length > 0) {
            // Fallback from Django context if query param was consumed
            if (savedIds.length === 0) {
                incomingTokens = window.CARVISTAHUB_INITIAL_CARS.map(String);
            }
        }

        let alertMessage = null;
        let alertType = 'info';

        if (incomingTokens.length > 0) {
            incomingTokens.forEach((token) => {
                const targetCar = carMap.get(token) || carMap.get(parseInt(token, 10));
                if (targetCar) {
                    // Check if targetCar is already in any slot
                    const isAlreadySelected = [state.slots[1], state.slots[2], state.slots[3]].some(c => c && c.id === targetCar.id);
                    if (isAlreadySelected) {
                        alertMessage = `<strong>${targetCar.title}</strong> is already in your comparison selection.`;
                        alertType = 'info';
                    } else {
                        const targetSlot = getFirstAvailableSlot();
                        if (targetSlot === null) {
                            // All 3 slots occupied
                            alertMessage = `Comparison limit reached (maximum 3 cars). Please remove a car from the selection below before adding <strong>${targetCar.title}</strong>.`;
                            alertType = 'warning';
                        } else {
                            state.slots[targetSlot] = targetCar;
                            if (targetSlot === 3) {
                                state.activeSlot3 = true;
                            }
                        }
                    }
                }
            });

            // Persist the updated slots to localStorage
            saveToLocalStorage();

            // Clean query parameter from browser address bar without page reload
            if (window.history && window.history.replaceState) {
                const cleanUrl = window.location.pathname;
                window.history.replaceState({}, document.title, cleanUrl);
            }
        }

        // Step 5: Render slot UI and sync controls
        if (state.activeSlot3 || state.slots[3]) {
            state.activeSlot3 = true;
            slotCol3.classList.remove('d-none');
            btnAddSlot.classList.add('d-none');
        } else {
            slotCol3.classList.add('d-none');
            btnAddSlot.classList.remove('d-none');
        }

        renderSlot(1);
        renderSlot(2);
        if (state.activeSlot3) {
            renderSlot(3);
        }
        updateControls();

        // Step 6: Display notification alert if triggered
        if (alertMessage) {
            showCompareAlert(alertMessage, alertType);
        }

        // Step 7: Auto-run side-by-side comparison if >= 2 cars selected
        const activeCars = [state.slots[1], state.slots[2], (state.activeSlot3 ? state.slots[3] : null)].filter(Boolean);
        if (activeCars.length >= 2) {
            executeComparison(false);
        } else {
            comparisonResultsSection.classList.add('d-none');
        }
    }

    // Start initialization
    restoreInitialSelections();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initComparePage);
} else {
    initComparePage();
}
