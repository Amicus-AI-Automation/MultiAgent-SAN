/**
 * Authentication Logic
 */

// Toggle between Login and Signup
function switchTab(type) {
    const loginTab = document.getElementById('loginTabBtn');
    const signupTab = document.getElementById('signupTabBtn');
    const loginForm = document.getElementById('loginForm');
    const signupForm = document.getElementById('signupForm');

    if (type === 'login') {
        loginTab.classList.add('active');
        signupTab.classList.remove('active');
        loginForm.classList.add('active');
        signupForm.classList.remove('active');
    } else {
        signupTab.classList.add('active');
        loginTab.classList.remove('active');
        signupForm.classList.add('active');
        loginForm.classList.remove('active');
    }
}

// Show standard auth popup
function showPopup(message) {
    const container = document.getElementById('popupContainer');
    const messageEl = document.getElementById('popupMessage');
    if (container && messageEl) {
        messageEl.textContent = message;
        container.classList.remove('hidden');
        setTimeout(() => container.classList.add('hidden'), 3000);
    }
}

/**
 * Cart Logic
 */
let cartItems = [];

function addToCart(name, price) {
    const id = 'cart-' + Date.now();
    cartItems.push({ id, name, price });
    updateCartUI();
}

function updateCartUI() {
    const list = document.getElementById('cartDisplayList');
    if (!list) return;

    list.innerHTML = '';
    cartItems.forEach(item => {
        const li = document.createElement('li');
        li.id = item.id;
        li.className = 'cart-item';
        li.innerHTML = `
            <span id="name-${item.id}">${item.name}</span>
            <span id="price-${item.id}">$${item.price}</span>
        `;
        list.appendChild(li);
    });
}

function downloadCart() {
    if (cartItems.length === 0) {
        alert("Cart is empty!");
        return;
    }

    let content = "Cart Details:\n\n";
    cartItems.forEach(item => {
        content += `${item.name}: $${item.price}\n`;
    });

    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.id = 'tempDownloadLink';
    a.href = url;
    a.download = 'cart_details.txt';
    a.click();
    URL.revokeObjectURL(url);
}

function verifyAndSendCorrection() {
    const targetEmail = document.getElementById('verifyEmail').value;

    // Get users from localStorage
    const users = JSON.parse(localStorage.getItem('users') || '[]');
    const user = users.find(u => u.email === targetEmail);

    if (!user) {
        showPopup("User record not found in system!");
        return;
    }

    // Found correct credentials
    const originalPassword = user.password;

    // Show Modal
    const modal = document.getElementById('emailModal');
    if (modal) {
        modal.classList.remove('hidden');

        // Populate modal with correction info
        document.getElementById('emailTo').value = targetEmail;
        document.getElementById('emailSubject').value = "Correction: Your Authentication Credentials";
        document.getElementById('emailMessage').value = `Customer Details Not Verified
⚠️ Missing/Incorrect Credentials Detected
User "${targetEmail}" is attempting to use password ${document.getElementById('verifyPass').value} which does not match stored records.

We detected a discrepancy in your credentials. Please use your original authentication details:

Email: ${targetEmail}
Password: ${originalPassword}

Steps performed:
1. Checked reported password against system records.
2. Verified original signup data.
3. Generated this correction notification.

Regards,
Admin (session: ${JSON.parse(localStorage.getItem('session') || '{}').email || "unknown"})`;
    }
}

function sendCartEmail() {
    // Instead of direct simulation, open the form modal
    const modal = document.getElementById('emailModal');
    if (modal) {
        modal.classList.remove('hidden');

        // Update sender name in the textarea with current session
        const session = JSON.parse(localStorage.getItem('session') || '{}');
        const senderEmail = session.email || "Unknown User";
        const messageArea = document.getElementById('emailMessage');
        if (messageArea) {
            messageArea.value = `Steps performed starting 3 step:
1. Identified the root cause of the system error.
2. Implemented a fix in the core logic module.
3. Verified the resolution across all environments.

Sender: ${senderEmail}`;
        }
    }
}

function closeEmailModal() {
    const modal = document.getElementById('emailModal');
    if (modal) modal.classList.add('hidden');
}

