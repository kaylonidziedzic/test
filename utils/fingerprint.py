"""
浏览器指纹随机化与反检测工具

通过 JavaScript 注入修改浏览器指纹，降低被检测风险。

支持的指纹类型:
- Canvas 指纹
- WebGL 指纹
- AudioContext 指纹
- Navigator 属性
- 自动化特征隐藏
"""

import random


def generate_noise() -> float:
    """生成微小的随机噪声值"""
    return random.uniform(-0.0001, 0.0001)


def get_stealth_script() -> str:
    """生成隐藏自动化特征的 JavaScript 脚本

    这是最关键的反检测脚本，必须在页面加载前注入。

    Returns:
        str: 用于注入的 JavaScript 代码
    """
    return """
    (function() {
        'use strict';

        // ========== 1. 隐藏 webdriver 属性 ==========
        // 这是最重要的检测点
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: true
        });

        // 删除 webdriver 相关痕迹
        delete navigator.__proto__.webdriver;

        // ========== 2. 修复 navigator.plugins ==========
        // 自动化浏览器通常 plugins 为空
        const pluginData = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
            { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
        ];

        const pluginArray = {
            length: pluginData.length,
            item: function(index) { return this[index] || null; },
            namedItem: function(name) {
                for (let i = 0; i < this.length; i++) {
                    if (this[i].name === name) return this[i];
                }
                return null;
            },
            refresh: function() {}
        };

        pluginData.forEach((p, i) => {
            pluginArray[i] = {
                name: p.name,
                filename: p.filename,
                description: p.description,
                length: 1,
                item: function() { return this; },
                namedItem: function() { return this; }
            };
        });

        Object.defineProperty(navigator, 'plugins', {
            get: () => pluginArray,
            configurable: true
        });

        // ========== 3. 修复 navigator.languages ==========
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
            configurable: true
        });

        // ========== 4. 修复 navigator.permissions ==========
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = function(parameters) {
            if (parameters.name === 'notifications') {
                return Promise.resolve({ state: Notification.permission });
            }
            return originalQuery.call(this, parameters);
        };

        // ========== 5. 隐藏 Chrome 自动化扩展 ==========
        // 移除 cdc_ 开头的属性（ChromeDriver 特征）
        const cdcProps = Object.keys(window).filter(k => k.startsWith('cdc_') || k.startsWith('$cdc_'));
        cdcProps.forEach(prop => {
            delete window[prop];
        });

        // ========== 6. 修复 window.chrome ==========
        if (!window.chrome) {
            window.chrome = {};
        }
        if (!window.chrome.runtime) {
            window.chrome.runtime = {
                connect: function() {},
                sendMessage: function() {},
                onMessage: { addListener: function() {} },
                onConnect: { addListener: function() {} },
                PlatformOs: { MAC: 'mac', WIN: 'win', ANDROID: 'android', CROS: 'cros', LINUX: 'linux', OPENBSD: 'openbsd' },
                PlatformArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64' },
                PlatformNaclArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64' },
                RequestUpdateCheckStatus: { THROTTLED: 'throttled', NO_UPDATE: 'no_update', UPDATE_AVAILABLE: 'update_available' },
                OnInstalledReason: { INSTALL: 'install', UPDATE: 'update', CHROME_UPDATE: 'chrome_update', SHARED_MODULE_UPDATE: 'shared_module_update' },
                OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' }
            };
        }

        // ========== 7. 修复 Permissions API ==========
        const originalPermissions = navigator.permissions;
        if (originalPermissions) {
            const originalQueryMethod = originalPermissions.query.bind(originalPermissions);
            navigator.permissions.query = async function(desc) {
                if (desc.name === 'notifications') {
                    return { state: 'prompt', onchange: null };
                }
                return originalQueryMethod(desc);
            };
        }

        // ========== 8. 隐藏 Headless 特征 ==========
        // 修复 navigator.connection
        if (!navigator.connection) {
            Object.defineProperty(navigator, 'connection', {
                get: () => ({
                    effectiveType: '4g',
                    rtt: 50,
                    downlink: 10,
                    saveData: false
                }),
                configurable: true
            });
        }

        // ========== 9. 修复 screen 属性 ==========
        Object.defineProperty(screen, 'availWidth', { get: () => screen.width, configurable: true });
        Object.defineProperty(screen, 'availHeight', { get: () => screen.height, configurable: true });

        // ========== 10. 防止 toString 检测 ==========
        // 某些检测会检查函数的 toString 是否被修改
        const nativeToString = Function.prototype.toString;
        const customFunctions = new WeakSet();

        Function.prototype.toString = function() {
            if (customFunctions.has(this)) {
                return 'function ' + this.name + '() { [native code] }';
            }
            return nativeToString.call(this);
        };

        customFunctions.add(Function.prototype.toString);

        // 标记已注入
        window.__stealthProtected = true;

    })();
    """


