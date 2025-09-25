(function () {
    'use strict';

    const container = document.getElementById('dvf-charts');
    if (!container || typeof Chart === 'undefined') {
        return;
    }

    const chartsUrl = container.dataset.chartsUrl;
    if (!chartsUrl) {
        return;
    }

    const TOP_LIMIT = 10;
    const palette = ['#4f46e5', '#f97316', '#0ea5e9', '#22c55e', '#a855f7', '#ef4444'];

    const cards = {
        top: container.querySelector('[data-chart="top-communes"]'),
        time: container.querySelector('[data-chart="time-series"]'),
        box: container.querySelector('[data-chart="price-boxplot"]'),
        mutation: container.querySelector('[data-chart="mutation-stack"]'),
    };

    const numberFormatter = new Intl.NumberFormat('fr-FR');
    const currencyFormatter = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 });

    const state = {
        metric: 'sales_count',
        lastPayload: null,
        controller: null,
    };

    let boxplotRegistered = false;

    function ensureBoxplotRegistered() {
        if (boxplotRegistered) {
            return true;
        }
        if (typeof Chart === 'undefined' || !Chart.registry) {
            return false;
        }
        try {
            if (Chart.registry.getController && Chart.registry.getController('boxplot')) {
                boxplotRegistered = true;
                return true;
            }
        } catch (error) {
            // ignore lookup errors
        }
        const globalPlugin = window.ChartjsChartBoxplot || window.chartjsChartBoxplot || window.ChartBoxPlot;
        if (!globalPlugin) {
            return false;
        }
        const registrables = [
            globalPlugin.BoxPlotController,
            globalPlugin.BoxPlotChart,
            globalPlugin.BoxAndWiskers || globalPlugin.BoxAndWhiskers,
            globalPlugin.ViolinController,
            globalPlugin.ViolinChart,
            globalPlugin.Violin,
        ].filter(Boolean);
        if (!registrables.length) {
            return false;
        }
        try {
            Chart.register.apply(Chart, registrables);
            boxplotRegistered = true;
            return true;
        } catch (error) {
            console.warn('Boxplot plugin registration failed', error);
            return false;
        }
    }

    const contextLabelEl = document.getElementById('charts-context-label');
    const badgesEl = document.getElementById('charts-badges');
    const scopeLabelEl = document.getElementById('top-communes-scope');
    const form = document.getElementById('filters');
    const departmentSelect = document.getElementById('department-select');
    const communeSelect = document.getElementById('commune-select');

    function formatNumber(value) {
        return numberFormatter.format(value || 0);
    }

    function formatCurrency(value) {
        return currencyFormatter.format(Math.round(value || 0));
    }

    function formatShort(value) {
        const absolute = Math.abs(value || 0);
        if (absolute >= 1_000_000_000) {
            return (value / 1_000_000_000).toFixed(1).replace(/\.0$/, '') + 'B';
        }
        if (absolute >= 1_000_000) {
            return (value / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M';
        }
        if (absolute >= 1_000) {
            return (value / 1_000).toFixed(1).replace(/\.0$/, '') + 'k';
        }
        return formatNumber(value);
    }

    function toCode(value) {
        return (value || '').trim().toUpperCase();
    }

    function setCardState(card, status, message) {
        if (!card) {
            return;
        }
        const placeholder = card.querySelector('.chart-placeholder');
        card.classList.remove('is-loading', 'is-empty');
        if (status === 'loading') {
            if (placeholder) {
                placeholder.textContent = message || 'Chargement...';
            }
            card.classList.add('is-loading');
        } else if (status === 'empty') {
            if (placeholder) {
                placeholder.textContent = message || 'Aucune donnee disponible';
            }
            card.classList.add('is-empty');
        } else if (status === 'error') {
            if (placeholder) {
                placeholder.textContent = message || 'Erreur de chargement';
            }
            card.classList.add('is-empty');
        } else if (placeholder && message) {
            placeholder.textContent = message;
        }
    }

    function getCurrentParams() {
        const params = {};
        const department = toCode(departmentSelect ? departmentSelect.value : '');
        const commune = toCode(communeSelect ? communeSelect.value : '');
        if (department) {
            params.department = department;
        }
        if (commune) {
            params.commune = commune;
        }
        return params;
    }

    const metricButtons = container.querySelectorAll('.chart-toggle[data-metric]');
    metricButtons.forEach((button) => {
        button.addEventListener('click', () => {
            const metric = button.dataset.metric;
            if (!metric || metric === state.metric) {
                return;
            }
            state.metric = metric;
            metricButtons.forEach((btn) => {
                btn.classList.toggle('is-active', btn === button);
            });
            if (state.lastPayload) {
                renderTopChart(state.lastPayload.top_communes);
            }
        });
    });

    const topChart = createTopChart();
    const timeChart = createTimeSeriesChart();
    const boxChart = createBoxplotChart();
    const mutationChart = createMutationChart();

    function createTopChart() {
        if (!cards.top) {
            return null;
        }
        const canvas = cards.top.querySelector('canvas');
        if (!canvas) {
            return null;
        }
        return new Chart(canvas.getContext('2d'), {
            type: 'bar',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Nombre de ventes',
                        data: [],
                        backgroundColor: [],
                        borderColor: [],
                        borderWidth: 1,
                        borderRadius: 10,
                        borderSkipped: false,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                indexAxis: 'y',
                scales: {
                    x: {
                        beginAtZero: true,
                        grid: {
                            color: 'rgba(79, 70, 229, 0.08)',
                        },
                        ticks: {
                            callback: (value) => formatShort(value),
                        },
                    },
                    y: {
                        grid: {
                            display: false,
                        },
                        ticks: {
                            color: 'rgba(15, 23, 42, 0.75)',
                        },
                    },
                },
                plugins: {
                    legend: {
                        display: false,
                    },
                    tooltip: {
                        callbacks: {
                            label(context) {
                                const chart = context.chart;
                                const items = chart.$linkedItems || [];
                                const item = items[context.dataIndex];
                                if (!item) {
                                    return formatNumber(context.parsed.x);
                                }
                                return [
                                    'Nb ventes: ' + formatNumber(item.sales_count || 0),
                                    'Volume ventes: ' + formatCurrency(item.total_value || 0) + ' EUR',
                                ];
                            },
                        },
                    },
                },
            },
        });
    }

    function createTimeSeriesChart() {
        if (!cards.time) {
            return null;
        }
        const canvas = cards.time.querySelector('canvas');
        if (!canvas) {
            return null;
        }
        return new Chart(canvas.getContext('2d'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Nombre de ventes',
                        data: [],
                        borderColor: '#4f46e5',
                        backgroundColor: 'rgba(79, 70, 229, 0.18)',
                        tension: 0.35,
                        pointRadius: 2,
                        yAxisID: 'y',
                        fill: true,
                    },
                    {
                        label: 'Volume ventes',
                        data: [],
                        borderColor: '#f97316',
                        backgroundColor: 'rgba(249, 115, 22, 0.15)',
                        tension: 0.35,
                        pointRadius: 2,
                        yAxisID: 'y1',
                        fill: true,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                interaction: {
                    mode: 'index',
                    intersect: false,
                },
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            unit: 'month',
                            tooltipFormat: 'MMM yyyy',
                        },
                        ticks: {
                            maxRotation: 0,
                            autoSkip: false,
                            source: 'data',
                        },
                        grid: {
                            color: 'rgba(15, 23, 42, 0.06)',
                        },
                    },
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Nb ventes',
                        },
                        grid: {
                            color: 'rgba(79, 70, 229, 0.08)',
                        },
                    },
                    y1: {
                        position: 'right',
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Volume ventes',
                        },
                        grid: {
                            drawOnChartArea: false,
                        },
                        ticks: {
                            callback: (value) => formatShort(value) + ' EUR',
                        },
                    },
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                    },
                    tooltip: {
                        callbacks: {
                            label(context) {
                                const chart = context.chart;
                                const points = chart.$linkedPoints || [];
                                const point = points[context.dataIndex];
                                if (!point) {
                                    return formatNumber(context.parsed.y);
                                }
                                if (context.datasetIndex === 0) {
                                    return 'Nb ventes: ' + formatNumber(point.sales_count || 0);
                                }
                                return 'Volume ventes: ' + formatCurrency(point.total_value || 0) + ' EUR';
                            },
                        },
                    },
                },
            },
        });
    }

    function createBoxplotChart() {
        if (!cards.box) {
            return null;
        }
        if (!ensureBoxplotRegistered()) {
            console.warn('Chart.js boxplot plugin not registered');
            setCardState(cards.box, 'error', 'Boxplot indisponible');
            return null;
        }
        const canvas = cards.box.querySelector('canvas');
        if (!canvas) {
            return null;
        }
        try {
            return new Chart(canvas.getContext('2d'), {
                type: 'boxplot',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'Prix au m2',
                            data: [],
                            backgroundColor: 'rgba(79, 70, 229, 0.25)',
                            borderColor: '#4f46e5',
                            borderWidth: 1.5,
                            outlierRadius: 2,
                            outlierBackgroundColor: '#4f46e5',
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                callback: (value) => formatNumber(value) + ' EUR',
                            },
                            grid: {
                                color: 'rgba(79, 70, 229, 0.08)',
                            },
                        },
                    },
                    plugins: {
                        legend: {
                            display: false,
                        },
                        tooltip: {
                            callbacks: {
                                label(context) {
                                    const stats = context.raw || {};
                                    const count = stats.count ? formatNumber(stats.count) : '0';
                                    const lines = [
                                        'Median: ' + formatNumber(stats.median || 0) + ' EUR',
                                        'Q1: ' + formatNumber(stats.q1 || 0) + ' EUR',
                                        'Q3: ' + formatNumber(stats.q3 || 0) + ' EUR',
                                        'Plage: ' + formatNumber(stats.min || 0) + ' ↔ ' + formatNumber(stats.max || 0) + ' EUR',
                                        'Echantillons: ' + count,
                                    ];
                                    if (typeof stats.rawMin === 'number' && stats.rawMin < (stats.min || stats.rawMin)) {
                                        lines.push('Min reel: ' + formatNumber(stats.rawMin) + ' EUR');
                                    }
                                    if (typeof stats.rawMax === 'number' && stats.rawMax > (stats.max || stats.rawMax)) {
                                        lines.push('Max reel: ' + formatNumber(stats.rawMax) + ' EUR');
                                    }
                                    if (Array.isArray(stats.outliers) && stats.outliers.length) {
                                        lines.push('Outliers: ' + formatNumber(stats.outliers.length));
                                    }
                                    return lines;
                                },
                            },
                        },
                    },
                },
            });
        } catch (error) {
            console.warn('Boxplot chart init failed', error);
            setCardState(cards.box, 'error', 'Boxplot indisponible');
            return null;
        }
    }

    function createMutationChart() {
        if (!cards.mutation) {
            return null;
        }
        const canvas = cards.mutation.querySelector('canvas');
        if (!canvas) {
            return null;
        }
        return new Chart(canvas.getContext('2d'), {
            type: 'bar',
            data: {
                labels: [],
                datasets: [],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                scales: {
                    x: {
                        stacked: true,
                        grid: {
                            display: false,
                        },
                    },
                    y: {
                        stacked: true,
                        beginAtZero: true,
                        ticks: {
                            callback: (value) => formatNumber(value),
                        },
                        grid: {
                            color: 'rgba(79, 70, 229, 0.08)',
                        },
                    },
                },
                plugins: {
                    legend: {
                        position: 'top',
                    },
                    tooltip: {
                        callbacks: {
                            label(context) {
                                const value = context.parsed.y || 0;
                                return context.dataset.label + ': ' + formatNumber(value);
                            },
                        },
                    },
                },
            },
        });
    }

    function updateSelectionMeta(payload) {
        const selection = payload && payload.selection ? payload.selection : {};
        let label = 'France entiere';
        if (selection.level === 'commune' && selection.commune) {
            label = selection.commune.name + ' (' + selection.commune.code + ')';
        } else if (selection.department) {
            const name = selection.department.name || ('Departement ' + selection.department.code);
            label = name + ' (' + selection.department.code + ')';
        }
        if (contextLabelEl) {
            contextLabelEl.textContent = label;
        }
        if (badgesEl) {
            badgesEl.innerHTML = '';
            const entries = selection && payload && payload.type_totals ? Object.entries(payload.type_totals) : [];
            entries.forEach(([name, count]) => {
                const badge = document.createElement('span');
                badge.className = 'badge';
                badge.textContent = name + ': ' + formatNumber(count);
                badgesEl.appendChild(badge);
            });
        }
    }

    function renderTopChart(topData) {
        if (!cards.top || !topChart) {
            return;
        }
        const items = topData && Array.isArray(topData.items) ? topData.items : [];
        if (!items.length) {
            setCardState(cards.top, 'empty', 'Aucune donnee disponible');
            if (scopeLabelEl) {
                const scopeText = topData && topData.scope_label ? topData.scope_label : 'France entiere';
                scopeLabelEl.textContent = scopeText + ' - Top 0';
            }
            topChart.data.labels = [];
            topChart.data.datasets[0].data = [];
            topChart.data.datasets[0].backgroundColor = [];
            topChart.data.datasets[0].borderColor = [];
            topChart.update('none');
            return;
        }
        setCardState(cards.top, 'ready');
        topChart.$linkedItems = items;
        topChart.data.labels = items.map((item) => item.label || item.code);
        const metric = state.metric === 'total_value' ? 'total_value' : 'sales_count';
        const label = metric === 'sales_count' ? 'Nombre de ventes' : 'Volume ventes';
        topChart.data.datasets[0].label = label;
        topChart.data.datasets[0].data = items.map((item) => {
            const value = metric === 'sales_count' ? item.sales_count : item.total_value;
            return value || 0;
        });
        topChart.data.datasets[0].backgroundColor = items.map((item) => (
            item.is_selected ? 'rgba(236, 72, 153, 0.78)' : 'rgba(79, 70, 229, 0.65)'
        ));
        topChart.data.datasets[0].borderColor = items.map((item) => (
            item.is_selected ? '#ec4899' : '#4f46e5'
        ));
        if (scopeLabelEl) {
            const scopeText = topData && topData.scope_label ? topData.scope_label : 'France entiere';
            const limitValue = topData && topData.limit ? Math.min(topData.limit, items.length) : items.length;
            scopeLabelEl.textContent = scopeText + ' - Top ' + (limitValue || 0);
        }
        topChart.update();
    }

    function renderTimeSeries(seriesData) {
        if (!cards.time || !timeChart) {
            return;
        }
        const points = seriesData && Array.isArray(seriesData.points) ? seriesData.points : [];
        if (!points.length) {
            setCardState(cards.time, 'empty', 'Aucune donnee disponible');
            timeChart.data.labels = [];
            timeChart.data.datasets.forEach((dataset) => {
                dataset.data = [];
            });
            timeChart.update('none');
            return;
        }
        setCardState(cards.time, 'ready');
        timeChart.$linkedPoints = points;
        timeChart.data.labels = points.map((point) => point.month);
        timeChart.data.datasets[0].data = points.map((point) => point.sales_count || 0);
        timeChart.data.datasets[1].data = points.map((point) => point.total_value || 0);
        if (timeChart.options && timeChart.options.scales && timeChart.options.scales.x) {
            timeChart.options.scales.x.min = points[0].month;
            timeChart.options.scales.x.max = points[points.length - 1].month;
        }
        timeChart.update();
    }

    function renderBoxplot(boxData) {
        if (!cards.box || !boxChart) {
            if (cards.box && !boxChart) {
                setCardState(cards.box, 'error', 'Boxplot indisponible');
            }
            return;
        }
        const items = boxData && Array.isArray(boxData.items) ? boxData.items : [];
        if (!items.length) {
            setCardState(cards.box, 'empty', 'Aucune donnee disponible');
            boxChart.data.labels = [];
            boxChart.data.datasets[0].data = [];
            boxChart.update('none');
            return;
        }
        setCardState(cards.box, 'ready');
        boxChart.data.labels = items.map((item) => item.label);
        boxChart.data.datasets[0].data = items.map((item) => item.stats || {});
        const displayValues = items
            .map((item) => item.stats || {})
            .filter((stats) => typeof stats.whiskerHigh === 'number' && typeof stats.whiskerLow === 'number');
        if (displayValues.length && boxChart.options && boxChart.options.scales && boxChart.options.scales.y) {
            const maxValue = Math.max(...displayValues.map((stats) => stats.whiskerHigh));
            const minValue = Math.min(...displayValues.map((stats) => stats.whiskerLow));
            boxChart.options.scales.y.suggestedMax = maxValue * 1.05;
            boxChart.options.scales.y.suggestedMin = Math.max(0, minValue * 0.95);
        }
        boxChart.update();
    }

    function renderMutation(stackData) {
        if (!cards.mutation || !mutationChart) {
            return;
        }
        const labels = stackData && Array.isArray(stackData.labels) ? stackData.labels : [];
        const series = stackData && Array.isArray(stackData.series) ? stackData.series : [];
        if (!labels.length || !series.length) {
            setCardState(cards.mutation, 'empty', 'Aucune donnee disponible');
            mutationChart.data.labels = [];
            mutationChart.data.datasets = [];
            mutationChart.update('none');
            return;
        }
        setCardState(cards.mutation, 'ready');
        mutationChart.data.labels = labels;
        mutationChart.data.datasets = series.map((serie, index) => ({
            label: serie.label,
            data: serie.data,
            backgroundColor: palette[index % palette.length],
            stack: 'mutation',
            borderWidth: 1,
        }));
        mutationChart.update();
    }

    function loadCharts(params) {
        if (!chartsUrl) {
            return;
        }
        Object.values(cards).forEach((card) => setCardState(card, 'loading', 'Chargement...'));
        if (window.DVF && typeof window.DVF.setKpiMetrics === 'function') {
            window.DVF.setKpiMetrics(null, 'loading');
        }
        if (state.controller) {
            state.controller.abort();
        }
        const controller = new AbortController();
        state.controller = controller;
        const url = new URL(chartsUrl, window.location.origin);
        Object.entries(params || {}).forEach(([key, value]) => {
            if (value) {
                url.searchParams.set(key, value);
            }
        });
        url.searchParams.set('top_limit', String(TOP_LIMIT));
        fetch(url.toString(), {
            headers: { Accept: 'application/json' },
            signal: controller.signal,
        })
            .then((response) => {
                if (!response.ok) {
                    throw new Error('Statut ' + response.status);
                }
                return response.json();
            })
            .then((payload) => {
                if (controller.signal.aborted) {
                    return;
                }
                if (state.controller === controller) {
                    state.controller = null;
                }
                state.lastPayload = payload;
                updateSelectionMeta(payload);
                if (window.DVF && typeof window.DVF.setKpiMetrics === 'function') {
                    window.DVF.setKpiMetrics(payload.metrics || null, 'ready');
                }
                renderTopChart(payload.top_communes);
                renderTimeSeries(payload.time_series);
                renderBoxplot(payload.price_boxplot);
                renderMutation(payload.mutation_stack);
            })
            .catch((error) => {
                if (controller.signal.aborted) {
                    return;
                }
                if (state.controller === controller) {
                    state.controller = null;
                }
                if (window.DVF && typeof window.DVF.setKpiMetrics === 'function') {
                    window.DVF.setKpiMetrics(null, 'error');
                }
                console.error('Erreur lors du chargement des graphiques DVF', error);
                Object.values(cards).forEach((card) => setCardState(card, 'error', 'Erreur de chargement'));
            });
    }

    if (departmentSelect) {
        departmentSelect.addEventListener('change', () => {
            const params = { department: toCode(departmentSelect.value) };
            loadCharts(params);
        });
    }

    if (form) {
        form.addEventListener('submit', (event) => {
            event.preventDefault();
            loadCharts(getCurrentParams());
        });
    }

    loadCharts(getCurrentParams());
})();
