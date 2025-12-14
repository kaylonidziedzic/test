/**
 * CF-Gateway Dashboard - Vue 组件模块
 */

// 折线图组件
const LineChart = {
    props: ['data'],
    setup(props) {
        const points = Vue.computed(() => {
            const d = props.data || [];
            if (d.length < 2) return '';
            const max = Math.max(...d.map(p => p.success_rate), 100);
            const min = Math.min(...d.map(p => p.success_rate), 0);
            const range = max - min || 1;
            const width = 100;
            const height = 100;
            return d.map((p, i) => {
                const x = (i / (d.length - 1)) * width;
                const y = height - ((p.success_rate - min) / range) * height;
                return `${x},${y}`;
            }).join(' ');
        });

        const areaPath = Vue.computed(() => {
            const d = props.data || [];
            if (d.length < 2) return '';
            const max = Math.max(...d.map(p => p.success_rate), 100);
            const min = Math.min(...d.map(p => p.success_rate), 0);
            const range = max - min || 1;
            const width = 100;
            const height = 100;
            const pts = d.map((p, i) => {
                const x = (i / (d.length - 1)) * width;
                const y = height - ((p.success_rate - min) / range) * height;
                return `${x},${y}`;
            });
            return `M0,${height} L${pts.join(' L')} L${width},${height} Z`;
        });

        return () => Vue.h('svg', {
            viewBox: '0 0 100 100',
            preserveAspectRatio: 'none',
            class: 'w-full h-full'
        }, [
            // 渐变定义
            Vue.h('defs', [
                Vue.h('linearGradient', { id: 'lineGradient', x1: '0%', y1: '0%', x2: '0%', y2: '100%' }, [
                    Vue.h('stop', { offset: '0%', 'stop-color': '#3b82f6', 'stop-opacity': '0.3' }),
                    Vue.h('stop', { offset: '100%', 'stop-color': '#3b82f6', 'stop-opacity': '0.05' })
                ])
            ]),
            // 区域填充
            Vue.h('path', {
                d: areaPath.value,
                fill: 'url(#lineGradient)'
            }),
            // 折线
            Vue.h('polyline', {
                points: points.value,
                fill: 'none',
                stroke: '#3b82f6',
                'stroke-width': '2',
                'stroke-linecap': 'round',
                'stroke-linejoin': 'round',
                'vector-effect': 'non-scaling-stroke'
            })
        ]);
    }
};

// 环形图组件
const DonutChart = {
    props: ['data'],
    setup(props) {
        const segments = Vue.computed(() => {
            const d = props.data || [];
            const total = d.reduce((sum, item) => sum + item.value, 0);
            if (total === 0) return [];

            let currentAngle = -90;
            return d.map(item => {
                const angle = (item.value / total) * 360;
                const startAngle = currentAngle;
                const endAngle = currentAngle + angle;
                currentAngle = endAngle;

                const startRad = (startAngle * Math.PI) / 180;
                const endRad = (endAngle * Math.PI) / 180;

                const x1 = 50 + 40 * Math.cos(startRad);
                const y1 = 50 + 40 * Math.sin(startRad);
                const x2 = 50 + 40 * Math.cos(endRad);
                const y2 = 50 + 40 * Math.sin(endRad);

                const largeArc = angle > 180 ? 1 : 0;

                return {
                    path: `M 50 50 L ${x1} ${y1} A 40 40 0 ${largeArc} 1 ${x2} ${y2} Z`,
                    color: item.color,
                    label: item.label,
                    percentage: item.percentage
                };
            });
        });

        return () => Vue.h('div', { class: 'relative w-full h-full flex items-center justify-center' }, [
            Vue.h('svg', { viewBox: '0 0 100 100', class: 'w-40 h-40' }, [
                ...segments.value.map(seg =>
                    Vue.h('path', {
                        d: seg.path,
                        fill: seg.color,
                        class: 'transition-all duration-300 hover:opacity-80'
                    })
                ),
                // 中心圆
                Vue.h('circle', { cx: '50', cy: '50', r: '25', fill: 'white' })
            ]),
            // 图例
            Vue.h('div', { class: 'ml-6 space-y-2' },
                (props.data || []).map(item =>
                    Vue.h('div', { class: 'flex items-center gap-2 text-sm' }, [
                        Vue.h('span', {
                            class: 'w-3 h-3 rounded-full',
                            style: { backgroundColor: item.color }
                        }),
                        Vue.h('span', { class: 'text-zinc-600' }, item.label),
                        Vue.h('span', { class: 'font-semibold text-zinc-900' }, `${item.percentage}%`)
                    ])
                )
            )
        ]);
    }
};

