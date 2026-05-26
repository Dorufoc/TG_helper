/**
 * Md3Select 组件 - Material Design 3 下拉选择菜单
 * 遵循项目现有的MD3主题色和设计风格，支持动画效果
 * 下拉菜单通过 Teleport 挂载到 body，使用 fixed 定位实现全局浮动
 */
const Md3Select = {
    name: 'Md3Select',
    template: `
        <div class="md3-select" :class="{ 'is-open': isOpen, 'is-disabled': disabled }" ref="selectRef">
            <!-- 触发按钮 -->
            <button
                type="button"
                class="md3-select-trigger"
                @click="toggleDropdown"
                :disabled="disabled"
                :aria-expanded="isOpen"
                aria-haspopup="listbox"
            >
                <span class="md3-select-label" v-if="label">{{ label }}</span>
                <span class="md3-select-value" :class="{ 'is-placeholder': !selectedOption }">
                    {{ displayValue }}
                </span>
                <span class="md3-select-arrow">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="6 9 12 15 18 9"></polyline>
                    </svg>
                </span>
            </button>

            <!-- 下拉菜单 (Teleport to body for global floating) -->
            <teleport to="body">
                <transition name="md3-select-dropdown">
                    <div
                        v-show="isOpen"
                        v-if="isOpen"
                        class="md3-select-dropdown"
                        role="listbox"
                        :aria-label="label || '选择菜单'"
                        :style="dropdownStyle"
                        :data-direction="dropdownDirection"
                        ref="dropdownRef"
                    >
                        <div class="md3-select-options">
                            <div
                                v-for="(option, index) in options"
                                :key="getOptionValue(option)"
                                class="md3-select-option"
                                :class="{
                                    'is-selected': isSelected(option),
                                    'is-highlighted': highlightedIndex === index
                                }"
                                role="option"
                                :aria-selected="isSelected(option)"
                                @click="selectOption(option)"
                                @mouseenter="highlightedIndex = index"
                            >
                                <span class="md3-select-option-text">{{ getOptionLabel(option) }}</span>
                                <span v-if="isSelected(option)" class="md3-select-check">
                                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                                        <polyline points="20 6 9 17 4 12"></polyline>
                                    </svg>
                                </span>
                            </div>
                        </div>
                    </div>
                </transition>
            </teleport>
        </div>
    `,
    props: {
        modelValue: {
            type: [String, Number, Object],
            default: null
        },
        options: {
            type: Array,
            default: () => []
        },
        label: {
            type: String,
            default: ''
        },
        placeholder: {
            type: String,
            default: '请选择'
        },
        disabled: {
            type: Boolean,
            default: false
        },
        optionLabel: {
            type: String,
            default: 'label'
        },
        optionValue: {
            type: String,
            default: 'value'
        }
    },
    emits: ['update:modelValue', 'change'],
    data() {
        return {
            isOpen: false,
            highlightedIndex: -1,
            dropdownStyle: {},
            dropdownDirection: 'down'
        };
    },
    computed: {
        selectedOption() {
            return this.options.find(opt => this.getOptionValue(opt) === this.modelValue);
        },
        displayValue() {
            if (this.selectedOption) {
                return this.getOptionLabel(this.selectedOption);
            }
            return this.placeholder;
        }
    },
    watch: {
        isOpen(val) {
            if (val) {
                this.highlightedIndex = this.options.findIndex(opt => this.isSelected(opt));
                this.$nextTick(() => {
                    this.updateDropdownPosition();
                    requestAnimationFrame(() => {
                        this.updateDropdownPosition();
                    });
                });
                document.addEventListener('click', this.handleClickOutside);
                document.addEventListener('keydown', this.handleKeydown);
                window.addEventListener('scroll', this.updateDropdownPosition, true);
                window.addEventListener('resize', this.updateDropdownPosition);
            } else {
                document.removeEventListener('click', this.handleClickOutside);
                document.removeEventListener('keydown', this.handleKeydown);
                window.removeEventListener('scroll', this.updateDropdownPosition, true);
                window.removeEventListener('resize', this.updateDropdownPosition);
                this.highlightedIndex = -1;
            }
        }
    },
    beforeUnmount() {
        document.removeEventListener('click', this.handleClickOutside);
        document.removeEventListener('keydown', this.handleKeydown);
        window.removeEventListener('scroll', this.updateDropdownPosition, true);
        window.removeEventListener('resize', this.updateDropdownPosition);
    },
    methods: {
        getOptionLabel(option) {
            if (typeof option === 'string' || typeof option === 'number') {
                return option;
            }
            return option[this.optionLabel] || '';
        },
        getOptionValue(option) {
            if (typeof option === 'string' || typeof option === 'number') {
                return option;
            }
            return option[this.optionValue];
        },
        isSelected(option) {
            return this.getOptionValue(option) === this.modelValue;
        },
        toggleDropdown() {
            if (this.disabled) return;
            this.isOpen = !this.isOpen;
        },
        selectOption(option) {
            const value = this.getOptionValue(option);
            this.$emit('update:modelValue', value);
            this.$emit('change', value);
            this.isOpen = false;
        },
        handleClickOutside(event) {
            if (this.$refs.selectRef && !this.$refs.selectRef.contains(event.target)) {
                this.isOpen = false;
            }
        },
        updateDropdownPosition() {
            const trigger = this.$refs.selectRef;
            const dropdown = this.$refs.dropdownRef;
            if (!trigger) return;

            const rect = trigger.getBoundingClientRect();
            const triggerButton = trigger.querySelector('.md3-select-trigger');
            const dropdownMaxHeight = 280;
            const viewportPadding = 8;
            const dropdownGap = 4;
            const viewportWidth = window.innerWidth;
            const viewportHeight = window.innerHeight;
            const triggerWidth = triggerButton ? triggerButton.getBoundingClientRect().width : rect.width;
            const dropdownHeight = dropdown ? dropdown.offsetHeight : 0;

            // 计算上下可用空间，预留边缘安全距离。
            const spaceBelow = viewportHeight - rect.bottom - viewportPadding;
            const spaceAbove = rect.top;

            let top;
            let maxHeight = Math.max(0, Math.min(dropdownMaxHeight, spaceBelow));
            let direction = 'down';

            const canOpenDownFully = dropdownHeight > 0 && dropdownHeight <= spaceBelow;
            const canOpenUpFully = dropdownHeight > 0 && dropdownHeight <= spaceAbove - viewportPadding;

            // 默认向下，只有下方不够时才切到上方。
            if (canOpenDownFully || spaceBelow >= spaceAbove) {
                top = rect.bottom + dropdownGap;
                maxHeight = Math.max(0, Math.min(dropdownMaxHeight, spaceBelow));
            } else {
                direction = 'up';
                maxHeight = Math.max(0, Math.min(dropdownMaxHeight, spaceAbove - viewportPadding));
                const renderedHeight = dropdownHeight > 0 ? Math.min(dropdownHeight, maxHeight) : maxHeight;
                top = rect.top - renderedHeight - dropdownGap;
            }

            // 兜底钳制，保证浮层始终留在视口内。
            const minTop = viewportPadding;
            const maxTop = Math.max(viewportPadding, viewportHeight - viewportPadding - Math.min(dropdownHeight || maxHeight, maxHeight));
            top = Math.min(Math.max(top, minTop), maxTop);

            // 水平对齐：默认左对齐，超出右边界时右对齐
            let left = rect.left;
            const minWidth = Math.max(triggerWidth, 120);
            if (left + minWidth > viewportWidth - viewportPadding) {
                left = Math.max(viewportPadding, viewportWidth - minWidth - viewportPadding);
            }

            this.dropdownDirection = direction;
            this.dropdownStyle = {
                position: 'fixed',
                top: top + 'px',
                left: left + 'px',
                width: triggerWidth + 'px',
                maxHeight: maxHeight + 'px',
                zIndex: 9999
            };
        },
        handleKeydown(event) {
            if (!this.isOpen) return;

            switch (event.key) {
                case 'Escape':
                    this.isOpen = false;
                    break;
                case 'ArrowDown':
                    event.preventDefault();
                    this.highlightedIndex = Math.min(this.highlightedIndex + 1, this.options.length - 1);
                    break;
                case 'ArrowUp':
                    event.preventDefault();
                    this.highlightedIndex = Math.max(this.highlightedIndex - 1, 0);
                    break;
                case 'Enter':
                    event.preventDefault();
                    if (this.highlightedIndex >= 0 && this.highlightedIndex < this.options.length) {
                        this.selectOption(this.options[this.highlightedIndex]);
                    }
                    break;
            }
        }
    }
};

window.Md3Select = Md3Select;
