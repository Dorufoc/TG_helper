const WrongBookItem = {
    name: 'WrongBookItem',
    template: `
        <div class="wrong-book-item" @click="$emit('click')">
            <span class="wrong-book-icon">&#128221;</span>
            <div class="wrong-book-info">
                <span class="wrong-book-title">{{ book.title }}</span>
                <span class="wrong-book-meta">{{ book.total_questions }}题 &middot; {{ book.generated_at }}</span>
            </div>
            <button class="btn delete-book-btn" @click.stop="$emit('delete')" title="删除错题本">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="3 6 5 6 21 6"/>
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    <line x1="10" y1="11" x2="10" y2="17"/>
                    <line x1="14" y1="11" x2="14" y2="17"/>
                </svg>
            </button>
        </div>
    `,
    props: {
        book: {
            type: Object,
            required: true
            // 期望结构: { file_name, title, total_questions, generated_at }
        }
    },
    emits: ['click', 'delete']
};
window.WrongBookItem = WrongBookItem;
