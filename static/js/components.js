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

// 导出到全局
window.CFComponents = {
    LineChart,
    DonutChart
};
