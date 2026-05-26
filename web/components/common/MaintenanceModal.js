/**
 * MaintenanceModal - 维护/游客提示弹窗组件
 * 
 * Props:
 *   - show (Boolean): 是否显示弹窗
 *   - title (String): 弹窗标题
 *   - message (String): 弹窗消息内容
 *   - errorHint (String): 错误提示编码（如 err:404notfind）
 */
const MaintenanceModal = {
    name: 'MaintenanceModal',
    props: {
        show: {
            type: Boolean,
            default: false
        },
        title: {
            type: String,
            default: ''
        },
        message: {
            type: String,
            default: ''
        },
        errorHint: {
            type: String,
            default: ''
        }
    },
    template: `
        <div v-if="show" class="maintenance-modal">
            <div class="maintenance-content">
                <div class="maintenance-icon">
                    <svg width="80" height="80" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="10"/>
                        <line x1="12" y1="8" x2="12" y2="12"/>
                        <line x1="12" y1="16" x2="12.01" y2="16"/>
                    </svg>
                </div>
                <h2>{{ title }}</h2>
                <p>{{ message }}</p>
                <p v-if="errorHint" class="maintenance-hint">{{ errorHint }}</p>
            </div>
        </div>
    `
};
window.MaintenanceModal = MaintenanceModal;
