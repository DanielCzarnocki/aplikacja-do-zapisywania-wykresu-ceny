// Initialize the chart
const chartOptions = {
    layout: {
        textColor: '#d1d4dc',
        background: { type: 'solid', color: '#151924' },
    },
    grid: {
        vertLines: { color: 'rgba(42, 46, 57, 0.5)' },
        horzLines: { color: 'rgba(42, 46, 57, 0.5)' },
    },
    crosshair: {
        mode: LightweightCharts.CrosshairMode.Normal,
    },
    rightPriceScale: {
        borderColor: 'rgba(42, 46, 57, 1)',
    },
    timeScale: {
        borderColor: 'rgba(42, 46, 57, 1)',
        timeVisible: true,
        secondsVisible: false,
    },
};

const chartContainer = document.getElementById('chart');
const chart = LightweightCharts.createChart(chartContainer, chartOptions);

const candlestickSeries = chart.addCandlestickSeries({
    upColor: '#089981',
    downColor: '#f23645',
    borderVisible: false,
    wickUpColor: '#089981',
    wickDownColor: '#f23645',
});

const mainLineSeries = chart.addLineSeries({
    color: '#FFEB3B',
    lineWidth: 2,
    crosshairMarkerVisible: true,
    lastValueVisible: false,
});

// Average position price lines
const longAvgSeries = chart.addLineSeries({
    color: '#2196F3',
    lineWidth: 1,
    lineStyle: LightweightCharts.LineStyle.Dashed,
    crosshairMarkerVisible: false,
    lastValueVisible: true,
    title: 'L Avg',
});

const shortAvgSeries = chart.addLineSeries({
    color: '#E040FB',
    lineWidth: 1,
    lineStyle: LightweightCharts.LineStyle.Dashed,
    crosshairMarkerVisible: false,
    lastValueVisible: true,
    title: 'S Avg',
});

// Target price lines
const longTargetSeries = chart.addLineSeries({
    color: '#FF9800',
    lineWidth: 2,
    lineStyle: LightweightCharts.LineStyle.Dotted,
    crosshairMarkerVisible: false,
    lastValueVisible: true,
    title: 'L Cel',
});

const shortTargetSeries = chart.addLineSeries({
    color: '#FF4081',
    lineWidth: 2,
    lineStyle: LightweightCharts.LineStyle.Dotted,
    crosshairMarkerVisible: false,
    lastValueVisible: true,
    title: 'S Cel',
});

// Auto-resize chart
new ResizeObserver(entries => {
    if (entries.length === 0 || entries[0].target !== chartContainer) { return; }
    const newRect = entries[0].contentRect;
    chart.applyOptions({ height: newRect.height, width: newRect.width });
}).observe(chartContainer);

