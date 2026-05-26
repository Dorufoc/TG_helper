/**
 * 答案验证工具模块
 * 提供答案正确性验证、得分计算、错题收集等功能
 * 支持单选题、多选题、判断题、填空题、简答题、释义题、论述题、编程题等题型
 */

// 支持的客观题类型（可精确判断对错）
const OBJECTIVE_TYPES = ['单选题', '判断题', '多选题', '选择题'];

// 支持的主观题类型（需要文本比对）
const SUBJECTIVE_TYPES = ['填空题', '简答题', '释义题', '论述题', '编程题'];

/**
 * 判断是否为客观题
 * @param {string} questionType - 题目类型
 * @returns {boolean}
 */
function isObjectiveQuestion(questionType) {
    return OBJECTIVE_TYPES.includes(questionType);
}

/**
 * 判断是否为主观题
 * @param {string} questionType - 题目类型
 * @returns {boolean}
 */
function isSubjectiveQuestion(questionType) {
    return SUBJECTIVE_TYPES.includes(questionType);
}

/**
 * 验证客观题答案（单选、多选、判断、选择）
 * @param {Array} userAnswer - 用户答案数组
 * @param {Array} correctAnswer - 正确答案数组
 * @returns {boolean} 是否正确
 */
function validateObjectiveAnswer(userAnswer, correctAnswer) {
    if (!userAnswer || !correctAnswer) return false;
    return JSON.stringify(userAnswer.slice().sort()) === JSON.stringify(correctAnswer.slice().sort());
}

/**
 * 验证主观题答案（填空、简答、释义、论述、编程）
 * @param {Array} userAnswer - 用户答案数组
 * @param {Array} correctAnswer - 正确答案数组
 * @returns {boolean} 是否正确（所有空都正确才算正确）
 */
function validateSubjectiveAnswer(userAnswer, correctAnswer) {
    if (!userAnswer || !correctAnswer) return false;
    if (userAnswer.length !== correctAnswer.length) return false;
    
    for (let i = 0; i < userAnswer.length; i++) {
        if (userAnswer[i].trim() !== correctAnswer[i].trim()) {
            return false;
        }
    }
    return true;
}

/**
 * 验证答案正确性的统一入口
 * @param {Object} question - 题目对象，包含type字段
 * @param {Array} userAnswer - 用户答案
 * @param {Array} correctAnswer - 正确答案
 * @returns {boolean} 是否正确
 */
function validateAnswer(question, userAnswer, correctAnswer) {
    if (isObjectiveQuestion(question.type)) {
        return validateObjectiveAnswer(userAnswer, correctAnswer);
    } else if (isSubjectiveQuestion(question.type)) {
        return validateSubjectiveAnswer(userAnswer, correctAnswer);
    }
    return false;
}

/**
 * 计算单题得分
 * @param {number} totalQuestions - 总题数
 * @param {boolean} isCorrect - 是否正确
 * @returns {number} 本题得分（满分100分制）
 */
function calculateQuestionScore(totalQuestions, isCorrect) {
    if (totalQuestions <= 0) return 0;
    return isCorrect ? (100 / totalQuestions) : 0;
}

/**
 * 计算考试总分
 * @param {number} correctCount - 正确题数
 * @param {number} totalQuestions - 总题数
 * @returns {number} 总分（保留一位小数）
 */
function calculateTotalScore(correctCount, totalQuestions) {
    if (totalQuestions <= 0) return 0;
    return Math.round((correctCount / totalQuestions) * 100 * 10) / 10;
}

/**
 * 统计考试结果
 * @param {Array} questions - 所有题目数组
 * @param {Object} answers - 用户答案对象，键为题目标索引，值为答案数组
 * @returns {Object} 包含correctCount、wrongCount、score、wrongQuestions的结果对象
 */
function calculateExamResults(questions, answers) {
    let correctCount = 0;
    const wrongQuestions = [];
    
    for (let i = 0; i < questions.length; i++) {
        const question = questions[i];
        const userAnswer = answers[i] || [];
        const correctAnswer = question.correct_answer;
        
        // 检查是否已作答
        const isAnswered = userAnswer.length > 0 && userAnswer.some(ans => ans && ans.trim() !== '');
        
        if (isAnswered) {
            const isCorrect = validateAnswer(question, userAnswer, correctAnswer);
            
            if (isCorrect) {
                correctCount++;
            } else {
                wrongQuestions.push({
                    index: i,
                    id: i + 1,
                    type: question.type,
                    content: question.content,
                    options: question.options || [],
                    user_answer: userAnswer,
                    correct_answer: correctAnswer,
                    analysis: question.analysis || ''
                });
            }
        }
    }
    
    return {
        correctCount: correctCount,
        wrongCount: questions.length - correctCount,
        totalQuestions: questions.length,
        score: calculateTotalScore(correctCount, questions.length),
        wrongQuestions: wrongQuestions
    };
}

/**
 * 收集错题信息
 * @param {Array} questions - 所有题目数组
 * @param {Object} answers - 用户答案对象
 * @param {number} [startIndex=0] - 起始索引（用于分批收集）
 * @param {number} [endIndex] - 结束索引（用于分批收集）
 * @returns {Array} 错题数组
 */
function collectWrongQuestions(questions, answers, startIndex = 0, endIndex = null) {
    const wrongQuestions = [];
    const end = endIndex !== null ? endIndex : questions.length;
    
    for (let i = startIndex; i < end; i++) {
        const question = questions[i];
        const userAnswer = answers[i] || [];
        const correctAnswer = question.correct_answer;
        
        const isAnswered = userAnswer.length > 0 && userAnswer.some(ans => ans && ans.trim() !== '');
        
        if (isAnswered) {
            const isCorrect = validateAnswer(question, userAnswer, correctAnswer);
            
            if (!isCorrect) {
                wrongQuestions.push({
                    index: i,
                    id: i + 1,
                    type: question.type,
                    content: question.content,
                    options: question.options || [],
                    user_answer: userAnswer,
                    correct_answer: correctAnswer,
                    analysis: question.analysis || ''
                });
            }
        }
    }
    
    return wrongQuestions;
}
