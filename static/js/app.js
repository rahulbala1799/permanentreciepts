// JavaScript for Receipts Automation Dashboard
document.addEventListener('DOMContentLoaded', function() {
    // Initialize the dashboard
    loadDashboard();
    
    // Set up periodic updates
    setInterval(loadDashboard, 30000); // Update every 30 seconds
});

function loadDashboard() {
    loadReceipts();
    loadJobs();
    checkSystemStatus();
}

function loadReceipts() {
    fetch('/api/receipts')
        .then(response => response.json())
        .then(data => {
            const container = document.getElementById('receipts-list');
            if (data.length === 0) {
                container.innerHTML = '<p class="text-muted">No receipts uploaded yet.</p>';
                return;
            }
            
            container.innerHTML = data.map(receipt => `
                <div class="receipt-item">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <strong>${receipt.filename}</strong>
                            <br>
                            <small class="text-muted">${new Date(receipt.created_at).toLocaleString()}</small>
                        </div>
                        <span class="badge status-badge ${getStatusClass(receipt.status)}">${receipt.status}</span>
                    </div>
                </div>
            `).join('');
        })
        .catch(error => {
            console.error('Error loading receipts:', error);
            document.getElementById('receipts-list').innerHTML = '<p class="text-danger">Error loading receipts</p>';
        });
}

function loadJobs() {
    fetch('/api/jobs')
        .then(response => response.json())
        .then(data => {
            const container = document.getElementById('jobs-list');
            if (data.length === 0) {
                container.innerHTML = '<p class="text-muted">No processing jobs yet.</p>';
                return;
            }
            
            container.innerHTML = data.map(job => `
                <div class="job-item">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <strong>${job.job_name}</strong>
                            <br>
                            <small class="text-muted">${new Date(job.created_at).toLocaleString()}</small>
                        </div>
                        <span class="badge status-badge ${getStatusClass(job.status)}">${job.status}</span>
                    </div>
                </div>
            `).join('');
        })
        .catch(error => {
            console.error('Error loading jobs:', error);
            document.getElementById('jobs-list').innerHTML = '<p class="text-danger">Error loading jobs</p>';
        });
}

function checkSystemStatus() {
    fetch('/api/health')
        .then(response => response.json())
        .then(data => {
            const container = document.getElementById('system-status');
            const statusClass = data.status === 'healthy' ? 'bg-success' : 'bg-danger';
            container.innerHTML = `
                <span class="badge ${statusClass}">${data.status.toUpperCase()}</span>
                <small class="ms-2 text-muted">Database: ${data.database}</small>
            `;
        })
        .catch(error => {
            console.error('Error checking system status:', error);
            document.getElementById('system-status').innerHTML = '<span class="badge bg-danger">ERROR</span>';
        });
}

function getStatusClass(status) {
    const statusClasses = {
        'pending': 'bg-warning',
        'processing': 'bg-info',
        'completed': 'bg-success',
        'error': 'bg-danger',
        'failed': 'bg-danger',
        'running': 'bg-primary'
    };
    return statusClasses[status] || 'bg-secondary';
}

function showUploadModal() {
    const modal = new bootstrap.Modal(document.getElementById('uploadModal'));
    modal.show();
}

function uploadFiles() {
    const fileInput = document.getElementById('files');
    const files = fileInput.files;
    
    if (files.length === 0) {
        alert('Please select files to upload');
        return;
    }
    
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
    }
    
    // Show loading state
    const uploadBtn = document.querySelector('#uploadModal .btn-primary');
    const originalText = uploadBtn.textContent;
    uploadBtn.textContent = 'Uploading...';
    uploadBtn.disabled = true;
    
    fetch('/api/upload', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        alert(`Successfully uploaded ${data.uploaded_count} files`);
        bootstrap.Modal.getInstance(document.getElementById('uploadModal')).hide();
        loadDashboard(); // Refresh the dashboard
    })
    .catch(error => {
        console.error('Upload error:', error);
        alert('Error uploading files');
    })
    .finally(() => {
        uploadBtn.textContent = originalText;
        uploadBtn.disabled = false;
        fileInput.value = ''; // Clear the file input
    });
}

// Navigation functions
function navigateToReceipts() {
    window.location.href = '/receipts';
}

function navigateToJobs() {
    // For now, show an alert - can be implemented later
    alert('Processing Jobs page coming soon!');
}

function navigateToSettings() {
    // For now, show an alert - can be implemented later
    alert('Settings page coming soon!');
}