// Helper for formatting time (HH:MM:SS format)
function formatCountdown(milliseconds) {
    if (milliseconds <= 0) return "00:00";
    const totalSeconds = Math.floor(milliseconds / 1000);
    const h = Math.floor(totalSeconds / 3600);
    const m = Math.floor((totalSeconds % 3600) / 60);
    const s = totalSeconds % 60;

    if (h > 0) {
        return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

// Variables to track our active candle and countdown UI
let currentCandleTracker = null;
let lastKnownPrice = 0;
let isLoadingHistory = false;
let oldestDataTime = null; // in milliseconds, because server expects ms timestamp (but chart uses seconds)
let allCandlesData = [];
let allIndicatorData = [];
let allMarkers = [];
let allLongAvgData = [];
let allShortAvgData = [];
let allLongTargetData = [];
let allShortTargetData = [];
let currentInterval = '1m';

// Map trend to color for indicator line
function trendColor(trend) {
    if (trend === 1) return '#089981';   // green
    if (trend === -1) return '#f23645'; // red
    return '#FFEB3B';                    // yellow (neutral)
}

// Transform raw indicator data: add per-point color, extract avg price arrays
function processIndicatorData(rawData) {
    const lineData = [];
    const longAvg = [];
    const shortAvg = [];
    const longTarget = [];
    const shortTarget = [];
    for (const pt of rawData) {
        lineData.push({ time: pt.time, value: pt.value, color: trendColor(pt.trend) });
        if (pt.L_blue != null) longAvg.push({ time: pt.time, value: pt.L_blue });
        if (pt.S_blue != null) shortAvg.push({ time: pt.time, value: pt.S_blue });
        if (pt.L_cel != null) longTarget.push({ time: pt.time, value: pt.L_cel });
        if (pt.S_cel != null) shortTarget.push({ time: pt.time, value: pt.S_cel });
    }
    return { lineData, longAvg, shortAvg, longTarget, shortTarget };
}

// --- Multiplier persistence ---
function getMnoznikLong() {
    return parseFloat(document.getElementById('mnoznik-long')?.value) || 10;
}
function getMnoznikShort() {
    return parseFloat(document.getElementById('mnoznik-short')?.value) || 10;
}
function getMnoznikParams() {
    return `&mnoznik_long=${getMnoznikLong()}&mnoznik_short=${getMnoznikShort()}`;
}

// Load saved values from localStorage
window.addEventListener('DOMContentLoaded', () => {
    const savedL = localStorage.getItem('mnoznik_long');
    const savedS = localStorage.getItem('mnoznik_short');
    if (savedL) document.getElementById('mnoznik-long').value = savedL;
    if (savedS) document.getElementById('mnoznik-short').value = savedS;
});
// Save on change
document.addEventListener('change', (e) => {
    if (e.target.id === 'mnoznik-long') {
        localStorage.setItem('mnoznik_long', e.target.value);
        fetchCandles(); // Recalculate with new value
    }
    if (e.target.id === 'mnoznik-short') {
        localStorage.setItem('mnoznik_short', e.target.value);
        fetchCandles(); // Recalculate with new value
    }
});

document.getElementById('chart-title').textContent = `LTC/USDT ${currentInterval} Chart`;

// Bind interval buttons
document.querySelectorAll('.interval-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        // Toggle active class
        document.querySelectorAll('.interval-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');

        currentInterval = e.target.dataset.interval;
        document.getElementById('chart-title').textContent = `LTC/USDT ${currentInterval} Chart`;

        // Reset chart data
        allCandlesData = [];
        allIndicatorData = [];
        allMarkers = [];
        allLongAvgData = [];
        allShortAvgData = [];
        allLongTargetData = [];
        allShortTargetData = [];
        oldestDataTime = null;
        isLoadingHistory = false;
        candlestickSeries.setData([]);
        candlestickSeries.setMarkers([]);
        mainLineSeries.setData([]);
        longAvgSeries.setData([]);
        shortAvgSeries.setData([]);
        longTargetSeries.setData([]);
        shortTargetSeries.setData([]);
        if (currentCandleTracker) {
            currentCandleTracker.applyOptions({ title: '...', price: lastKnownPrice });
        }

        fetchCandles();
    });
});

// Fetch data (handles both initial load and history pagination)
async function fetchCandles(isHistory = false) {
    if (isLoadingHistory) return;

    if (isHistory) {
        isLoadingHistory = true;
    } else {
        const loader = document.getElementById('loading');
        loader.classList.remove('hidden');
    }

    try {
        let url = '/api/candles';

        // If loading history, change limit to 1000 and pass the 'before' timestamp
        if (isHistory && oldestDataTime) {
            url += `?limit=1000&before=${oldestDataTime}&interval=${currentInterval}${getMnoznikParams()}`;
        } else {
            url += `?limit=10000&interval=${currentInterval}${getMnoznikParams()}`;
        }
        // By default /api/candles pulls 10000 for the initial load

        const response = await fetch(url);
        const data = await response.json();

        const newCandles = data.candles || [];
        const newIndicator = data.indicator || [];
        const newMarkers = data.markers || [];
        const panelData = data.panel || null;

        console.log("Fetched data:", newCandles.length, "History flag:", isHistory);
        if (newCandles && newCandles.length > 0) {
            try {
                if (isHistory) {
                    // Prepend the new historical data to our existing data array
                    allCandlesData = [...newCandles, ...allCandlesData];
                    allIndicatorData = [...newIndicator, ...allIndicatorData];
                    allMarkers = [...newMarkers, ...allMarkers];
                } else {
                    allCandlesData = newCandles;
                    allIndicatorData = newIndicator;
                    allMarkers = newMarkers;
                    if (panelData) updatePanel(panelData);
                }

                // Update the oldest known timestamp for the next pagination request
                oldestDataTime = allCandlesData[0].time * 1000;

                // Process indicator data: add trend colors + extract avg price arrays
                const processed = processIndicatorData(allIndicatorData);
                allLongAvgData = processed.longAvg;
                allShortAvgData = processed.shortAvg;
                allLongTargetData = processed.longTarget;
                allShortTargetData = processed.shortTarget;

                candlestickSeries.setData(allCandlesData);
                candlestickSeries.setMarkers(allMarkers);
                mainLineSeries.setData(processed.lineData);
                longAvgSeries.setData(allLongAvgData);
                shortAvgSeries.setData(allShortAvgData);
                longTargetSeries.setData(allLongTargetData);
                shortTargetSeries.setData(allShortTargetData);
                console.log("Data set successfully. Total items:", allCandlesData.length);
            } catch (err) {
                document.getElementById('loading').innerHTML = "<div style='color:red'>Render Error: " + err.message + "</div>";
                // Ensure loader is hidden even on render error if it was shown
                if (!isHistory) {
                    document.getElementById('loading').classList.add('hidden');
                }
            }
        }
    } catch (error) {
        console.error('Error fetching candles:', error);
    } finally {
        if (!isHistory) {
            document.getElementById('loading').classList.add('hidden');
        } else {
            isLoadingHistory = false;
        }
    }
}

