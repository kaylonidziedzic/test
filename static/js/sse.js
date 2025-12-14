/**
 * CF-Gateway Dashboard - SSE 连接管理模块
 */

class SSEManager {
    constructor() {
        this.eventSource = null;
        this.logEventSource = null;
        this.refreshInterval = null;
        this.onConnected = null;
        this.onDisconnected = null;
        this.onMessage = null;
        this.onLogMessage = null;
        this.onError = null;
    }

    // 构建 URL
    buildUrl(baseUrl, path) {
        const base = baseUrl.trim().replace(/\/$/, '');
        return `${base}${path.startsWith('/') ? path : '/' + path}`;
    }

    // 连接主数据流
    connectStream(baseUrl, apiKey, callbacks = {}) {
        if (!apiKey) return;
        if (typeof EventSource === 'undefined') {
            callbacks.onFallback?.();
            return;
        }

        this.closeStream();

        const url = this.buildUrl(baseUrl, `/api/dashboard/stream?key=${encodeURIComponent(apiKey)}`);
        this.eventSource = new EventSource(url);

        this.eventSource.onopen = () => {
            callbacks.onConnected?.();
        };

        this.eventSource.onmessage = (ev) => {
            try {
                const data = JSON.parse(ev.data);
                callbacks.onMessage?.(data);
            } catch (err) {
                console.error('SSE parse error:', err);
            }
        };

        this.eventSource.onerror = () => {
            this.closeStream();
            callbacks.onError?.();
        };
    }

    // 关闭主数据流
    closeStream() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
    }

    // 连接日志流
    connectLogStream(baseUrl, apiKey, user = null, callbacks = {}) {
        if (!apiKey) return;
        if (typeof EventSource === 'undefined') return;

        this.closeLogStream();

        let url = this.buildUrl(baseUrl, `/api/dashboard/logs/stream?key=${encodeURIComponent(apiKey)}`);
        if (user && user !== 'all') {
            url += `&user=${encodeURIComponent(user)}`;
        }

        this.logEventSource = new EventSource(url);

        this.logEventSource.onmessage = (ev) => {
            try {
                const data = JSON.parse(ev.data);
                callbacks.onMessage?.(data);
            } catch (err) {
                console.error('Log SSE parse error:', err);
            }
        };

        this.logEventSource.onerror = () => {
            this.closeLogStream();
            callbacks.onError?.();
        };
    }

    // 关闭日志流
    closeLogStream() {
        if (this.logEventSource) {
            this.logEventSource.close();
            this.logEventSource = null;
        }
    }

    // 启动轮询
    startPolling(callback, interval = 4000) {
        this.stopPolling();
        this.refreshInterval = setInterval(callback, interval);
    }

    // 停止轮询
    stopPolling() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }

    // 关闭所有连接
    closeAll() {
        this.closeStream();
        this.closeLogStream();
        this.stopPolling();
    }

    // 检查 SSE 是否已连接
    isConnected() {
        return this.eventSource !== null && this.eventSource.readyState === EventSource.OPEN;
    }
}

// 创建全局实例
window.CFSse = new SSEManager();
