                const tabs = [
                    { id: 'monitor', name: '总览', icon: 'ri-dashboard-3-line', desc: '实时监控和数据分�? },
                    { id: 'logs', name: '日志', icon: 'ri-file-list-3-line', desc: '系统日志和活�? },
                    { id: 'pool', name: '实例�?, icon: 'ri-cpu-line', desc: '浏览器池管理' },
                    { id: 'cache', name: '缓存', icon: 'ri-database-2-line', desc: '缓存统计' },
                    { id: 'rules', name: '爬虫工坊', icon: 'ri-magic-line', desc: '可视化规则生成器' },
                    { id: 'config', name: '配置', icon: 'ri-settings-4-line', desc: '系统配置' },
                    { id: 'actions', name: '操作', icon: 'ri-flashlight-line', desc: '测试和操作工�? },
                    { id: 'users', name: '用户/密钥', icon: 'ri-key-2-line', desc: '管理 API Key 和权�?, adminOnly: true },
                ];

                const status = reactive({}), stats = reactive({}), config = reactive({}), timeSeries = reactive([]);
                const requestHistory = reactive([]), systemInfo = reactive({}), browserPoolInfo = reactive({ instances: [] });
                const apiUsers = reactive([]);
                const newUserName = ref(''), newUserRole = ref('user');
                const userLoading = ref(false), rotatingUser = ref('');
                const toast = reactive({ show: false, message: '', type: 'success' }), logs = reactive([]);
                const userLogs = reactive([]);
                const rules = reactive([]);
                const showRuleModal = ref(false), ruleLoading = ref(false);
                const newRule = reactive({ name: '', target_url: '', method: 'GET', mode: 'cookie', proxy: '', selectors: [{ key: 'title', value: 'title' }] });
                const createdRuleResult = ref(null);
                let refreshInterval = null, lastErrorToast = 0, errorMuteUntil = 0, eventSource = null, logEventSource = null;

                const requestDistribution = computed(() => {
                    const t = stats.requests?.total || 0, s = stats.requests?.success || 0, f = stats.requests?.failed || 0;
                    return [
                        { label: '成功', value: s, percentage: t > 0 ? Math.round(s / t * 100) : 0, color: '#10b981' },
                        { label: '失败', value: f, percentage: t > 0 ? Math.round(f / t * 100) : 0, color: '#ef4444' },
                    ];
                });

                const userOptions = computed(() => [...new Set([
                    ...requestHistory.map(r => r.user || '未知'),
                    ...apiUsers.map(u => u.user || '未知')
                ])].filter(Boolean));

                const filteredRequests = computed(() => {
                    let list = requestHistory;
                    if (requestUserFilter.value !== 'all') {
                        list = list.filter(r => (r.user || '未知') === requestUserFilter.value);
                    }
                    if (!searchQuery.value) return list;
                    const q = searchQuery.value.toLowerCase();
                    return list.filter(r => r.url.toLowerCase().includes(q) || r.timestamp.includes(q));
                });

                const filteredLogs = computed(() => (logFilter.value === 'all' ? logs : logs.filter(l => l.level === logFilter.value)));
                const filteredUserLogs = computed(() => (logFilter.value === 'all' ? userLogs : userLogs.filter(l => l.level === logFilter.value)));

                const isAdmin = computed(() => status.current_user?.role === 'admin');
                const visibleTabs = computed(() => tabs.filter(t => !t.adminOnly || isAdmin.value));
                const currentTabName = computed(() => visibleTabs.value.find(t => t.id === activeTab.value)?.name);
                const currentTabDesc = computed(() => visibleTabs.value.find(t => t.id === activeTab.value)?.desc);

                const showToast = (msg, type = 'success') => {
                    toast.message = msg; toast.type = type; toast.show = true;
                    setTimeout(() => toast.show = false, 3500);
                };

                const notifyError = (msg) => {
                    const now = Date.now();
                    if (now < errorMuteUntil) return;
                    if (now - lastErrorToast > 5000) {
                        showToast(msg, 'error');
                        lastErrorToast = now;
                    }
                };

                const muteErrors = (ms = 60000) => {
                    errorMuteUntil = Date.now() + ms;
                    showToast(`错误提示已静�?${ms / 1000} 秒`, 'info');
                };

                const buildUrl = (path) => {
                    const base = apiBaseUrl.value.trim().replace(/\/$/, '');
                    return `${base}${path.startsWith('/') ? path : '/' + path}`;
                };

                const api = async (path, opts = {}, timeoutMs = 10000) => {
                    const controller = new AbortController();
                    const timer = setTimeout(() => controller.abort(), timeoutMs);
                    try {
                        const res = await fetch(buildUrl(`/api/dashboard${path}`), {
                            ...opts,
                            signal: controller.signal,
                            headers: { 'Content-Type': 'application/json', 'X-API-KEY': apiKey.value, ...opts.headers }
                        });
                        if (!res.ok) {
                            const text = await res.text();
                            throw new Error(text || `请求失败 (${res.status})`);
                        }
                        return res.json();
                    } catch (e) {
                        if (e.name === 'AbortError') throw new Error('请求超时，请检查网络或后端状�?);
                        throw e;
                    } finally {
                        clearTimeout(timer);
                    }
                };

                const loadData = async () => {
                    if (!authenticated.value) return;
                    try {
                        const userParam = requestUserFilter.value !== 'all' ? `&user=${encodeURIComponent(requestUserFilter.value)}` : '';
                        const [s, st, c, ts, h, sys, bp, l] = await Promise.all([
                            api('/status'), api('/stats'), api('/config'), api('/time-series'),
                            api(`/history${requestUserFilter.value !== 'all' ? '?user=' + requestUserFilter.value : ''}`), api('/system'), api('/browser-pool'), api(`/logs?limit=200${userParam}`)
                        ]);
                        Object.assign(status, s); Object.assign(stats, st); Object.assign(config, c);
                        timeSeries.splice(0, timeSeries.length, ...ts);
                        requestHistory.splice(0, requestHistory.length, ...h);
                        Object.assign(systemInfo, sys); Object.assign(browserPoolInfo, bp);
                        logs.splice(0, logs.length, ...(l.all || []));
                        userLogs.splice(0, userLogs.length, ...(l.user || []));
                        if (activeTab.value === 'rules') await loadRules();
                        if (isAdmin.value) await loadUsers();
                    } catch (e) {
                        if (e.message.includes('401')) {
                            authenticated.value = false;
                            clearInterval(refreshInterval);
                            showToast('会话已过�?, 'error');
                        } else {
                            notifyError(e.message || '请求失败，请检查网络或后端状�?);
                        }
                    }
                };

                const stopPolling = () => {
                    if (refreshInterval) {
                        clearInterval(refreshInterval);
                        refreshInterval = null;
                    }
                };

                const startPolling = (notify = false) => {
                    stopPolling();
                    if (!autoRefresh.value) return;
                    refreshInterval = setInterval(loadData, 4000);
                    if (notify) showToast('SSE 断开，已回退轮询', 'error');
                };

                const applySnapshot = (data) => {
                    if (!data) return;
                    if (data.status) {
                        const prevUser = status.current_user;
                        Object.assign(status, data.status);
                        if (!data.status.current_user && prevUser) status.current_user = prevUser;
                    }
                    if (data.stats) Object.assign(stats, data.stats);
                    if (data.config) Object.assign(config, data.config);
                    if (data.time_series) { timeSeries.splice(0, timeSeries.length, ...(data.time_series || [])); }
                    if (data.history) { requestHistory.splice(0, requestHistory.length, ...(data.history || [])); }
                    if (data.system) Object.assign(systemInfo, data.system);
                    if (data.browser_pool) Object.assign(browserPoolInfo, data.browser_pool);
                    if (data.logs) { logs.splice(0, logs.length, ...(data.logs || [])); }
                };

                const closeStream = () => {
                    if (eventSource) {
                        eventSource.close();
                        eventSource = null;
                    }
                    sseConnected.value = false;
                };

                const closeLogStream = () => {
                    if (logEventSource) {
                        logEventSource.close();
                        logEventSource = null;
                    }
                };

                const connectLogStream = () => {
                    if (activeTab.value !== 'logs' || !authenticated.value) return;
                    if (typeof EventSource === 'undefined') return;
                    closeLogStream();
                    const userParam = requestUserFilter.value !== 'all' ? `&user=${encodeURIComponent(requestUserFilter.value)}` : '';
                    const url = buildUrl(`/api/dashboard/logs/stream?key=${encodeURIComponent(apiKey.value)}${userParam}`);
                    logEventSource = new EventSource(url);
                    logEventSource.onmessage = (ev) => {
                        try {
                            const data = JSON.parse(ev.data);
                            if (data.all) {
                                logs.push(...data.all);
                                if (logs.length > 400) logs.splice(0, logs.length - 400);
                            }
                            if (data.user) {
                                userLogs.push(...data.user);
                                if (userLogs.length > 400) userLogs.splice(0, userLogs.length - 400);
                            }
                        } catch (err) {
                            console.error('Log SSE parse error', err);
                        }
                    };
                    logEventSource.onerror = () => {
                        closeLogStream();
                        notifyError('日志流已断开，切换到轮询');
                        loadData();
                    };
                };

                const connectStream = () => {
                    if (!autoRefresh.value || !authenticated.value) return;
                    if (typeof EventSource === 'undefined') {
                        startPolling();
                        return;
                    }
                    closeStream();
                    const url = buildUrl(`/api/dashboard/stream?key=${encodeURIComponent(apiKey.value)}`);
                    eventSource = new EventSource(url);
                    eventSource.onopen = () => {
                        sseConnected.value = true;
                        stopPolling(); // SSE 已连接，暂停轮询
                    };
                    eventSource.onmessage = (ev) => {
                        try {
                            const data = JSON.parse(ev.data);
                            applySnapshot(data);
                        } catch (err) {
                            console.error('SSE parse error', err);
                        }
                    };
                    eventSource.onerror = () => {
                        sseConnected.value = false;
                        closeStream();
                        startPolling(true);
                    };
                };

                const login = async () => {
                    loading.value = true; loginError.value = '';
                    try {
                        const s = await api('/status');
                        Object.assign(status, s);
                        if (status.current_user?.role !== 'admin') {
                            loginError.value = '非管理员无权访问控制�?;
                            authenticated.value = false;
                            return;
                        }
                        authenticated.value = true;
                        localStorage.setItem('apiKey', apiKey.value);
                        await loadData();
                        connectStream();
                        connectLogStream();
                        if (!sseConnected.value) startPolling();
                        showToast('欢迎回来�?, 'success');
                    } catch (e) { loginError.value = 'API 密钥无效'; }
                    finally { loading.value = false; }
                };

                const logout = () => {
                    authenticated.value = false; apiKey.value = '';
                    localStorage.removeItem('apiKey');
                    localStorage.removeItem('activeTab');
                    closeStream();
                    closeLogStream();
                    stopPolling();
                    showToast('已退出登�?, 'info');
                };

                const switchTab = (tabId) => {
                    const allowed = visibleTabs.value.find(t => t.id === tabId);
                    activeTab.value = allowed ? tabId : 'monitor';
                    localStorage.setItem('activeTab', activeTab.value);
                };

                const saveBaseUrl = () => {
                    const norm = apiBaseUrl.value.trim().replace(/\/$/, '');
                    apiBaseUrl.value = norm;
                    localStorage.setItem('apiBaseUrl', norm);
                    showToast('后端地址已保�?, 'success');
                    if (authenticated.value) loadData();
                };

                const toggleAutoRefresh = () => {
                    autoRefresh.value = !autoRefresh.value;
                    if (!autoRefresh.value) {
                        closeStream(); stopPolling();
                        showToast('自动刷新已暂�?, 'info');
                        return;
                    }
                    loadData();
                    connectStream();
                    if (!sseConnected.value) startPolling();
                    showToast(autoRefresh.value ? '自动刷新已开�? : '自动刷新已暂�?, 'info');
                };

                const loadUsers = async () => {
                    if (!isAdmin.value) { apiUsers.splice(0, apiUsers.length); return; }
                    userLoading.value = true;
                    try {
                        const res = await api('/users');
                        apiUsers.splice(0, apiUsers.length, ...(res.users || []));
                    } catch (e) { notifyError(e.message || '获取用户列表失败'); }
                    finally { userLoading.value = false; }
                };

                const createUser = async () => {
                    if (!newUserName.value.trim()) { showToast('请输入用户名', 'error'); return; }
                    userLoading.value = true;
                    try {
                        const res = await api('/users', { method: 'POST', body: JSON.stringify({ user: newUserName.value.trim(), role: newUserRole.value }) });
                        showToast('用户创建成功', 'success');
                        newUserName.value = ''; newUserRole.value = 'user';
                        apiUsers.push(res.user);
                    } catch (e) { notifyError(e.message || '创建用户失败'); }
                    finally { userLoading.value = false; }
                };

                const deleteUser = async (user) => {
                    if (!confirm(`确定删除用户 ${user.user}?`)) return;
                    try {
                        await api(`/users/${encodeURIComponent(user.user)}`, { method: 'DELETE' });
                        const idx = apiUsers.findIndex(u => u.user === user.user);
                        if (idx >= 0) apiUsers.splice(idx, 1);
                        showToast('用户已删�?, 'success');
                    } catch (e) { notifyError(e.message || '删除用户失败'); }
                };

                const rotateUser = async (user) => {
                    rotatingUser.value = user.user;
                    try {
                        const res = await api(`/users/${encodeURIComponent(user.user)}/rotate`, { method: 'POST' });
                        const idx = apiUsers.findIndex(u => u.user === user.user);
                        if (idx >= 0) apiUsers[idx].key = res.user.key;
                        showToast('密钥已重�?, 'success');
                    } catch (e) { notifyError(e.message || '重置密钥失败'); }
                    finally { rotatingUser.value = ''; }
                };

                const loadRules = async () => {
                    try {
                        const res = await api('/v1/rules');
                        rules.splice(0, rules.length, ...(res.rules || []));
                    } catch (e) { notifyError('获取规则列表失败'); }
                };

                const createRule = async () => {
                    if (!newRule.name || !newRule.target_url) { showToast('请填写完整信�?, 'error'); return; }
                    ruleLoading.value = true;
                    try {
                        // 转换 selectors 数组为对�?                        const selectorsObj = {};
                        newRule.selectors.forEach(s => {
                            if (s.key && s.value) selectorsObj[s.key] = s.value;
                        });

                        const payload = {
                            name: newRule.name,
                            target_url: newRule.target_url,
                            method: newRule.method,
                            mode: newRule.mode,
                            proxy: newRule.proxy || null,
                            selectors: selectorsObj
                        };

                        const res = await api('/v1/rules', { method: 'POST', body: JSON.stringify(payload) });
                        createdRuleResult.value = res;
                        showRuleModal.value = false;
                        loadRules();
                        showToast('规则已创�?, 'success');
                    } catch (e) { showToast(e.message, 'error'); }
                    finally { ruleLoading.value = false; }
                };

                const deleteRule = async (id) => {
                    if (!confirm('确定删除此规则吗�?)) return;
                    try {
                        await api(`/v1/rules/${id}`, { method: 'DELETE' });
                        showToast('规则已删�?, 'success');
                        loadRules();
                    } catch (e) { showToast(e.message, 'error'); }
                };

                const addSelector = () => newRule.selectors.push({ key: '', value: '' });
                const removeSelector = (i) => newRule.selectors.splice(i, 1);

                const copyPermlink = (path) => {
                    const url = buildUrl(path);
                    navigator.clipboard.writeText(url).then(() => showToast('链接已复�?, 'success'));
                };

                const saveConfig = async () => {
                    saving.value = true;
                    try {
                        await api('/config', { method: 'PUT', body: JSON.stringify(config) });
                        showToast('配置保存成功', 'success');
                    } catch (e) { showToast(e.message, 'error'); }
                    finally { saving.value = false; }
                };

                const clearAllCache = async () => {
                    if (!confirm('确定要清空所有缓存吗�?)) return;
                    try {
                        await api('/cache/clear', { method: 'POST' });
                        showToast('缓存清空成功', 'success');
                        loadData();
                    } catch (e) { showToast(e.message, 'error'); }
                };

                const restartBrowserPool = async () => {
                    if (!confirm('确定要重启浏览器池吗�?)) return;
                    try {
                        await api('/browser-pool/restart', { method: 'POST' });
                        showToast('浏览器池重启�?..', 'info');
                        setTimeout(loadData, 2000);
                    } catch (e) { showToast(e.message, 'error'); }
                };

                const testBypass = async () => {
                    testing.value = true; testResult.value = null;
                    try {
                        testResult.value = await api('/test', { method: 'POST', body: JSON.stringify({ url: testUrl.value }) }, 60000);
                        showToast(testResult.value.success ? '测试通过�? : '测试失败', testResult.value.success ? 'success' : 'error');
                    } catch (e) {
                        testResult.value = { success: false, error: e.message };
                        showToast('测试失败', 'error');
                    } finally { testing.value = false; }
                };

                const batchTestBypass = async () => {
                    const urls = batchTestUrls.value.split('\n').filter(u => u.trim());
                    if (!urls.length) { showToast('请至少输入一�?URL', 'error'); return; }
                    batchTesting.value = true; batchProgress.value = 0;
                    try {
                        // 分批次处理，前端分片，避免单次过�?                        const chunkSize = 3;
                        const allResults = [];
                        for (let i = 0; i < urls.length; i += chunkSize) {
                            const chunk = urls.slice(i, i + chunkSize);
                            const res = await api('/test/batch', { method: 'POST', body: JSON.stringify({ urls: chunk }) }, 60000);
                            allResults.push(...res.results);
                            batchProgress.value = Math.round(((i + chunk.length) / urls.length) * 100);
                        }
                        const success = allResults.filter(r => r.success).length;
                        batchTestResults.value = { total: allResults.length, success, failed: allResults.length - success, results: allResults };
                        showToast(`批量测试完成: ${batchTestResults.value.success}/${batchTestResults.value.total} 通过`, 'success');
                    } catch (e) { showToast(e.message, 'error'); }
                    finally { batchTesting.value = false; }
                };

                const exportConfig = () => {
                    const a = document.createElement('a');
                    a.href = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(config, null, 2));
                    a.download = "gateway-config.json"; a.click();
                    showToast('配置已导�?, 'success');
                };

                const exportRequests = () => {
                    const csv = [['状�?, 'URL', '延迟 (ms)', '时间�?],
                    ...requestHistory.map(r => [r.success ? '成功' : '失败', r.url, r.duration_ms, r.timestamp])
                    ].map(row => row.join(',')).join('\n');
                    const a = document.createElement('a');
                    a.href = "data:text/csv;charset=utf-8," + encodeURIComponent(csv);
                    a.download = "requests-export.csv"; a.click();
                    showToast('请求数据已导�?, 'success');
                };

                const exportLogs = () => {
                    const txt = filteredLogs.value.map(l => `[${l.timestamp}] [${l.level.toUpperCase()}] ${l.message}`).join('\n');
                    const a = document.createElement('a');
                    a.href = "data:text/plain;charset=utf-8," + encodeURIComponent(txt);
                    a.download = "system-logs.txt"; a.click();
                    showToast('日志已导�?, 'success');
                };

                const clearLogs = () => {
                    if (!confirm('确定要清空所有日志吗�?)) return;
                    logs.splice(0, logs.length);
                    showToast('日志已清�?, 'success');
                };

                const applyPreset = (preset) => {
                    const p = {
                        development: { browser_pool_min: 1, browser_pool_max: 3, browser_pool_idle_timeout: 60, memory_limit_mb: 512, cookie_expire_seconds: 300, fingerprint_enabled: true },
                        production: { browser_pool_min: 3, browser_pool_max: 10, browser_pool_idle_timeout: 300, memory_limit_mb: 2048, cookie_expire_seconds: 1800, fingerprint_enabled: true },
                        conservative: { browser_pool_min: 1, browser_pool_max: 2, browser_pool_idle_timeout: 30, memory_limit_mb: 256, cookie_expire_seconds: 600, fingerprint_enabled: false }
                    };
                    Object.assign(config, p[preset]);
                    const n = { development: '开发环�?, production: '生产环境', conservative: '保守模式' };
                    showToast(`${n[preset]}预设已应用`, 'success');
                };

                const formatBytes = (b) => {
                    if (!b) return '0 B';
                    const k = 1024, s = ['B', 'KB', 'MB', 'GB'];
                    const i = Math.floor(Math.log(b) / Math.log(k));
                    return Math.round(b / Math.pow(k, i) * 100) / 100 + ' ' + s[i];
                };

                // 监听 activeTab 变化，保存到 localStorage & 控制日志�?                watch(activeTab, (newTab) => {
                    localStorage.setItem('activeTab', newTab);
                    if (newTab === 'logs') {
                        connectLogStream();
                    } else {
                        closeLogStream();
                    }
                });

                watch(requestUserFilter, () => {
                    if (activeTab.value === 'logs') {
                        logs.splice(0, logs.length);
                        connectLogStream();
                    }
                    loadData();
                });

                onMounted(() => {
                    document.getElementById('init-loader').style.display = 'none';

                    const savedBase = localStorage.getItem('apiBaseUrl');
                    if (savedBase) apiBaseUrl.value = savedBase;

                    // 恢复上次的标签页
                    const savedTab = localStorage.getItem('activeTab');
                    if (savedTab && visibleTabs.value.find(t => t.id === savedTab)) {
                        activeTab.value = savedTab;
                    }

                    const k = localStorage.getItem('apiKey');
                    if (k) { apiKey.value = k; login(); }
                });

                onUnmounted(() => { closeStream(); closeLogStream(); stopPolling(); });

                return {
                    authenticated, apiKey, apiBaseUrl, autoRefresh, sseConnected, loading, loginError, activeTab, tabs, visibleTabs, currentTabName, currentTabDesc,
                    status, stats, config, timeSeries, requestHistory, systemInfo, browserPoolInfo, requestUserFilter, userOptions, apiUsers, isAdmin,
                    toast, saving, testing, testUrl, testResult, batchTesting, batchTestUrls, batchTestResults, newUserName, newUserRole, userLoading, rotatingUser,
                    selectedRequest, searchQuery, logs, userLogs, logFilter, filteredLogs, filteredUserLogs, requestDistribution, filteredRequests,
                    login, logout, switchTab, loadData, showRequestDetail: (r) => selectedRequest.value = r,
                    exportRequests, exportLogs, clearLogs, clearAllCache, restartBrowserPool,
                    testBypass, batchTestBypass, exportConfig, applyPreset, saveConfig, formatBytes,
                    saveBaseUrl, toggleAutoRefresh, muteErrors,
                    loadUsers, createUser, deleteUser, rotateUser,
                    rules, showRuleModal, ruleLoading, newRule, createdRuleResult, loadRules, createRule, deleteRule, addSelector, removeSelector, copyPermlink, buildUrl
                };
            }
        }).component('line-chart', LineChart).component('donut-chart', DonutChart).mount('#app');
    </script>
</body>

</html>
