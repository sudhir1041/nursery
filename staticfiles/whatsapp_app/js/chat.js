// whatsapp_app/static/whatsapp_app/js/chat.js

/**
 * Handles real-time chat functionality using AJAX polling:
 * - Fetches new messages periodically.
 * - Sends new messages typed by the user.
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

    // --- Basic Configuration & State ---
    if (!messageList || !messageForm || !messageInput || !sendButton || !sendButtonIcon) {
        console.log("Chat UI elements not found or incomplete. Chat script inactive.");
        return; // Exit if essential elements aren't present
    }

    const contactWaId = messageList.dataset.contactWaId; // Get WA ID from data attribute
    let lastTimestamp = messageList.dataset.lastTimestamp; // Get initial timestamp from data attribute
    let pollIntervalId = null; // To store the interval timer ID
    const pollInterval = 5000; // Poll every 5 seconds (adjust as needed)
    let isPolling = false; // Flag to prevent overlapping poll requests
    let isSending = false; // Flag to prevent double message sends
    const originalSendButtonHtml = sendButton.innerHTML; // Store original button content (icon + text)

    if (!contactWaId || !lastTimestamp) {
        console.error("Chat script error: Missing 'data-contact-wa-id' or 'data-last-timestamp' attributes on #message-list.");
        // Disable form if critical data is missing
        messageInput.disabled = true;
        sendButton.disabled = true;
        sendButton.title = "Chat unavailable: Missing configuration.";
        return;
    }

    console.log(`Chat script initialized for contact ${contactWaId}, starting poll after ${lastTimestamp}`);

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
        console.warn("CSRF token not found. Message sending might fail.");
        // Consider disabling send button if CSRF is absolutely required and missing
        // sendButton.disabled = true;
        // sendButton.title = "Cannot send messages: CSRF token missing.";
    }

    // --- Helper: Format Timestamp for Display ---
    function formatTime(isoTimestamp) {
        if (!isoTimestamp) return '';
        try {
            // Use browser's locale for time formatting (HH:MM)
            return new Date(isoTimestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch (e) {
            console.error("Error formatting time:", e);
            return '';
        }
    }

    // --- Helper: Get Status Icon HTML (Using Font Awesome) ---
    function getStatusIconHTML(status) {
        // Ensure status is compared case-insensitively
        const statusLower = status ? status.toLowerCase() : '';
        switch (statusLower) {
            case 'failed': return '<i class="fas fa-exclamation-circle status-icon-failed" title="Failed"></i>'; // Example custom class
            case 'read': return '<i class="fas fa-check-double status-icon-read" title="Read"></i>'; // Example custom class (blue double tick)
            case 'delivered': return '<i class="fas fa-check-double status-icon-delivered" title="Delivered"></i>'; // Example custom class (grey double tick)
            case 'sent': return '<i class="fas fa-check status-icon-sent" title="Sent"></i>'; // Example custom class (grey single tick)
            case 'pending': return '<i class="fas fa-clock status-icon-pending" title="Pending"></i>'; // Example custom class
            default: return ''; // No icon for received or unknown
        }
    }

    // --- Function to add a single message object to the UI ---
    function addMessageToUI(msg) {
        // Remove placeholder if it exists
        if (noMessagesPlaceholder) {
            noMessagesPlaceholder.style.display = 'none';
        }

        // Avoid adding duplicate messages
        if (document.querySelector(`.message[data-message-id="${msg.message_id}"]`)) {
            return;
        }

        const messageElement = document.createElement('div');
        // Apply base and direction-specific classes (defined in your CSS)
        messageElement.className = `message ${msg.direction === 'OUT' ? 'outgoing' : 'incoming'}`;
        messageElement.dataset.messageId = msg.message_id; // Store ID for potential updates

        const bubble = document.createElement('div');
        bubble.className = 'message-bubble'; // Style bubble in CSS

        // --- Message Content ---
        const content = document.createElement('div');
        content.className = 'message-text'; // Style text content in CSS

        // Render content based on type (use textContent for safety against XSS)
        if (msg.message_type === 'text') {
            content.textContent = msg.text_content || '';
        } else if (msg.message_type === 'template') {
             // Use innerHTML carefully for formatting, ensure backend sanitizes template names
            content.innerHTML = `<span class="template-indicator"><i class="fas fa-file-alt"></i> Template: ${msg.template_name || 'Unknown'}</span>`;
            if(msg.text_content) {
                 const templateText = document.createElement('div');
                 templateText.className = 'template-text-content';
                 templateText.textContent = msg.text_content; // Use textContent for safety
                 content.appendChild(templateText);
            }
        } else if (msg.message_type === 'image' && msg.media_url) {
            content.innerHTML = `<span class="media-indicator"><i class="fas fa-image"></i> [Image]</span>
                                 <a href="${msg.media_url}" target="_blank" rel="noopener noreferrer" class="media-preview-link">
                                     <img src="${msg.media_url}" alt="Image Attachment" class="media-image-preview">
                                 </a>`; // Style .media-image-preview in CSS
        } else if (msg.message_type === 'document') {
            content.innerHTML = `<span class="media-indicator"><i class="fas fa-file-alt"></i> [Document]</span>`;
            if (msg.media_url) {
                content.innerHTML += `<a href="${msg.media_url}" target="_blank" rel="noopener noreferrer" class="custom-button button-outline-secondary button-sm media-download-button">
                                          <i class="fas fa-download"></i> Download
                                      </a>`; // Use custom button styles
            }
            if (msg.text_content) {
                 const docCaption = document.createElement('p');
                 docCaption.className = 'media-caption';
                 docCaption.textContent = msg.text_content;
                 content.appendChild(docCaption);
            }
        } else {
            // Fallback for other types
            content.innerHTML = `<span class="media-indicator"><i class="fas fa-file"></i> [${msg.message_type || 'Unknown Type'}]</span>`;
            if(msg.text_content) {
                const otherCaption = document.createElement('p');
                otherCaption.className = 'media-caption';
                otherCaption.textContent = msg.text_content;
                content.appendChild(otherCaption);
            }
        }
        bubble.appendChild(content);

        // --- Message Meta (Timestamp & Status) ---
        const meta = document.createElement('div'); // Use div for easier styling/alignment
        meta.className = 'message-meta'; // Style meta info (time, status) in CSS

        const timeSpan = document.createElement('span');
        timeSpan.className = 'message-time';
        timeSpan.textContent = formatTime(msg.timestamp);
        meta.appendChild(timeSpan);

        if (msg.direction === 'OUT') {
            const statusSpan = document.createElement('span');
            statusSpan.className = 'message-status-icon'; // Style status icon container
            statusSpan.innerHTML = getStatusIconHTML(msg.status); // Render icon HTML
            meta.appendChild(statusSpan);
        }
        bubble.appendChild(meta);

        messageElement.appendChild(bubble);
        messageList.appendChild(messageElement);

        // Update the global 'lastTimestamp' if this message is newer
        if (msg.timestamp && new Date(msg.timestamp) > new Date(lastTimestamp)) {
            lastTimestamp = msg.timestamp;
        }
    }

    // --- Function to scroll message list to bottom ---
    function scrollToBottom(force = false) {
        const threshold = 150; // How close to bottom user needs to be to auto-scroll
        const isNearBottom = messageList.scrollHeight - messageList.scrollTop - messageList.clientHeight < threshold;

        if (force || isNearBottom) {
            // Use smooth scrolling if available
            if ('scrollBehavior' in document.documentElement.style) {
                messageList.scrollTo({ top: messageList.scrollHeight, behavior: 'smooth' });
            } else {
                messageList.scrollTop = messageList.scrollHeight; // Fallback
            }
        }
    }

    // --- Function to display errors in a non-blocking way ---
    function displayError(message) {
        console.error("Chat Error:", message); // Log error to console
        // TODO: Implement a user-friendly error display mechanism
        // Example: Find an error div and set its text content
        const errorDisplay = document.getElementById('chat-error-display'); // Assume you have <div id="chat-error-display"></div>
        if (errorDisplay) {
            errorDisplay.textContent = message;
            errorDisplay.style.display = 'block'; // Make it visible
            // Optionally hide after a few seconds
            setTimeout(() => {
                 if (errorDisplay) errorDisplay.style.display = 'none';
            }, 5000);
        } else {
             // Fallback if error div doesn't exist (less ideal)
             // alert(message);
             console.warn("No #chat-error-display element found to show error message to user.");
        }
    }


    // --- Function to fetch new messages via AJAX ---
    async function fetchNewMessages() {
        if (isPolling) return;
        isPolling = true;

        // *** IMPORTANT: Define this URL in your urls.py and create the corresponding view ***
        const fetchUrl = `/whatsapp/api/messages/latest/?wa_id=${contactWaId}&last_timestamp=${encodeURIComponent(lastTimestamp)}`;

        try {
            const response = await fetch(fetchUrl, {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json',
                }
            });

            if (!response.ok) {
                const errorText = await response.text(); // Get potential error details from body
                console.error(`Error fetching messages: ${response.status} ${response.statusText}`, errorText);
                displayError(`Error fetching messages (${response.status}). Please try again later.`); // User-friendly message
                if (response.status === 404 || response.status === 403) {
                    stopPolling();
                    console.warn("Stopping polling due to client/server error (403/404).");
                }
                return;
            }

            const data = await response.json();

            if (data.status === 'success') {
                if (data.new_messages && data.new_messages.length > 0) {
                    console.log(`Received ${data.new_messages.length} new messages.`);
                    data.new_messages.forEach(addMessageToUI);
                    scrollToBottom(); // Auto-scroll if user is near bottom
                }
                // Update timestamp for the *next* poll
                if (data.next_poll_timestamp && new Date(data.next_poll_timestamp) > new Date(lastTimestamp)) {
                    lastTimestamp = data.next_poll_timestamp;
                }
                // TODO: Handle updated_statuses if implemented
                // if (data.updated_statuses && data.updated_statuses.length > 0) {
                //     updateMessageStatuses(data.updated_statuses); // Implement this function
                // }
            } else {
                console.error("AJAX endpoint returned error:", data.message || "Unknown error");
                displayError(data.message || "An error occurred while fetching messages.");
            }
        } catch (error) {
            console.error("Network or fetch error during polling:", error);
            // Avoid alerting on every poll failure during network issues
            // displayError("Network error checking for messages.");
        } finally {
            isPolling = false;
        }
    }

    // --- Function to send manual message via AJAX ---
    async function sendManualMessage(event) {
        event.preventDefault();
        if (isSending) return;

        const messageText = messageInput.value.trim();
        if (!messageText) return;

        // *** IMPORTANT: Define this URL in your urls.py and create the corresponding view ***
        // It should match the form's action attribute if set, otherwise define explicitly
        const sendUrl = messageForm.action || `/whatsapp/api/messages/send/`;

        isSending = true;
        messageInput.disabled = true;
        sendButton.disabled = true;
        // Show spinner icon (Font Awesome)
        sendButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending...'; // Replace icon and text

        const formData = new FormData();
        formData.append('text_content', messageText);
        formData.append('wa_id', contactWaId); // Send contact ID with the message
        if (csrftoken) {
            formData.append('csrfmiddlewaretoken', csrftoken);
        }

        try {
            const response = await fetch(sendUrl, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json',
                    // 'X-CSRFToken': csrftoken // Often not needed if token is in form data
                }
            });

            const data = await response.json();

            if (response.ok && data.status === 'success' && data.message) {
                // Success - add the 'PENDING' message immediately
                addMessageToUI(data.message); // Backend should return the created message object
                scrollToBottom(true); // Force scroll
                messageInput.value = ''; // Clear input
                console.log("Message sent successfully via AJAX.");
            } else {
                // Handle errors
                let errorMessage = "Failed to send message.";
                if (data.message) {
                    errorMessage = data.message;
                } else if (data.errors && data.errors.text_content) {
                    errorMessage = data.errors.text_content.join(' ');
                } else if (!response.ok) {
                    errorMessage = `Server error: ${response.status} ${response.statusText}`;
                }
                console.error("Error sending message:", errorMessage, data);
                displayError(`Error: ${errorMessage}`); // Show error to user
            }
        } catch (error) {
            console.error("Network error sending message:", error);
            displayError("Network error: Could not send message. Please check your connection.");
        } finally {
            // Re-enable form elements
            messageInput.disabled = false;
            sendButton.disabled = false;
            sendButton.innerHTML = originalSendButtonHtml; // Restore original button content
            messageInput.focus();
            isSending = false;
        }
    }

    // --- Start/Stop Polling ---
    function startPolling() {
        if (pollIntervalId === null) {
            console.log("Starting message polling...");
            fetchNewMessages(); // Fetch immediately
            pollIntervalId = setInterval(fetchNewMessages, pollInterval);
        }
    }

    function stopPolling() {
        if (pollIntervalId !== null) {
            console.log("Stopping message polling.");
            clearInterval(pollIntervalId);
            pollIntervalId = null;
        }
    }

    // --- Event Listeners ---
    messageForm.addEventListener('submit', sendManualMessage);

    messageInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            if (messageInput.value.trim()) {
                sendManualMessage(event);
            }
        }
    });

    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            console.log("Tab became visible, resuming polling.");
            fetchNewMessages(); // Fetch immediately on resume
            startPolling();
        } else {
            console.log("Tab became hidden, pausing polling.");
            stopPolling();
        }
    });

    // --- Initial Setup ---
    scrollToBottom(true); // Scroll on load
    if (document.visibilityState === 'visible') {
        startPolling(); // Start polling if tab is visible
    } else {
         console.log("Tab initially hidden, polling paused.");
    }

}); // End DOMContentLoaded