// Attach a listener to the time scale to detect when the user scrolls near the left edge.
chart.timeScale().subscribeVisibleLogicalRangeChange(logicalRange => {
    // logicalRange.from gives the index of the leftmost visible bar.
    // If it gets below 50, it means the user is viewing the oldest bars we have loaded.
    if (logicalRange !== null && logicalRange.from < 50) {
        // Trigger loading earlier history!
        fetchCandles(true);
    }
});

// Initial fetch
fetchCandles();

// Refresh button
document.getElementById('refreshBtn').addEventListener('click', fetchCandles);

// Auto-refresh historical data every 5 minutes (optional, as real-time handles the rest)
setInterval(fetchCandles, 300000);

// Real-time tracking for the current candle
async function fetchCurrentCandle() {
    try {
        const response = await fetch(`/api/current_candle?interval=${currentInterval}${getMnoznikParams()}`);
        const data = await response.json();

        const candle = data.candle;
        const indicator = data.indicator;
        const panelData = data.panel;
        const newMarkers = data.markers || [];

        if (candle && candle.time) {
            candlestickSeries.update(candle);
            lastKnownPrice = candle.close;

            if (indicator && indicator.time) {
                mainLineSeries.update({ time: indicator.time, value: indicator.value, color: trendColor(indicator.trend) });

                // Update avg price lines
                if (indicator.L_blue != null) {
                    longAvgSeries.update({ time: indicator.time, value: indicator.L_blue });
                }
                if (indicator.S_blue != null) {
                    shortAvgSeries.update({ time: indicator.time, value: indicator.S_blue });
                }
                if (indicator.L_cel != null) {
                    longTargetSeries.update({ time: indicator.time, value: indicator.L_cel });
                }
                if (indicator.S_cel != null) {
                    shortTargetSeries.update({ time: indicator.time, value: indicator.S_cel });
                }
            }

            if (panelData) {
                updatePanel(panelData);
            }
            if (data.live_position) {
                updateLivePositionPanel(data.live_position);
            }
            if (data.is_auto_trading !== undefined) {
                const autoCheckbox = document.getElementById('auto-toggle-checkbox');
                const autoIndicator = document.getElementById('auto-status-indicator');
                if (autoCheckbox && autoCheckbox.checked !== data.is_auto_trading) {
                    autoCheckbox.checked = data.is_auto_trading;
                }
                if (autoIndicator) {
                    autoIndicator.style.background = data.is_auto_trading ? '#089981' : '#f23645';
                }
            }

            if (newMarkers.length > 0) {
                // To safely update markers without losing historical ones we could re-run setMarkers.
                // But in real-time tracking, it's safer to just set all markers to the new combined array 
                // ONLY if there's a novel marker we don't have yet.
                // For simplicity, lightweight charts requires the entire marker array every time.
                // We will append to allMarkers and setMarkers.
                let added = false;
                for (const m of newMarkers) {
                    if (!allMarkers.some(existM => existM.time === m.time && existM.text === m.text)) {
                        allMarkers.push(m);
                        added = true;
                    }
                }
                if (added) {
                    // Sort markers by time just in case as required by LightweightCharts
                    allMarkers.sort((a, b) => a.time - b.time);
                    candlestickSeries.setMarkers(allMarkers);
                }
            }

            // Recreate or move the line tracking the price
            if (!currentCandleTracker) {
                currentCandleTracker = candlestickSeries.createPriceLine({
                    price: candle.close,
                    color: 'rgba(0, 0, 0, 0)', // Invisible line
                    lineWidth: 1,
                    lineStyle: LightweightCharts.LineStyle.Dotted,
                    axisLabelVisible: true,
                    title: '...',
                    axisLabelColor: '#2962ff',
                    axisLabelTextColor: '#ffffff',
                });
            }
            // Note: lightweight-charts 4.1.1 doesn't allow dynamic update of priceLine price natively through an update method.
            // We use applyOptions instead to move the line and update the text.
        }
    } catch (error) {
        console.error('Error fetching current candle:', error);
    }
}

