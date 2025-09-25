(function () {
    const page = document.getElementById('dvf-map-page');
    if (!page) {
        return;
    }

    const heatmapUrl = page.dataset.heatmapUrl;
    const communeOptionsUrl = page.dataset.communeOptionsUrl;

    const FRANCE_CENTER = [46.5, 2];
    const FRANCE_BOUNDS = [
        [51.2, -5.0],
        [41.0, 9.7],
    ];

    const elements = {
        departmentSelect: document.getElementById('department-select'),
        communeSelect: document.getElementById('commune-select'),
        filtersForm: document.getElementById('filters'),
        statTotal: document.querySelector('#stat-total p'),
        statEntitiesTitle: document.getElementById('stat-entities-title'),
        statEntitiesValue: document.querySelector('#stat-entities p'),
    };

    const map = L.map('dvf-map', {
        zoomControl: false,
        minZoom: 4,
        maxZoom: 18,
    }).setView(FRANCE_CENTER, 5);

    L.control.zoom({ position: 'bottomright' }).addTo(map);

    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a> contributors',
    }).addTo(map);

    map.fitBounds(FRANCE_BOUNDS, { padding: [30, 30] });

    const markersLayer = L.layerGroup().addTo(map);
    let latestRequestId = 0;

    function formatNumber(value) {
        return new Intl.NumberFormat('fr-FR').format(value || 0);
    }

    function getFillColor(scale) {
        if (scale >= 0.66) {
            return 'rgba(79, 70, 229, 0.9)';
        }
        if (scale >= 0.33) {
            return 'rgba(129, 140, 248, 0.8)';
        }
        return 'rgba(196, 181, 253, 0.75)';
    }

    function escapeHtml(value) {
        return (value || '').replace(/[&<>"']/g, (char) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        })[char] || char);
    }

    function buildPopup(level, item, intensity) {
        const name = escapeHtml(item.name);
        const subtitle = level === 'department'
            ? `Code departement ${escapeHtml(item.code)}`
            : `Departement ${escapeHtml(item.department_code || '')}`;
        const lines = [`<div><strong>Transactions DVF :</strong> ${formatNumber(intensity)}</div>`];

        if (level === 'department') {
            lines.push(`<div><strong>Communes couvertes :</strong> ${formatNumber(item.commune_count || 0)}</div>`);
            lines.push(`<div><strong>Adresses BAN :</strong> ${formatNumber(item.address_count || 0)}</div>`);
        } else {
            lines.push(`<div><strong>Adresses BAN recensees :</strong> ${formatNumber(item.address_count || 0)}</div>`);
            if (item.postal_codes && item.postal_codes.length) {
                lines.push(`<div><strong>Codes postaux :</strong> ${item.postal_codes.map(escapeHtml).join(', ')}</div>`);
            }
        }

        return `
            <div class="dvf-map-popup">
                <div class="popup-title">${name}</div>
                <div class="popup-subtitle">${subtitle}</div>
                <div class="popup-section">${lines.join('')}</div>
            </div>
        `;
    }

    function resetView(level) {
        elements.statTotal.textContent = 'Aucune transaction dans ce perimetre';
        elements.statEntitiesTitle.textContent = level === 'department'
            ? 'Departements representes'
            : 'Communes representees';
        elements.statEntitiesValue.textContent = level === 'department'
            ? '0 departement'
            : '0 commune';
        map.fitBounds(FRANCE_BOUNDS, { padding: [30, 30] });
    }

    function updateSummary(summary) {
        const level = summary.level || 'commune';
        elements.statTotal.textContent = `${formatNumber(summary.total_sales)} ventes`;

        const label = level === 'department'
            ? 'Departements representes'
            : 'Communes representees';
        elements.statEntitiesTitle.textContent = label;

        const unit = level === 'department' ? 'departements' : 'communes';
        elements.statEntitiesValue.textContent = `${formatNumber(summary.entity_count)} ${unit}`;
    }

    function renderMarkers(payload) {
        const summary = payload?.summary || {};
        const points = payload?.points || [];
        const level = summary.level || 'commune';

        markersLayer.clearLayers();

        if (!points.length) {
            resetView(level);
            return;
        }

        updateSummary(summary);

        const bounds = [];
        const maxSales = summary.max_sales || 1;

        points.forEach((item) => {
            if (item.centroid_lat == null || item.centroid_lon == null) {
                return;
            }

            const intensity = item.sales_count || 0;
            const scale = maxSales > 0 ? Math.sqrt(intensity / maxSales) : 0;
            const baseRadius = level === 'department' ? 2.5 : 4;
            const radius = baseRadius + scale * (level === 'department' ? 8 : 16);
            const fillOpacity = 0.25 + 0.45 * scale;

            const marker = L.circleMarker([item.centroid_lat, item.centroid_lon], {
                radius,
                fillColor: getFillColor(scale),
                color: 'rgba(79, 70, 229, 0.5)',
                weight: 1,
                fillOpacity,
            });

            marker.bindPopup(buildPopup(level, item, intensity), { className: 'dvf-map-popup' });
            marker.addTo(markersLayer);
            bounds.push([item.centroid_lat, item.centroid_lon]);
        });

        if (bounds.length) {
            map.fitBounds(bounds, { padding: [40, 40] });
        }
    }

    async function loadHeatmap(params) {
        const requestId = ++latestRequestId;
        const url = new URL(heatmapUrl, window.location.origin);

        Object.entries(params || {}).forEach(([key, value]) => {
            if (value) {
                url.searchParams.set(key, value);
            }
        });

        elements.statTotal.textContent = 'Chargement...';
        elements.statEntitiesTitle.textContent = 'Chargement';
        elements.statEntitiesValue.textContent = '...';

        try {
            const response = await fetch(url.toString(), { headers: { Accept: 'application/json' } });
            if (!response.ok) {
                throw new Error(`Statut ${response.status}`);
            }
            const payload = await response.json();
            if (requestId !== latestRequestId) {
                return;
            }
            renderMarkers(payload);
        } catch (error) {
            console.error('Erreur lors du chargement des donnees DVF', error);
            elements.statTotal.textContent = 'Erreur de chargement';
            elements.statEntitiesTitle.textContent = 'Communes representees';
            elements.statEntitiesValue.textContent = '-';
            markersLayer.clearLayers();
            map.fitBounds(FRANCE_BOUNDS, { padding: [30, 30] });
        }
    }

    async function refreshCommuneOptions(departmentCode) {
        const select = elements.communeSelect;
        select.innerHTML = '<option value="">Toutes les communes</option>';
        select.disabled = true;

        if (!departmentCode) {
            return;
        }

        try {
            const url = new URL(communeOptionsUrl, window.location.origin);
            url.searchParams.set('department', departmentCode);
            const response = await fetch(url.toString(), { headers: { Accept: 'application/json' } });
            if (!response.ok) {
                throw new Error(`Statut ${response.status}`);
            }
            const payload = await response.json();
            payload.communes.forEach((item) => {
                const option = document.createElement('option');
                option.value = item.code_commune;
                option.textContent = `${item.code_commune} - ${item.name}`;
                select.appendChild(option);
            });
            select.disabled = false;
        } catch (error) {
            console.error('Erreur lors du chargement des communes', error);
        }
    }

    elements.departmentSelect.addEventListener('change', (event) => {
        const departmentCode = event.target.value;
        elements.communeSelect.value = '';
        refreshCommuneOptions(departmentCode);
        loadHeatmap({ department: departmentCode });
    });

    elements.filtersForm.addEventListener('submit', (event) => {
        event.preventDefault();
        loadHeatmap({
            department: elements.departmentSelect.value,
            commune: elements.communeSelect.value,
        });
    });

    loadHeatmap({});
})();
