/* GEO Analyzer — Single Page Application */

const API = '';
let pollInterval = null;

// ── API Helpers ──

async function api(path, opts = {}) {
    const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    const res = await fetch(`${API}${path}`, { ...opts, headers });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || err.message || 'API error');
    }
    return res.json();
}

// ── Score Helpers ──

function scoreColor(score) {
    if (score >= 80) return 'var(--success)';
    if (score >= 60) return 'var(--info)';
    if (score >= 40) return 'var(--warning)';
    return 'var(--danger)';
}

function scoreClass(score) {
    if (score >= 80) return 'score-excellent';
    if (score >= 60) return 'score-good';
    if (score >= 40) return 'score-moderate';
    return 'score-poor';
}

function scoreLabel(score) {
    if (score >= 85) return 'Excellent';
    if (score >= 70) return 'Good';
    if (score >= 55) return 'Moderate';
    if (score >= 40) return 'Below Average';
    return 'Needs Attention';
}

// ── Rendering ──

function render() {
    const nav = document.getElementById('nav-right');
    nav.innerHTML = '';

    // Check hash route
    const hash = window.location.hash;
    if (hash.startsWith('#/analysis/')) {
        const id = hash.split('/')[2];
        showAnalysis(id);
    } else if (hash.startsWith('#/results/')) {
        const id = hash.split('/')[2];
        showResults(id);
    } else {
        showDashboard();
    }
}

// ── Dashboard View ──

async function showDashboard() {
    const main = document.getElementById('main-content');

    main.innerHTML = `
        <div class="dashboard-header">
            <h2>Dashboard</h2>
        </div>
        <div class="analyze-form">
            <form id="analyze-form">
                <div class="input-row">
                    <input type="url" id="analyze-url" placeholder="https://example.com" required>
                    <input type="text" id="analyze-brand" placeholder="Brand name (optional)" style="max-width: 200px;">
                    <button type="submit" class="btn btn-primary">Analyze</button>
                </div>
                <div class="error-msg hidden" id="analyze-error"></div>
            </form>
        </div>
        <div class="history-table" id="history">
            <h3>Recent Analyses</h3>
            <div id="history-content" style="padding: 20px; text-align: center; color: var(--text-secondary);">Loading...</div>
        </div>
    `;

    // Bind form
    document.getElementById('analyze-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const url = document.getElementById('analyze-url').value;
        const brand = document.getElementById('analyze-brand').value;
        const errEl = document.getElementById('analyze-error');
        errEl.classList.add('hidden');
        try {
            const data = await api('/api/geo/analyze', {
                method: 'POST',
                body: JSON.stringify({ url, brand_name: brand || null }),
            });
            window.location.hash = `#/analysis/${data.analysis_id}`;
        } catch (err) {
            errEl.textContent = err.message;
            errEl.classList.remove('hidden');
        }
    });

    // Load history
    try {
        const history = await api('/api/geo/history');
        const content = document.getElementById('history-content');
        if (history.length === 0) {
            content.textContent = 'No analyses yet. Enter a URL above to get started.';
            return;
        }
        content.innerHTML = `
            <table>
                <thead><tr><th>URL</th><th>Score</th><th>Status</th><th>Date</th><th></th></tr></thead>
                <tbody>
                    ${history.map(h => `
                        <tr>
                            <td class="url-cell">${h.url}</td>
                            <td class="score-cell ${h.geo_score ? scoreClass(h.geo_score) : ''}">${h.geo_score ?? '-'}</td>
                            <td>${h.status}</td>
                            <td>${new Date(h.created_at).toLocaleDateString()}</td>
                            <td>${h.status === 'complete' ?
                                `<button class="btn btn-outline btn-sm" onclick="window.location.hash='#/results/${h.id}'">View</button>` :
                                h.status === 'running' ?
                                `<button class="btn btn-outline btn-sm" onclick="window.location.hash='#/analysis/${h.id}'">Progress</button>` : ''
                            }</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (err) {
        document.getElementById('history-content').textContent = 'Failed to load history.';
    }
}

// ── Analysis Progress View ──

