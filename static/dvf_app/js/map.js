
(function () {
    const page = document.getElementById('dvf-map-page');
    if (!page) {
        return;
    }

    const DVF = window.DVF || (window.DVF = {});

    const heatmapUrl = page.dataset.heatmapUrl;
    const communeOptionsUrl = page.dataset.communeOptionsUrl;

    const FRANCE_CENTER = [46.5, 2];
    const FRANCE_BOUNDS = [
        [51.2, -5.0],
        [41.0, 9.7],
    ];

    const headerKpis = {
        totalSales: document.getElementById('kpi-total-sales'),
        totalValue: document.getElementById('kpi-total-value'),
        medianPrice: document.getElementById('kpi-median-price'),
        period: document.getElementById('kpi-period'),
    };

    const summaryKpis = {
        totalSales: document.getElementById('summary-total-sales'),
        totalValue: document.getElementById('summary-total-value'),
        medianPrice: document.getElementById('summary-median-price'),
    };

    const elements = {
        departmentSelect: document.getElementById('department-select'),
        communeSelect: document.getElementById('commune-select'),
        filtersForm: document.getElementById('filters'),
    };

    const numberFormatter = new Intl.NumberFormat('fr-FR');
    const dateFormatter = new Intl.DateTimeFormat('fr-FR', {
        month: 'short',
        year: 'numeric',
    });

    function setText(node, value) {
        if (node) {
            node.textContent = value;
        }
    }

    function formatNumber(value) {
        return numberFormatter.format(value || 0);
    }

    function formatEuro(value) {
        if (value == null) {
            return null;
        }
        return `${formatNumber(Math.round(value))} €`;
    }

    function formatPricePerSqm(value) {
        if (value == null) {
            return null;
        }
        return `${formatNumber(Math.round(value))} €/m²`;
    }

    function formatDateRange(minIso, maxIso) {
        if (!minIso && !maxIso) {
            return null;
        }
        const minDate = minIso ? new Date(minIso) : null;
        const maxDate = maxIso ? new Date(maxIso) : null;
        if (minDate && maxDate) {
            if (minDate.getTime() === maxDate.getTime()) {
                return dateFormatter.format(minDate);
            }
            return `${dateFormatter.format(minDate)} – ${dateFormatter.format(maxDate)}`;
        }
        const target = minDate || maxDate;
        return target ? dateFormatter.format(target) : null;
    }

    function updateKpiWidgets(status = 'ready', metrics = null) {
        const placeholder = status === 'loading' ? '...' : '—';
        const hasMetrics = status === 'ready' && metrics;

        const totalSalesText = hasMetrics
            ? formatNumber(metrics.total_sales || 0)
            : placeholder;

        const totalValueText = hasMetrics
            ? (metrics.total_value == null
                ? '—'
                : formatEuro(metrics.total_value) || '0 €')
            : placeholder;

        const medianPriceText = hasMetrics
            ? (metrics.median_price_sqm == null
                ? '—'
                : formatPricePerSqm(metrics.median_price_sqm))
            : placeholder;

        const periodText = hasMetrics
            ? (formatDateRange(metrics.date_min, metrics.date_max) || '—')
            : placeholder;

        setText(headerKpis.totalSales, totalSalesText);
        setText(headerKpis.totalValue, totalValueText);
        setText(headerKpis.medianPrice, medianPriceText);
        setText(headerKpis.period, periodText);

        setText(summaryKpis.totalSales, totalSalesText);
        setText(summaryKpis.totalValue, totalValueText);
        setText(summaryKpis.medianPrice, medianPriceText);
    }

    DVF.setKpiMetrics = (metrics, status = 'ready') => {
        updateKpiWidgets(status, metrics);
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

    function resetMapView() {
        map.fitBounds(FRANCE_BOUNDS, { padding: [30, 30] });
    }

    function renderMarkers(payload) {
        const summary = payload?.summary || {};
        const points = payload?.points || [];
        const level = summary.level || 'commune';

        updateKpiWidgets('ready', summary);

        markersLayer.clearLayers();

        if (!points.length) {
            resetMapView();
            return;
        }

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

        updateKpiWidgets('loading');

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
            updateKpiWidgets('error');
            markersLayer.clearLayers();
            resetMapView();
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
