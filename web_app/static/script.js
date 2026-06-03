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
    document.getElementById('rowCount').textContent = '';
    
    try {
        const response = await fetch('/api/execute', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ query: query })
        });
        
        const data = await response.json();
        
        // Handle different response types
        if (data.type === 'error' || data.success === false) {
            displayConstraintError(data);
        } else {
            displayResults(data);
        }
        
        // Refresh sidebar if needed
        const queryUpper = query.toUpperCase();
        if (queryUpper.includes('CREATE DATABASE') || 
            queryUpper.includes('USE DATABASE') ||
            queryUpper.includes('DROP DATABASE')) {
            await refreshSidebar();
        }
        
        if (queryUpper.includes('CREATE TABLE') || 
            queryUpper.includes('DROP TABLE')) {
            await refreshTables();
        }
        
        // Refresh tables after INSERT as well to show new data
        if (queryUpper.includes('INSERT INTO')) {
            await refreshTables();
        }
        
    } catch (error) {
        showError(`Connection error: ${error.message}`);
    }
}

function displayConstraintError(data) {
    const resultsDiv = document.getElementById('results');
    const errorMessage = data.message || data.error || 'Unknown error occurred';
    
    // Check for specific constraint violations and format accordingly
    let errorType = 'General Error';
    let formattedMessage = errorMessage;
    let suggestion = 'Please check your query syntax and data types.';
    
    if (errorMessage.includes('AUTO_INCREMENT')) {
        errorType = 'AUTO_INCREMENT Violation';
        suggestion = 'Do not provide values for AUTO_INCREMENT columns. They will be auto-generated.';
        formattedMessage = errorMessage.replace('Cannot insert value into AUTO_INCREMENT column', 
                                                '❌ Cannot manually insert into AUTO_INCREMENT column');
    } 
    else if (errorMessage.includes('NOT NULL')) {
        errorType = 'NOT NULL Constraint Violation';
        suggestion = 'Provide a value for the required column or set a DEFAULT value.';
    }
    else if (errorMessage.includes('UNIQUE')) {
        errorType = 'UNIQUE Constraint Violation';
        suggestion = 'The value you\'re trying to insert already exists. Use a different value.';
    }
    else if (errorMessage.includes('FOREIGN KEY')) {
        errorType = 'FOREIGN KEY Constraint Violation';
        suggestion = 'Make sure the referenced value exists in the parent table.';
    }
    else if (errorMessage.includes('INT column')) {
        errorType = 'Type Mismatch Error';
        suggestion = 'INT columns accept only numeric values. Remove quotes or use numbers.';
    }
    else if (errorMessage.includes('DATE format')) {
        errorType = 'Date Format Error';
        suggestion = 'Use YYYY-MM-DD format for DATE columns (e.g., 2024-01-01).';
    }
    else if (errorMessage.includes('Expected') && errorMessage.includes('values')) {
        errorType = 'Value Count Mismatch';
        suggestion = 'Check if you\'re inserting the correct number of values.';
    }
    
    // Create a detailed error display
    resultsDiv.innerHTML = `
        <div class="error-container">
            <div class="error-header">
                <span class="error-icon">❌</span>
                <span class="error-type">${escapeHtml(errorType)}</span>
            </div>
            <div class="error-message">${escapeHtml(formattedMessage)}</div>
            <div class="error-suggestion">💡 ${escapeHtml(suggestion)}</div>
            <div class="error-help">
                <details>
                    <summary>🔍 Show query help</summary>
                    <div class="help-content">
                        <p><strong>Common issues:</strong></p>
                        <ul>
                            <li>Don't use quotes around numbers for INT/DECIMAL columns</li>
                            <li>Don't insert values into AUTO_INCREMENT columns</li>
                            <li>Use YYYY-MM-DD format for DATE columns</li>
                            <li>Make sure foreign key values exist in referenced tables</li>
                            <li>Check that NOT NULL columns have values</li>
                        </ul>
                    </div>
                </details>
            </div>
        </div>
    `;
    document.getElementById('rowCount').textContent = '';
}

