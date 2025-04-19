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
    
    // Store WebSocket status globally
    window.webSocketStatus = {
        isConnected: false,
        connectionState: 'connecting'
    };
    
    // Initialize WebSocket connection if webSocketManager is available
    let chatSocket = null;
    
    function initializeWebSocket() {
        if (!window.webSocketManager) {
            console.error('WebSocketManager not found. Make sure websocket-manager.js is loaded first.');
            window.webSocketStatus.connectionState = 'error';
            return null;
        }
        
        try {
            const socket = window.webSocketManager.createConnection(wsUrl, {
                debug: true,
                onOpen: () => {
                    console.log('Chat WebSocket connected');
                    window.webSocketStatus.isConnected = true;
                    window.webSocketStatus.connectionState = 'connected';
                    // Update UI to show connection status if needed
                },
                onClose: () => {
                    console.log('Chat WebSocket closed');
                    window.webSocketStatus.isConnected = false;
                    window.webSocketStatus.connectionState = 'closed';
                    
                    // Try to reconnect after a delay
                    setTimeout(() => {
                        if (!window.webSocketStatus.isConnected) {
                            console.log('Attempting to reconnect WebSocket...');
                            window.chatSocket = initializeWebSocket();
                        }
                    }, 5000);
                },
                onError: (error) => {
                    console.error('Chat WebSocket error:', error);
                    window.webSocketStatus.connectionState = 'error';
                }
            });
            
            // Connect to WebSocket
            socket.connect();
            
            // Register message handler
            socket.on('message', function(data) {
                addMessageToChat(data.message, data.username, new Date(data.timestamp || Date.now()));
                scrollToBottom();
            });
            
            return socket;
        } catch (error) {
            console.error('Error initializing WebSocket:', error);
            window.webSocketStatus.connectionState = 'error';
            return null;
        }
    }
    
    // Initialize the chat socket
    chatSocket = initializeWebSocket();
    
    // Store socket instance for sending messages
    window.chatSocket = chatSocket;
    
    // Set up form submission handler
    const chatForm = document.getElementById('chat-form');
    if (chatForm) {
        chatForm.addEventListener('submit', handleFormSubmit);
    } else {
        console.error('Chat form not found');
    }
    
    // Display selected file name - updated to use chat-file-input
    const chatFileInput = document.getElementById('chat-file-input');
    if (chatFileInput) {
        chatFileInput.addEventListener('change', handleFileSelection);
    }
    
    // Handle file upload form
    const fileUploadForm = document.getElementById('file-upload-form');
    if (fileUploadForm) {
        fileUploadForm.addEventListener('submit', function(e) {
            // File uploads should use the regular form submission
            // No need to use WebSocket for file uploads
            
            // Optional: Show upload status
            const fileInput = document.getElementById('chat-file-input');
            if (fileInput && fileInput.files.length > 0) {
                console.log(`Uploading file: ${fileInput.files[0].name}`);
            } else {
                e.preventDefault(); // Prevent submission if no file selected
                console.error('No file selected for upload');
                alert('Please select a file to upload');
            }
        });
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
        if (message) {
            sendMessage(message);
            messageInput.value = '';
        }
    }
    
    /**
     * Send a message via the WebSocket connection
     */
    function sendMessage(message) {
        if (window.chatSocket && window.webSocketStatus.isConnected) {
            window.chatSocket.send(JSON.stringify({
                'message': message,
                'username': username,
                'user_id': userId
            }));
            return true;
        } else {
            console.error('WebSocket is not open. Current state:', window.webSocketStatus.connectionState);
            
            // Try to reconnect if connection is lost
            if (!window.webSocketStatus.isConnected && window.webSocketStatus.connectionState !== 'connecting') {
                console.log('Attempting to reconnect WebSocket...');
                window.chatSocket = initializeWebSocket();
                
                // Queue message to be sent once connection is established
                setTimeout(() => {
                    if (window.webSocketStatus.isConnected) {
                        sendMessage(message);
                    } else {
                        alert('Connection to chat server is not open. Please refresh the page.');
                    }
                }, 1000);
            } else {
                alert('Connection to chat server is not open. Please refresh the page.');
            }
            
            return false;
        }
    }
    
    /**
     * Handle file selection
     */
    function handleFileSelection(e) {
        const fileName = this.files.length > 0 ? this.files[0].name : '';
        const fileNameElement = document.getElementById('chat-file-name');
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