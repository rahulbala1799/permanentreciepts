// JavaScript for Receipts Management Page
document.addEventListener('DOMContentLoaded', function() {
    // Initialize the receipts page
    loadReceipts();
    loadJobs();
    
    // Set up periodic updates
    setInterval(loadReceipts, 30000); // Update every 30 seconds
    setInterval(loadJobs, 30000); // Update jobs every 30 seconds
});

function loadReceipts() {
    fetch('/api/receipts')
        .then(response => response.json())
        .then(data => {
            updateStatistics(data);
            updateReceiptsTable(data);
        })
        .catch(error => {
            console.error('Error loading receipts:', error);
            document.getElementById('receipts-table-body').innerHTML = 
                '<tr><td colspan="6" class="text-center text-danger">Error loading receipts</td></tr>';
        });
}

function updateStatistics(receipts) {
    const total = receipts.length;
    const pending = receipts.filter(r => r.status === 'pending').length;
    const completed = receipts.filter(r => r.status === 'completed').length;
    const errors = receipts.filter(r => r.status === 'error').length;
    
    document.getElementById('total-receipts').textContent = total;
    document.getElementById('pending-receipts').textContent = pending;
    document.getElementById('completed-receipts').textContent = completed;
    document.getElementById('error-receipts').textContent = errors;
}

function updateReceiptsTable(receipts) {
    const tbody = document.getElementById('receipts-table-body');
    
    if (receipts.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No receipts uploaded yet.</td></tr>';
        return;
    }
    
    tbody.innerHTML = receipts.map(receipt => `
        <tr>
            <td>
                <i class="fas fa-file-excel text-success"></i>
                <strong>${receipt.filename}</strong>
            </td>
            <td>
                <span class="badge ${getStatusClass(receipt.status)}">${receipt.status}</span>
            </td>
            <td>${new Date(receipt.created_at).toLocaleDateString()}</td>
            <td>${receipt.vendor_name || '-'}</td>
            <td>${receipt.total_amount ? '$' + receipt.total_amount.toFixed(2) : '-'}</td>
            <td>
                <div class="btn-group btn-group-sm" role="group">
                    <button type="button" class="btn btn-outline-primary" onclick="viewReceipt(${receipt.id})">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button type="button" class="btn btn-outline-success" onclick="processReceipt(${receipt.id})">
                        <i class="fas fa-play"></i>
                    </button>
                    <button type="button" class="btn btn-outline-danger" onclick="deleteReceipt(${receipt.id})">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </td>
        </tr>
    `).join('');
}

function getStatusClass(status) {
    const statusClasses = {
        'pending': 'bg-warning',
        'processing': 'bg-info',
        'completed': 'bg-success',
        'error': 'bg-danger',
        'failed': 'bg-danger'
    };
    return statusClasses[status] || 'bg-secondary';
}

function filterReceipts(status) {
    // This would filter the table based on status
    // For now, just reload all receipts
    loadReceipts();
}

function viewReceipt(receiptId) {
    // Navigate to receipt detail view
    window.location.href = `/receipt/${receiptId}`;
}

function processReceipt(receiptId) {
    // Start processing the receipt
    fetch(`/api/receipts/${receiptId}/process`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        alert('Processing started for receipt ' + receiptId);
        loadReceipts(); // Refresh the table
    })
    .catch(error => {
        console.error('Error processing receipt:', error);
        alert('Error starting processing');
    });
}

function deleteReceipt(receiptId) {
    if (confirm('Are you sure you want to delete this receipt?')) {
        fetch(`/api/receipts/${receiptId}`, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            alert('Receipt deleted successfully');
            loadReceipts(); // Refresh the table
        })
        .catch(error => {
            console.error('Error deleting receipt:', error);
            alert('Error deleting receipt');
        });
    }
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
        loadReceipts(); // Refresh the table
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

// Job Management Functions
function loadJobs() {
    fetch('/api/jobs')
        .then(response => response.json())
        .then(data => {
            updateJobsTable(data);
        })
        .catch(error => {
            console.error('Error loading jobs:', error);
            document.getElementById('jobs-table-body').innerHTML = 
                '<tr><td colspan="6" class="text-center text-danger">Error loading jobs</td></tr>';
        });
}

