// whatsapp_app/static/whatsapp_app/js/chat.js

/**
 * Handles real-time chat functionality using WebSockets:
 * - Establishes WebSocket connection.
 * - Sends text and initiates media uploads.
 * - Receives messages and updates via WebSocket.
 * - Updates the chat UI dynamically using custom CSS classes.
 */
document.addEventListener('DOMContentLoaded', () => {
    // --- Get DOM Elements ---
    const messageList = document.getElementById('message-list'); // Expects a container for messages
    const messageForm = document.getElementById('manual-message-form'); // Expects the form element
    const messageInput = messageForm?.querySelector('textarea[name="text_content"]'); // Expects the textarea
    const noMessagesPlaceholder = document.getElementById('no-messages-placeholder'); // Optional placeholder div
    const sendButton = messageForm?.querySelector('button[type="submit"]'); // Expects the submit button
    const sendButtonIcon = sendButton?.querySelector('i'); // Expects an <i> tag inside the button
    const errorDisplay = document.getElementById('chat-error-display'); // Expects <div id="chat-error-display">
    const attachButton = document.getElementById('attach-file-button'); // Expects <button id="attach-file-button">
    const fileInput = document.getElementById('chat-file-input'); // Expects <input type="file" id="chat-file-input">
    const fileUploadSpinner = document.getElementById('file-upload-spinner'); // Expects <span id="file-upload-spinner">

    // --- Basic Configuration & State ---
    if (!messageList || !messageForm || !messageInput || !sendButton || !sendButtonIcon || !attachButton || !fileInput || !fileUploadSpinner) {
        console.warn("Chat UI elements not found or incomplete. Chat script may not fully function.");
        // Allow script to continue if some non-essential elements are missing, but log warning.
        // return; // Uncomment this to completely stop if elements are missing
    }

    const contactWaId = messageList?.dataset.contactWaId; // Get WA ID from data attribute
    // lastTimestamp is less critical with WebSockets but can be useful for initial load or fallback
    let lastTimestamp = messageList?.dataset.lastTimestamp;
    let isSending = false; // Flag to prevent double message sends/uploads
    const originalSendButtonHtml = sendButton?.innerHTML; // Store original button content

    if (!contactWaId) {
        console.error("Chat script error: Missing 'data-contact-wa-id' attribute on #message-list.");
        if(messageInput) messageInput.disabled = true;
        if(sendButton) sendButton.disabled = true;
        if(sendButton) sendButton.title = "Chat unavailable: Missing configuration.";
        return; // Exit if contact ID is missing
    }

    console.log(`Chat script initialized for contact ${contactWaId}`);

    // --- Helper: Get CSRF token from cookies ---
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
    const csrftoken = getCookie('csrftoken');
    if (!csrftoken) {
        console.warn("CSRF token not found. File uploads might fail if not handled otherwise.");
    }

    // --- Helper: Format Timestamp for Display ---
    function formatTime(isoTimestamp) {
        if (!isoTimestamp) return '';
        try {
            return new Date(isoTimestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch (e) {
            console.error("Error formatting time:", e);
            return '';
        }
    }

    // --- Helper: Get Status Icon HTML (Using Font Awesome) ---
    function getStatusIconHTML(status) {
        const statusLower = status ? status.toLowerCase() : '';
        switch (statusLower) {
            case 'failed': return '<i class="fas fa-exclamation-circle status-icon-failed" title="Failed"></i>';
            case 'read': return '<i class="fas fa-check-double status-icon-read" title="Read"></i>';
            case 'delivered': return '<i class="fas fa-check-double status-icon-delivered" title="Delivered"></i>';
            case 'sent': return '<i class="fas fa-check status-icon-sent" title="Sent"></i>';
            case 'pending': return '<i class="fas fa-clock status-icon-pending" title="Pending"></i>';
            default: return '';
        }
    }

    // --- Function to display errors in a non-blocking way ---
    function displayError(message) {
        console.error("Chat Error:", message);
        if (errorDisplay) {
            errorDisplay.textContent = message;
            errorDisplay.style.display = message ? 'block' : 'none';
            // Auto-hide non-connection errors after a delay
            if (message && !message.toLowerCase().includes("connection")) {
                 setTimeout(() => { if (errorDisplay) errorDisplay.style.display = 'none'; }, 6000);
            }
        } else {
            console.warn("No #chat-error-display element found.");
            // Avoid alert() in production if possible
            // alert(message);
        }
    }

    // --- Function to scroll message list to bottom ---
    function scrollToBottom(force = false) {
        if (!messageList) return;
        const threshold = 150; // How close to bottom user needs to be to auto-scroll
        const isNearBottom = messageList.scrollHeight - messageList.scrollTop - messageList.clientHeight < threshold;

        if (force || isNearBottom) {
            if ('scrollBehavior' in document.documentElement.style) {
                messageList.scrollTo({ top: messageList.scrollHeight, behavior: 'smooth' });
            } else {
                messageList.scrollTop = messageList.scrollHeight; // Fallback
            }
        }
    }

    // --- Function to add a single message object to the UI ---
    function addMessageToUI(msg) {
        if (!messageList) return; // Don't proceed if list doesn't exist
        if (noMessagesPlaceholder) noMessagesPlaceholder.style.display = 'none';

        // Avoid adding duplicate messages (check by WAMID)
        if (msg.message_id && document.querySelector(`.message[data-message-id="${msg.message_id}"]`)) {
             console.log(`Message ${msg.message_id} already exists, skipping UI add.`);
            return;
        }

        const messageElement = document.createElement('div');
        messageElement.className = `message ${msg.direction === 'OUT' ? 'outgoing' : 'incoming'}`;
        if (msg.message_id) {
            messageElement.dataset.messageId = msg.message_id;
        }

        const bubble = document.createElement('div');
        bubble.className = 'message-bubble';

        const content = document.createElement('div');
        content.className = 'message-text'; // Base class

        // --- Render based on type ---
        const messageType = msg.message_type || 'text'; // Default to text
        const textContent = msg.text_content || '';
        const mediaUrl = msg.media_url; // URL from DB (potentially after download/save)
        const filename = msg.filename || ''; // Filename if available

        if (messageType === 'text') {
            content.textContent = textContent;
        } else if (messageType === 'template') {
            content.innerHTML = `<span class="template-indicator"><i class="fas fa-file-alt"></i> Template: ${msg.template_name || 'Unknown'}</span>`;
            if(textContent) {
                 const templateText = document.createElement('div');
                 templateText.className = 'template-text-content';
                 templateText.textContent = textContent;
                 content.appendChild(templateText);
            }
        } else if (messageType === 'image') {
             content.innerHTML = `<span class="media-indicator"><i class="fas fa-image"></i> [Image Received]</span>`;
             if (textContent) content.innerHTML += `<p class="media-caption">${textContent}</p>`;
             if (mediaUrl) { // If URL is available (e.g., saved locally)
                 content.innerHTML += `<a href="${mediaUrl}" target="_blank" rel="noopener noreferrer" class="media-preview-link">
                                         <img src="${mediaUrl}" alt="Image Attachment" class="media-image-preview">
                                     </a>`; // Style .media-image-preview in CSS
             } else {
                  content.innerHTML += `<span class="text-muted small">(Preview unavailable)</span>`;
             }
        } else if (messageType === 'video') {
             content.innerHTML = `<span class="media-indicator"><i class="fas fa-video"></i> [Video Received]</span>`;
             if (textContent) content.innerHTML += `<p class="media-caption">${textContent}</p>`;
             if (mediaUrl) {
                  // Provide download link or embed video player if desired
                  content.innerHTML += `<a href="${mediaUrl}" target="_blank" rel="noopener noreferrer" class="custom-button button-outline-secondary button-sm media-download-button"><i class="fas fa-download"></i> View/Download Video</a>`;
             } else {
                  content.innerHTML += `<span class="text-muted small">(Link unavailable)</span>`;
             }
        } else if (messageType === 'audio') {
             content.innerHTML = `<span class="media-indicator"><i class="fas fa-volume-up"></i> [Audio Received]</span>`;
             if (mediaUrl) {
                  // Embed audio player
                  content.innerHTML += `<audio controls src="${mediaUrl}" class="media-audio-player"></audio>`;
             } else {
                  content.innerHTML += `<span class="text-muted small">(Audio unavailable)</span>`;
             }
        } else if (messageType === 'document') {
            content.innerHTML = `<span class="media-indicator"><i class="fas fa-file-alt"></i> [Document: ${filename || 'Received'}]</span>`;
             if (textContent) content.innerHTML += `<p class="media-caption">${textContent}</p>`;
             if (mediaUrl) {
                 content.innerHTML += `<a href="${mediaUrl}" target="_blank" rel="noopener noreferrer" class="custom-button button-outline-secondary button-sm media-download-button"><i class="fas fa-download"></i> Download Document</a>`;
             } else {
                 content.innerHTML += `<span class="text-muted small">(Link unavailable)</span>`;
             }
        } else { // Fallback
            content.innerHTML = `<span class="media-indicator"><i class="fas fa-file"></i> [${messageType}]</span>`;
            if(textContent) content.innerHTML += `<p class="media-caption">${textContent}</p>`;
        }
        bubble.appendChild(content);

        // --- Message Meta ---
        const meta = document.createElement('div');
        meta.className = 'message-meta';
        const timeSpan = document.createElement('span');
        timeSpan.className = 'message-time';
        timeSpan.textContent = formatTime(msg.timestamp);
        meta.appendChild(timeSpan);
        if (msg.direction === 'OUT') {
            const statusSpan = document.createElement('span');
            statusSpan.className = 'message-status-icon';
            statusSpan.innerHTML = getStatusIconHTML(msg.status);
            meta.appendChild(statusSpan);
        }
        bubble.appendChild(meta);

        messageElement.appendChild(bubble);
        messageList.appendChild(messageElement);

        // Update lastTimestamp if needed (less critical now)
        if (msg.timestamp && (!lastTimestamp || new Date(msg.timestamp) > new Date(lastTimestamp))) {
            lastTimestamp = msg.timestamp;
            // Update data attribute for potential fallback polling?
            // messageList.dataset.lastTimestamp = lastTimestamp;
        }
    }

    // --- Function to Update Message Status Icon ---
    function updateMessageStatus(statusData) {
         if (!statusData || !statusData.message_id || !statusData.status) return;

         const messageElement = document.querySelector(`.message[data-message-id="${statusData.message_id}"]`);
         if (messageElement && messageElement.classList.contains('outgoing')) { // Only update outgoing messages
             const statusIconSpan = messageElement.querySelector('.message-status-icon');
             if (statusIconSpan) {
                 const newIconHTML = getStatusIconHTML(statusData.status);
                 if (statusIconSpan.innerHTML !== newIconHTML) { // Avoid unnecessary updates
                     console.log(`Updating status for ${statusData.message_id} to ${statusData.status}`);
                     statusIconSpan.innerHTML = newIconHTML;
                     statusIconSpan.title = statusData.status; // Update tooltip
                 }
             }
         }
    }

    // --- WebSocket Connection ---
    const chatSocketProtocol = window.location.protocol === "https:" ? "wss" : "ws";
    const chatSocketUrl = `${chatSocketProtocol}://${window.location.host}/ws/chat/${contactWaId}/`;
    let chatSocket = null;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;

    function connectWebSocket() {
        console.log(`Attempting WebSocket connection (Attempt ${reconnectAttempts + 1})...`);
        chatSocket = new WebSocket(chatSocketUrl);

        chatSocket.onopen = function(e) {
            console.log("WebSocket connection established.");
            reconnectAttempts = 0;
            displayError(""); // Clear connection errors
        };

        chatSocket.onmessage = function(e) {
            try {
                const data = JSON.parse(e.data);
                console.log("WebSocket message received:", data);

                if (data.type === 'chat_message' && data.message) {
                    addMessageToUI(data.message);
                    scrollToBottom();
                } else if (data.type === 'status_update' && data.data) {
                     updateMessageStatus(data.data); // Update status icon
                } else if (data.type === 'message_sending') {
                     console.log("Server acknowledged message sending task for:", data.text);
                     // Optionally show a temporary "Sending..." state visually
                } else if (data.type === 'error') {
                     displayError(`Server error: ${data.message}`);
                }

            } catch (error) { console.error("Error parsing WebSocket message:", error); }
        };

        chatSocket.onerror = function(e) { console.error("WebSocket error:", e); }

        chatSocket.onclose = function(e) {
            console.error(`WebSocket closed. Code: ${e.code}, Reason: ${e.reason}.`);
            chatSocket = null;
            if (reconnectAttempts < maxReconnectAttempts) {
                reconnectAttempts++;
                const delay = Math.pow(2, reconnectAttempts) * 1000; // Exponential backoff
                console.log(`Attempting reconnect in ${delay / 1000}s...`);
                displayError(`Connection lost. Reconnecting (Attempt ${reconnectAttempts})...`);
                setTimeout(connectWebSocket, delay);
            } else {
                console.error("Max WebSocket reconnect attempts reached.");
                displayError("Connection failed. Please refresh the page.");
                if(messageInput) messageInput.disabled = true;
                if(sendButton) sendButton.disabled = true;
                if(sendButton) sendButton.title = "Connection failed.";
            }
        };
    }

    // --- Function to send TEXT message via WebSocket ---
    function sendWebSocketMessage(event) {
        event?.preventDefault();
        if (isSending || !chatSocket || chatSocket.readyState !== WebSocket.OPEN) {
            if (!chatSocket || chatSocket.readyState !== WebSocket.OPEN) displayError("Cannot send: Connection not open.");
            return;
        }
        const messageText = messageInput.value.trim();
        if (!messageText) return;

        isSending = true; messageInput.disabled = true; sendButton.disabled = true;
        sendButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

        console.log("Sending TEXT message via WebSocket:", messageText);
        chatSocket.send(JSON.stringify({ 'type': 'text', 'message': messageText }));

        // Reset form immediately (optimistic, message appears when echoed back)
        messageInput.value = ''; messageInput.disabled = false; sendButton.disabled = false;
        sendButton.innerHTML = originalSendButtonHtml; messageInput.focus(); isSending = false;
    }

    // --- Function to handle file upload and send media info via WebSocket ---
    async function handleFileUpload() {
        const file = fileInput.files[0];
        if (!file || isSending || !chatSocket || chatSocket.readyState !== WebSocket.OPEN) {
            if (!chatSocket || chatSocket.readyState !== WebSocket.OPEN) displayError("Cannot upload: Connection not open.");
            return;
        }

        // Client-side validation (add more checks as needed)
        const maxSize = 16 * 1024 * 1024; // Example 16MB limit
        if (file.size > maxSize) { displayError(`File exceeds ${maxSize/1024/1024}MB limit.`); fileInput.value = ''; return; }

        isSending = true; attachButton.style.display = 'none'; fileUploadSpinner.style.display = 'inline-block';
        sendButton.disabled = true; messageInput.disabled = true;

        const uploadFormData = new FormData();
        uploadFormData.append('media_file', file);
        uploadFormData.append('wa_id', contactWaId);
        if (csrftoken) uploadFormData.append('csrfmiddlewaretoken', csrftoken);

        // *** Use the correct upload URL from your urls.py ***
        const uploadUrl = '/whatsapp/api/media/upload/';

        try {
            const response = await fetch(uploadUrl, { method: 'POST', body: uploadFormData, headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' } });
            const data = await response.json();

            if (response.ok && data.status === 'success' && data.media_id) {
                console.log(`Media uploaded. ID: ${data.media_id}, Type: ${data.media_type}`);
                // Send media info via WebSocket
                chatSocket.send(JSON.stringify({
                    'type': data.media_type || 'document',
                    'media_id': data.media_id,
                    'filename': file.name,
                    'message': messageInput.value.trim() // Send current text as caption
                }));
                messageInput.value = ''; // Clear caption input
                displayError('');
            } else {
                const errorMsg = data.message || `Upload failed (${response.status}).`;
                console.error("Media upload error:", errorMsg, data);
                displayError(`Upload Error: ${errorMsg}`);
            }
        } catch (error) {
            console.error("Network error during file upload:", error);
            displayError("Network error: Could not upload file.");
        } finally {
            isSending = false; attachButton.style.display = 'inline-block'; fileUploadSpinner.style.display = 'none';
            sendButton.disabled = false; messageInput.disabled = false; fileInput.value = '';
        }
    }

    // --- Event Listeners ---
    if (messageForm) messageForm.addEventListener('submit', sendWebSocketMessage);
    if (messageInput) messageInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            if (messageInput.value.trim()) { sendWebSocketMessage(event); }
        }
    });
    if (attachButton) attachButton.addEventListener('click', () => fileInput?.click());
    if (fileInput) fileInput.addEventListener('change', handleFileUpload);

    // --- Initial Setup ---
    scrollToBottom(true);
    connectWebSocket();

}); // End DOMContentLoaded
