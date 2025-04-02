/**
 * Enhanced WebSocket Manager for CollabHub
 * Handles connections with automatic reconnection, heartbeats, and error management
 */
class WebSocketManager {
    constructor(url, options = {}) {
        this.url = url;
        this.socket = null;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = options.maxReconnectAttempts || 10;
        this.reconnectInterval = options.reconnectInterval || 2000;  // Start with 2s
        this.maxReconnectInterval = options.maxReconnectInterval || 30000;  // Max 30s
        this.heartbeatInterval = options.heartbeatInterval || 30000;  // 30s heartbeat
        this.heartbeatTimer = null;
        this.reconnectTimer = null;
        this.messageHandlers = {};
        this.connectionHandlers = {
            onOpen: options.onOpen || (() => {}),
            onClose: options.onClose || (() => {}),
            onError: options.onError || (() => {}),
            onReconnect: options.onReconnect || (() => {})
        };
        
        // Debug mode
        this.debug = options.debug || false;
    }
    
    connect() {
        // Clear any existing reconnect timer
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        
        try {
            this.log('Connecting to WebSocket:', this.url);
            this.socket = new WebSocket(this.url);
            
            this.socket.onopen = (event) => this.handleOpen(event);
            this.socket.onclose = (event) => this.handleClose(event);
            this.socket.onerror = (event) => this.handleError(event);
            this.socket.onmessage = (event) => this.handleMessage(event);
        } catch (error) {
            this.log('Error creating WebSocket:', error);
            this.scheduleReconnect();
        }
    }
    
    disconnect() {
        this.log('Disconnecting WebSocket');
        if (this.socket) {
            // Prevent reconnection attempts when manually disconnected
            this.socket.onclose = null; 
            this.socket.close();
            this.socket = null;
        }
        
        this.isConnected = false;
        this.stopHeartbeat();
        
        // Clear any reconnection timer
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
    }
    
    handleOpen(event) {
        this.log('WebSocket connection established');
        this.isConnected = true;
        this.reconnectAttempts = 0;
        
        // Start sending heartbeats
        this.startHeartbeat();
        
        // Call user-provided handler
        this.connectionHandlers.onOpen(event);
    }
    
    handleClose(event) {
        this.isConnected = false;
        this.stopHeartbeat();
        
        this.log(`WebSocket closed with code ${event.code}:`, event.reason);
        
        // Call user-provided handler
        this.connectionHandlers.onClose(event);
        
        // Check if this was a normal closure
        if (event.code !== 1000) {
            this.scheduleReconnect();
        }
    }
    
    handleError(event) {
        this.log('WebSocket error:', event);
        
        // Call user-provided handler
        this.connectionHandlers.onError(event);
        
        // Error doesn't always trigger a close event, 
        // so we might need to reconnect here too
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.close();
        }
    }
    
    handleMessage(event) {
        try {
            const data = JSON.parse(event.data);
            
            // Handle heartbeat response
            if (data.type === 'heartbeat_response') {
                this.log('Received heartbeat response');
                return;
            }
            
            // Call message type specific handlers
            if (data.type && this.messageHandlers[data.type]) {
                this.messageHandlers[data.type](data);
            }
            
            // Call general message handler if provided
            if (this.messageHandlers['message']) {
                this.messageHandlers['message'](data);
            }
        } catch (error) {
            this.log('Error handling message:', error);
        }
    }
    
    scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            this.log('Maximum reconnection attempts reached');
            return;
        }
        
        this.reconnectAttempts++;
        
        // Use exponential backoff with jitter
        const delay = Math.min(
            this.reconnectInterval * Math.pow(1.5, this.reconnectAttempts - 1) * (1 + Math.random() * 0.1),
            this.maxReconnectInterval
        );
        
        this.log(`Scheduling reconnect attempt ${this.reconnectAttempts} in ${Math.round(delay)}ms`);
        
        this.reconnectTimer = setTimeout(() => {
            // Notify about reconnection attempt
            this.connectionHandlers.onReconnect(this.reconnectAttempts);
            
            // Attempt to reconnect
            this.connect();
        }, delay);
    }
    
    startHeartbeat() {
        this.stopHeartbeat();
        
        this.heartbeatTimer = setInterval(() => {
            if (this.socket && this.socket.readyState === WebSocket.OPEN) {
                this.log('Sending heartbeat');
                this.socket.send(JSON.stringify({ type: 'heartbeat' }));
            }
        }, this.heartbeatInterval);
    }
    
    stopHeartbeat() {
        if (this.heartbeatTimer) {
            clearInterval(this.heartbeatTimer);
            this.heartbeatTimer = null;
        }
    }
    
    send(message) {
        if (!this.isConnected) {
            this.log('Cannot send message: WebSocket is not connected');
            return false;
        }
        
        try {
            // Convert to string if it's an object
            const messageText = typeof message === 'object' 
                ? JSON.stringify(message) 
                : message;
                
            this.socket.send(messageText);
            return true;
        } catch (error) {
            this.log('Error sending message:', error);
            return false;
        }
    }
    
    // Register a handler for a specific message type
    on(messageType, handler) {
        this.messageHandlers[messageType] = handler;
    }
    
    // Remove a specific handler
    off(messageType) {
        delete this.messageHandlers[messageType];
    }
    
    log(...args) {
        if (this.debug) {
            console.log('[WebSocketManager]', ...args);
        }
    }
}

// Global instance for easy use
window.webSocketManager = {
    createConnection(url, options = {}) {
        const manager = new WebSocketManager(url, options);
        return manager;
    }
};
