/**
 * ConfirmModal - 确认弹窗组件
 * 
 * Props:
 *   - show (Boolean): 是否显示弹窗
 *   - title (String): 弹窗标题
 *   - message (String): 弹窗消息内容
 * 
 * Emits:
 *   - confirm: 用户点击确认按钮时触发
 *   - cancel: 用户点击取消按钮时触发
 */
const ConfirmModal = {
    name: 'ConfirmModal',
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
        }
    },
    emits: ['confirm', 'cancel'],
    template: `
        <div v-if="show" class="modal">
            <div class="modal-content">
                <h3>{{ title }}</h3>
                <p>{{ message }}</p>
                <div class="modal-buttons">
                    <button @click="$emit('confirm')" class="btn btn-primary">确认</button>
                    <button @click="$emit('cancel')" class="btn btn-secondary">取消</button>
                </div>
            </div>
        </div>
    `
};
window.ConfirmModal = ConfirmModal;
