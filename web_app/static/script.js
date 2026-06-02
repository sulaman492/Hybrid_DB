let queryHistory = [];

document.addEventListener('DOMContentLoaded', function() {
    const executeBtn = document.getElementById('executeBtn');
    const clearBtn = document.getElementById('clearBtn');
    const resetBtn = document.getElementById('resetBtn');
    const clearHistoryBtn = document.getElementById('clearHistoryBtn');
    const queryInput = document.getElementById('queryInput');

    executeBtn.addEventListener('click', executeQuery);
    clearBtn.addEventListener('click', () => { queryInput.value = ''; });
    resetBtn.addEventListener('click', resetSession);
    clearHistoryBtn.addEventListener('click', clearHistory);

    // Enter key to execute (Ctrl+Enter)
    queryInput.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.key === 'Enter') {
            executeQuery();
        }
    });

    // Database/table clicks
    document.getElementById('databaseList')?.addEventListener('click', (e) => {
        if (e.target.tagName === 'LI') {
            const dbName = e.target.textContent;
            executeCommand(`USE DATABASE ${dbName};`);
        }
    });

    document.getElementById('tableList')?.addEventListener('click', (e) => {
        if (e.target.tagName === 'LI') {
            const tableName = e.target.textContent;
            executeCommand(`SELECT * FROM ${tableName};`);
        }
    });
});

async function executeQuery() {
    const queryInput = document.getElementById('queryInput');
    const query = queryInput.value.trim();
    
    if (!query) {
        showError('Please enter a query');
        return;
    }

    await executeCommand(query);
}

async function executeCommand(query) {
    // Add to history
    addToHistory(query);
    
    // Show loading
    const resultsDiv = document.getElementById('results');
    resultsDiv.innerHTML = '<div class="placeholder">Executing query...</div>';
    
    try {
        const response = await fetch('/api/execute', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ query: query })
        });
        
        const data = await response.json();
        displayResults(data);
        
        // Refresh sidebar if needed
        if (query.toUpperCase().includes('CREATE DATABASE') || 
            query.toUpperCase().includes('USE DATABASE') ||
            query.toUpperCase().includes('DROP DATABASE')) {
            refreshSidebar();
        }
        
        if (query.toUpperCase().includes('CREATE TABLE') || 
            query.toUpperCase().includes('DROP TABLE')) {
            refreshTables();
        }
        
    } catch (error) {
        showError(`Connection error: ${error.message}`);
    }
}

function displayResults(data) {
    const resultsDiv = document.getElementById('results');
    const rowCountSpan = document.getElementById('rowCount');
    
    if (data.type === 'select') {
        if (data.rows.length === 0) {
            resultsDiv.innerHTML = '<div class="placeholder">No results found</div>';
            rowCountSpan.textContent = '0 rows';
            return;
        }
        
        // Create table
        const table = document.createElement('table');
        const headers = Object.keys(data.rows[0]);
        
        // Header
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        headers.forEach(header => {
            const th = document.createElement('th');
            th.textContent = header;
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);
        
        // Body
        const tbody = document.createElement('tbody');
        data.rows.forEach(row => {
            const tr = document.createElement('tr');
            headers.forEach(header => {
                const td = document.createElement('td');
                let value = row[header];
                if (value === undefined || value === null) value = 'NULL';
                td.textContent = value;
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        
        resultsDiv.innerHTML = '';
        resultsDiv.appendChild(table);
        rowCountSpan.textContent = `${data.count} row(s)`;
        
    } else if (data.type === 'value') {
        resultsDiv.innerHTML = `<div class="value-result">Result: ${data.value}</div>`;
        rowCountSpan.textContent = '1 value';
        
    } else if (data.type === 'message') {
        const className = data.success ? 'success' : 'error';
        resultsDiv.innerHTML = `<div class="${className}">${data.message}</div>`;
        rowCountSpan.textContent = '';
        
    } else if (data.type === 'schema') {
        let html = '<table><thead><tr><th>Column</th><th>Type</th></tr></thead><tbody>';
        data.columns.forEach(col => {
            html += `<tr><td>${col.name}</td><td>${col.type}</td></tr>`;
        });
        html += '</tbody></table>';
        resultsDiv.innerHTML = html;
        rowCountSpan.textContent = `${data.columns.length} column(s)`;
        
    } else if (data.type === 'databases') {
        let html = '<table><thead><tr><th>Database</th><th>Status</th></tr></thead><tbody>';
        data.databases.forEach(db => {
            const isCurrent = db === data.current_db;
            html += `<tr><td>${db}</td><td>${isCurrent ? '🟢 Current' : ''}</td></tr>`;
        });
        html += '</tbody></table>';
        resultsDiv.innerHTML = html;
        rowCountSpan.textContent = `${data.databases.length} database(s)`;
        
    } else if (data.type === 'tables') {
        if (data.tables.length === 0) {
            resultsDiv.innerHTML = '<div class="placeholder">No tables found</div>';
        } else {
            let html = '<table><thead><tr><th>Table Name</th></tr></thead><tbody>';
            data.tables.forEach(table => {
                html += `<tr><td>📋 ${table}</td></tr>`;
            });
            html += '</tbody></table>';
            resultsDiv.innerHTML = html;
        }
        rowCountSpan.textContent = `${data.tables.length} table(s)`;
        
    } else if (data.type === 'error') {
        showError(data.message);
    }
}

function showError(message) {
    const resultsDiv = document.getElementById('results');
    resultsDiv.innerHTML = `<div class="error">❌ Error: ${message}</div>`;
    document.getElementById('rowCount').textContent = '';
}

function addToHistory(query) {
    queryHistory.unshift(query);
    if (queryHistory.length > 10) queryHistory.pop();
    updateHistoryDisplay();
}

function updateHistoryDisplay() {
    const historyList = document.getElementById('historyList');
    if (queryHistory.length === 0) {
        historyList.innerHTML = '<li class="placeholder">No queries executed yet</li>';
        return;
    }
    
    historyList.innerHTML = queryHistory.map(q => 
        `<li onclick="executeCommand('${q.replace(/'/g, "\\'")}')">${q.substring(0, 60)}${q.length > 60 ? '...' : ''}</li>`
    ).join('');
}

function clearHistory() {
    queryHistory = [];
    updateHistoryDisplay();
}

async function refreshSidebar() {
    try {
        const response = await fetch('/api/databases');
        const data = await response.json();
        
        const dbList = document.getElementById('databaseList');
        dbList.innerHTML = data.databases.map(db => 
            `<li class="${db === data.current_db ? 'active' : ''}">${db}</li>`
        ).join('');
        
        document.getElementById('currentDb').textContent = data.current_db || 'None';
        
        if (data.current_db) {
            refreshTables();
        }
    } catch (error) {
        console.error('Error refreshing sidebar:', error);
    }
}

async function refreshTables() {
    try {
        const response = await fetch('/api/tables');
        const data = await response.json();
        
        const tableList = document.getElementById('tableList');
        if (data.tables.length === 0) {
            tableList.innerHTML = '<li class="placeholder">No tables</li>';
        } else {
            tableList.innerHTML = data.tables.map(table => `<li>${table}</li>`).join('');
        }
    } catch (error) {
        console.error('Error refreshing tables:', error);
    }
}

async function resetSession() {
    if (confirm('Reset will clear all results and history. Continue?')) {
        queryHistory = [];
        updateHistoryDisplay();
        document.getElementById('queryInput').value = '';
        document.getElementById('results').innerHTML = '<div class="placeholder">Execute a query to see results</div>';
        document.getElementById('rowCount').textContent = '';
        await refreshSidebar();
    }
}