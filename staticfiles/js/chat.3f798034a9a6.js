// Initialize WebSocket connections when document is ready
document.addEventListener('DOMContentLoaded', function() {
    // Only initialize if we're on a work item detail page with chat functionality
    const chatMessages = document.getElementById('chat-messages');
    if (!chatMessages) return;
    
    // Get the work item ID from the data attribute
    const workItemId = chatMessages.getAttribute('data-work-item-id');
    const userId = document.querySelector('meta[name="user-id"]').getAttribute('content');
    const username = document.querySelector('meta[name="username"]').getAttribute('content');
    
    if (!workItemId || !userId || !username) {
        console.error('Missing required data attributes for chat');
        return;
    }
    
    // Scroll chat to bottom
    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    
    // Initial scroll to bottom
    scrollToBottom();
    
    // Initialize text message WebSocket using WebSocketManager
    const wsProtocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
    const wsUrl = `${wsProtocol}${window.location.host}/ws/chat/${workItemId}/`;
    
    const chatSocket = window.webSocketManager.createConnection(wsUrl, {
        debug: true,
        onOpen: () => {
            console.log('Chat WebSocket connected');
            // Update UI to show connection status if needed
        },
        onClose: () => {
            console.log('Chat WebSocket closed');
        },
        onError: (error) => {
            console.error('Chat WebSocket error:', error);
        }
    });
    
    // Connect to WebSocket
    chatSocket.connect();
    
    // Register message handler
    chatSocket.on('message', function(data) {
        addMessageToChat(data.message, data.username, new Date(data.timestamp || Date.now()));
        scrollToBottom();
    });
    
    // Store socket instance for sending messages
    window.chatSocket = chatSocket;
    
    // Set up form submission handler
    const chatForm = document.getElementById('chat-form');
    if (chatForm) {
        chatForm.addEventListener('submit', handleFormSubmit);
    } else {
        console.error('Chat form not found');
    }
    
    // Display selected file name
    const fileInput = document.getElementById('file-input');
    if (fileInput) {
        fileInput.addEventListener('change', handleFileSelection);
    }
    
    /**
     * Handle form submission for messages and files
     */
    function handleFormSubmit(e) {
        e.preventDefault();
        
        const messageInput = document.getElementById('message-input');
        if (!messageInput) {
            console.error('Message input not found');
            return;
        }
        
        const message = messageInput.value.trim();
        
        // Send text message if there is one
        if (message && window.chatSocket && window.chatSocket.readyState === WebSocket.OPEN) {
            window.chatSocket.send(JSON.stringify({
                'message': message,
                'username': username,
                'user_id': userId
            }));
            
            messageInput.value = '';
        } else if (window.chatSocket && window.chatSocket.readyState !== WebSocket.OPEN) {
            console.error('WebSocket is not open. Current state:', window.chatSocket.readyState);
            alert('Connection to chat server is not open. Please refresh the page.');
        }
    }
    
    /**
     * Handle file selection
     */
    function handleFileSelection(e) {
        const fileName = this.files.length > 0 ? this.files[0].name : '';
        const fileNameElement = document.getElementById('file-name');
        if (fileNameElement) {
            fileNameElement.textContent = fileName;
        }
    }
    
    /**
     * Add a text message to the chat container
     */
    function addMessageToChat(message, messageUsername, timestamp) {
        const isSelf = messageUsername === username;
        
        // Create message element
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message ' + (isSelf ? 'message-sent' : 'message-received');
        
        const userDiv = document.createElement('div');
        userDiv.className = 'message-user';
        userDiv.textContent = messageUsername;
        messageDiv.appendChild(userDiv);
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.textContent = message;
        messageDiv.appendChild(contentDiv);
        
        const timeDiv = document.createElement('div');
        timeDiv.className = 'message-time';
        const hours = timestamp.getHours().toString().padStart(2, '0');
        const minutes = timestamp.getMinutes().toString().padStart(2, '0');
        timeDiv.textContent = `${hours}:${minutes}`;
        messageDiv.appendChild(timeDiv);
        
        // Add to chat
        chatMessages.appendChild(messageDiv);
    }
});