// Tooltip 组件 - 帮助提示（使用 fixed 定位避免被 overflow 裁剪）
const HelpTip = {
    props: ['text'],
    setup(props) {
        const show = Vue.ref(false);
        const style = Vue.ref({});

        const showTip = (e) => {
            const rect = e.target.getBoundingClientRect();
            const tipWidth = 256; // w-64 = 16rem = 256px
            const spaceRight = window.innerWidth - rect.right;

            // 计算位置
            let left;
            if (spaceRight < tipWidth + 20) {
                // 右边空间不足，右对齐
                left = rect.right - tipWidth;
            } else {
                // 左对齐
                left = rect.left;
            }

            style.value = {
                position: 'fixed',
                left: `${left}px`,
                top: `${rect.top - 8}px`,
                transform: 'translateY(-100%)',
                zIndex: 9999
            };
            show.value = true;
        };

        return () => Vue.h('span', {
            class: 'relative inline-flex items-center ml-1 cursor-help',
            onMouseenter: showTip,
            onMouseleave: () => show.value = false
        }, [
            Vue.h('i', { class: 'ri-question-line text-zinc-400 hover:text-blue-500 text-sm' }),
            show.value ? Vue.h('div', {
                class: 'px-3 py-2 bg-zinc-800 text-white text-xs rounded-lg shadow-lg w-64 leading-relaxed',
                style: { ...style.value, whiteSpace: 'normal', wordWrap: 'break-word' }
            }, props.text) : null
        ]);
    }
};

// 选择器模板配置
const SELECTOR_TEMPLATES = [
    { name: '文章标题', key: 'title', selector: 'h1, .title, .article-title, [class*="title"]' },
    { name: '正文内容', key: 'content', selector: 'article, .content, .article-content, .post-content, main' },
    { name: '发布时间', key: 'time', selector: 'time, .time, .date, .publish-time, [datetime]' },
    { name: '作者', key: 'author', selector: '.author, .byline, [rel="author"], .writer' },
    { name: '商品价格', key: 'price', selector: '.price, [class*="price"], [data-price]' },
    { name: '商品名称', key: 'product_name', selector: '.product-name, .item-title, h1.title' },
    { name: '图片链接', key: 'image', selector: 'img.main, .product-image img, article img' },
    { name: '列表项', key: 'items', selector: 'ul li, ol li, .list-item, .item' }
];

// 示例规则配置
const EXAMPLE_RULES = [
    {
        name: '🌐 获取网页标题和描述',
        target_url: 'https://example.com',
        method: 'GET',
        mode: 'cookie',
        api_type: 'proxy',
        selectors: { title: 'h1', description: 'p' },
        description: '最简单的示例，抓取页面标题和第一段文字'
    },
    {
        name: '📰 新闻文章采集',
        target_url: 'https://news.ycombinator.com',
        method: 'GET',
        mode: 'cookie',
        api_type: 'proxy',
        selectors: {
            title: '.titleline > a',
            score: '.score',
            comments: '.subline a:last-child'
        },
        description: '采集 Hacker News 首页的标题、分数和评论数'
    },
    {
        name: '🔍 搜索结果（带参数）',
        target_url: 'https://example.com/search?q={keyword}',
        method: 'GET',
        mode: 'browser',
        api_type: 'proxy',
        selectors: { results: '.search-result', count: '.result-count' },
        description: '带占位符的搜索，调用时传入 ?keyword=xxx 替换'
    }
];

// 帮助文案配置
const HELP_TEXTS = {
    // 采集模式
    mode_cookie: '快速模式：复用登录凭证，速度快（毫秒级），适合大多数网站',
    mode_browser: '完整模式：真实浏览器访问，速度慢（秒级）但更稳定，适合反爬严格的网站',
    // 接口类型
    api_proxy: '返回 JSON 格式，包含状态码、响应头、提取的数据等结构化信息',
    api_raw: '返回网站原始内容（HTML/JSON/图片等），适合需要完整响应的场景',
    api_reader: '返回处理后的干净 HTML，去除广告和干扰元素，适合阅读类应用',
    // 代理模式
    proxy_none: '直接连接目标网站，不使用代理',
    proxy_pool: '从代理池中自动轮换 IP，适合需要大量请求的场景',
    proxy_fixed: '使用指定的代理 IP，适合需要固定出口 IP 的场景',
    // 其他
    is_public: '公开：任何人无需密钥即可调用；私有：需要 API Key 才能访问',
    wait_for: '等待页面中某个元素出现后再采集，确保动态内容加载完成',
    cache_ttl: '相同请求在此时间内返回缓存结果，0 表示不缓存',
    selectors: 'CSS 选择器用于从页面提取特定内容，如 h1 表示标题，.price 表示价格',
    permlink: '专属链接，通过 GET 请求即可获取数据，支持传参替换占位符'
};

// 导出到全局
window.CFComponents = {
    LineChart,
    DonutChart,
    HelpTip,
    SELECTOR_TEMPLATES,
    EXAMPLE_RULES,
    HELP_TEXTS
};
