/**
 * CF-Gateway Dashboard - 工具函数模块
 */

// 格式化字节数
function formatBytes(bytes) {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// 格式化规则时间
function formatRuleTime(timestamp) {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    return date.toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// 导出为 CSV
function exportToCsv(filename, headers, rows) {
    const csv = [headers, ...rows].map(row => row.join(',')).join('\n');
    const a = document.createElement('a');
    a.href = "data:text/csv;charset=utf-8," + encodeURIComponent(csv);
    a.download = filename;
    a.click();
}

// 导出为 JSON
function exportToJson(filename, data) {
    const a = document.createElement('a');
    a.href = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(data, null, 2));
    a.download = filename;
    a.click();
}

// 导出为文本
function exportToText(filename, text) {
    const a = document.createElement('a');
    a.href = "data:text/plain;charset=utf-8," + encodeURIComponent(text);
    a.download = filename;
    a.click();
}

// 复制到剪贴板
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch (e) {
        console.error('复制失败:', e);
        return false;
    }
}

// 配置预设
const CONFIG_PRESETS = {
    development: {
        browser_pool_min: 1,
        browser_pool_max: 3,
        browser_pool_idle_timeout: 60,
        memory_limit_mb: 512,
        cookie_expire_seconds: 300,
        fingerprint_enabled: true
    },
    production: {
        browser_pool_min: 3,
        browser_pool_max: 10,
        browser_pool_idle_timeout: 300,
        memory_limit_mb: 2048,
        cookie_expire_seconds: 1800,
        fingerprint_enabled: true
    },
    conservative: {
        browser_pool_min: 1,
        browser_pool_max: 2,
        browser_pool_idle_timeout: 30,
        memory_limit_mb: 256,
        cookie_expire_seconds: 600,
        fingerprint_enabled: false
    }
};

const PRESET_NAMES = {
    development: '开发环境',
    production: '生产环境',
    conservative: '保守模式'
};

// 导出到全局
window.CFUtils = {
    formatBytes,
    formatRuleTime,
    exportToCsv,
    exportToJson,
    exportToText,
    copyToClipboard,
    CONFIG_PRESETS,
    PRESET_NAMES
};
