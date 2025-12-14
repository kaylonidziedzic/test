/**
 * CF-Gateway Dashboard - 状态管理模块
 */

const { reactive, ref, computed } = Vue;

// Tab 配置
const TABS = [
    { id: 'monitor', name: '总览', icon: 'ri-dashboard-3-line', desc: '实时监控和数据分析' },
    { id: 'logs', name: '日志', icon: 'ri-file-list-3-line', desc: '系统日志和活动' },
    { id: 'pool', name: '实例池', icon: 'ri-cpu-line', desc: '浏览器池管理' },
    { id: 'cache', name: '缓存', icon: 'ri-database-2-line', desc: '缓存统计' },
    { id: 'rules', name: '爬虫工坊', icon: 'ri-magic-line', desc: '可视化规则生成器' },
    { id: 'config', name: '配置', icon: 'ri-settings-4-line', desc: '系统配置' },
    { id: 'proxies', name: '代理管理', icon: 'ri-global-line', desc: 'IP 代理池管理' },
    { id: 'users', name: '用户/密钥', icon: 'ri-key-2-line', desc: '管理 API Key 和权限', adminOnly: true }
];

// 创建应用状态
function createAppState() {
    // 认证状态
    const authenticated = ref(false);
    const apiKey = ref('');
    const apiBaseUrl = ref(window.location.origin);
    const loading = ref(false);
    const loginError = ref('');

    // UI 状态
    const activeTab = ref('monitor');
    const autoRefresh = ref(true);
    const sseConnected = ref(false);
    const searchQuery = ref('');
    const logFilter = ref('all');
    const requestUserFilter = ref('all');

    // 数据状态
    const status = reactive({});
    const stats = reactive({});
    const config = reactive({});
    const timeSeries = reactive([]);
    const requestHistory = reactive([]);
    const systemInfo = reactive({});
    const browserPoolInfo = reactive({ instances: [] });
    const logs = reactive([]);
    const userLogs = reactive([]);

    // 用户管理
    const apiUsers = reactive([]);
    const newUserName = ref('');
    const newUserRole = ref('user');
    const userLoading = ref(false);
    const rotatingUser = ref('');

    // 规则管理
    const rules = reactive([]);
    const rulesLoading = ref(false);
    const showRuleForm = ref(false);
    const editingRule = ref(null);
    const ruleForm = reactive({
        name: '',
        target_url: '',
        method: 'GET',
        mode: 'cookie',
        api_type: 'proxy',
        is_public: false,
        proxy_mode: 'none',
        proxy: '',
        wait_for: '',
        cache_ttl: 0,
        body_type: 'none',
        body: '',
        headers_list: [],
        selectors: []
    });
    const ruleTestResult = ref(null);
    const ruleTesting = ref(false);
    const copiedRuleId = ref(null);

    // 代理管理
    const proxyList = reactive([]);
    const proxyStats = reactive({ total: 0, available: 0, strategy: 'round_robin' });
    const proxyLoading = ref(false);
    const newProxyText = ref('');

    // 测试
    const testing = ref(false);
    const testUrl = ref('');
    const testResult = ref(null);
    const batchTesting = ref(false);
    const batchTestUrls = ref('');
    const batchTestResults = ref(null);
    const batchProgress = ref(0);
    const quickTestParams = reactive({
        api_type: 'proxy',
        mode: 'cookie',
        proxy_mode: 'none',
        force_refresh: false,
        method: 'GET',
        body_type: 'none',
        body: ''
    });

    // 其他
    const saving = ref(false);
    const selectedRequest = ref(null);
    const toast = reactive({ show: false, message: '', type: 'success' });

    // 计算属性
    const isAdmin = computed(() => status.current_user?.role === 'admin');
    const visibleTabs = computed(() => TABS.filter(t => !t.adminOnly || isAdmin.value));
    const currentTabName = computed(() => visibleTabs.value.find(t => t.id === activeTab.value)?.name);
    const currentTabDesc = computed(() => visibleTabs.value.find(t => t.id === activeTab.value)?.desc);

    const userOptions = computed(() => {
        const users = new Set([
            ...requestHistory.map(r => r.user || '未知'),
            ...apiUsers.map(u => u.user || '未知')
        ]);
        return [...users].filter(Boolean);
    });

    const filteredRequests = computed(() => {
        let list = requestHistory;
        if (requestUserFilter.value !== 'all') {
            list = list.filter(r => (r.user || '未知') === requestUserFilter.value);
        }
        if (!searchQuery.value) return list;
        const q = searchQuery.value.toLowerCase();
        return list.filter(r => r.url.toLowerCase().includes(q) || r.timestamp.includes(q));
    });

    const filteredLogs = computed(() => {
        return logFilter.value === 'all' ? logs : logs.filter(l => l.level === logFilter.value);
    });

    const filteredUserLogs = computed(() => {
        return logFilter.value === 'all' ? userLogs : userLogs.filter(l => l.level === logFilter.value);
    });

    const requestDistribution = computed(() => {
        const t = stats.requests?.total || 0;
        const s = stats.requests?.success || 0;
        const f = stats.requests?.failed || 0;
        return [
            { label: '成功', value: s, percentage: t > 0 ? Math.round(s / t * 100) : 0, color: '#10b981' },
            { label: '失败', value: f, percentage: t > 0 ? Math.round(f / t * 100) : 0, color: '#ef4444' }
        ];
    });

    return {
        // 认证
        authenticated,
        apiKey,
        apiBaseUrl,
        loading,
        loginError,

        // UI
        activeTab,
        autoRefresh,
        sseConnected,
        searchQuery,
        logFilter,
        requestUserFilter,
        tabs: TABS,

        // 数据
        status,
        stats,
        config,
        timeSeries,
        requestHistory,
        systemInfo,
        browserPoolInfo,
        logs,
        userLogs,

        // 用户
        apiUsers,
        newUserName,
        newUserRole,
        userLoading,
        rotatingUser,

        // 规则
        rules,
        rulesLoading,
        showRuleForm,
        editingRule,
        ruleForm,
        ruleTestResult,
        ruleTesting,
        copiedRuleId,

        // 代理
        proxyList,
        proxyStats,
        proxyLoading,
        newProxyText,

        // 测试
        testing,
        testUrl,
        testResult,
        batchTesting,
        batchTestUrls,
        batchTestResults,
        batchProgress,
        quickTestParams,

        // 其他
        saving,
        selectedRequest,
        toast,

        // 计算属性
        isAdmin,
        visibleTabs,
        currentTabName,
        currentTabDesc,
        userOptions,
        filteredRequests,
        filteredLogs,
        filteredUserLogs,
        requestDistribution
    };
}

// 导出到全局
window.CFState = {
    TABS,
    createAppState
};