function updateJobsTable(jobs) {
    const tbody = document.getElementById('jobs-table-body');
    
    if (jobs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No processing jobs created yet.</td></tr>';
        return;
    }
    
    tbody.innerHTML = jobs.map(job => `
        <tr>
            <td>
                <i class="fas fa-tasks text-primary"></i>
                <strong>${job.job_name}</strong>
            </td>
            <td>
                <span class="badge ${getJobStatusClass(job.status)}">${job.status}</span>
            </td>
            <td>${new Date(job.created_at).toLocaleDateString()}</td>
            <td>${job.started_at ? new Date(job.started_at).toLocaleDateString() : '-'}</td>
            <td>${job.completed_at ? new Date(job.completed_at).toLocaleDateString() : '-'}</td>
            <td>
                <div class="btn-group btn-group-sm" role="group">
                    <button type="button" class="btn btn-outline-primary" onclick="viewJob(${job.id})">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button type="button" class="btn btn-outline-success" onclick="restartJob(${job.id})" ${job.status === 'running' ? 'disabled' : ''}>
                        <i class="fas fa-play"></i>
                    </button>
                    <button type="button" class="btn btn-outline-danger" onclick="deleteJob(${job.id})">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </td>
        </tr>
    `).join('');
}

function getJobStatusClass(status) {
    const statusClasses = {
        'created': 'bg-primary',
        'pending': 'bg-warning',
        'running': 'bg-info',
        'completed': 'bg-success',
        'failed': 'bg-danger',
        'error': 'bg-danger'
    };
    return statusClasses[status] || 'bg-secondary';
}

function showCreateJobModal() {
    const modal = new bootstrap.Modal(document.getElementById('createJobModal'));
    modal.show();
}

function loadReceiptsForJob() {
    fetch('/api/receipts')
        .then(response => response.json())
        .then(data => {
            const receiptsList = document.getElementById('receipts-list');
            
            if (data.length === 0) {
                receiptsList.innerHTML = '<div class="text-center text-muted">No receipts available. Please upload some receipts first.</div>';
                return;
            }
            
            receiptsList.innerHTML = data.map(receipt => `
                <div class="form-check">
                    <input class="form-check-input receipt-checkbox" type="checkbox" value="${receipt.id}" id="receipt-${receipt.id}">
                    <label class="form-check-label" for="receipt-${receipt.id}">
                        <i class="fas fa-file-excel text-success"></i>
                        ${receipt.filename} 
                        <span class="badge ${getStatusClass(receipt.status)} ms-2">${receipt.status}</span>
                    </label>
                </div>
            `).join('');
        })
        .catch(error => {
            console.error('Error loading receipts for job:', error);
            document.getElementById('receipts-list').innerHTML = '<div class="text-center text-danger">Error loading receipts</div>';
        });
}

function toggleAllReceipts() {
    const selectAll = document.getElementById('selectAllReceipts');
    const checkboxes = document.querySelectorAll('.receipt-checkbox');
    
    checkboxes.forEach(checkbox => {
        checkbox.checked = selectAll.checked;
    });
}

function createJob() {
    const jobName = document.getElementById('jobName').value.trim();
    const jobDescription = document.getElementById('jobDescription').value.trim();
    
    if (!jobName) {
        alert('Please enter a reconciliation job name');
        return;
    }
    
    const jobData = {
        job_name: jobName,
        job_description: jobDescription,
        status: 'created'
    };
    
    // Show loading state
    const createBtn = document.querySelector('#createJobModal .btn-success');
    const originalText = createBtn.textContent;
    createBtn.textContent = 'Creating...';
    createBtn.disabled = true;
    
    fetch('/api/jobs', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(jobData)
    })
    .then(response => response.json())
    .then(data => {
        alert(`Reconciliation job "${jobName}" created successfully!`);
        bootstrap.Modal.getInstance(document.getElementById('createJobModal')).hide();
        
        // Reset form
        document.getElementById('create-job-form').reset();
        
        // Refresh jobs table
        loadJobs();
    })
    .catch(error => {
        console.error('Error creating job:', error);
        alert('Error creating reconciliation job');
    })
    .finally(() => {
        createBtn.textContent = originalText;
        createBtn.disabled = false;
    });
}

function viewJob(jobId) {
    // Navigate to reconciliation page for this job
    window.location.href = `/reconciliation/${jobId}`;
}

function restartJob(jobId) {
    if (confirm('Are you sure you want to restart this job?')) {
        fetch(`/api/jobs/${jobId}/restart`, {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            alert('Job restarted successfully');
            loadJobs(); // Refresh the table
        })
        .catch(error => {
            console.error('Error restarting job:', error);
            alert('Error restarting job');
        });
    }
}

function deleteJob(jobId) {
    if (confirm('Are you sure you want to delete this job? This action cannot be undone.')) {
        fetch(`/api/jobs/${jobId}`, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            alert('Job deleted successfully');
            loadJobs(); // Refresh the table
        })
        .catch(error => {
            console.error('Error deleting job:', error);
            alert('Error deleting job');
        });
    }
}
