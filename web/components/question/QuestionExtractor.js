const QuestionExtractor = {
    name: 'QuestionExtractor',
    props: {
        availableTypes: {
            type: Array,
            default: () => []
        },
        stats: {
            type: Object,
            default: null
        },
        typeCounts: {
            type: Object,
            default: () => ({})
        },
        totalSelectedQuestions: {
            type: Number,
            default: 0
        },
        studyMode: {
            type: Boolean,
            default: false
        },
        autoShowAnswer: {
            type: Boolean,
            default: false
        },
        shuffleOptions: {
            type: Boolean,
            default: false
        },
        error: {
            type: String,
            default: ''
        }
    },
    emits: ['extractQuestions', 'toggleStudyMode', 'toggleAutoShowAnswer', 'toggleShuffleOptions', 'update:typeCounts'],
    methods: {
        handleTypeCountChange(type, event) {
            const newCounts = { ...this.typeCounts };
            newCounts[type] = event.target.value;
            this.$emit('update:typeCounts', newCounts);
        }
    },
    template: `
        <div class="container">
            <h1>抽取题目</h1>

            <h3>题型数量设置：</h3>
            <div
                v-for="(type, index) in availableTypes"
                :key="index"
                class="form-group"
            >
                <label>{{ type }}数量（最多{{ stats.stats[type] }}题）：</label>
                <input
                    type="number"
                    :value="typeCounts[type]"
                    @input="handleTypeCountChange(type, $event)"
                    min="0"
                    :max="stats.stats[type]"
                >
            </div>

            <div class="form-group">
                <p>总题数：{{ totalSelectedQuestions }}</p>
            </div>

            <div class="form-group">
                <label>
                    <input
                        type="checkbox"
                        :checked="studyMode"
                        @change="$emit('toggleStudyMode')"
                    >
                    开启背题模式
                </label>
            </div>

            <div v-if="!studyMode" class="form-group">
                <label>
                    <input
                        type="checkbox"
                        :checked="autoShowAnswer"
                        @change="$emit('toggleAutoShowAnswer')"
                    >
                    选择答案后自动显示答案
                </label>
            </div>

            <div class="form-group">
                <label>
                    <input
                        type="checkbox"
                        :checked="shuffleOptions"
                        @change="$emit('toggleShuffleOptions')"
                    >
                    选项乱序（开启后可能导致解析选项和实际选项顺序不同）
                </label>
            </div>

            <button
                @click="$emit('extractQuestions')"
                class="btn btn-primary"
                :disabled="totalSelectedQuestions === 0"
            >
                抽取题目
            </button>

            <div v-if="error" class="error-message">{{ error }}</div>
        </div>
    `
};
window.QuestionExtractor = QuestionExtractor;
