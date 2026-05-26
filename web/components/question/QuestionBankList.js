const QuestionBankList = {
    name: 'QuestionBankList',
    props: {
        availableFiles: {
            type: Array,
            default: () => []
        },
        filePath: {
            type: String,
            default: 'questions.json'
        },
        isLoggedIn: {
            type: Boolean,
            default: false
        },
        wrongBooks: {
            type: Array,
            default: () => []
        },
        showWrongBooks: {
            type: Boolean,
            default: false
        },
        stats: {
            type: Object,
            default: null
        },
        error: {
            type: String,
            default: ''
        },
        userRole: {
            type: String,
            default: 'user'
        }
    },
    emits: ['selectFile', 'loadQuestions', 'toggleWrongBooks', 'loadWrongBook', 'deleteWrongBook', 'goToExtract', 'logout'],
    template: `
        <div class="container">
            <div class="load-page-header">
                <h1>在线答题系统</h1>
                <div class="header-actions">
                    <a
                        v-if="isLoggedIn"
                        href="/rag"
                        class="btn btn-secondary rag-btn"
                    >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                        </svg>
                        知识库
                    </a>
                    <a
                        v-if="userRole === 'admin'"
                        href="/admin"
                        class="btn btn-secondary admin-btn"
                    >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                        </svg>
                        管理后台
                    </a>
                    <button @click="$emit('logout')" class="btn btn-secondary logout-btn">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                            <polyline points="16 17 21 12 16 7"/>
                            <line x1="21" y1="12" x2="9" y2="12"/>
                        </svg>
                        退出登录
                    </button>
                </div>
            </div>

            <div class="form-group">
                <label>选择题库：</label>
                <div class="question-bank-list">
                    <div
                        v-for="file in availableFiles"
                        :key="file"
                        class="question-bank-item"
                        :class="{ 'selected': filePath === file }"
                        @click="$emit('selectFile', file)"
                    >
                        <span class="file-icon">📄</span>
                        <span class="file-name">{{ file }}</span>
                    </div>
                    <div v-if="availableFiles.length === 0" class="no-data">
                        暂无可用题库，请将JSON文件放入paper_json目录
                    </div>
                </div>
            </div>

            <div v-if="isLoggedIn" class="form-group wrong-books-section">
                <div class="wrong-books-header" @click="$emit('toggleWrongBooks')">
                    <span class="wrong-books-icon">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                            <polyline points="14 2 14 8 20 8"/>
                            <line x1="9" y1="15" x2="15" y2="15"/>
                        </svg>
                    </span>
                    <span class="wrong-books-title">我的错题本 ({{ wrongBooks.length }})</span>
                    <svg
                        class="wrong-books-arrow"
                        :class="{ 'rotated': showWrongBooks }"
                        width="16"
                        height="16"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                    >
                        <polyline points="6 9 12 15 18 9"/>
                    </svg>
                </div>

                <Transition name="expand">
                    <div v-if="showWrongBooks" class="wrong-books-list">
                        <div
                            v-for="book in wrongBooks"
                            :key="book.file_name"
                            class="wrong-book-item"
                            @click="$emit('loadWrongBook', book.file_name)"
                        >
                            <span class="wrong-book-icon">📝</span>
                            <div class="wrong-book-info">
                                <span class="wrong-book-title">{{ book.title }}</span>
                                <span class="wrong-book-meta">{{ book.total_questions }}题 · {{ book.generated_at }}</span>
                            </div>
                            <button
                                class="btn delete-book-btn"
                                @click.stop="$emit('deleteWrongBook', book.file_name, book.title)"
                                title="删除错题本"
                            >
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <polyline points="3 6 5 6 21 6"/>
                                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                                    <line x1="10" y1="11" x2="10" y2="17"/>
                                    <line x1="14" y1="11" x2="14" y2="17"/>
                                </svg>
                            </button>
                        </div>
                        <div v-if="wrongBooks.length === 0" class="no-data">
                            暂无错题本，完成答题后可生成错题本
                        </div>
                    </div>
                </Transition>
            </div>

            <button @click="$emit('loadQuestions')" class="btn btn-primary" :disabled="!filePath">
                加载题库
            </button>

            <div v-if="error" class="error-message">{{ error }}</div>

            <div v-if="stats" class="stats">
                <h3>题库统计：</h3>
                <p>总题数：{{ stats.total_questions }}</p>
                <ul>
                    <li v-for="(count, type) in stats.stats" :key="type">
                        {{ type }}：{{ count }}题
                    </li>
                </ul>
                <button @click="$emit('goToExtract')" class="btn btn-secondary">
                    开始抽取题目
                </button>
            </div>
        </div>
    `
};
window.QuestionBankList = QuestionBankList;
