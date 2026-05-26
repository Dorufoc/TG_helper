/**
 * ToastNotification - 悬浮提示Toast组件
 * 
 * Props:
 *   - message (String): 提示消息内容
 *   - type (String): 提示类型，可选值: info / success / warning / error
 *   - show (Boolean): 是否显示
 */
const ToastNotification = {
    name: 'ToastNotification',
    props: {
        message: {
            type: String,
            default: ''
        },
        type: {
            type: String,
            default: 'info',
            validator(value) {
                return ['info', 'success', 'warning', 'error'].includes(value);
            }
        },
        show: {
            type: Boolean,
            default: false
        }
    },
    template: `
        <div v-if="show" :class="['notification', type]">
            {{ message }}
        </div>
    `
};
window.ToastNotification = ToastNotification;