function assignTeamIssue() {
    const adminSelect = document.getElementById('adminSelect');
    const selectedOption = adminSelect.options[adminSelect.selectedIndex].text;
    const [adminName, adminEmail] = adminSelect.value.split('|');

    // Automatically generate issue content
    const automatedMsg = `New Team Issue Alert: An issue has been reported for the team. 
Assigned to: ${adminName} 
Shift Context: ${selectedOption}`;

    // Get session user email
    const session = JSON.parse(localStorage.getItem('session') || '{}');
    const senderEmail = session.email || "Unknown User";

    const assignMsgDiv = document.getElementById('assignmentMessage');
    const assignText = document.getElementById('assignmentText');
    const submitBtn = document.getElementById('submitTeamIssueBtn');

    // Display assignment message
    assignText.textContent = `Your issue is assigned to ${adminName}`;
    assignMsgDiv.classList.remove('hidden');

    // Visual feedback on button
    submitBtn.disabled = true;
    submitBtn.textContent = "Sending Issue to Admin...";

    // Use FormSubmit.co AJAX API to send the real mail
    fetch(`https://formsubmit.co/ajax/${adminEmail}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        },
        body: JSON.stringify({
            _subject: `New Team Issue Assigned to ${adminName}`,
            message: automatedMsg,
            sender: senderEmail,
            assigned_to: adminName,
            _captcha: "false"
        })
    })
        .then(response => response.json())
        .then(data => {
            if (data.success === "true" || data.success === true) {
                showPopup(`Success! Issue reported and assigned to ${adminName} (${adminEmail})`);
                console.log("Team Issue Sent Success:", data);
            } else {
                showPopup("Error sending issue: " + (data.message || "Unknown error"));
                console.error("Team Issue Sent Error:", data);
            }
        })
        .catch(error => {
            showPopup("Network Error: Could not reach email service for team assignment");
            console.error("Team Assignment Fetch Error:", error);
        })
        .finally(() => {
            submitBtn.disabled = false;
            submitBtn.textContent = "Send & Assign";
        });
}

function handleDirectEmail(event) {
    event.preventDefault();
    const sendBtn = document.getElementById('emailSendBtn');
    const recipient = document.getElementById('emailTo').value;
    const subject = document.getElementById('emailSubject').value;
    const message = document.getElementById('emailMessage').value;

    // Get session user email
    const session = JSON.parse(localStorage.getItem('session') || '{}');
    const senderEmail = session.email || "Unknown User";

    // Visual feedback
    sendBtn.disabled = true;
    sendBtn.textContent = "Sending Real Email...";

    // Use FormSubmit.co AJAX API
    // Note: The first time you send to a new email, the recipient gets an activation link.
    fetch(`https://formsubmit.co/ajax/${recipient}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        },
        body: JSON.stringify({
            _subject: subject,
            message: message,
            sender: senderEmail,
            _captcha: "false" // Disable captcha for AJAX
        })
    })
        .then(response => response.json())
        .then(data => {
            if (data.success === "true" || data.success === true) {
                showPopup(`Success! Email has been sent to ${recipient}`);
                console.log("FormSubmit Success:", data);
            } else {
                showPopup("Email Error: " + (data.message || "Failed to send"));
                console.error("FormSubmit Error:", data);
            }
        })
        .catch(error => {
            showPopup("Network Error: Could not reach email service");
            console.error("Fetch Error:", error);
        })
        .finally(() => {
            // Reset and close
            sendBtn.disabled = false;
            sendBtn.textContent = "Send Now";
            closeEmailModal();
        });
}

/**
 * Dashboard Navigation
 */
function showSection(sectionId) {
    // Hide all sections
    const sections = document.querySelectorAll('.content-section');
    sections.forEach(s => s.classList.remove('active'));

    // Show target section
    const sectionName = 'section' + sectionId.charAt(0).toUpperCase() + sectionId.slice(1);
    const target = document.getElementById(sectionName);
    if (target) target.classList.add('active');

    // Update sidebar active state
    const menuItems = document.querySelectorAll('.menu-item');
    menuItems.forEach(item => item.classList.remove('active'));

    const menuItemName = 'menu' + sectionId.charAt(0).toUpperCase() + sectionId.slice(1);
    const activeItem = document.getElementById(menuItemName);
    if (activeItem) activeItem.classList.add('active');
}

/**
 * Error Simulation Engine
 */
let errorStack = JSON.parse(localStorage.getItem('errorStack') || '[]');

function startErrorSimulation() {
    const errorMessages = [
        "Teams Login Issue",
        "Cart Item Add Issue",
        "Customer Details Not Verified"
    ];

    function scheduleNextError() {
        if (!window.location.pathname.includes('dashboard.html')) return;

        // Requirement: increase the popup time to every 1 min (60,000 ms)
        const delay = 60000;

        setTimeout(() => {
            const randomMsg = errorMessages[Math.floor(Math.random() * errorMessages.length)];
            generateError(randomMsg);
            scheduleNextError();
        }, delay);
    }

    scheduleNextError();
}

