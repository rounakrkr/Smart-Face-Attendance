// Polling intervals
let dataInterval, statusInterval, logInterval;

// Start polling when page loads
window.onload = function() {
    fetchData();
    fetchRecentLog();
    checkStatus();

    dataInterval = setInterval(fetchData, 5000);
    logInterval = setInterval(fetchRecentLog, 5000);
    statusInterval = setInterval(checkStatus, 3000);
};

// Fetch attendance summary and update table + cards
function fetchData() {
    fetch('/api/attendance_summary')
        .then(response => response.json())
        .then(data => {
            updateCards(data);
            updateTable(data.students);
        })
        .catch(error => console.error('Error fetching summary:', error));
}

// Update summary cards
function updateCards(data) {
    document.getElementById('totalStudents').innerText = data.total_students;
    document.getElementById('presentToday').innerText = data.present_today;
    document.getElementById('detentionRisk').innerText = data.detention_risk;
    document.getElementById('earlyWarning').innerText = data.early_warning;
}

// Update attendance table
function updateTable(students) {
    const tbody = document.querySelector('#attendanceTable tbody');
    tbody.innerHTML = '';
    students.forEach(s => {
        const row = document.createElement('tr');
        const statusClass = s.status === 'At Risk' ? 'status-risk' : 'status-safe';
        let interventionBadge = '';
        if (s.warning_level >= 3) {
            interventionBadge = '<span class="intervention-badge intervention-required">⚠️ Needs Attention</span>';
        } else {
            interventionBadge = '<span class="intervention-badge intervention-normal">✅ Normal</span>';
        }
        row.innerHTML = `
             <td>${s.roll_no}</td>
             <td>${s.name}</td>
             <td>${s.present}</td>
             <td>${s.total}</td>
             <td>${s.percentage}%</td>
             <td><span class="status-badge ${statusClass}">${s.status}</span></td>
             <td>${interventionBadge}</td>
        `;
        tbody.appendChild(row);
    });
}

// Fetch recent attendance log
function fetchRecentLog() {
    fetch('/api/recent_attendance')
        .then(response => response.json())
        .then(data => {
            const logDiv = document.getElementById('attendanceLog');
            if (!data || data.length === 0) {
                logDiv.innerHTML = '<p>No attendance marked today yet.</p>';
                return;
            }
            let html = '<table>';
            data.forEach(entry => {
                const statusClass = entry.status === 'Present' ? 'status-present' : 'status-absent';
                html += `<tr>
                    <td class="time-col">${entry.time}</td>
                    <td class="name-col">${entry.name}</td>
                    <td class="status-col ${statusClass}">${entry.status}</td>
                </tr>`;
            });
            html += '</table>';
            logDiv.innerHTML = html;
        })
        .catch(error => console.error('Error fetching log:', error));
}

// Check if attendance session is running
function checkStatus() {
    fetch('/attendance_status')
        .then(response => response.json())
        .then(data => {
            const indicator = document.getElementById('statusIndicator');
            const startBtn = document.getElementById('startBtn');
            const stopBtn = document.getElementById('stopBtn');
            if (data.running) {
                indicator.innerText = '🟢 Running';
                indicator.style.background = '#d4f8d4';
                indicator.style.color = '#1e7e34';
                startBtn.disabled = true;
                stopBtn.style.display = 'inline-block';
            } else {
                indicator.innerText = '🔴 Stopped';
                indicator.style.background = '#fdeaea';
                indicator.style.color = '#c82333';
                startBtn.disabled = false;
                stopBtn.style.display = 'none';
            }
        });
}

// Start attendance session
function startAttendance() {
    fetch('/start_attendance', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            alert('Attendance Session: ' + data.status);
            checkStatus();
        })
        .catch(error => console.error('Error starting session:', error));
}

// Stop attendance session
function stopAttendance() {
    fetch('/stop_attendance', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            alert('Stopping attendance session...');
            checkStatus();
        })
        .catch(error => console.error('Error stopping session:', error));
}

// Finalize class and run early warning
function finalizeClass() {
    if (confirm('Finalize today\'s class? This will update total classes and check early warnings.')) {
        fetch('/finalize_class')
            .then(response => response.json())
            .then(data => {
                alert('Class finalized! ' + (data.early_warning_executed ? 'Early warning executed.' : ''));
                fetchData(); // refresh dashboard data
            })
            .catch(error => console.error('Error finalizing class:', error));
    }
}

// Sidebar toggle functionality
const hamburger = document.getElementById('hamburger');
const sidebar = document.getElementById('sidebar');
const overlay = document.getElementById('overlay');

function openSidebar() {
    sidebar.classList.add('open');
    overlay.style.display = 'block';
    document.body.style.overflow = 'hidden';
}

function closeSidebar() {
    sidebar.classList.remove('open');
    overlay.style.display = 'none';
    document.body.style.overflow = '';
}

if (hamburger) {
    hamburger.addEventListener('click', function(e) {
        if (sidebar.classList.contains('open')) {
            closeSidebar();
        } else {
            openSidebar();
        }
    });
}
if (overlay) {
    overlay.addEventListener('click', closeSidebar);
}

document.querySelectorAll('.sidebar-nav a').forEach(link => {
    link.addEventListener('click', closeSidebar);
});