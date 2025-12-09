// /opt/xin/patches/stealth.js
(() => {
    console.log('[Stealth] Injecting CDP MouseEvent Patch...');

    // 核心：修复 CDP 环境下 MouseEvent.screenX/Y 为 0 的指纹特征
    // 来源：CDP-bug-MouseEvent-.screenX-.screenY-patcher
    try {
        const getScreenX = Object.getOwnPropertyDescriptor(MouseEvent.prototype, 'screenX').get;
        const getScreenY = Object.getOwnPropertyDescriptor(MouseEvent.prototype, 'screenY').get;

        Object.defineProperty(MouseEvent.prototype, 'screenX', {
            get: function() {
                // 只有当事件是“可信的”且原始值为0时，才进行修补
                if (this.isTrusted && getScreenX.call(this) === 0) {
                    // clientX + window.screenX 模拟真实的屏幕绝对坐标
                    return this.clientX + (window.screenX || 0);
                }
                return getScreenX.call(this);
            }
        });

        Object.defineProperty(MouseEvent.prototype, 'screenY', {
            get: function() {
                if (this.isTrusted && getScreenY.call(this) === 0) {
                    return this.clientY + (window.screenY || 0);
                }
                return getScreenY.call(this);
            }
        });
    } catch (e) {
        console.error('[Stealth] Patch failed:', e);
    }
})();
