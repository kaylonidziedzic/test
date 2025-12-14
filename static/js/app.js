/**
 * CF-Gateway Dashboard - 主应用入口
 * 整合所有模块，创建 Vue 应用
 */

const { createApp, watch, onMounted, onUnmounted } = Vue;

// 创建 Vue 应用
const app = createApp({
    setup() {
        // 获取状态
        const state = CFState.createAppState();
        const api = CFApi;
        const sse = CFSse;
        const utils = CFUtils;

        // 错误提示控制
        let lastErrorToast = 0;
        let errorMuteUntil = 0;

        // Toast 显示
        const showToast = (msg, type = 'success') => {
            state.toast.message = msg;
            state.toast.type = type;
            state.toast.show = true;
            setTimeout(() => state.toast.show = false, 3500);
        };

        // 错误通知（带节流）
        const notifyError = (msg) => {
            const now = Date.now();
            if (now < errorMuteUntil) return;
            if (now - lastErrorToast > 5000) {
                showToast(msg, 'error');
                lastErrorToast = now;
            }
        };

        // 静音错误
        const muteErrors = (ms = 60000) => {
            errorMuteUntil = Date.now() + ms;
            showToast(`错误提示已静音 ${ms / 1000} 秒`, 'info');
        };

        // 应用快照数据
        const applySnapshot = (data) => {
            if (!data) return;
            if (data.status) {
                const prevUser = state.status.current_user;
                Object.assign(state.status, data.status);
                if (!data.status.current_user && prevUser) {
                    state.status.current_user = prevUser;
                }
            }
            if (data.stats) Object.assign(state.stats, data.stats);
            // 当用户在配置页面时，不覆盖 config（避免用户编辑时被覆盖）
            if (data.config && state.activeTab.value !== 'config') {
                Object.assign(state.config, data.config);
            }
            if (Array.isArray(data.time_series)) {
                state.timeSeries.splice(0, state.timeSeries.length, ...data.time_series);
            }
            if (Array.isArray(data.history)) {
                state.requestHistory.splice(0, state.requestHistory.length, ...data.history);
            }
            if (data.system) Object.assign(state.systemInfo, data.system);
            if (data.browser_pool) Object.assign(state.browserPoolInfo, data.browser_pool);
            if (Array.isArray(data.logs)) {
                state.logs.splice(0, state.logs.length, ...data.logs);
            }
        };

        // 加载数据
        const loadData = async () => {
            if (!state.authenticated.value) return;
            try {
                const userParam = state.requestUserFilter.value !== 'all' ? state.requestUserFilter.value : null;
                const [s, st, c, ts, h, sys, bp, l] = await Promise.all([
                    api.getStatus(),
                    api.getStats(),
                    api.getConfig(),
                    api.getTimeSeries(),
                    api.getHistory(userParam),
                    api.getSystem(),
                    api.getBrowserPool(),
                    api.getLogs(200, userParam)
                ]);

                Object.assign(state.status, s);
                Object.assign(state.stats, st);
                // 当用户在配置页面时，不覆盖 config（避免用户编辑时被覆盖）
                if (state.activeTab.value !== 'config') {
                    Object.assign(state.config, c);
                }
                state.timeSeries.splice(0, state.timeSeries.length, ...ts);
                state.requestHistory.splice(0, state.requestHistory.length, ...h);
                Object.assign(state.systemInfo, sys);
                Object.assign(state.browserPoolInfo, bp);
                state.logs.splice(0, state.logs.length, ...(l.all || []));
                state.userLogs.splice(0, state.userLogs.length, ...(l.user || []));

                if (state.activeTab.value === 'rules') await loadRules();
                if (state.activeTab.value === 'proxies') await loadProxies();
                if (state.isAdmin.value) await loadUsers();
            } catch (e) {
                if (e.message.includes('401')) {
                    state.authenticated.value = false;
                    sse.closeAll();
                    showToast('会话已过期', 'error');
                } else {
                    notifyError(e.message || '请求失败，请检查网络或后端状态');
                }
            }
        };

        // 连接 SSE
        const connectStream = () => {
            if (!state.autoRefresh.value || !state.authenticated.value) return;

            sse.connectStream(state.apiBaseUrl.value, state.apiKey.value, {
                onConnected: () => {
                    state.sseConnected.value = true;
                    sse.stopPolling();
                },
                onMessage: applySnapshot,
                onError: () => {
                    state.sseConnected.value = false;
                    sse.startPolling(loadData, 4000);
                    showToast('SSE 断开，已回退轮询', 'error');
                },
                onFallback: () => {
                    sse.startPolling(loadData, 4000);
                }
            });
        };

        // 连接日志流
        const connectLogStream = () => {
            if (state.activeTab.value !== 'logs' || !state.authenticated.value) return;

            sse.connectLogStream(state.apiBaseUrl.value, state.apiKey.value, state.requestUserFilter.value, {
                onMessage: (data) => {
                    if (data.all) {
                        state.logs.push(...data.all);
                        if (state.logs.length > 400) state.logs.splice(0, state.logs.length - 400);
                    }
                    if (data.user) {
                        state.userLogs.push(...data.user);
                        if (state.userLogs.length > 400) state.userLogs.splice(0, state.userLogs.length - 400);
                    }
                },
                onError: () => {
                    notifyError('日志流已断开，切换到轮询');
                    loadData();
                }
            });
        };

        // 登录
        const login = async () => {
            state.loading.value = true;
            state.loginError.value = '';
            try {
                api.setBaseUrl(state.apiBaseUrl.value);
                api.setApiKey(state.apiKey.value);

                const s = await api.getStatus();
                Object.assign(state.status, s);

                // 移除管理员限制，允许所有用户登录
                state.authenticated.value = true;
                localStorage.setItem('apiKey', state.apiKey.value);
                await loadData();
                connectStream();
                connectLogStream();
                if (!state.sseConnected.value) {
                    sse.startPolling(loadData, 4000);
                }
                showToast('欢迎回来！', 'success');
            } catch (e) {
                state.loginError.value = 'API 密钥无效';
            } finally {
                state.loading.value = false;
            }
        };

        // 登出
        const logout = () => {
            state.authenticated.value = false;
            state.apiKey.value = '';
            localStorage.removeItem('apiKey');
            localStorage.removeItem('activeTab');
            sse.closeAll();
            showToast('已退出登录', 'info');
        };

        // 切换标签
        const switchTab = (tabId) => {
            const allowed = state.visibleTabs.value.find(t => t.id === tabId);
            state.activeTab.value = allowed ? tabId : 'monitor';
            localStorage.setItem('activeTab', state.activeTab.value);
        };

        // 保存后端地址
        const saveBaseUrl = () => {
            const norm = state.apiBaseUrl.value.trim().replace(/\/$/, '');
            state.apiBaseUrl.value = norm;
            localStorage.setItem('apiBaseUrl', norm);
            api.setBaseUrl(norm);
            showToast('后端地址已保存', 'success');
            if (state.authenticated.value) loadData();
        };

        // 切换自动刷新
        const toggleAutoRefresh = () => {
            state.autoRefresh.value = !state.autoRefresh.value;
            if (!state.autoRefresh.value) {
                sse.closeAll();
                showToast('自动刷新已暂停', 'info');
                return;
            }
            loadData();
            connectStream();
            if (!state.sseConnected.value) {
                sse.startPolling(loadData, 4000);
            }
            showToast('自动刷新已开启', 'info');
        };

        // ========== 用户管理 ==========
        const loadUsers = async () => {
            if (!state.isAdmin.value) {
                state.apiUsers.splice(0, state.apiUsers.length);
                return;
            }
            state.userLoading.value = true;
            try {
                const res = await api.getUsers();
                state.apiUsers.splice(0, state.apiUsers.length, ...(res.users || []));
            } catch (e) {
                notifyError(e.message || '获取用户列表失败');
            } finally {
                state.userLoading.value = false;
            }
        };

        const createUser = async () => {
            if (!state.newUserName.value.trim()) {
                showToast('请输入用户名', 'error');
                return;
            }
            state.userLoading.value = true;
            try {
                const res = await api.createUser(state.newUserName.value.trim(), state.newUserRole.value);
                showToast('用户创建成功', 'success');
                state.newUserName.value = '';
                state.newUserRole.value = 'user';
                state.apiUsers.push(res.user);
            } catch (e) {
                notifyError(e.message || '创建用户失败');
            } finally {
                state.userLoading.value = false;
            }
        };

        const deleteUser = async (user) => {
            if (!confirm(`确定删除用户 ${user.user}?`)) return;
            try {
                await api.deleteUser(user.user);
                const idx = state.apiUsers.findIndex(u => u.user === user.user);
                if (idx >= 0) state.apiUsers.splice(idx, 1);
                showToast('用户已删除', 'success');
            } catch (e) {
                notifyError(e.message || '删除用户失败');
            }
        };

        const rotateUser = async (user) => {
            state.rotatingUser.value = user.user;
            try {
                const res = await api.rotateUserKey(user.user);
                const idx = state.apiUsers.findIndex(u => u.user === user.user);
                if (idx >= 0) state.apiUsers[idx].key = res.user.key;
                showToast('密钥已重置', 'success');
            } catch (e) {
                notifyError(e.message || '重置密钥失败');
            } finally {
                state.rotatingUser.value = '';
            }
        };

        // ========== 规则管理 ==========
        const loadRules = async () => {
            state.rulesLoading.value = true;
            try {
                const res = await api.getRules();
                state.rules.splice(0, state.rules.length, ...(res.rules || []));
            } catch (e) {
                notifyError('获取规则列表失败');
            } finally {
                state.rulesLoading.value = false;
            }
        };

        const openRuleForm = (rule = null) => {
            state.editingRule.value = rule;
            if (rule) {
                // 编辑模式：填充表单
                state.ruleForm.name = rule.name || '';
                state.ruleForm.target_url = rule.target_url || '';
                state.ruleForm.method = rule.method || 'GET';
                state.ruleForm.mode = rule.mode || 'cookie';
                state.ruleForm.api_type = rule.api_type || 'proxy';
                state.ruleForm.is_public = rule.is_public || false;
                state.ruleForm.proxy_mode = rule.proxy_mode || 'none';
                state.ruleForm.proxy = rule.proxy || '';
                state.ruleForm.wait_for = rule.wait_for || '';
                state.ruleForm.cache_ttl = rule.cache_ttl || 0;
                state.ruleForm.body_type = rule.body_type || 'none';
                state.ruleForm.body = rule.body || '';

                // 转换 headers
                state.ruleForm.headers_list = [];
                if (rule.headers && typeof rule.headers === 'object') {
                    for (const [key, value] of Object.entries(rule.headers)) {
                        state.ruleForm.headers_list.push({ key, value });
                    }
                }

                // 转换 selectors
                state.ruleForm.selectors = [];
                if (rule.selectors && typeof rule.selectors === 'object') {
                    for (const [key, selector] of Object.entries(rule.selectors)) {
                        state.ruleForm.selectors.push({ key, selector });
                    }
                }
            } else {
                // 新建模式：重置表单
                state.ruleForm.name = '';
                state.ruleForm.target_url = '';
                state.ruleForm.method = 'GET';
                state.ruleForm.mode = 'cookie';
                state.ruleForm.api_type = 'proxy';
                state.ruleForm.is_public = false;
                state.ruleForm.proxy_mode = 'none';
                state.ruleForm.proxy = '';
                state.ruleForm.wait_for = '';
                state.ruleForm.cache_ttl = 0;
                state.ruleForm.body_type = 'none';
                state.ruleForm.body = '';
                state.ruleForm.headers_list = [];
                state.ruleForm.selectors = [];
            }
            state.showRuleForm.value = true;
        };

        const saveRule = async () => {
            if (!state.ruleForm.name || !state.ruleForm.target_url) {
                showToast('请填写规则名称和目标 URL', 'error');
                return;
            }

            state.rulesLoading.value = true;
            try {
                // 构建 selectors 对象
                const selectorsObj = {};
                state.ruleForm.selectors.forEach(s => {
                    if (s.key && s.selector) selectorsObj[s.key] = s.selector;
                });

                // 构建 headers 对象
                const headersObj = {};
                state.ruleForm.headers_list.forEach(h => {
                    if (h.key && h.value) headersObj[h.key] = h.value;
                });

                // 构建代理配置
                let proxyValue = null;
                if (state.ruleForm.proxy_mode === 'pool') {
                    proxyValue = 'pool';
                } else if (state.ruleForm.proxy_mode === 'fixed' && state.ruleForm.proxy) {
                    proxyValue = state.ruleForm.proxy;
                }

                const payload = {
                    name: state.ruleForm.name,
                    target_url: state.ruleForm.target_url,
                    method: state.ruleForm.method,
                    mode: state.ruleForm.mode,
                    api_type: state.ruleForm.api_type,
                    is_public: state.ruleForm.is_public,
                    proxy: proxyValue,
                    proxy_mode: state.ruleForm.proxy_mode,
                    wait_for: state.ruleForm.wait_for || null,
                    cache_ttl: state.ruleForm.cache_ttl || 0,
                    body_type: state.ruleForm.body_type,
                    body: state.ruleForm.body || null,
                    headers: headersObj,
                    selectors: selectorsObj
                };

                if (state.editingRule.value) {
                    await api.updateRule(state.editingRule.value.id, payload);
                    showToast('规则已更新', 'success');
                } else {
                    await api.createRule(payload);
                    showToast('规则已创建', 'success');
                }

                state.showRuleForm.value = false;
                await loadRules();
            } catch (e) {
                showToast(e.message || '保存规则失败', 'error');
            } finally {
                state.rulesLoading.value = false;
            }
        };

        const deleteRule = async (rule) => {
            if (!confirm('确定删除此规则吗？')) return;
            try {
                await api.deleteRule(rule.id);
                showToast('规则已删除', 'success');
                await loadRules();
            } catch (e) {
                showToast(e.message || '删除规则失败', 'error');
            }
        };

        const testRule = async (rule) => {
            state.ruleTesting.value = true;
            state.ruleTestResult.value = null;
            try {
                const res = await api.testRule(rule.id);
                state.ruleTestResult.value = res;
                showToast(res.error ? '测试失败' : '测试成功', res.error ? 'error' : 'success');
            } catch (e) {
                state.ruleTestResult.value = { error: e.message };
                showToast('测试失败', 'error');
            } finally {
                state.ruleTesting.value = false;
            }
        };

        const copyPermlink = async (rule) => {
            const url = api.buildUrl(`/v1/run/${rule.id}`);
            const success = await utils.copyToClipboard(url);
            if (success) {
                state.copiedRuleId.value = rule.id;
                showToast('链接已复制', 'success');
                setTimeout(() => state.copiedRuleId.value = null, 2000);
            }
        };

        const addSelector = () => {
            state.ruleForm.selectors.push({ key: '', selector: '' });
        };

        const removeSelector = (idx) => {
            state.ruleForm.selectors.splice(idx, 1);
        };

        const addHeader = () => {
            state.ruleForm.headers_list.push({ key: '', value: '' });
        };

        const removeHeader = (idx) => {
            state.ruleForm.headers_list.splice(idx, 1);
        };

        // ========== 代理管理 ==========
        const loadProxies = async () => {
            state.proxyLoading.value = true;
            try {
                const res = await api.getProxies();
                state.proxyList.splice(0, state.proxyList.length, ...(res.proxies || []));
                Object.assign(state.proxyStats, {
                    total: res.total || 0,
                    available: res.available || 0,
                    strategy: res.strategy || 'round_robin'
                });
            } catch (e) {
                notifyError('获取代理列表失败');
            } finally {
                state.proxyLoading.value = false;
            }
        };

        const addProxies = async () => {
            const proxies = state.newProxyText.value.split('\n').filter(p => p.trim());
            if (!proxies.length) {
                showToast('请输入代理地址', 'error');
                return;
            }
            state.proxyLoading.value = true;
            try {
                await api.addProxies(proxies);
                showToast('代理添加成功', 'success');
                state.newProxyText.value = '';
                await loadProxies();
            } catch (e) {
                showToast(e.message || '添加代理失败', 'error');
            } finally {
                state.proxyLoading.value = false;
            }
        };

        const removeProxy = async (address) => {
            try {
                await api.removeProxy(address);
                showToast('代理已删除', 'success');
                await loadProxies();
            } catch (e) {
                showToast(e.message || '删除代理失败', 'error');
            }
        };

        const reloadProxies = async () => {
            state.proxyLoading.value = true;
            try {
                await api.reloadProxies();
                showToast('代理已从文件重新加载', 'success');
                await loadProxies();
            } catch (e) {
                showToast(e.message || '重新加载失败', 'error');
            } finally {
                state.proxyLoading.value = false;
            }
        };

        // ========== 测试功能 ==========
        const testBypass = async () => {
            state.testing.value = true;
            state.testResult.value = null;
            try {
                const params = {
                    api_type: state.quickTestParams.api_type,
                    mode: state.quickTestParams.mode,
                    proxy_mode: state.quickTestParams.proxy_mode,
                    force_refresh: state.quickTestParams.force_refresh
                };
                // 代理设置
                if (state.quickTestParams.proxy_mode === 'pool') {
                    params.proxy = 'pool';
                }
                // POST 请求体
                if (state.quickTestParams.body_type !== 'none' && state.quickTestParams.body) {
                    params.body_type = state.quickTestParams.body_type;
                    params.body = state.quickTestParams.body;
                }
                state.testResult.value = await api.testBypass(state.testUrl.value, params);
                showToast(state.testResult.value.success ? '测试通过！' : '测试失败', state.testResult.value.success ? 'success' : 'error');
            } catch (e) {
                state.testResult.value = { success: false, error: e.message };
                showToast('测试失败', 'error');
            } finally {
                state.testing.value = false;
            }
        };

        const batchTestBypass = async () => {
            const urls = state.batchTestUrls.value.split('\n').filter(u => u.trim());
            if (!urls.length) {
                showToast('请至少输入一个 URL', 'error');
                return;
            }
            state.batchTesting.value = true;
            state.batchProgress.value = 0;
            try {
                const chunkSize = 3;
                const allResults = [];
                for (let i = 0; i < urls.length; i += chunkSize) {
                    const chunk = urls.slice(i, i + chunkSize);
                    const res = await api.batchTest(chunk);
                    allResults.push(...res.results);
                    state.batchProgress.value = Math.round(((i + chunk.length) / urls.length) * 100);
                }
                const success = allResults.filter(r => r.success).length;
                state.batchTestResults.value = {
                    total: allResults.length,
                    success,
                    failed: allResults.length - success,
                    results: allResults
                };
                showToast(`批量测试完成: ${success}/${allResults.length} 通过`, 'success');
            } catch (e) {
                showToast(e.message || '批量测试失败', 'error');
            } finally {
                state.batchTesting.value = false;
            }
        };

        // ========== 配置管理 ==========
        const saveConfig = async () => {
            state.saving.value = true;
            try {
                await api.saveConfig(state.config);
                showToast('配置保存成功', 'success');
            } catch (e) {
                showToast(e.message || '保存配置失败', 'error');
            } finally {
                state.saving.value = false;
            }
        };

        const applyPreset = (preset) => {
            Object.assign(state.config, utils.CONFIG_PRESETS[preset]);
            showToast(`${utils.PRESET_NAMES[preset]}预设已应用`, 'success');
        };

        const exportConfig = () => {
            utils.exportToJson('gateway-config.json', state.config);
            showToast('配置已导出', 'success');
        };

        // ========== 其他功能 ==========
        const clearAllCache = async () => {
            if (!confirm('确定要清空所有缓存吗？')) return;
            try {
                await api.clearCache();
                showToast('缓存清空成功', 'success');
                loadData();
            } catch (e) {
                showToast(e.message || '清空缓存失败', 'error');
            }
        };

        const restartBrowserPool = async () => {
            if (!confirm('确定要重启浏览器池吗？')) return;
            try {
                await api.restartBrowserPool();
                showToast('浏览器池重启中...', 'info');
                setTimeout(loadData, 2000);
            } catch (e) {
                showToast(e.message || '重启失败', 'error');
            }
        };

        const exportRequests = () => {
            utils.exportToCsv(
                'requests-export.csv',
                ['状态', 'URL', '延迟 (ms)', '时间戳'],
                state.requestHistory.map(r => [r.success ? '成功' : '失败', r.url, r.duration_ms, r.timestamp])
            );
            showToast('请求数据已导出', 'success');
        };

        const exportLogs = () => {
            const txt = state.filteredLogs.value.map(l => `[${l.timestamp}] [${l.level.toUpperCase()}] ${l.message}`).join('\n');
            utils.exportToText('system-logs.txt', txt);
            showToast('日志已导出', 'success');
        };

        const clearLogs = () => {
            if (!confirm('确定要清空所有日志吗？')) return;
            state.logs.splice(0, state.logs.length);
            showToast('日志已清空', 'success');
        };

        const showRequestDetail = (req) => {
            state.selectedRequest.value = req;
        };

        // ========== 示例规则和选择器模板 ==========
        const selectorTemplates = CFComponents.SELECTOR_TEMPLATES;
        const exampleRules = CFComponents.EXAMPLE_RULES;
        const helpTexts = CFComponents.HELP_TEXTS;

        // 应用选择器模板
        const applySelectorTemplate = (template) => {
            // 检查是否已存在相同 key
            const exists = state.ruleForm.selectors.find(s => s.key === template.key);
            if (exists) {
                exists.selector = template.selector;
                showToast(`已更新选择器: ${template.name}`, 'info');
            } else {
                state.ruleForm.selectors.push({ key: template.key, selector: template.selector });
                showToast(`已添加选择器: ${template.name}`, 'success');
            }
        };

        // 应用示例规则
        const applyExampleRule = (example) => {
            state.ruleForm.name = example.name;
            state.ruleForm.target_url = example.target_url;
            state.ruleForm.method = example.method || 'GET';
            state.ruleForm.mode = example.mode || 'cookie';
            state.ruleForm.api_type = example.api_type || 'proxy';
            state.ruleForm.is_public = example.is_public || false;
            state.ruleForm.proxy_mode = example.proxy_mode || 'none';
            state.ruleForm.proxy = example.proxy || '';
            state.ruleForm.wait_for = example.wait_for || '';
            state.ruleForm.cache_ttl = example.cache_ttl || 0;
            state.ruleForm.body_type = example.body_type || 'none';
            state.ruleForm.body = example.body || '';
            state.ruleForm.headers_list = [];

            // 转换 selectors
            state.ruleForm.selectors = [];
            if (example.selectors && typeof example.selectors === 'object') {
                for (const [key, selector] of Object.entries(example.selectors)) {
                    state.ruleForm.selectors.push({ key, selector });
                }
            }

            showToast(`已加载示例: ${example.name}`, 'success');
        };

        // 获取帮助文本
        const getHelpText = (key) => {
            return helpTexts[key] || '';
        };

        // 监听标签页变化
        watch(() => state.activeTab.value, async (newTab) => {
            localStorage.setItem('activeTab', newTab);
            if (newTab === 'logs') {
                connectLogStream();
            } else {
                sse.closeLogStream();
            }
            if (newTab === 'rules') {
                loadRules();
            }
            if (newTab === 'proxies') {
                loadProxies();
            }
            // 首次进入配置页面时加载配置（如果 config 为空）
            if (newTab === 'config' && Object.keys(state.config).length === 0) {
                try {
                    const c = await api.getConfig();
                    Object.assign(state.config, c);
                } catch (e) {
                    console.error('Failed to load config:', e);
                }
            }
        });

        // 监听用户筛选变化
        watch(() => state.requestUserFilter.value, () => {
            if (state.activeTab.value === 'logs') {
                state.logs.splice(0, state.logs.length);
                connectLogStream();
            }
            loadData();
        });

        // 挂载时初始化
        onMounted(() => {
            document.getElementById('init-loader').style.display = 'none';

            const savedBase = localStorage.getItem('apiBaseUrl');
            if (savedBase) {
                state.apiBaseUrl.value = savedBase;
                api.setBaseUrl(savedBase);
            } else {
                api.setBaseUrl(state.apiBaseUrl.value);
            }

            const savedTab = localStorage.getItem('activeTab');
            if (savedTab && state.visibleTabs.value.find(t => t.id === savedTab)) {
                state.activeTab.value = savedTab;
            }

            const savedKey = localStorage.getItem('apiKey');
            if (savedKey) {
                state.apiKey.value = savedKey;
                login();
            }
        });

        // 卸载时清理
        onUnmounted(() => {
            sse.closeAll();
        });

        // 返回所有状态和方法
        return {
            // 状态
            ...state,

            // 方法
            login,
            logout,
            switchTab,
            loadData,
            saveBaseUrl,
            toggleAutoRefresh,
            muteErrors,
            showToast,

            // 用户管理
            loadUsers,
            createUser,
            deleteUser,
            rotateUser,

            // 规则管理
            loadRules,
            openRuleForm,
            saveRule,
            deleteRule,
            testRule,
            copyPermlink,
            addSelector,
            removeSelector,
            addHeader,
            removeHeader,

            // 代理管理
            loadProxies,
            addProxies,
            removeProxy,
            reloadProxies,

            // 测试
            testBypass,
            batchTestBypass,

            // 配置
            saveConfig,
            applyPreset,
            exportConfig,

            // 其他
            clearAllCache,
            restartBrowserPool,
            exportRequests,
            exportLogs,
            clearLogs,
            showRequestDetail,

            // 示例规则和选择器模板
            selectorTemplates,
            exampleRules,
            helpTexts,
            applySelectorTemplate,
            applyExampleRule,
            getHelpText,

            // 工具函数
            formatBytes: utils.formatBytes,
            formatRuleTime: utils.formatRuleTime,
            buildUrl: (path) => api.buildUrl(path)
        };
    }
});

// 注册组件
app.component('line-chart', CFComponents.LineChart);
app.component('donut-chart', CFComponents.DonutChart);
app.component('help-tip', CFComponents.HelpTip);

// 挂载应用
app.mount('#app');