// Poll for the forming candle every 5 seconds
setInterval(fetchCurrentCandle, 5000);

// Tick every second to update the countdown label
setInterval(() => {
    if (currentCandleTracker && lastKnownPrice > 0) {
        let minutesToAdd = 1;
        if (currentInterval.endsWith('m')) {
            minutesToAdd = parseInt(currentInterval);
        } else if (currentInterval.endsWith('h')) {
            minutesToAdd = parseInt(currentInterval) * 60;
        } else if (currentInterval.endsWith('d')) {
            minutesToAdd = parseInt(currentInterval) * 1440;
        }

        const now = new Date();
        const interval_ms = minutesToAdd * 60 * 1000;
        // next boundary is exactly divisible by the interval_ms
        const nextBoundary = Math.ceil(now.getTime() / interval_ms) * interval_ms;

        const diff = nextBoundary - now.getTime();
        const countdownStr = formatCountdown(diff);

        // Update the tracking line text and keep it exactly at the current price
        currentCandleTracker.applyOptions({
            price: lastKnownPrice,
            title: countdownStr
        });
    }
}, 1000);

// Bind Auto Sync toggle
const autoToggle = document.getElementById('auto-toggle-checkbox');
if (autoToggle) {
    autoToggle.addEventListener('change', async (e) => {
        const isAuto = e.target.checked;
        const indicator = document.getElementById('auto-status-indicator');
        if (indicator) {
            indicator.style.background = isAuto ? '#089981' : '#f23645';
        }

        try {
            await fetch('/api/set_auto', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_auto: isAuto })
            });
        } catch (error) {
            console.error('Error toggling auto sync:', error);
            // Revert UI on error
            e.target.checked = !isAuto;
            if (indicator) {
                indicator.style.background = !isAuto ? '#089981' : '#f23645';
            }
        }
    });
}

// Function to update the PNL Info panel
function updatePanel(data) {
    const el = document.getElementById('info-panel');
    if (!el) return;

    el.classList.remove('hidden');

    // Update LONG
    document.getElementById('l-status').textContent = data.L_status;
    document.getElementById('l-poz').textContent = data.L_poz + " LTC";
    const lPnl = document.getElementById('l-pnl');
    lPnl.textContent = data.L_pnl.toFixed(2);
    lPnl.style.color = data.L_pnl > 0 ? '#089981' : (data.L_pnl < 0 ? '#f23645' : '#fff');
    document.getElementById('l-usr').textContent = data.L_usr;
    document.getElementById('l-avg-usr').textContent = data.L_avg_usr;

    // Update SHORT
    document.getElementById('s-status').textContent = data.S_status;
    document.getElementById('s-poz').textContent = data.S_poz + " LTC";
    const sPnl = document.getElementById('s-pnl');
    sPnl.textContent = data.S_pnl.toFixed(2);
    sPnl.style.color = data.S_pnl > 0 ? '#089981' : (data.S_pnl < 0 ? '#f23645' : '#fff');
    document.getElementById('s-usr').textContent = data.S_usr;
    document.getElementById('s-avg-usr').textContent = data.S_avg_usr;

    // Updates VOL
    document.getElementById('vol-100').textContent = data.vol.toLocaleString();
}