function displayResults(data) {
    const resultsDiv = document.getElementById('results');
    const rowCountSpan = document.getElementById('rowCount');
    
    if (data.type === 'select') {
        if (!data.rows || data.rows.length === 0) {
            resultsDiv.innerHTML = '<div class="placeholder">No results found</div>';
            rowCountSpan.textContent = '0 rows';
            return;
        }
        
        // Create table with better styling
        const table = document.createElement('table');
        table.className = 'results-table';
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
        resultsDiv.innerHTML = `
            <div class="value-result">
                <div class="value-label">Result:</div>
                <div class="value-content">${escapeHtml(String(data.value))}</div>
            </div>
        `;
        rowCountSpan.textContent = '1 value';
        
    } else if (data.type === 'message') {
        if (data.success) {
            resultsDiv.innerHTML = `
                <div class="success-container">
                    <div class="success-icon">✅</div>
                    <div class="success-message">${escapeHtml(data.message)}</div>
                </div>
            `;
        } else {
            displayConstraintError(data);
        }
        rowCountSpan.textContent = '';
        
    } else if (data.type === 'schema') {
        if (!data.columns || data.columns.length === 0) {
            resultsDiv.innerHTML = '<div class="placeholder">No schema information available</div>';
        } else {
            let html = '<table class="schema-table"><thead><tr><th>Column</th><th>Type</th><th>Constraints</th></tr></thead><tbody>';
            data.columns.forEach(col => {
                html += `<tr>
                            <td><strong>${escapeHtml(col.name)}</strong></td>
                            <td>${escapeHtml(col.type)}</td>
                            <td>${escapeHtml(col.constraints || '-')}</td>
                         </tr>`;
            });
            html += '</tbody></table>';
            resultsDiv.innerHTML = html;
        }
        rowCountSpan.textContent = `${data.columns ? data.columns.length : 0} column(s)`;
        
    } else if (data.type === 'databases') {
        if (!data.databases || data.databases.length === 0) {
            resultsDiv.innerHTML = '<div class="placeholder">No databases found</div>';
        } else {
            let html = '<table class="db-table"><thead><tr><th>Database</th><th>Status</th></tr></thead><tbody>';
            data.databases.forEach(db => {
                const isCurrent = db === data.current_db;
                html += `<tr>
                            <td>📁 ${escapeHtml(db)}</td>
                            <td>${isCurrent ? '🟢 Current' : ''}</td>
                         </tr>`;
            });
            html += '</tbody></table>';
            resultsDiv.innerHTML = html;
        }
        rowCountSpan.textContent = `${data.databases.length} database(s)`;
        
    } else if (data.type === 'tables') {
        if (data.tables.length === 0) {
            resultsDiv.innerHTML = '<div class="placeholder">No tables found in current database</div>';
        } else {
            let html = '<table class="tables-table"><thead><tr><th>Table Name</th></tr></thead><tbody>';
            data.tables.forEach(table => {
                html += `<tr><td>📋 ${escapeHtml(table)}</td></tr>`;
            });
            html += '</tbody></table>';
            resultsDiv.innerHTML = html;
        }
        rowCountSpan.textContent = `${data.tables.length} table(s)`;
        
    } else {
        resultsDiv.innerHTML = `<div class="error">❌ Unexpected response format</div>`;
        console.error('Unexpected response:', data);
    }
}

function showError(message) {
    const resultsDiv = document.getElementById('results');
    resultsDiv.innerHTML = `
        <div class="error-container">
            <div class="error-header">
                <span class="error-icon">❌</span>
                <span class="error-type">Connection Error</span>
            </div>
            <div class="error-message">${escapeHtml(message)}</div>
        </div>
    `;
    document.getElementById('rowCount').textContent = '';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
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
        `<li onclick="executeCommand('${q.replace(/'/g, "\\'").replace(/\n/g, ' ')}')">
            <span class="history-query">${escapeHtml(q.substring(0, 60))}${q.length > 60 ? '...' : ''}</span>
         </li>`
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
        if (data.databases && data.databases.length > 0) {
            dbList.innerHTML = data.databases.map(db => 
                `<li class="${db === data.current_db ? 'active' : ''}">📁 ${escapeHtml(db)}</li>`
            ).join('');
        } else {
            dbList.innerHTML = '<li class="placeholder">No databases</li>';
        }
        
        document.getElementById('currentDb').textContent = data.current_db || 'None';
        
        if (data.current_db) {
            await refreshTables();
        } else {
            const tableList = document.getElementById('tableList');
            tableList.innerHTML = '<li class="placeholder">No database selected</li>';
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
        if (data.tables && data.tables.length > 0) {
            tableList.innerHTML = data.tables.map(table => `<li>📋 ${escapeHtml(table)}</li>`).join('');
        } else {
            tableList.innerHTML = '<li class="placeholder">No tables</li>';
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