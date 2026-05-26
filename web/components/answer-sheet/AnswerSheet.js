const AnswerSheet = {
    name: 'AnswerSheet',
    template: `
        <div v-if="show" class="modal">
            <div class="modal-content answer-sheet-modal">
                <div class="modal-header">
                    <h3>答题卡</h3>
                    <button @click="$emit('close')" class="btn close-btn">&times;</button>
                </div>
                <div class="answer-sheet-content">
                    <div v-for="group in questions" :key="group.type" class="question-group">
                        <h4 class="group-title">{{ group.type }}</h4>
                        <div class="question-cards">
                            <button
                                v-for="question in group.questions"
                                :key="question.index"
                                class="question-card"
                                :class="getCardClasses(question)"
                                @click="$emit('jumpToQuestion', question.index)"
                            >
                                {{ question.displayNumber }}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `,
    props: {
        show: {
            type: Boolean,
            required: true
        },
        questions: {
            type: Array,
            required: true
            // 按题型分组的题目数组
            // 期望结构: [{ type: '单选题', questions: [{ index, displayNumber, is_answered, is_viewed }] }]
        },
        currentIndex: {
            type: Number,
            required: true
        }
    },
    emits: ['close', 'jumpToQuestion'],
    methods: {
        getCardClasses(question) {
            const classes = [];
            if (question.is_answered) classes.push('answered');
            if (question.is_viewed) classes.push('viewed');
            if (question.index === this.currentIndex) classes.push('current');
            return classes;
        }
    }
};
window.AnswerSheet = AnswerSheet;
