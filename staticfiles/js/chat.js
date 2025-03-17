// Initialize WebSocket connections when document is ready
document.addEventListener('DOMContentLoaded', function() {
    // Only initialize if we're on a work item detail page with chat functionality
    const chatMessages = document.getElementById('chat-messages');
    if (!chatMessages) return;
    
    // Get the work item ID from the data attribute
    const workItemId = chatMessages.getAttribute('data-work-item-id');
    const userId = chatMessages.getAttribute('data-user-id');
    const username = chatMessages.getAttribute('data-username');
    
    if (!workItemId || !userId || !username) return;
    
    // Scroll chat to bottom
    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    
    // Initial scroll to bottom
    scrollToBottom();
    
    // Initialize text message WebSocket
    initializeChatWebSocket();
    
    // Initialize file upload WebSocket
    initializeFileWebSocket();
    
    // Set up form submission handler
    document.getElementById('chat-form').addEventListener('submit', handleFormSubmit);
    
    // Display selected file name
    document.getElementById('file-input').addEventListener('change', handleFileSelection);
    
    /**
     * Initialize WebSocket for text messages
     */
    function initializeChatWebSocket() {
        const chatSocket = new WebSocket(
            'ws://' + window.location.host + '/ws/chat/' + workItemId + '/'
        );
        
        chatSocket.onmessage = function(e) {
            const data = JSON.parse(e.data);
            addMessageToChat(data.message, data.username, new Date());
            scrollToBottom();
        };
        
        chatSocket.onclose = function(e) {
            console.error('Chat socket closed unexpectedly');
            // Attempt to reconnect after a delay
            setTimeout(initializeChatWebSocket, 3000);
        };
        
        // Store socket instance for sending messages
        window.chatSocket = chatSocket;
    }
    
    /**
     * Initialize WebSocket for file uploads
     */
    function initializeFileWebSocket() {
        const fileSocket = new WebSocket(
            'ws://' + window.location.host + '/ws/file/' + workItemId + '/'
        );
        
        fileSocket.onmessage = function(e) {
            const data = JSON.parse(e.data);
            addFileToChat(data.file_url, data.file_name, data.username, new Date());
            scrollToBottom();
        };
        
        fileSocket.onclose = function(e) {
            console.error('File socket closed unexpectedly');
            // Attempt to reconnect after a delay
            setTimeout(initializeFileWebSocket, 3000);
        };
        
        // Store socket instance for sending files
        window.fileSocket = fileSocket;
    }
    
    /**
     * Handle form submission for messages and files
     */
    function handleFormSubmit(e) {
        e.preventDefault();
        
        const messageInput = document.getElementById('message-input');
        const fileInput = document.getElementById('file-input');
        const message = messageInput.value.trim();
        
        // Send text message if there is one
        if (message && window.chatSocket) {
            window.chatSocket.send(JSON.stringify({
                'message': message,
                'username': username,
                'user_id': userId
            }));
            
            messageInput.value = '';
        }
        
        // Send file if one is selected
        if (fileInput.files.length > 0 && window.fileSocket) {
            const file = fileInput.files[0];
            const reader = new FileReader();
            
            // Show loading indicator
            document.getElementById('file-name').textContent = 'Uploading...';
            document.getElementById('file-name').classList.add('loading');
            
            reader.onload = function(e) {
                window.fileSocket.send(JSON.stringify({
                    'file_data': e.target.result,
                    'file_name': file.name,
                    'username': username,
                    'user_id': userId
                }));
                
                // Clear file input and loading indicator
                fileInput.value = '';
                document.getElementById('file-name').textContent = '';
                document.getElementById('file-name').classList.remove('loading');
            };
            
            reader.readAsDataURL(file);
        }
    }
    
    /**
     * Handle file selection
     */
    function handleFileSelection(e) {
        const fileName = this.files.length > 0 ? this.files[0].name : '';
        document.getElementById('file-name').textContent = fileName;
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
        const hours = timestamp.getHours();
        const minutes = timestamp.getMinutes().toString().padStart(2, '0');
        timeDiv.textContent = `${hours}:${minutes}`;
        messageDiv.appendChild(timeDiv);
        
        // Add to chat
        chatMessages.appendChild(messageDiv);
    }
    
    /**
     * Add a file attachment to the chat container
     */
    function addFileToChat(fileUrl, fileName, messageUsername, timestamp) {
        const isSelf = messageUsername === username;
        
        // Create message element
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message ' + (isSelf ? 'message-sent' : 'message-received');
        
        const userDiv = document.createElement('div');
        userDiv.className = 'message-user';
        userDiv.textContent = messageUsername;
        messageDiv.appendChild(userDiv);
        
        const fileDiv = document.createElement('div');
        fileDiv.className = 'message-file';
        
        const fileLink = document.createElement('a');
        fileLink.href = fileUrl;
        fileLink.target = '_blank';
        fileLink.className = 'btn btn-sm btn-outline-primary';
        
        const fileIcon = document.createElement('i');
        fileIcon.className = 'fas fa-file';
        fileLink.appendChild(fileIcon);
        fileLink.innerHTML += ' ' + fileName;
        
        fileDiv.appendChild(fileLink);
        messageDiv.appendChild(fileDiv);
        
        const timeDiv = document.createElement('div');
        timeDiv.className = 'message-time';
        const hours = timestamp.getHours();
        const minutes = timestamp.getMinutes().toString().padStart(2, '0');
        timeDiv.textContent = `${hours}:${minutes}`;
        messageDiv.appendChild(timeDiv);
        
        // Add to chat
        chatMessages.appendChild(messageDiv);
    }
});