def get_fingerprint_script() -> str:
    """生成指纹随机化的 JavaScript 脚本

    注意：此脚本经过优化，只在指纹检测场景添加噪声，
    不会干扰正常的 Canvas 渲染（如 Cloudflare 验证动画）。

    Returns:
        str: 用于注入的 JavaScript 代码
    """
    # 每次生成不同的噪声种子
    noise_seed = random.randint(1, 1000000)

    script = f"""
    (function() {{
        'use strict';

        // 噪声种子
        const noiseSeed = {noise_seed};

        // 简单的伪随机数生成器
        function seededRandom(seed) {{
            const x = Math.sin(seed) * 10000;
            return x - Math.floor(x);
        }}

        // ========== Canvas 指纹随机化（智能模式） ==========
        // 只在 toDataURL 调用时添加噪声，不影响正常渲染
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        const originalToBlob = HTMLCanvasElement.prototype.toBlob;
        const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;

        // 判断是否是指纹检测调用（小尺寸 Canvas 通常用于指纹）
        function isFingerprinting(canvas) {{
            // 指纹检测通常使用小尺寸 Canvas
            if (canvas.width <= 300 && canvas.height <= 300) {{
                return true;
            }}
            // 检查是否有特定的指纹检测文本
            const ctx = canvas.getContext('2d');
            if (ctx) {{
                try {{
                    const imageData = originalGetImageData.call(ctx, 0, 0, Math.min(canvas.width, 16), Math.min(canvas.height, 16));
                    // 如果有非空像素，可能是指纹检测
                    for (let i = 0; i < imageData.data.length; i += 4) {{
                        if (imageData.data[i] !== 0 || imageData.data[i+1] !== 0 || imageData.data[i+2] !== 0) {{
                            return true;
                        }}
                    }}
                }} catch(e) {{}}
            }}
            return false;
        }}

        // 添加噪声到 ImageData
        function addNoise(imageData) {{
            const data = imageData.data;
            for (let i = 0; i < data.length; i += 4) {{
                const noise = seededRandom(noiseSeed + i) * 2 - 1;
                data[i] = Math.max(0, Math.min(255, data[i] + noise));     // R
                data[i+1] = Math.max(0, Math.min(255, data[i+1] + noise)); // G
                data[i+2] = Math.max(0, Math.min(255, data[i+2] + noise)); // B
            }}
            return imageData;
        }}

        // 修改 toDataURL - 只在指纹检测时添加噪声
        HTMLCanvasElement.prototype.toDataURL = function(type, quality) {{
            if (isFingerprinting(this)) {{
                const context = this.getContext('2d');
                if (context) {{
                    try {{
                        const imageData = originalGetImageData.call(context, 0, 0, this.width, this.height);
                        addNoise(imageData);
                        context.putImageData(imageData, 0, 0);
                    }} catch(e) {{}}
                }}
            }}
            return originalToDataURL.call(this, type, quality);
        }};

        // 修改 toBlob - 只在指纹检测时添加噪声
        HTMLCanvasElement.prototype.toBlob = function(callback, type, quality) {{
            if (isFingerprinting(this)) {{
                const context = this.getContext('2d');
                if (context) {{
                    try {{
                        const imageData = originalGetImageData.call(context, 0, 0, this.width, this.height);
                        addNoise(imageData);
                        context.putImageData(imageData, 0, 0);
                    }} catch(e) {{}}
                }}
            }}
            return originalToBlob.call(this, callback, type, quality);
        }};

        // ========== WebGL 指纹随机化 ==========
        const getParameterProxyHandler = {{
            apply: function(target, thisArg, args) {{
                const param = args[0];
                const result = Reflect.apply(target, thisArg, args);

                // 随机化渲染器和厂商信息
                if (param === 37445) {{ // UNMASKED_VENDOR_WEBGL
                    return 'Google Inc. (NVIDIA)';
                }}
                if (param === 37446) {{ // UNMASKED_RENDERER_WEBGL
                    const renderers = [
                        'ANGLE (NVIDIA, NVIDIA GeForce GTX 1080 Direct3D11 vs_5_0 ps_5_0)',
                        'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0)',
                        'ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 Direct3D11 vs_5_0 ps_5_0)',
                        'ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0)',
                    ];
                    return renderers[noiseSeed % renderers.length];
                }}

                return result;
            }}
        }};

        // 代理 WebGL getParameter
        const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = new Proxy(originalGetParameter, getParameterProxyHandler);

        // WebGL2 也需要处理
        if (typeof WebGL2RenderingContext !== 'undefined') {{
            const originalGetParameter2 = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = new Proxy(originalGetParameter2, getParameterProxyHandler);
        }}

        // ========== AudioContext 指纹随机化 ==========
        const originalCreateAnalyser = AudioContext.prototype.createAnalyser;
        AudioContext.prototype.createAnalyser = function() {{
            const analyser = originalCreateAnalyser.call(this);
            const originalGetFloatFrequencyData = analyser.getFloatFrequencyData.bind(analyser);

            analyser.getFloatFrequencyData = function(array) {{
                originalGetFloatFrequencyData(array);
                for (let i = 0; i < array.length; i++) {{
                    array[i] += seededRandom(noiseSeed + i) * 0.1;
                }}
            }};

            return analyser;
        }};

        // 标记已注入
        window.__fingerprintProtected = true;

    }})();
    """

    return script


def get_webrtc_disable_script() -> str:
    """生成禁用 WebRTC 泄露真实 IP 的脚本

    Returns:
        str: 用于注入的 JavaScript 代码
    """
    return """
    (function() {
        'use strict';

        // 禁用 WebRTC
        if (typeof RTCPeerConnection !== 'undefined') {
            RTCPeerConnection.prototype.createDataChannel = function() { return null; };
            RTCPeerConnection.prototype.createOffer = function() { return Promise.reject('WebRTC disabled'); };
            RTCPeerConnection.prototype.setLocalDescription = function() { return Promise.reject('WebRTC disabled'); };
        }

        window.__webrtcDisabled = true;
    })();
    """