async function showAnalysis(analysisId) {
    const main = document.getElementById('main-content');

    const steps = [
        { key: 'fetch', label: 'Fetching page' },
        { key: 'detect', label: 'Detecting business type' },
        { key: 'ai_visibility', label: 'AI Visibility analysis' },
        { key: 'platform_analysis', label: 'Platform analysis' },
        { key: 'technical', label: 'Technical analysis' },
        { key: 'content_quality', label: 'Content quality analysis' },
        { key: 'schema_analysis', label: 'Schema analysis' },
        { key: 'veto', label: 'Trust verification' },
    ];

    function renderProgress(progress, status) {
        return `
            <div class="progress-container">
                <h2>Analyzing...</h2>
                <div class="progress-steps">
                    ${steps.map(s => {
                        const state = progress[s.key] || 'pending';
                        const cls = state === 'complete' ? 'step-complete' :
                                    state === 'running' ? 'step-running' :
                                    state.startsWith('error') ? 'step-error' : 'step-pending';
                        const icon = state === 'complete' ? '&#10003;' :
                                     state === 'running' ? '...' :
                                     state.startsWith('error') ? '!' : '&#8226;';
                        return `<div class="progress-step ${cls}">
                            <div class="step-icon">${icon}</div>
                            <span>${s.label}</span>
                        </div>`;
                    }).join('')}
                </div>
                ${status === 'error' ? '<p class="error-msg">Analysis failed. Please try again.</p>' : ''}
                <button class="btn btn-outline" onclick="window.location.hash='#/'" style="margin-top: 16px;">Back to Dashboard</button>
            </div>
        `;
    }

    main.innerHTML = renderProgress({}, 'running');

    // Poll for progress
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(async () => {
        try {
            const data = await api(`/api/geo/status/${analysisId}`);
            main.innerHTML = renderProgress(data.progress || {}, data.status);

            if (data.status === 'complete') {
                clearInterval(pollInterval);
                pollInterval = null;
                window.location.hash = `#/results/${analysisId}`;
            } else if (data.status === 'error') {
                clearInterval(pollInterval);
                pollInterval = null;
            }
        } catch (err) {
            clearInterval(pollInterval);
            pollInterval = null;
            main.innerHTML = renderProgress({}, 'error');
        }
    }, 2000);
}

// ── Results View ──

async function showResults(analysisId) {
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
    const main = document.getElementById('main-content');
    main.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-secondary)">Loading results...</div>';

    try {
        const data = await api(`/api/geo/result/${analysisId}`);
        renderResults(data, analysisId);
    } catch (err) {
        main.innerHTML = `<div style="text-align:center;padding:40px">
            <p class="error-msg">${err.message}</p>
            <button class="btn btn-outline" onclick="window.location.hash='#/'" style="margin-top:16px">Back</button>
        </div>`;
    }
}

function renderResults(data, analysisId) {
    const main = document.getElementById('main-content');
    const scores = data.scores || {};
    const geo = data.geo_score || 0;
    const platforms = data.platforms || {};
    const findings = data.findings || [];
    const plan = data.action_plan || {};

    const labels = {
        ai_citability: 'AI Citability', brand_authority: 'Brand Authority',
        content_eeat: 'Content & E-E-A-T', technical: 'Technical',
        schema: 'Structured Data', platform_optimization: 'Platform Optimization',
    };
    const weights = { ai_citability: 25, brand_authority: 20, content_eeat: 20, technical: 15, schema: 10, platform_optimization: 10 };

    main.innerHTML = `
        <div class="results-header">
            <div class="score-gauge" style="border-color: ${scoreColor(geo)}">
                <div class="score-value" style="color: ${scoreColor(geo)}">${geo}</div>
                <div class="score-label">/100</div>
            </div>
            <div class="meta">
                <h2>${data.brand_name || data.url}</h2>
                <p>${data.url} &middot; ${data.label} &middot; ${data.date}</p>
                <p style="font-size:13px;color:var(--text-secondary)">Business type: ${data.business_type?.type || 'unknown'} (${data.business_type?.confidence || 0}% confidence)</p>
            </div>
        </div>

        <div class="score-grid">
            ${Object.entries(labels).map(([key, label]) => {
                const s = scores[key] || 0;
                return `<div class="score-card">
                    <div class="card-header">
                        <span class="card-title">${label}</span>
                        <span class="card-score ${scoreClass(s)}">${s}</span>
                    </div>
                    <div class="card-bar"><div class="card-bar-fill" style="width:${s}%;background:${scoreColor(s)}"></div></div>
                    <div class="card-weight">${weights[key]}% weight</div>
                </div>`;
            }).join('')}
        </div>

        ${Object.keys(platforms).length ? `
        <div class="section">
            <h3>AI Platform Readiness</h3>
            ${Object.entries(platforms).map(([name, score]) => `
                <div class="platform-row">
                    <span class="platform-name">${name}</span>
                    <div class="platform-bar"><div class="platform-bar-fill" style="width:${score}%;background:${scoreColor(score)}"></div></div>
                    <span class="platform-score ${scoreClass(score)}">${score}</span>
                </div>
            `).join('')}
        </div>` : ''}

        ${findings.length ? `
        <div class="section">
            <h3>Key Findings (${findings.length})</h3>
            ${findings.slice(0, 15).map(f => `
                <div class="finding ${f.severity}">
                    <div class="finding-severity" style="color:${f.severity === 'critical' ? 'var(--danger)' : f.severity === 'high' ? 'var(--warning)' : 'var(--info)'}">${f.severity}</div>
                    <div class="finding-title">${f.title}</div>
                    ${f.description ? `<div class="finding-desc">${f.description}</div>` : ''}
                </div>
            `).join('')}
        </div>` : ''}

        ${plan.quick_wins?.length ? `
        <div class="section">
            <h3>Action Plan</h3>
            <h4 style="margin-bottom:8px;color:var(--success)">Quick Wins</h4>
            <ol class="action-list">${plan.quick_wins.map(w => `<li>${typeof w === 'string' ? w : w.action}</li>`).join('')}</ol>
            ${plan.medium_term?.length ? `<h4 style="margin:16px 0 8px;color:var(--info)">Medium-Term</h4>
            <ol class="action-list">${plan.medium_term.map(w => `<li>${typeof w === 'string' ? w : w.action}</li>`).join('')}</ol>` : ''}
            ${plan.strategic?.length ? `<h4 style="margin:16px 0 8px;color:var(--accent)">Strategic</h4>
            <ol class="action-list">${plan.strategic.map(w => `<li>${typeof w === 'string' ? w : w.action}</li>`).join('')}</ol>` : ''}
        </div>` : ''}

        <div class="section">
            <h3>Trust Certification</h3>
            <p><strong>Status:</strong> ${data.veto_result?.certification_status || 'N/A'}</p>
            <p style="font-size:13px;color:var(--text-secondary);margin-top:4px">${data.veto_result?.certification_reason || ''}</p>
        </div>

        <div class="report-buttons">
            <button class="btn btn-outline btn-sm" id="dl-md-btn">Download Markdown</button>
            <button class="btn btn-outline btn-sm" id="dl-pdf-btn">Download PDF</button>
            <button class="btn btn-outline btn-sm" onclick="window.location.hash='#/'">Back to Dashboard</button>
        </div>
    `;

    document.getElementById('dl-md-btn').addEventListener('click', () => downloadMarkdown(data));
    document.getElementById('dl-pdf-btn').addEventListener('click', () => window.print());
}

