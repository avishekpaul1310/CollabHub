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
    
    // Initialize text message WebSocket
    initializeChatWebSocket();
    
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
     * Initialize WebSocket for text messages
     */
    function initializeChatWebSocket() {
        const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
        let chatSocket;
        
        try {
            chatSocket = new WebSocket(
                wsScheme + '://' + window.location.host + '/ws/chat/' + workItemId + '/'
            );
            
            chatSocket.onmessage = function(e) {
                try {
                    const data = JSON.parse(e.data);
                    addMessageToChat(data.message, data.username, new Date(data.timestamp || Date.now()));
                    scrollToBottom();
                } catch (error) {
                    console.error('Error processing message:', error);
                }
            };
            
            chatSocket.onopen = function(e) {
                console.log('Chat WebSocket connection established');
                // Update UI to show connection status if needed
            };
            
            chatSocket.onclose = function(e) {
                console.error('Chat socket closed unexpectedly:', e.code, e.reason);
                // In a real app, we'd attempt to reconnect
                setTimeout(() => {
                    console.log('Attempting to reconnect...');
                    initializeChatWebSocket();
                }, 3000);
            };
            
            chatSocket.onerror = function(e) {
                console.error('WebSocket error:', e);
            };
            
            // Store socket instance for sending messages
            window.chatSocket = chatSocket;
        } catch (error) {
            console.error('Error initializing WebSocket:', error);
        }
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