function updateLivePositionPanel(livePosition) {
    if (!livePosition) return;
    const elRight = document.getElementById('info-panel-right');
    if (!elRight) return;

    elRight.classList.remove('hidden');

    // Live Long
    document.getElementById('live-l-status').textContent = livePosition.long_amount > 0 ? "OTWARTA" : "BRAK";
    document.getElementById('live-l-amt').textContent = livePosition.long_amount + " LTC";
    document.getElementById('live-l-price').textContent = livePosition.long_price;
    const lPnl = document.getElementById('live-l-pnl');
    lPnl.textContent = livePosition.long_pnl;
    lPnl.style.color = livePosition.long_pnl > 0 ? '#089981' : (livePosition.long_pnl < 0 ? '#f23645' : '#fff');

    // Live Short
    document.getElementById('live-s-status').textContent = livePosition.short_amount > 0 ? "OTWARTA" : "BRAK";
    document.getElementById('live-s-amt').textContent = livePosition.short_amount + " LTC";
    document.getElementById('live-s-price').textContent = livePosition.short_price;
    const sPnl = document.getElementById('live-s-pnl');
    sPnl.textContent = livePosition.short_pnl;
    sPnl.style.color = livePosition.short_pnl > 0 ? '#089981' : (livePosition.short_pnl < 0 ? '#f23645' : '#fff');

    // Update Modal Data
    const modLStatus = document.getElementById('modal-l-status');
    if (modLStatus) {
        modLStatus.textContent = livePosition.long_amount > 0 ? "OTWARTA" : "BRAK";
        document.getElementById('modal-l-amt').textContent = livePosition.long_amount + " LTC";
        document.getElementById('modal-l-price').textContent = livePosition.long_price;
        document.getElementById('modal-l-pnl').textContent = livePosition.long_pnl;
        document.getElementById('modal-l-pnl').style.color = livePosition.long_pnl > 0 ? '#089981' : (livePosition.long_pnl < 0 ? '#f23645' : '#fff');
    }
    const modSStatus = document.getElementById('modal-s-status');
    if (modSStatus) {
        modSStatus.textContent = livePosition.short_amount > 0 ? "OTWARTA" : "BRAK";
        document.getElementById('modal-s-amt').textContent = livePosition.short_amount + " LTC";
        document.getElementById('modal-s-price').textContent = livePosition.short_price;
        document.getElementById('modal-s-pnl').textContent = livePosition.short_pnl;
        document.getElementById('modal-s-pnl').style.color = livePosition.short_pnl > 0 ? '#089981' : (livePosition.short_pnl < 0 ? '#f23645' : '#fff');
    }
}

// --- Manual Trading Modal Logic ---
const btnManualTrade = document.getElementById('btn-manual-trade');
const manualModal = document.getElementById('manual-trade-modal');
const closeModal = document.getElementById('close-modal-btn');

if (btnManualTrade && manualModal && closeModal) {
    btnManualTrade.addEventListener('click', () => manualModal.classList.remove('hidden'));
    closeModal.addEventListener('click', () => manualModal.classList.add('hidden'));
}

async function sendManualTrade(action) {
    const amtInput = document.getElementById('manual-amount');
    const amount = parseFloat(amtInput ? amtInput.value : 0);
    try {
        const response = await fetch('/api/manual_trade', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: action, amount: amount })
        });
        const res = await response.json();
        if (res.status === 'ok') {
            console.log('Trade sent:', action);
        }
    } catch (e) {
        console.error('Failed manual trade', e);
    }
}

document.getElementById('btn-open-long')?.addEventListener('click', () => sendManualTrade('LONG'));
document.getElementById('btn-open-short')?.addEventListener('click', () => sendManualTrade('SHORT'));
document.getElementById('btn-close-long')?.addEventListener('click', () => sendManualTrade('CLOSE_LONG'));
document.getElementById('btn-close-short')?.addEventListener('click', () => sendManualTrade('CLOSE_SHORT'));
document.getElementById('btn-test-popup')?.addEventListener('click', () => sendManualTrade('TEST_POPUP'));


// --- Dev Info Modal Logic ---
const btnDevInfo = document.getElementById('btn-dev-info');
const devInfoModal = document.getElementById('dev-info-modal');
const closeDevInfo = document.getElementById('close-dev-info-btn');

if (btnDevInfo && devInfoModal) {
    btnDevInfo.addEventListener('click', async () => {
        devInfoModal.classList.remove('hidden');
        await fetchDevInfo();
    });
}
if (closeDevInfo) {
    closeDevInfo.addEventListener('click', () => {
        devInfoModal.classList.add('hidden');
    });
}