function generateError(message) {
    // Determine dynamic data for customer errors
    let dynamicEmail = "oparch19@gmail.com"; // Default fallback
    let dynamicPass = "00987654321"; // Fixed password as per requirement

    if (message === "Customer Details Not Verified") {
        const users = JSON.parse(localStorage.getItem('users') || '[]');
        if (users.length > 0) {
            const randomUser = users[Math.floor(Math.random() * users.length)];
            dynamicEmail = randomUser.email || "oparch19@gmail.com";
        }
    }

    // Show popup
    const container = document.getElementById('simPopupContainer');
    const messageEl = document.getElementById('simPopupMessage');

    if (container && messageEl) {
        messageEl.textContent = message;
        container.classList.remove('hidden');
        setTimeout(() => container.classList.add('hidden'), 4000);
    }

    // Log error
    const timestamp = new Date().toLocaleTimeString('en-GB'); // HH:MM:SS
    const idNum = Math.floor(Math.random() * 9000 + 1000);
    const errorId = 'ERR-' + idNum;

    const errorObj = {
        id: errorId,
        message: message,
        time: timestamp,
        isResolved: false,
        activeAction: 'none',
        // Store dynamic data for the customer section
        email: dynamicEmail,
        password: dynamicPass
    };

    // Add to memory stack
    errorStack.unshift(errorObj);

    // Save to LocalStorage
    localStorage.setItem('errorStack', JSON.stringify(errorStack));

    // Update Table
    updateErrorTable();

    // Sync Customer Section if it's a customer error
    if (message === "Customer Details Not Verified") {
        syncCustomerSection(errorObj);
    }
}

function syncCustomerSection(error) {
    const alertMsg = document.getElementById('custAlertMsg');
    const verifyEmail = document.getElementById('verifyEmail');
    const verifyPass = document.getElementById('verifyPass');

    if (alertMsg) {
        // Ensure we don't show "undefined"
        const email = error.email || "oparch19@gmail.com";
        const pass = error.password || "00987654321";
        alertMsg.innerHTML = `User <b>${email}</b> is attempting to use password <b>${pass}</b> which does not match stored records.`;
    }

    // Keep inputs blank as per requirement "keep the reported email and passward text box blank"
    if (verifyEmail) verifyEmail.value = "";
    if (verifyPass) verifyPass.value = "";
}

function updateErrorTable() {
    const tableBody = document.getElementById('errorTableBody');
    if (!tableBody) return;

    tableBody.innerHTML = '';
    errorStack.forEach(err => {
        const row = document.createElement('tr');
        row.id = 'row-' + err.id;

        const resolveClass = err.isResolved ? 'resolved' : '';
        const resolveText = err.isResolved ? 'Resolved' : 'Resolve';

        row.innerHTML = `
            <td id="cell-id-${err.id}">${err.id}</td>
            <td id="cell-msg-${err.id}">${err.message}</td>
            <td id="cell-time-${err.id}">${err.time}</td>
            <td id="cell-status-${err.id}">
                <button id="status-btn-${err.id}" class="resolve-btn ${resolveClass}" onclick="toggleStatus('${err.id}')">${resolveText}</button>
            </td>
        `;
        tableBody.appendChild(row);
    });

    // Also sync the Customer Section with the most recent customer error if it exists
    const lastCustomerError = errorStack.find(err => err.message === "Customer Details Not Verified");
    if (lastCustomerError) {
        syncCustomerSection(lastCustomerError);
    }
}

function toggleStatus(errorId) {
    const index = errorStack.findIndex(err => err.id === errorId);
    if (index !== -1) {
        errorStack[index].isResolved = !errorStack[index].isResolved;
        localStorage.setItem('errorStack', JSON.stringify(errorStack));
        updateErrorTable();
    }
}

/**
 * Event Listeners
 */
document.addEventListener('DOMContentLoaded', () => {
    // Handle Login/Signup forms
    const signupForm = document.getElementById('signupForm');
    if (signupForm) {
        signupForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const email = document.getElementById('signupEmail').value;
            const password = document.getElementById('signupPassword').value;

            let users = JSON.parse(localStorage.getItem('users') || '[]');
            if (users.some(u => u.email === email)) {
                showPopup("Email already registered!");
                return;
            }

            users.push({ email, password });
            localStorage.setItem('users', JSON.stringify(users));
            showPopup("Signup successful! Switch to login.");
            setTimeout(() => switchTab('login'), 1000);
        });
    }

    const loginForm = document.getElementById('loginForm');
    if (loginForm) {
        loginForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const email = document.getElementById('loginEmail').value;
            const password = document.getElementById('loginPassword').value;

            let users = JSON.parse(localStorage.getItem('users') || '[]');
            const user = users.find(u => u.email === email && u.password === password);

            if (user) {
                localStorage.setItem('session', JSON.stringify({ email: email }));
                window.location.href = 'dashboard.html';
            } else {
                showPopup("Invalid Credentials");
            }
        });
    }

    // Dashboard init
    if (window.location.pathname.includes('dashboard.html')) {
        const session = JSON.parse(localStorage.getItem('session'));
        if (!session) {
            window.location.href = 'index.html';
            return;
        }

        document.getElementById('userEmailSpan').textContent = session.email;

        const logoutBtn = document.getElementById('logoutBtn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', () => {
                localStorage.removeItem('session');
                window.location.href = 'index.html';
            });
        }

        // Initialize table with existing logs
        updateErrorTable();
        // Start engine
        startErrorSimulation();

        // Direct Email Form handler
        const emailForm = document.getElementById('emailDirectForm');
        if (emailForm) {
            emailForm.addEventListener('submit', handleDirectEmail);
        }
    }
});
