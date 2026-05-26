const ProgressBar = {
    name: 'ProgressBar',
    props: {
        progress: {
            type: Number,
            default: 0
        },
        showText: {
            type: Boolean,
            default: true
        },
        currentIndex: {
            type: Number,
            default: 0
        },
        total: {
            type: Number,
            default: 0
        }
    },
    emits: [],
    template: `
        <div class="header">
            <div v-if="showText" class="progress-text">
                <span>答题进度</span>
                <span>{{ currentIndex + 1 }}/{{ total }}</span>
            </div>
            <div class="progress">
                <div class="progress-bar" :style="{ width: progress + '%' }"></div>
            </div>
        </div>
    `
};
window.ProgressBar = ProgressBar;
