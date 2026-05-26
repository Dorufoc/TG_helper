const TopBar = {
    name: 'TopBar',
    props: {
        isLoggedIn: {
            type: Boolean,
            default: false
        },
        currentUser: {
            type: String,
            default: ''
        },
        progress: {
            type: Number,
            default: 0
        },
        currentIndex: {
            type: Number,
            default: 0
        },
        totalQuestions: {
            type: Number,
            default: 0
        },
        isDarkMode: {
            type: Boolean,
            default: false
        }
    },
    emits: ['logout', 'toggleDarkMode', 'toggleAnswerSheet'],
    template: `
        <div class="top-bar">
            <div class="top-bar-left">
                <button
                    v-if="isLoggedIn"
                    @click="$emit('logout')"
                    class="btn btn-secondary nav-btn top-bar-btn pill-user-btn"
                >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                        <polyline points="16 17 21 12 16 7"/>
                        <line x1="21" y1="12" x2="9" y2="12"/>
                    </svg>
                    <span class="btn-text">{{ currentUser }}</span>
                </button>
            </div>

            <div class="top-bar-center">
                <div class="top-bar-progress-text">{{ currentIndex + 1 }}/{{ totalQuestions }}</div>
                <div class="top-bar-progress">
                    <div class="top-bar-progress-bar" :style="{ width: progress + '%' }"></div>
                </div>
            </div>

            <div class="top-bar-right">
                <button @click="$emit('toggleDarkMode')" class="btn btn-secondary nav-btn top-bar-btn">
                    <svg v-if="!isDarkMode" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
                    </svg>
                    <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="5"/>
                        <line x1="12" y1="1" x2="12" y2="3"/>
                        <line x1="12" y1="21" x2="12" y2="23"/>
                        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
                        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
                        <line x1="1" y1="12" x2="3" y2="12"/>
                        <line x1="21" y1="12" x2="23" y2="12"/>
                        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
                        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
                    </svg>
                </button>

                <button @click="$emit('toggleAnswerSheet')" class="btn btn-secondary nav-btn top-bar-btn">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="3" y="3" width="7" height="7"/>
                        <rect x="14" y="3" width="7" height="7"/>
                        <rect x="3" y="14" width="7" height="7"/>
                        <rect x="14" y="14" width="7" height="7"/>
                    </svg>
                </button>
            </div>
        </div>
    `
};
window.TopBar = TopBar;
