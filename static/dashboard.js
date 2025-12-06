if (window['chartjs-plugin-annotation']) {
    Chart.register(window['chartjs-plugin-annotation']);
}

class TradingDashboard {
    constructor() {
        this.ws = null;
        this.charts = {};
        this.priceData = {};
        this.positions = {};
        this.tradeHistory = [];
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 2000;
        this.authToken = null;
        this.pendingEntryMarkers = {};
        
        this.symbols = [
            'R_100', 'R_75', 'R_50', 'R_25', 'R_10',
            '1HZ100V', '1HZ75V', '1HZ50V'
        ];
        
        this.init();
    }
    
    init() {
        if (window.Telegram?.WebApp?.initData) {
            this.telegramAuth();
            return;
        }
        
        this.authToken = sessionStorage.getItem('dashboard_token');
        
        if (!this.authToken) {
            this.showAuthPrompt();
            return;
        }
        
        this.initCharts();
        this.connectWebSocket();
        this.fetchInitialData();
        
        setInterval(() => this.sendPing(), 30000);
    }
    
    async telegramAuth() {
        const tg = window.Telegram.WebApp;
        const initData = tg.initData;
        
        sessionStorage.removeItem('dashboard_token');
        this.authToken = null;
        
        try {
            const response = await fetch('/api/auth/telegram', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData })
            });
            
            const data = await response.json();
            
            if (response.status === 403 && data.error === 'not_authenticated') {
                console.log('User not authenticated in bot, showing login required');
                this.showLoginRequired(data.message);
                tg.ready();
                return;
            }
            
            if (!response.ok) {
                console.error('Telegram auth failed:', response.status);
                this.showAuthPrompt();
                return;
            }
            
            if (data.success && data.token) {
                this.authToken = data.token;
                this.telegramUser = data.user;
                sessionStorage.setItem('dashboard_token', data.token);
                
                tg.ready();
                tg.expand();
                
                this.initCharts();
                this.connectWebSocket();
                this.fetchInitialData();
                this.showTelegramWelcome(data.user);
                
                setInterval(() => this.sendPing(), 30000);
            } else {
                console.error('Telegram auth response invalid:', data);
                this.showAuthPrompt();
            }
        } catch (e) {
            console.error('Telegram auth error:', e);
            this.showAuthPrompt();
        }
    }
    
    showTelegramWelcome(user) {
        const header = document.querySelector('.header h1');
        if (header && user?.first_name) {
            header.textContent = `Welcome, ${user.first_name}!`;
        }
    }
    
    showLoginRequired(message) {
        const container = document.querySelector('.container');
        container.innerHTML = `
            <div class="login-required-container">
                <div class="login-icon">🔒</div>
                <h1>Login Diperlukan</h1>
                <p class="message">${message || 'Anda belum login ke bot.'}</p>
                <div class="instructions">
                    <p><strong>Cara Login:</strong></p>
                    <ol>
                        <li>Kembali ke chat bot</li>
                        <li>Ketik <code>/login</code> atau <code>/start</code></li>
                        <li>Pilih tipe akun (Demo/Real)</li>
                        <li>Masukkan token API Deriv Anda</li>
                        <li>Setelah login berhasil, buka Dashboard lagi</li>
                    </ol>
                </div>
                <button id="close-btn" onclick="window.Telegram?.WebApp?.close()">Tutup</button>
            </div>
            <style>
                .login-required-container { 
                    max-width: 400px; 
                    margin: 50px auto; 
                    text-align: center;
                    background: var(--bg-secondary);
                    padding: 40px;
                    border-radius: 12px;
                    border: 1px solid var(--border-color);
                }
                .login-icon { font-size: 4rem; margin-bottom: 20px; }
                .login-required-container h1 { 
                    color: var(--accent-red); 
                    margin-bottom: 15px;
                    font-size: 1.5rem;
                }
                .login-required-container .message { 
                    color: var(--text-secondary); 
                    margin-bottom: 25px;
                    font-size: 1rem;
                }
                .instructions {
                    text-align: left;
                    background: var(--bg-card);
                    padding: 20px;
                    border-radius: 8px;
                    margin-bottom: 25px;
                }
                .instructions p { margin-bottom: 10px; color: var(--text-primary); }
                .instructions ol { 
                    margin: 0; 
                    padding-left: 20px;
                    color: var(--text-secondary);
                }
                .instructions li { margin-bottom: 8px; }
                .instructions code {
                    background: var(--bg-secondary);
                    padding: 2px 6px;
                    border-radius: 4px;
                    color: var(--accent-primary);
                }
                #close-btn {
                    width: 100%;
                    padding: 12px;
                    background: var(--accent-primary);
                    color: #fff;
                    border: none;
                    border-radius: 8px;
                    font-size: 1rem;
                    font-weight: 600;
                    cursor: pointer;
                    transition: opacity 0.2s;
                }
                #close-btn:hover { opacity: 0.9; }
            </style>
        `;
    }
    
    showAuthPrompt() {
        const container = document.querySelector('.container');
        container.innerHTML = `
            <div class="auth-container">
                <h1>Deriv Trading Bot Dashboard</h1>
                <div class="auth-form">
                    <p>Enter your dashboard access token to continue.</p>
                    <p class="hint">The token is displayed in the bot console logs when it starts.</p>
                    <input type="password" id="token-input" placeholder="Enter access token" autocomplete="off">
                    <button id="auth-btn">Connect</button>
                    <div id="auth-error" class="auth-error"></div>
                </div>
            </div>
            <style>
                .auth-container { 
                    max-width: 400px; 
                    margin: 100px auto; 
                    text-align: center;
                    background: var(--bg-secondary);
                    padding: 40px;
                    border-radius: 12px;
                    border: 1px solid var(--border-color);
                }
                .auth-form { margin-top: 30px; }
                .auth-form p { color: var(--text-secondary); margin-bottom: 10px; }
                .auth-form .hint { font-size: 0.85rem; color: #888; }
                #token-input {
                    width: 100%;
                    padding: 12px;
                    margin: 20px 0;
                    border: 1px solid var(--border-color);
                    border-radius: 8px;
                    background: var(--bg-card);
                    color: var(--text-primary);
                    font-size: 1rem;
                }
                #auth-btn {
                    width: 100%;
                    padding: 12px;
                    background: var(--accent-primary);
                    color: #fff;
                    border: none;
                    border-radius: 8px;
                    font-size: 1rem;
                    font-weight: 600;
                    cursor: pointer;
                    transition: background 0.2s ease;
                }
                #auth-btn:hover { background: #2563EB; }
                .auth-error { 
                    color: var(--accent-red); 
                    margin-top: 15px;
                    font-size: 0.9rem;
                }
            </style>
        `;
        
        document.getElementById('auth-btn').addEventListener('click', () => this.authenticate());
        document.getElementById('token-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.authenticate();
        });
    }
    
    async authenticate() {
        const tokenInput = document.getElementById('token-input');
        const errorDiv = document.getElementById('auth-error');
        const token = tokenInput.value.trim();
        
        if (!token) {
            errorDiv.textContent = 'Please enter a token';
            return;
        }
        
        errorDiv.textContent = 'Verifying...';
        
        try {
            const response = await fetch('/api/health');
            if (!response.ok) throw new Error('Server not available');
            
            const testResponse = await fetch('/api/summary', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            if (testResponse.status === 401) {
                errorDiv.textContent = 'Invalid token. Please check and try again.';
                return;
            }
            
            if (!testResponse.ok) {
                throw new Error('Connection failed');
            }
            
            sessionStorage.setItem('dashboard_token', token);
            this.authToken = token;
            
            window.location.reload();
        } catch (e) {
            errorDiv.textContent = `Error: ${e.message}`;
        }
    }
    
    logout() {
        sessionStorage.removeItem('dashboard_token');
        window.location.reload();
    }
    
    initCharts() {
        this.symbols.forEach(symbol => {
            const canvas = document.getElementById(`chart-${symbol}`);
            if (!canvas) return;
            
            const ctx = canvas.getContext('2d');
            
            this.priceData[symbol] = {
                labels: [],
                prices: [],
                entryIndex: null,
                entryPrice: null
            };
            
            const chartOptions = {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: true },
                    annotation: {
                        annotations: {}
                    }
                },
                scales: {
                    x: {
                        display: false,
                        grid: { display: false }
                    },
                    y: {
                        display: true,
                        grid: {
                            color: 'rgba(0, 0, 0, 0.06)',
                            drawBorder: false
                        },
                        ticks: {
                            color: '#6B7280',
                            font: { size: 10 },
                            maxTicksLimit: 4
                        }
                    }
                },
                elements: {
                    point: { radius: 0 },
                    line: {
                        tension: 0.1,
                        borderWidth: 2
                    }
                }
            };
            
            this.charts[symbol] = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            data: [],
                            borderColor: '#3B82F6',
                            backgroundColor: 'rgba(59, 130, 246, 0.1)',
                            fill: true,
                            pointRadius: 0
                        },
                        {
                            label: 'Entry Point',
                            data: [],
                            borderColor: 'transparent',
                            backgroundColor: 'transparent',
                            pointRadius: [],
                            pointBackgroundColor: [],
                            pointBorderColor: [],
                            pointBorderWidth: 2,
                            showLine: false
                        }
                    ]
                },
                options: chartOptions
            });
        });
    }
    
    updateChartEntryMarkers(symbol) {
        const chart = this.charts[symbol];
        const priceData = this.priceData[symbol];
        if (!chart || !priceData) return;
        
        const position = this.getPositionForSymbol(symbol);
        
        if (position) {
            const entryPrice = position.entry_price;
            const direction = position.direction.toLowerCase();
            const isCall = direction === 'call';
            const color = isCall ? '#10B981' : '#EF4444';
            
            chart.options.plugins.annotation.annotations = {
                entryLine: {
                    type: 'line',
                    yMin: entryPrice,
                    yMax: entryPrice,
                    borderColor: color,
                    borderWidth: 2,
                    borderDash: [6, 4],
                    label: {
                        display: true,
                        content: `Entry: ${entryPrice.toFixed(2)} (${position.direction})`,
                        position: 'start',
                        backgroundColor: color,
                        color: '#000',
                        font: {
                            size: 10,
                            weight: 'bold'
                        },
                        padding: { top: 2, bottom: 2, left: 4, right: 4 }
                    }
                }
            };
            
            const entryDataset = chart.data.datasets[1];
            const dataLength = priceData.prices.length;
            
            entryDataset.data = new Array(dataLength).fill(null);
            entryDataset.pointRadius = new Array(dataLength).fill(0);
            entryDataset.pointBackgroundColor = new Array(dataLength).fill('transparent');
            entryDataset.pointBorderColor = new Array(dataLength).fill('transparent');
            
            if (priceData.entryIndex !== null && priceData.entryIndex < dataLength) {
                const idx = priceData.entryIndex;
                entryDataset.data[idx] = entryPrice;
                entryDataset.pointRadius[idx] = 8;
                entryDataset.pointBackgroundColor[idx] = color;
                entryDataset.pointBorderColor[idx] = '#fff';
            }
        } else {
            chart.options.plugins.annotation.annotations = {};
            
            const entryDataset = chart.data.datasets[1];
            entryDataset.data = [];
            entryDataset.pointRadius = [];
            entryDataset.pointBackgroundColor = [];
            entryDataset.pointBorderColor = [];
            
            priceData.entryIndex = null;
            priceData.entryPrice = null;
        }
        
        chart.update('none');
    }
    
    getPositionForSymbol(symbol) {
        const positions = Object.values(this.positions);
        return positions.find(pos => pos.symbol === symbol);
    }
    
    markEntryPoint(symbol, entryPrice) {
        const priceData = this.priceData[symbol];
        
        if (!priceData || priceData.prices.length === 0) {
            this.pendingEntryMarkers[symbol] = entryPrice;
            this.updateChartCardIndicator(symbol);
            return;
        }
        
        priceData.entryIndex = priceData.prices.length - 1;
        priceData.entryPrice = entryPrice;
        
        delete this.pendingEntryMarkers[symbol];
        
        this.updateChartEntryMarkers(symbol);
        this.updateChartCardIndicator(symbol);
    }
    
    processPendingEntryMarkers(symbol) {
        if (this.pendingEntryMarkers[symbol]) {
            const entryPrice = this.pendingEntryMarkers[symbol];
            this.markEntryPoint(symbol, entryPrice);
        }
    }
    
    updateChartCardIndicator(symbol) {
        const chartCard = document.querySelector(`.chart-card[data-symbol="${symbol}"]`);
        if (!chartCard) return;
        
        const existingIndicator = chartCard.querySelector('.position-indicator');
        if (existingIndicator) {
            existingIndicator.remove();
        }
        
        chartCard.classList.remove('has-position', 'put');
        
        const position = this.getPositionForSymbol(symbol);
        
        if (position) {
            const direction = position.direction.toLowerCase();
            chartCard.classList.add('has-position');
            if (direction === 'put') {
                chartCard.classList.add('put');
            }
            
            const indicator = document.createElement('div');
            indicator.className = `position-indicator ${direction}`;
            indicator.textContent = direction === 'call' ? 'CALL' : 'PUT';
            chartCard.appendChild(indicator);
        }
    }
    
    updateAllChartCardIndicators() {
        this.symbols.forEach(symbol => {
            this.updateChartCardIndicator(symbol);
        });
    }
    
    connectWebSocket() {
        this.updateConnectionStatus('connecting');
        
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/stream?token=${encodeURIComponent(this.authToken)}`;
        
        try {
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                console.log('WebSocket connected');
                this.updateConnectionStatus('connected');
                this.reconnectAttempts = 0;
            };
            
            this.ws.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    this.handleMessage(message);
                } catch (e) {
                    console.error('Failed to parse message:', e);
                }
            };
            
            this.ws.onclose = (event) => {
                console.log('WebSocket disconnected', event.code, event.reason);
                this.updateConnectionStatus('disconnected');
                
                if (event.code === 4001) {
                    sessionStorage.removeItem('dashboard_token');
                    window.location.reload();
                    return;
                }
                
                this.scheduleReconnect();
            };
            
            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.updateConnectionStatus('disconnected');
            };
        } catch (e) {
            console.error('Failed to create WebSocket:', e);
            this.updateConnectionStatus('disconnected');
            this.scheduleReconnect();
        }
    }
    
    scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.log('Max reconnect attempts reached');
            return;
        }
        
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.min(this.reconnectAttempts, 5);
        
        console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
        setTimeout(() => this.connectWebSocket(), delay);
    }
    
    sendPing() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send('ping');
        }
    }
    
    handleMessage(message) {
        switch (message.type) {
            case 'snapshot':
                this.handleSnapshot(message.data);
                break;
            case 'event':
                this.handleEvent(message.channel, message.data);
                break;
            case 'pong':
                break;
            default:
                console.log('Unknown message type:', message.type);
        }
    }
    
    handleSnapshot(snapshot) {
        console.log('Received snapshot:', snapshot);
        
        if (snapshot.last_ticks) {
            Object.entries(snapshot.last_ticks).forEach(([symbol, tick]) => {
                this.updateTick(tick);
            });
        }
        
        if (snapshot.open_positions) {
            this.positions = snapshot.open_positions;
            this.renderPositions();
            
            Object.values(this.positions).forEach(pos => {
                this.markEntryPoint(pos.symbol, pos.entry_price);
            });
            
            this.updateAllChartCardIndicators();
        }
        
        if (snapshot.trade_history) {
            this.tradeHistory = snapshot.trade_history;
            this.renderTradeHistory();
        }
        
        if (snapshot.balance) {
            this.updateBalance(snapshot.balance);
        }
        
        if (snapshot.status) {
            this.updateTradingStatus(snapshot.status);
        }
    }
    
    handleEvent(channel, data) {
        switch (channel) {
            case 'tick':
                this.updateTick(data);
                break;
            case 'position':
                this.handlePositionEvent(data);
                break;
            case 'trade':
                this.handleTradeEvent(data);
                break;
            case 'balance':
                this.updateBalance(data);
                break;
            case 'status':
                this.updateTradingStatus(data);
                break;
        }
    }
    
    updateTick(tick) {
        const symbol = tick.symbol;
        if (!this.priceData[symbol]) return;
        
        const data = this.priceData[symbol];
        const price = tick.price;
        const time = new Date(tick.timestamp || Date.now()).toLocaleTimeString();
        
        data.labels.push(time);
        data.prices.push(price);
        
        const maxPoints = 60;
        let shifted = false;
        if (data.labels.length > maxPoints) {
            data.labels.shift();
            data.prices.shift();
            shifted = true;
            
            if (data.entryIndex !== null) {
                data.entryIndex--;
                if (data.entryIndex < 0) {
                    data.entryIndex = null;
                }
            }
        }
        
        if (this.charts[symbol]) {
            this.charts[symbol].data.labels = data.labels;
            this.charts[symbol].data.datasets[0].data = data.prices;
            
            this.processPendingEntryMarkers(symbol);
            
            const position = this.getPositionForSymbol(symbol);
            if (position) {
                this.updateChartEntryMarkers(symbol);
            } else {
                this.charts[symbol].update('none');
            }
        }
        
        const priceEl = document.getElementById(`price-${symbol}`);
        if (priceEl) {
            const prevPrice = parseFloat(priceEl.textContent) || 0;
            priceEl.textContent = price.toFixed(2);
            priceEl.classList.remove('up', 'down');
            if (price > prevPrice) {
                priceEl.classList.add('up');
            } else if (price < prevPrice) {
                priceEl.classList.add('down');
            }
        }
    }
    
    handlePositionEvent(data) {
        switch (data.type) {
            case 'position_open':
                this.positions[data.contract_id] = data;
                this.markEntryPoint(data.symbol, data.entry_price);
                break;
            case 'position_update':
                if (this.positions[data.contract_id]) {
                    Object.assign(this.positions[data.contract_id], {
                        current_price: data.current_price,
                        pnl: data.pnl,
                        duration: data.duration
                    });
                }
                break;
            case 'position_close':
                const closedSymbol = this.positions[data.contract_id]?.symbol;
                delete this.positions[data.contract_id];
                if (closedSymbol) {
                    this.updateChartEntryMarkers(closedSymbol);
                    this.updateChartCardIndicator(closedSymbol);
                }
                break;
        }
        this.renderPositions();
    }
    
    handleTradeEvent(data) {
        if (data.type === 'trade_history') {
            this.tradeHistory.push(data);
            if (this.tradeHistory.length > 200) {
                this.tradeHistory.shift();
            }
            this.renderTradeHistory();
        }
    }
    
    renderPositions() {
        const container = document.getElementById('positions-container');
        if (!container) return;
        
        const positionsList = Object.values(this.positions);
        
        if (positionsList.length === 0) {
            container.innerHTML = '<div class="no-positions">No active positions</div>';
            return;
        }
        
        container.innerHTML = positionsList.map(pos => {
            const direction = pos.direction.toLowerCase();
            const pnl = pos.pnl || 0;
            const pnlClass = pnl >= 0 ? 'profit' : 'loss';
            const martingaleBadge = pos.martingale_level > 0 
                ? `<span class="martingale-badge">M${pos.martingale_level}</span>` 
                : '';
            
            return `
                <div class="position-card ${direction}">
                    <div class="position-info">
                        <span class="position-symbol">${pos.symbol}</span>
                        <span class="position-direction ${direction}">${pos.direction}${martingaleBadge}</span>
                    </div>
                    <div class="position-stake">
                        <span class="position-label">Stake</span>
                        <span class="position-value">$${pos.stake.toFixed(2)}</span>
                    </div>
                    <div class="position-entry">
                        <span class="position-label">Entry</span>
                        <span class="position-value">${pos.entry_price.toFixed(2)}</span>
                    </div>
                    <div class="position-pnl">
                        <span class="position-label">P/L</span>
                        <span class="position-value ${pnlClass}">${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}</span>
                    </div>
                </div>
            `;
        }).join('');
    }
    
    renderTradeHistory() {
        const tbody = document.getElementById('history-tbody');
        if (!tbody) return;
        
        const recentTrades = [...this.tradeHistory].reverse().slice(0, 50);
        
        tbody.innerHTML = recentTrades.map(trade => {
            const time = new Date(trade.timestamp).toLocaleString();
            const direction = trade.direction.toLowerCase();
            const result = trade.result.toLowerCase();
            const profit = trade.profit;
            const profitClass = profit >= 0 ? 'positive' : 'negative';
            
            return `
                <tr>
                    <td>${time}</td>
                    <td>${trade.symbol}</td>
                    <td><span class="direction-badge ${direction}">${trade.direction}</span></td>
                    <td>$${trade.stake.toFixed(2)}</td>
                    <td><span class="result-badge ${result}">${result}</span></td>
                    <td class="profit-cell ${profitClass}">${profit >= 0 ? '+' : ''}$${profit.toFixed(2)}</td>
                </tr>
            `;
        }).join('');
        
        this.updateStats();
    }
    
    updateStats() {
        const totalTrades = this.tradeHistory.length;
        const wins = this.tradeHistory.filter(t => t.result.toLowerCase() === 'win').length;
        const winRate = totalTrades > 0 ? ((wins / totalTrades) * 100).toFixed(1) : 0;
        const totalPnl = this.tradeHistory.reduce((sum, t) => sum + (t.profit || 0), 0);
        
        const totalEl = document.getElementById('total-trades');
        const winRateEl = document.getElementById('win-rate');
        const pnlEl = document.getElementById('total-pnl');
        
        if (totalEl) totalEl.textContent = totalTrades;
        if (winRateEl) winRateEl.textContent = `${winRate}%`;
        if (pnlEl) {
            pnlEl.textContent = `${totalPnl >= 0 ? '+' : ''}$${totalPnl.toFixed(2)}`;
            pnlEl.classList.remove('positive', 'negative');
            pnlEl.classList.add(totalPnl >= 0 ? 'positive' : 'negative');
        }
    }
    
    updateBalance(balance) {
        const balanceEl = document.querySelector('.balance-value');
        if (balanceEl && balance) {
            balanceEl.textContent = `${balance.currency || 'USD'} ${balance.balance.toFixed(2)}`;
        }
    }
    
    updateTradingStatus(status) {
        const tradingEl = document.querySelector('.trading-indicator');
        if (tradingEl && status) {
            const isTrading = status.is_trading;
            const accountType = status.account_type || 'unknown';
            tradingEl.textContent = `Trading: ${isTrading ? 'Active' : 'Stopped'} (${accountType})`;
            tradingEl.classList.remove('active', 'inactive');
            tradingEl.classList.add(isTrading ? 'active' : 'inactive');
        }
    }
    
    updateConnectionStatus(status) {
        const statusDot = document.querySelector('.status-dot');
        const statusText = document.querySelector('.status-text');
        
        if (statusDot) {
            statusDot.classList.remove('connected', 'disconnected', 'connecting');
            statusDot.classList.add(status);
        }
        
        if (statusText) {
            const texts = {
                connected: 'Connected',
                disconnected: 'Disconnected',
                connecting: 'Connecting...'
            };
            statusText.textContent = texts[status] || status;
        }
    }
    
    async fetchInitialData() {
        const headers = { 'Authorization': `Bearer ${this.authToken}` };
        
        try {
            const [summaryRes, historyRes] = await Promise.all([
                fetch('/api/summary', { headers }),
                fetch('/api/history?limit=50', { headers })
            ]);
            
            if (summaryRes.status === 401 || historyRes.status === 401) {
                sessionStorage.removeItem('dashboard_token');
                window.location.reload();
                return;
            }
            
            if (summaryRes.ok) {
                const summary = await summaryRes.json();
                if (summary.success && summary.data) {
                    if (summary.data.balance) {
                        this.updateBalance(summary.data.balance);
                    }
                    if (summary.data.status) {
                        this.updateTradingStatus(summary.data.status);
                    }
                    if (summary.data.open_positions) {
                        this.positions = summary.data.open_positions;
                        this.renderPositions();
                    }
                }
            }
            
            if (historyRes.ok) {
                const history = await historyRes.json();
                if (history.success && history.data && history.data.trades) {
                    this.tradeHistory = history.data.trades;
                    this.renderTradeHistory();
                }
            }
        } catch (e) {
            console.error('Failed to fetch initial data:', e);
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new TradingDashboard();
});
