
// QS Robot UI 主逻辑 - 完整版（含语音功能）

document.addEventListener('DOMContentLoaded', () => {
    // DOM 元素
    const floatBall = document.getElementById('float-ball');
    const sidebar = document.getElementById('sidebar');
    const btnClose = document.getElementById('btn-close');
    const btnMinimize = document.getElementById('btn-minimize');
    const btnSend = document.getElementById('btn-send');
    const btnVoice = document.getElementById('btn-voice');
    const btnTTS = document.getElementById('btn-tts');
    const messageInput = document.getElementById('message-input');
    const chatContainer = document.getElementById('chat-container');
    const quickBtns = document.querySelectorAll('.quick-btn');
    const llmStatus = document.getElementById('llm-status');
    const llmStatusDot = document.getElementById('llm-status-dot');
    const systemStatus = document.getElementById('system-status');
    const systemStatusDot = document.getElementById('system-status-dot');

    let isSidebarOpen = false;
    let isLoading = false;
    let isListening = false;
    let speechRecognition = null;
    let speechSynthesis = window.speechSynthesis;

    // === 初始化语音识别 ===
    function initSpeechRecognition() {
        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            speechRecognition = new SpeechRecognition();
            speechRecognition.continuous = false;
            speechRecognition.interimResults = false;
            speechRecognition.lang = 'zh-CN';

            speechRecognition.onstart = () => {
                isListening = true;
                btnVoice.textContent = '🔴';
                btnVoice.title = '正在聆听...';
            };

            speechRecognition.onresult = (event) => {
                const transcript = event.results[0][0].transcript;
                messageInput.value = transcript;
                sendMessage();
            };

            speechRecognition.onerror = (event) => {
                console.error('Speech recognition error:', event.error);
                isListening = false;
                btnVoice.textContent = '🎤';
                btnVoice.title = '语音输入';
            };

            speechRecognition.onend = () => {
                isListening = false;
                btnVoice.textContent = '🎤';
                btnVoice.title = '语音输入';
            };

            console.log('✅ 语音识别已初始化');
        } else {
            console.warn('⚠️ 浏览器不支持语音识别');
            btnVoice.style.opacity = '0.5';
            btnVoice.title = '浏览器不支持语音识别';
        }
    }

    // === 侧边窗控制 ===
    floatBall.addEventListener('click', () => {
        if (!isSidebarOpen) {
            sidebar.classList.add('open');
            floatBall.style.display = 'none';
            isSidebarOpen = true;
            messageInput.focus();
            refreshStatus();
        }
    });

    btnClose.addEventListener('click', closeSidebar);
    btnMinimize.addEventListener('click', closeSidebar);

    function closeSidebar() {
        sidebar.classList.remove('open');
        floatBall.style.display = 'flex';
        isSidebarOpen = false;
    }

    // === 语音输入 ===
    btnVoice.addEventListener('click', () => {
        if (!speechRecognition) {
            alert('抱歉，您的浏览器不支持语音识别功能');
            return;
        }

        if (isListening) {
            speechRecognition.stop();
        } else {
            speechRecognition.start();
        }
    });

    // === 语音播报 ===
    btnTTS.addEventListener('click', () => {
        // 获取最后一条助手消息进行播报
        const messages = chatContainer.querySelectorAll('.message.assistant .message-content');
        if (messages.length === 0) {
            return;
        }

        const lastMessage = messages[messages.length - 1].textContent;
        speakText(lastMessage);
    });

    function speakText(text) {
        if (!speechSynthesis) {
            console.warn('浏览器不支持语音合成');
            return;
        }

        // 取消当前正在播放的
        speechSynthesis.cancel();

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'zh-CN';
        utterance.rate = 1.0;
        utterance.pitch = 1.0;
        utterance.volume = 1.0;

        utterance.onstart = () => {
            btnTTS.textContent = '🔊';
            btnTTS.title = '正在播报...';
        };

        utterance.onend = () => {
            btnTTS.textContent = '🔊';
            btnTTS.title = '语音播报';
        };

        utterance.onerror = (event) => {
            console.error('TTS error:', event);
            btnTTS.textContent = '🔊';
            btnTTS.title = '语音播报';
        };

        speechSynthesis.speak(utterance);
    }

    // === 发送消息 ===
    btnSend.addEventListener('click', sendMessage);
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !isLoading) {
            sendMessage();
        }
    });

    // 快捷按钮
    quickBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const query = btn.getAttribute('data-query');
            if (query) {
                messageInput.value = query;
                sendMessage();
            }
        });
    });

    async function sendMessage() {
        const message = messageInput.value.trim();
        if (!message || isLoading) return;

        // 添加用户消息
        addMessage(message, 'user');
        messageInput.value = '';
        isLoading = true;
        btnSend.textContent = '发送中...';
        btnSend.disabled = true;

        // 显示加载中
        const loadingMsg = document.createElement('div');
        loadingMsg.className = 'message assistant';
        loadingMsg.innerHTML = '&lt;div class="message-content"&gt;思考中...&lt;/div&gt;';
        chatContainer.appendChild(loadingMsg);
        scrollToBottom();

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message })
            });

            const result = await response.json();

            // 移除加载消息
            chatContainer.removeChild(loadingMsg);

            if (result.success) {
                addMessage(result.response, 'assistant');
            } else {
                addMessage('抱歉，出现了一个错误：' + (result.error || '未知错误'), 'assistant');
            }
        } catch (error) {
            chatContainer.removeChild(loadingMsg);
            addMessage('抱歉，网络错误，请稍后重试。', 'assistant');
            console.error('Error:', error);
        } finally {
            isLoading = false;
            btnSend.textContent = '发送';
            btnSend.disabled = false;
        }
    }

    function addMessage(content, role) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}`;
        msgDiv.innerHTML = `&lt;div class="message-content"&gt;${escapeHtml(content)}&lt;/div&gt;`;
        chatContainer.appendChild(msgDiv);
        scrollToBottom();
    }

    function scrollToBottom() {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML.replace(/\n/g, '&lt;br&gt;');
    }

    // === 状态检查 ===
    async function refreshStatus() {
        try {
            const response = await fetch('/api/system/status');
            const result = await response.json();

            if (result.success) {
                const data = result.data;

                // LLM 状态
                if (data.llm_available) {
                    llmStatus.textContent = 'LLM: 在线';
                    llmStatusDot.className = 'dot online';
                } else {
                    llmStatus.textContent = 'LLM: 离线';
                    llmStatusDot.className = 'dot offline';
                }

                // 系统状态
                if (data.connected) {
                    systemStatus.textContent = '系统: 在线';
                    systemStatusDot.className = 'dot online';
                } else {
                    systemStatus.textContent = '系统: 离线';
                    systemStatusDot.className = 'dot offline';
                }
            }
        } catch (error) {
            console.error('Status check failed:', error);
        }
    }

    // 初始化
    initSpeechRecognition();
    refreshStatus();
    setInterval(refreshStatus, 10000); // 每10秒刷新一次状态
});