// ── Client-side Report Generation ──

function generateMarkdown(data) {
    const scores = data.scores || {};
    const findings = data.findings || [];
    const plan = data.action_plan || {};
    const platforms = data.platforms || {};
    const labels = {
        ai_citability: 'AI Citability', brand_authority: 'Brand Authority',
        content_eeat: 'Content & E-E-A-T', technical: 'Technical',
        schema: 'Structured Data', platform_optimization: 'Platform Optimization',
    };

    let md = `# GEO Analysis Report\n\n`;
    md += `**URL:** ${data.url}\n`;
    md += `**Brand:** ${data.brand_name || 'N/A'}\n`;
    md += `**Date:** ${data.date}\n`;
    md += `**Business Type:** ${data.business_type?.type || 'unknown'}\n`;
    md += `**GEO Score:** ${data.geo_score || 0}/100 (${data.label || ''})\n\n`;

    md += `## Dimension Scores\n\n`;
    md += `| Dimension | Score |\n|---|---|\n`;
    for (const [key, label] of Object.entries(labels)) {
        md += `| ${label} | ${scores[key] || 0} |\n`;
    }

    if (Object.keys(platforms).length) {
        md += `\n## AI Platform Readiness\n\n`;
        md += `| Platform | Score |\n|---|---|\n`;
        for (const [name, score] of Object.entries(platforms)) {
            md += `| ${name} | ${score} |\n`;
        }
    }

    if (findings.length) {
        md += `\n## Key Findings\n\n`;
        findings.forEach(f => {
            md += `- **[${f.severity}]** ${f.title}`;
            if (f.description) md += ` — ${f.description}`;
            md += `\n`;
        });
    }

    if (plan.quick_wins?.length) {
        md += `\n## Action Plan\n\n### Quick Wins\n`;
        plan.quick_wins.forEach((w, i) => { md += `${i+1}. ${typeof w === 'string' ? w : w.action}\n`; });
    }
    if (plan.medium_term?.length) {
        md += `\n### Medium-Term\n`;
        plan.medium_term.forEach((w, i) => { md += `${i+1}. ${typeof w === 'string' ? w : w.action}\n`; });
    }
    if (plan.strategic?.length) {
        md += `\n### Strategic\n`;
        plan.strategic.forEach((w, i) => { md += `${i+1}. ${typeof w === 'string' ? w : w.action}\n`; });
    }

    if (data.veto_result) {
        md += `\n## Trust Certification\n\n`;
        md += `**Status:** ${data.veto_result.certification_status || 'N/A'}\n`;
        if (data.veto_result.certification_reason) md += `${data.veto_result.certification_reason}\n`;
    }

    return md;
}

function downloadMarkdown(data) {
    const md = generateMarkdown(data);
    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `geo-report-${data.brand_name || 'analysis'}.md`;
    a.click();
    URL.revokeObjectURL(url);
}

// ── Router ──
window.addEventListener('hashchange', render);
window.addEventListener('load', render);
