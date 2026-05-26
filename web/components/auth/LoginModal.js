/**
 * LoginModal - 登录/注册弹窗组件
 * 
 * Props:
 *   - show (Boolean): 是否显示弹窗
 *   - authMode (String): 当前模式，'login' 或 'register'
 *   - authForm (Object): 表单数据对象，包含:
 *       - username (String): 用户名
 *       - password (String): 密码
 *       - confirmPassword (String): 确认密码
 *       - captcha (String): 验证码
 *       - inviteCode (String): 邀请码
 *       - rememberPassword (Boolean): 是否记住用户名
 *   - authLoading (Boolean): 是否正在加载/提交中
 *   - authError (String): 认证错误信息
 *   - captchaUrl (String): 验证码图片URL
 * 
 * Emits:
 *   - login: 用户点击登录按钮时触发
 *   - register: 用户点击注册按钮时触发
 *   - switchMode: 用户切换登录/注册模式时触发
 *   - refreshCaptcha: 用户点击刷新验证码时触发
 *   - close: 用户关闭弹窗时触发
 */
const LoginModal = {
    name: 'LoginModal',
    props: {
        show: {
            type: Boolean,
            default: false
        },
        authMode: {
            type: String,
            default: 'login',
            validator(value) {
                return ['login', 'register'].includes(value);
            }
        },
        authForm: {
            type: Object,
            default: () => ({
                username: '',
                password: '',
                confirmPassword: '',
                captcha: '',
                inviteCode: '',
                rememberPassword: false
            })
        },
        authLoading: {
            type: Boolean,
            default: false
        },
        authError: {
            type: String,
            default: ''
        },
        captchaUrl: {
            type: String,
            default: ''
        }
    },
    emits: ['login', 'register', 'switchMode', 'refreshCaptcha', 'close'],
    template: `
        <div v-if="show" class="modal login-modal">
            <div class="modal-content login-modal-content">
                <div class="login-modal-header">
                    <h2>用户登录</h2>
                </div>
                
                <!-- 登录表单 -->
                <div v-if="authMode === 'login'" class="auth-form">
                    <h3>用户登录</h3>
                    <div class="form-group">
                        <label for="login-username">用户名</label>
                        <input type="text" id="login-username" v-model="authForm.username" placeholder="请输入用户名" @keyup.enter="$emit('login')">
                    </div>
                    <div class="form-group">
                        <label for="login-password">密码</label>
                        <input type="password" id="login-password" v-model="authForm.password" placeholder="请输入密码" @keyup.enter="$emit('login')">
                    </div>
                    <div class="form-group remember-password-group">
                        <label>
                            <input type="checkbox" v-model="authForm.rememberPassword"> 记住用户名
                        </label>
                    </div>
                    <div class="form-group captcha-group">
                        <label for="login-captcha">验证码</label>
                        <div class="captcha-input">
                            <input type="text" id="login-captcha" v-model="authForm.captcha" placeholder="请输入验证码" maxlength="4" @keyup.enter="$emit('login')">
                            <img :src="captchaUrl" @click="$emit('refreshCaptcha')" class="captcha-image" alt="验证码" title="点击刷新">
                        </div>
                    </div>
                    <button @click="$emit('login')" class="btn btn-primary auth-btn" :disabled="authLoading">
                        <span v-if="authLoading">登录中...</span>
                        <span v-else>登录</span>
                    </button>
                    <p class="auth-switch">
                        还没有账号？
                        <a @click="$emit('switchMode', 'register')">立即注册</a>
                    </p>
                </div>

                <!-- 注册表单 -->
                <div v-if="authMode === 'register'" class="auth-form">
                    <h3>用户注册</h3>
                    <div class="form-group">
                        <label for="reg-username">用户名</label>
                        <input type="text" id="reg-username" v-model="authForm.username" placeholder="3-20位字母或数字" @keyup.enter="$emit('register')">
                    </div>
                    <div class="form-group">
                        <label for="reg-password">密码</label>
                        <input type="password" id="reg-password" v-model="authForm.password" placeholder="至少6个字符" @keyup.enter="$emit('register')">
                    </div>
                    <div class="form-group">
                        <label for="reg-confirm-password">确认密码</label>
                        <input type="password" id="reg-confirm-password" v-model="authForm.confirmPassword" placeholder="再次输入密码" @keyup.enter="$emit('register')">
                    </div>
                    <div class="form-group">
                        <label for="reg-invite-code">邀请码</label>
                        <input type="text" id="reg-invite-code" v-model="authForm.inviteCode" placeholder="没有可留空" @keyup.enter="$emit('register')">
                    </div>
                    <div class="form-group captcha-group">
                        <label for="reg-captcha">验证码</label>
                        <div class="captcha-input">
                            <input type="text" id="reg-captcha" v-model="authForm.captcha" placeholder="请输入验证码" maxlength="4" @keyup.enter="$emit('register')">
                            <img :src="captchaUrl" @click="$emit('refreshCaptcha')" class="captcha-image" alt="验证码" title="点击刷新">
                        </div>
                    </div>
                    <button @click="$emit('register')" class="btn btn-primary auth-btn" :disabled="authLoading">
                        <span v-if="authLoading">注册中...</span>
                        <span v-else>注册</span>
                    </button>
                    <p class="auth-switch">
                        已有账号？
                        <a @click="$emit('switchMode', 'login')">立即登录</a>
                    </p>
                </div>

                <div v-if="authError" class="error-message">{{ authError }}</div>
            </div>
        </div>
    `
};
window.LoginModal = LoginModal;