async function fetchDevInfo() {
    const body = document.getElementById('dev-info-body');
    if (!body) return;
    body.innerHTML = '<div style="color: #8a8d9a; text-align: center; padding: 20px;">Ładowanie danych...</div>';

    try {
        const res = await fetch('/api/dev_info');
        const data = await res.json();
        const counters = data.counters || [];

        const totalAll = counters.reduce((s, c) => s + c.count, 0);
        const maxCount = Math.max(...counters.map(c => c.count), 1);

        // Find last non-zero counter to trim empty tail
        let lastNonZero = 0;
        for (let i = counters.length - 1; i >= 0; i--) {
            if (counters[i].count > 0) { lastNonZero = i; break; }
        }
        // Show at least up to lastNonZero + 2 rows (some padding), min 5
        const visibleRows = Math.max(5, Math.min(lastNonZero + 3, counters.length));

        let html = '';

        // --- Summary header ---
        html += `<div style="margin-bottom: 10px; padding: 8px 12px; background: #2a2e39; border-radius: 6px; display: flex; justify-content: space-between; align-items: center;">
            <span style="color: #d1d4dc; font-size: 13px;">Zamknięte pozycje łącznie:</span>
            <strong style="color: #FFEB3B; font-size: 16px;">${totalAll}</strong>
        </div>`;

        // --- Collapsible raw counters ---
        html += `<details style="margin-bottom: 10px; background: #1e222d; border: 1px solid #2a2e39; border-radius: 6px;">
            <summary style="cursor: pointer; padding: 8px 12px; color: #8a8d9a; font-size: 12px; user-select: none;">📊 Pokaż surowe liczniki (L.1 – L.20)</summary>
            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; padding: 8px;">`;
        for (const c of counters) {
            const label = c.averagings === 0 ? '0 uśr.' : `${c.averagings} uśr.`;
            html += `<div style="text-align: center; padding: 4px; background: #131722; border-radius: 3px;">
                <div style="color: #8a8d9a; font-size: 9px;">L.${c.averagings + 1}</div>
                <div style="color: ${c.count > 0 ? '#d1d4dc' : '#434651'}; font-size: 13px; font-weight: 600;">${c.count}</div>
                <div style="color: #434651; font-size: 8px;">${label}</div>
            </div>`;
        }
        html += `</div></details>`;

        // --- Horizontal bar chart ---
        html += `<div style="background: #1e222d; border: 1px solid #2a2e39; border-radius: 6px; padding: 10px;">
            <div style="color: #d1d4dc; font-size: 12px; font-weight: 600; margin-bottom: 8px;">Rozkład uśrednień</div>`;

        for (let i = 0; i < visibleRows; i++) {
            const c = counters[i];
            const pct = totalAll > 0 ? ((c.count / totalAll) * 100) : 0;
            const barWidth = maxCount > 0 ? ((c.count / maxCount) * 100) : 0;
            const hasData = c.count > 0;
            const barColor = hasData ? (pct > 30 ? '#089981' : pct > 10 ? '#2196F3' : '#FF9800') : 'transparent';

            html += `<div style="display: grid; grid-template-columns: 42px 1fr 52px; align-items: center; gap: 6px; margin-bottom: 3px; height: 20px;">
                <span style="color: #8a8d9a; font-size: 10px; text-align: right; white-space: nowrap;">${c.averagings} uśr.</span>
                <div style="position: relative; height: 16px; background: #131722; border-radius: 3px; overflow: hidden;">
                    <div style="height: 100%; width: ${barWidth}%; background: ${barColor}; border-radius: 3px; transition: width 0.3s ease;"></div>
                    ${hasData ? `<span style="position: absolute; left: 6px; top: 50%; transform: translateY(-50%); font-size: 9px; color: #fff; font-weight: 600; text-shadow: 0 0 3px rgba(0,0,0,0.8);">${c.count}</span>` : ''}
                </div>
                <span style="color: ${hasData ? '#d1d4dc' : '#434651'}; font-size: 11px; font-weight: 500; text-align: right;">${pct.toFixed(1)}%</span>
            </div>`;
        }

        html += `</div>`;
        body.innerHTML = html;
    } catch (err) {
        body.innerHTML = `<div style="color: #f23645; text-align: center; padding: 20px;">Błąd: ${err.message}</div>`;
    }
}
