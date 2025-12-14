/**
 * CF-Gateway Dashboard - API 请求模块
 */

class ApiClient {
    constructor() {
        this.baseUrl = '';
        this.apiKey = '';
    }

    setBaseUrl(url) {
        this.baseUrl = url.trim().replace(/\/$/, '');
    }

    setApiKey(key) {
        this.apiKey = key;
    }

    buildUrl(path) {
        return `${this.baseUrl}${path.startsWith('/') ? path : '/' + path}`;
    }

    async request(path, opts = {}, timeoutMs = 10000) {
        return this._fetch(`/api/dashboard${path}`, opts, timeoutMs);
    }

    // 直接请求（用于 /v1 API，不带 /api 前缀）
    async requestDirect(path, opts = {}, timeoutMs = 10000) {
        return this._fetch(path, opts, timeoutMs);
    }

    async _fetch(fullPath, opts = {}, timeoutMs = 10000) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);

        try {
            const res = await fetch(this.buildUrl(fullPath), {
                ...opts,
                signal: controller.signal,
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-KEY': this.apiKey,
                    ...opts.headers
                }
            });

            if (!res.ok) {
                const text = await res.text();
                throw new Error(text || `请求失败 (${res.status})`);
            }

            return res.json();
        } catch (e) {
            if (e.name === 'AbortError') {
                throw new Error('请求超时，请检查网络或后端状态');
            }
            throw e;
        } finally {
            clearTimeout(timer);
        }
    }

    // 状态相关
    async getStatus() {
        return this.request('/status');
    }

    async getStats() {
        return this.request('/stats');
    }

    async getConfig() {
        return this.request('/config');
    }

    async saveConfig(config) {
        return this.request('/config', {
            method: 'PUT',
            body: JSON.stringify(config)
        });
    }

    async getTimeSeries() {
        return this.request('/time-series');
    }

    async getHistory(user = null) {
        const query = user ? `?user=${encodeURIComponent(user)}` : '';
        return this.request(`/history${query}`);
    }

    async getSystem() {
        return this.request('/system');
    }

    // 浏览器池
    async getBrowserPool() {
        return this.request('/browser-pool');
    }

    async restartBrowserPool() {
        return this.request('/browser-pool/restart', { method: 'POST' });
    }

    // 日志
    async getLogs(limit = 200, user = null) {
        let query = `?limit=${limit}`;
        if (user) query += `&user=${encodeURIComponent(user)}`;
        return this.request(`/logs${query}`);
    }

    // 缓存
    async clearCache() {
        return this.request('/cache/clear', { method: 'POST' });
    }

    // 用户管理
    async getUsers() {
        return this.request('/users');
    }

    async createUser(user, role) {
        return this.request('/users', {
            method: 'POST',
            body: JSON.stringify({ user, role })
        });
    }

    async deleteUser(username) {
        return this.request(`/users/${encodeURIComponent(username)}`, {
            method: 'DELETE'
        });
    }

    async rotateUserKey(username) {
        return this.request(`/users/${encodeURIComponent(username)}/rotate`, {
            method: 'POST'
        });
    }

    // 规则管理（使用 /v1 路径，不带 /api 前缀）
    async getRules() {
        return this.requestDirect('/v1/rules');
    }

    async createRule(rule) {
        return this.requestDirect('/v1/rules', {
            method: 'POST',
            body: JSON.stringify(rule)
        });
    }

    async updateRule(ruleId, rule) {
        return this.requestDirect(`/v1/rules/${ruleId}`, {
            method: 'PUT',
            body: JSON.stringify(rule)
        });
    }

    async deleteRule(ruleId) {
        return this.requestDirect(`/v1/rules/${ruleId}`, {
            method: 'DELETE'
        });
    }

    async testRule(ruleId) {
        return this.requestDirect(`/v1/run/${ruleId}?test=true`, {}, 60000);
    }

    // 测试
    async testBypass(url, params = {}) {
        return this.request('/test', {
            method: 'POST',
            body: JSON.stringify({ url, ...params })
        }, 60000);
    }

    async batchTest(urls, params = {}) {
        return this.request('/test/batch', {
            method: 'POST',
            body: JSON.stringify({ urls, ...params })
        }, 60000);
    }

    // 代理管理
    async getProxies() {
        return this.request('/proxies');
    }

    async addProxies(proxies) {
        return this.request('/proxies', {
            method: 'POST',
            body: JSON.stringify({ proxies })
        });
    }

    async removeProxy(address) {
        return this.request(`/proxies/${encodeURIComponent(address)}`, {
            method: 'DELETE'
        });
    }

    async reloadProxies() {
        return this.request('/proxies/reload', { method: 'POST' });
    }
}

// 创建全局实例
window.CFApi = new ApiClient();
