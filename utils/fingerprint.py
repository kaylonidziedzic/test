"""
浏览器指纹随机化工具

通过 JavaScript 注入修改浏览器指纹，降低被检测风险。

支持的指纹类型:
- Canvas 指纹
- WebGL 指纹
- AudioContext 指纹
"""

import random


def generate_noise() -> float:
    """生成微小的随机噪声值"""
    return random.uniform(-0.0001, 0.0001)


def get_fingerprint_script() -> str:
    """生成指纹随机化的 JavaScript 脚本

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

        // ========== Canvas 指纹随机化 ==========
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;

        // 修改 toDataURL
        HTMLCanvasElement.prototype.toDataURL = function(type, quality) {{
            const context = this.getContext('2d');
            if (context) {{
                const imageData = originalGetImageData.call(context, 0, 0, this.width, this.height);
                const data = imageData.data;

                // 对像素数据添加微小噪声
                for (let i = 0; i < data.length; i += 4) {{
                    const noise = seededRandom(noiseSeed + i) * 2 - 1;
                    data[i] = Math.max(0, Math.min(255, data[i] + noise));     // R
                    data[i+1] = Math.max(0, Math.min(255, data[i+1] + noise)); // G
                    data[i+2] = Math.max(0, Math.min(255, data[i+2] + noise)); // B
                }}

                context.putImageData(imageData, 0, 0);
            }}
            return originalToDataURL.call(this, type, quality);
        }};

        // 修改 getImageData
        CanvasRenderingContext2D.prototype.getImageData = function(sx, sy, sw, sh) {{
            const imageData = originalGetImageData.call(this, sx, sy, sw, sh);
            const data = imageData.data;

            for (let i = 0; i < data.length; i += 4) {{
                const noise = seededRandom(noiseSeed + i) * 2 - 1;
                data[i] = Math.max(0, Math.min(255, data[i] + noise));
                data[i+1] = Math.max(0, Math.min(255, data[i+1] + noise));
                data[i+2] = Math.max(0, Math.min(255, data[i+2] + noise));
            }}

            return imageData;
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
