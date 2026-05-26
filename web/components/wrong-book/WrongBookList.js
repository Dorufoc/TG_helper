const WrongBookList = {
    name: 'WrongBookList',
    template: `
        <div class="form-group wrong-books-section">
            <div class="wrong-books-header" @click="$emit('toggle')">
                <span class="wrong-books-icon">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                        <line x1="9" y1="15" x2="15" y2="15"/>
                    </svg>
                </span>
                <span class="wrong-books-title">我的错题本 ({{ wrongBooks.length }})</span>
                <svg class="wrong-books-arrow" :class="{ 'rotated': showWrongBooks }" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="6 9 12 15 18 9"/>
                </svg>
            </div>
            <Transition name="expand">
                <div v-if="showWrongBooks" class="wrong-books-list">
                    <WrongBookItem
                        v-for="book in wrongBooks"
                        :key="book.file_name"
                        :book="book"
                        @click="$emit('loadWrongBook', book.file_name)"
                        @delete="$emit('deleteWrongBook', book.file_name, book.title)"
                    />
                    <div v-if="wrongBooks.length === 0" class="no-data">
                        暂无错题本，完成答题后可生成错题本
                    </div>
                </div>
            </Transition>
        </div>
    `,
    props: {
        wrongBooks: {
            type: Array,
            required: true
        },
        showWrongBooks: {
            type: Boolean,
            required: true
        },
        isLoggedIn: {
            type: Boolean,
            required: true
        }
    },
    emits: ['toggle', 'loadWrongBook', 'deleteWrongBook'],
    components: {
        WrongBookItem: window.WrongBookItem
    }
};
window.WrongBookList = WrongBookList;
