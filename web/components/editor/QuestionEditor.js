/**
 * QuestionEditor 组件 - 题目编辑组件
 * 用于在题库编辑页面中展示和编辑单道题目
 * 复用答题界面的解析逻辑，支持双向绑定和AI辅助
 */
const QuestionEditor = {
    name: 'QuestionEditor',
    props: {
        question: { type: Object, required: true },
        questionIndex: { type: Number, default: 0 },
        aiLoading: { type: Boolean, default: false }
    },
    emits: ['update', 'ai-start', 'ai-done', 'ai-error', 'notify'],
    data() {
        return {
            editingOptions: [],
            editingAnswer: [],
            localContent: '',
            localAnalysis: '',
            uploadingImage: false
        };
    },
    computed: {
        isChoiceType() {
            return ['单选题', '多选题', '判断题'].includes(this.question.type);
        },
        isInputType() {
            return ['填空题', '简答题', '释义题', '论述题', '编程题'].includes(this.question.type);
        },
        correctAnswerLetters() {
            if (!this.isChoiceType) return [];
            return (this.question.correct_answer || []).map(a => a.toUpperCase());
        }
    },
    watch: {
        question: {
            handler(q) {
                if (!q) return;
                this.localContent = q.content || '';
                this.localAnalysis = q.analysis || '';
                if (this.isChoiceType) {
                    this.editingOptions = (q.options || []).map(o => ({ text: o }));
                }
                if (this.isInputType) {
                    this.editingAnswer = [...(q.correct_answer || [])];
                }
            },
            immediate: true,
            deep: true
        }
    },
    methods: {
        getOptionLetter(index) {
            return String.fromCharCode(65 + index);
        },
        emitUpdate() {
            const updated = { ...this.question };
            updated.content = this.localContent;
            updated.analysis = this.localAnalysis;
            if (this.isChoiceType) {
                updated.options = this.editingOptions.map(o => o.text);
            }
            if (this.isInputType) {
                updated.correct_answer = [...this.editingAnswer];
            }
            this.$emit('update', updated);
        },
        addOption() {
            this.editingOptions.push({ text: '' });
            this.emitUpdate();
        },
        removeOption(index) {
            if (this.editingOptions.length <= 2) return;
            this.editingOptions.splice(index, 1);
            this.emitUpdate();
        },
        toggleAnswer(option) {
            const upper = option.toUpperCase();
            const idx = this.question.correct_answer.indexOf(upper);
            const newAnswer = [...this.question.correct_answer];
            if (idx >= 0) {
                newAnswer.splice(idx, 1);
            } else {
                if (this.question.type === '单选题' || this.question.type === '判断题') {
                    newAnswer.length = 0;
                }
                newAnswer.push(upper);
            }
            const updated = { ...this.question, correct_answer: newAnswer };
            this.$emit('update', updated);
        },
        isAnswerSelected(option) {
            return (this.question.correct_answer || []).map(a => a.toUpperCase()).includes(option.toUpperCase());
        },
        addAnswerItem() {
            this.editingAnswer.push('');
            this.emitUpdate();
        },
        removeAnswerItem(index) {
            if (this.editingAnswer.length <= 1) return;
            this.editingAnswer.splice(index, 1);
            this.emitUpdate();
        },
        getQuestionImage(imagePath) {
            if (!imagePath) return '';
            if (imagePath.startsWith('http://') || imagePath.startsWith('https://') || imagePath.startsWith('data:')) {
                return imagePath;
            }
            let p = imagePath.replace(/\\/g, '/');
            if (p.startsWith('/')) p = p.substring(1);
            return '/api/question_image/' + p;
        },
        async aiParseAnalysis() {
            this.$emit('ai-start', 'analysis');
            try {
                const res = await fetch('/api/admin/question_bank/ai_parse', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                    body: JSON.stringify({
                        content: this.localContent,
                        options: this.isChoiceType ? this.editingOptions.map(o => o.text) : (this.question.options || []),
                        correct_answer: this.question.correct_answer || [],
                        type: this.question.type,
                        mode: 'parse_analysis'
                    })
                });
                const data = await res.json();
                if (data.success) {
                    this.localAnalysis = data.result || '';
                    this.emitUpdate();
                } else {
                    this.$emit('ai-error', data.message || 'AI解析失败');
                }
            } catch (e) {
                this.$emit('ai-error', e.message);
            } finally {
                this.$emit('ai-done', 'analysis');
            }
        },
        async aiParseAnswer() {
            this.$emit('ai-start', 'answer');
            try {
                const res = await fetch('/api/admin/question_bank/ai_parse', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                    body: JSON.stringify({
                        content: this.localContent,
                        options: this.isChoiceType ? this.editingOptions.map(o => o.text) : (this.question.options || []),
                        correct_answer: this.question.correct_answer || [],
                        type: this.question.type,
                        mode: 'parse_answer'
                    })
                });
                const data = await res.json();
                if (data.success) {
                    const aiResult = (data.result || '').trim();
                    if (this.isChoiceType) {
                        const letters = aiResult.match(/[A-Z]/g);
                        if (letters && letters.length > 0) {
                            const newAnswer = letters.map(l => l.toUpperCase());
                            const updated = { ...this.question, correct_answer: newAnswer };
                            this.$emit('update', updated);
                        }
                    } else if (this.isInputType) {
                        const parts = aiResult.split(/\n+/).filter(s => s.trim());
                        if (parts.length > 0) {
                            this.editingAnswer = parts.map(p => p.trim());
                            this.emitUpdate();
                        }
                    }
                } else {
                    this.$emit('ai-error', data.message || 'AI答案生成失败');
                }
            } catch (e) {
                this.$emit('ai-error', e.message);
            } finally {
                this.$emit('ai-done', 'answer');
            }
        },
        triggerImageUpload() {
            this.$refs.imageInput?.click();
        },
        async handleImageUpload(event) {
            const file = event.target.files?.[0];
            if (!file) return;
            
            const allowedTypes = ['image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/bmp'];
            if (!allowedTypes.includes(file.type)) {
                this.$emit('notify', 'error', '仅支持 PNG、JPG、GIF、WebP、BMP 格式的图片');
                return;
            }
            
            if (file.size > 10 * 1024 * 1024) {
                this.$emit('notify', 'error', '图片大小不能超过 10MB');
                return;
            }
            
            this.uploadingImage = true;
            try {
                const formData = new FormData();
                formData.append('image', file);
                
                const res = await fetch('/api/admin/question_bank/upload_image', {
                    method: 'POST',
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                    body: formData
                });
                const data = await res.json();
                
                if (data.success) {
                    const updated = { ...this.question, image: data.image_url };
                    this.$emit('update', updated);
                } else {
                    this.$emit('notify', 'error', data.message || '图片上传失败');
                }
            } catch (e) {
                this.$emit('notify', 'error', '图片上传失败');
            } finally {
                this.uploadingImage = false;
                event.target.value = '';
            }
        },
        removeImage() {
            const updated = { ...this.question, image: '' };
            this.$emit('update', updated);
        }
    },
    template: `
        <div class="question-editor-card" :key="question.id || questionIndex">
            <div class="qe-header">
                <span class="qe-number">第 {{ questionIndex + 1 }} 题</span>
                <span class="chip primary">{{ question.type }}</span>
            </div>

            <div v-if="question.image" class="qe-image-wrapper">
                <img :src="getQuestionImage(question.image)" alt="题目图片" class="qe-image" />
                <button class="qe-image-remove" @click="removeImage" title="移除图片">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
            </div>

            <div v-else class="qe-image-upload-area">
                <input type="file" ref="imageInput" accept="image/png,image/jpeg,image/gif,image/webp,image/bmp" @change="handleImageUpload" style="display:none" />
                <button class="qe-upload-btn" @click="triggerImageUpload" :disabled="uploadingImage">
                    <svg v-if="!uploadingImage" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                    <svg v-else width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10" stroke-dasharray="60" stroke-dashoffset="15"><animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="1s" repeatCount="indefinite"/></circle></svg>
                    <span v-if="!uploadingImage">上传题目图片</span>
                    <span v-else>上传中...</span>
                </button>
            </div>

            <div class="qe-section">
                <label class="qe-section-label">题目内容</label>
                <textarea class="qe-textarea" v-model="localContent" rows="3" @input="emitUpdate" placeholder="请输入题目内容"></textarea>
            </div>

            <template v-if="isChoiceType">
                <div class="qe-section">
                    <label class="qe-section-label">选项</label>
                    <div class="qe-options-list">
                        <div v-for="(opt, idx) in editingOptions" :key="idx" class="qe-option-row">
                            <span class="qe-option-letter">{{ getOptionLetter(idx) }}.</span>
                            <input type="text" class="qe-option-input" v-model="opt.text" @input="emitUpdate" :placeholder="'选项' + getOptionLetter(idx)" />
                            <button class="btn btn-icon" @click="removeOption(idx)" :disabled="editingOptions.length <= 2" title="删除选项">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                            </button>
                        </div>
                        <div class="qe-action-row">
                            <button class="btn btn-tonal btn-small" @click="addOption">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                                添加选项
                            </button>
                        </div>
                    </div>
                </div>

                <div class="qe-section">
                    <label class="qe-section-label">正确答案</label>
                    <div class="qe-answer-chips">
                        <button
                            v-for="(opt, idx) in editingOptions"
                            :key="'ans-' + idx"
                            :class="['qe-answer-chip', { active: isAnswerSelected(getOptionLetter(idx)) }]"
                            @click="toggleAnswer(getOptionLetter(idx))"
                        >
                            {{ getOptionLetter(idx) }}
                        </button>
                    </div>
                    <div class="qe-action-row">
                        <button class="btn btn-tonal btn-small" @click="aiParseAnswer" :disabled="aiLoading">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 1 0 10 10H12V2z"/><circle cx="12" cy="12" r="3"/></svg>
                            AI答案
                        </button>
                    </div>
                </div>
            </template>

            <template v-if="isInputType">
                <div class="qe-section">
                    <label class="qe-section-label">正确答案</label>
                    <div class="qe-input-answers">
                        <div v-for="(ans, idx) in editingAnswer" :key="'ia-' + idx" class="qe-input-row">
                            <span class="qe-input-label">空{{ idx + 1 }}:</span>
                            <input type="text" class="qe-input-field" v-model="editingAnswer[idx]" @input="emitUpdate" :placeholder="'第' + (idx + 1) + '个空的答案'" />
                            <button class="btn btn-icon" @click="removeAnswerItem(idx)" :disabled="editingAnswer.length <= 1" title="删除">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                            </button>
                        </div>
                        <div class="qe-action-row">
                            <button class="btn btn-tonal btn-small" @click="addAnswerItem">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                                添加空
                            </button>
                        </div>
                    </div>
                    <div class="qe-action-row">
                        <button class="btn btn-tonal btn-small" @click="aiParseAnswer" :disabled="aiLoading">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 1 0 10 10H12V2z"/><circle cx="12" cy="12" r="3"/></svg>
                            AI答案
                        </button>
                    </div>
                </div>
            </template>

            <div class="qe-section">
                <label class="qe-section-label">答案解析</label>
                <textarea class="qe-textarea qe-analysis-area" v-model="localAnalysis" rows="5" @input="emitUpdate" placeholder="请输入答案解析"></textarea>
                <div class="qe-action-row">
                    <button class="btn btn-tonal btn-small" @click="aiParseAnalysis" :disabled="aiLoading">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 1 0 10 10H12V2z"/><circle cx="12" cy="12" r="3"/></svg>
                        AI解析
                    </button>
                </div>
            </div>
        </div>
    `
};

window.QuestionEditor = QuestionEditor;
