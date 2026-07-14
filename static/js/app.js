let currentQuery = '';
let currentData = null;
let currentView = 'timeline';
let currentPaperData = {};

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('searchInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') searchPapers();
    });
    renderSearchHistory();
    initTheme();
});

// ============ 主题切换 ============

function initTheme() {
    const savedTheme = localStorage.getItem('paper_theme') || 'light';
    applyTheme(savedTheme);
}

function toggleTheme() {
    const currentTheme = document.body.getAttribute('data-theme') || 'light';
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    applyTheme(newTheme);
    localStorage.setItem('paper_theme', newTheme);
}

function applyTheme(theme) {
    document.body.setAttribute('data-theme', theme);
    const btn = document.getElementById('themeBtn');
    if (btn) {
        btn.textContent = theme === 'light' ? '🌙' : '☀️';
    }
}

// ============ 搜索历史 ============

function getSearchHistory() {
    try {
        return JSON.parse(localStorage.getItem('paper_search_history') || '[]');
    } catch (e) {
        return [];
    }
}

function saveSearchHistory(query) {
    let history = getSearchHistory();
    history = history.filter(q => q !== query);
    history.unshift(query);
    if (history.length > 10) history = history.slice(0, 10);
    localStorage.setItem('paper_search_history', JSON.stringify(history));
    renderSearchHistory();
}

function renderSearchHistory() {
    const history = getSearchHistory();
    const bar = document.getElementById('historyBar');
    const tags = document.getElementById('historyTags');
    if (!bar || !tags) return;

    if (history.length === 0) {
        bar.classList.add('hidden');
        return;
    }

    bar.classList.remove('hidden');
    tags.innerHTML = history.map(q => `
        <span class="history-tag" onclick="quickSearch('${q.replace(/'/g, "\\'")}')">
            ${q}
            <span class="history-tag-remove" onclick="event.stopPropagation(); removeSearchHistory('${q.replace(/'/g, "\\'")}')">✕</span>
        </span>
    `).join('');
}

function removeSearchHistory(query) {
    let history = getSearchHistory();
    history = history.filter(q => q !== query);
    localStorage.setItem('paper_search_history', JSON.stringify(history));
    renderSearchHistory();
}

function clearSearchHistory() {
    localStorage.removeItem('paper_search_history');
    renderSearchHistory();
}

// ============ 论文收藏 ============

function getFavorites() {
    try {
        return JSON.parse(localStorage.getItem('paper_favorites') || '{}');
    } catch (e) {
        return {};
    }
}

function saveFavorite(paper) {
    const favs = getFavorites();
    favs[paper.id] = {
        id: paper.id,
        title: paper.title,
        authors: paper.authors,
        summary: paper.summary,
        published: paper.published,
        categories: paper.categories,
        abs_url: paper.abs_url,
        pdf_url: paper.pdf_url,
        saved_at: Date.now()
    };
    localStorage.setItem('paper_favorites', JSON.stringify(favs));
    updateFavoriteButtons(paper.id, true);
    updateFavCount();
}

function removeFavorite(paperId) {
    const favs = getFavorites();
    delete favs[paperId];
    localStorage.setItem('paper_favorites', JSON.stringify(favs));
    updateFavoriteButtons(paperId, false);
    updateFavCount();
}

function updateFavCount() {
    const countEl = document.getElementById('favCount');
    if (countEl) {
        countEl.textContent = Object.keys(getFavorites()).length;
    }
}

function toggleFavorite(paperId) {
    const favs = getFavorites();
    if (favs[paperId]) {
        removeFavorite(paperId);
    } else {
        const paper = currentPaperData[paperId];
        if (paper) {
            saveFavorite(paper);
        }
    }
}

function isFavorite(paperId) {
    const favs = getFavorites();
    return !!favs[paperId];
}

function updateFavoriteButtons(paperId, isFav) {
    // 更新所有收藏按钮的状态
    document.querySelectorAll(`[data-fav-id="${paperId}"]`).forEach(btn => {
        btn.innerHTML = isFav ? '⭐' : '☆';
        btn.classList.toggle('favorited', isFav);
        btn.title = isFav ? '取消收藏' : '收藏';
    });
}

function showFavorites() {
    const favs = getFavorites();
    const papers = Object.values(favs).sort((a, b) => b.saved_at - a.saved_at);

    // 重置currentPaperData以便详情弹窗正常工作
    papers.forEach(p => { currentPaperData[p.id] = p; });

    const placeholder = document.getElementById('timelinePlaceholder');
    const content = document.getElementById('timelineContent');
    placeholder.classList.add('hidden');
    content.classList.remove('hidden');

    let html = `
        <div class="search-info-bar">
            <div class="search-info-left">
                <span class="search-info-query">⭐ 我的收藏</span>
            </div>
            <div class="search-info-stats">
                <span>📄 ${papers.length} 篇收藏</span>
            </div>
        </div>
        <div class="favorites-list">
    `;

    if (papers.length === 0) {
        html += `
            <div class="favorites-empty">
                <div style="font-size: 48px; margin-bottom: 16px;">📭</div>
                <div style="font-size: 16px; color: var(--text-secondary);">还没有收藏的论文</div>
                <div style="font-size: 13px; color: var(--text-tertiary); margin-top: 8px;">搜索论文后点击 ⭐ 按钮收藏</div>
            </div>
        `;
    } else {
        html += '<div class="papers-list">';
        papers.forEach((paper, idx) => {
            const authors = paper.authors ? paper.authors.join(', ') : 'Unknown';
            const date = paper.published ? new Date(paper.published).toLocaleDateString('zh-CN') : '';
            html += `
                <div class="paper-item is-breakthrough" onclick="showPaperDetail('${paper.id}')">
                    <div class="paper-index">⭐</div>
                    <div class="paper-info">
                        <div class="paper-title">${paper.title}</div>
                        <div class="paper-authors">${authors}</div>
                        <div class="paper-date">${date}</div>
                        <div class="paper-brief">${paper.summary || ''}</div>
                    </div>
                    <button class="paper-fav-btn favorited" data-fav-id="${paper.id}" onclick="event.stopPropagation(); toggleFavorite('${paper.id}')" title="取消收藏">⭐</button>
                </div>
            `;
        });
        html += '</div>';
    }

    html += '</div>';
    content.innerHTML = html;
}

// ============ 搜索 ============

function searchPapers() {
    const input = document.getElementById('searchInput');
    const query = input.value.trim();
    if (!query) {
        alert('请输入搜索关键词');
        return;
    }

    currentQuery = query;
    showLoading(true);
    updateLoadingSteps([
        '正在翻译关键词',
        '检索期刊与顶会论文',
        '检索预印本论文',
        '多源去重与排序',
        'AI生成影响力评分',
        '构建技术演进图谱'
    ]);

    const url = `/api/search?q=${encodeURIComponent(query)}&cache=false`;
    fetch(url, {
        method: 'GET',
        headers: {
            'Accept': 'application/json',
        },
        signal: AbortSignal.timeout(180000)
    })
        .then(response => {
            if (!response.ok) {
                return response.text().then(text => {
                    throw new Error(`HTTP ${response.status}: ${text}`);
                });
            }
            return response.json();
        })
        .then(data => {
            showLoading(false);
            if (data.error) {
                console.error('Search failed:', data.error);
                alert(`搜索失败: ${data.error}`);
                return;
            }
            currentData = data;
            if (data.papers) {
                data.papers.forEach(p => { currentPaperData[p.id] = p; });
            }
            saveSearchHistory(query);
            displayTimeline(data);
        })
        .catch(error => {
            showLoading(false);
            console.error('Search error:', error);
            if (error.name === 'TimeoutError') {
                alert('搜索超时，请稍后重试');
            } else if (error.name === 'AbortError') {
                alert('搜索已取消');
            } else {
                alert('搜索失败，请检查网络后重试\n\n错误详情: ' + error.message);
            }
        });
}

function quickSearch(query) {
    document.getElementById('searchInput').value = query;
    searchPapers();
}

// ============ 时间线渲染 ============

function displayTimeline(data) {
    const placeholder = document.getElementById('timelinePlaceholder');
    const content = document.getElementById('timelineContent');
    placeholder.classList.add('hidden');
    content.classList.remove('hidden');

    const timeline = data.timeline || {};
    const periods = timeline.periods || [];

    let html = '';

    // 搜索结果信息条
    const queryKeywords = data.query.split(/[,，]/).map(q => q.trim()).filter(Boolean);
    const overview = data.field_overview || {};
    html += `
        <div class="search-info-bar">
            <div class="search-info-left">
                <div class="search-keywords">
                    ${queryKeywords.map(q => `<span class="search-keyword-tag">${q}</span>`).join('')}
                </div>
                ${data.translated_query && data.translated_query !== data.query ?
                    `<span class="search-info-translated">→ ${data.translated_query}</span>` : ''}
            </div>
            <div class="search-info-stats">
                <span>📄 ${data.total} 篇论文</span>
                <span>📅 ${periods.length} 个时段</span>
                <span>🔬 ${overview.breakthrough_count || 0} 个突破</span>
                ${renderSourceStats(data.papers)}
            </div>
        </div>
    `;

    // 领域概览卡片
    if (overview && Object.keys(overview).length > 0) {
        html += `
            <div class="field-overview-card">
                <div class="overview-header">
                    <div class="overview-title">
                        <span class="overview-icon">📊</span>
                        <span>领域概览</span>
                    </div>
                    <div class="overview-subtitle">快速了解研究领域全貌</div>
                </div>
                <div class="overview-stats">
                    <div class="overview-stat-item">
                        <div class="overview-stat-value">${overview.year_range || 'N/A'}</div>
                        <div class="overview-stat-label">研究时间跨度</div>
                    </div>
                    <div class="overview-stat-item">
                        <div class="overview-stat-value">${overview.total_papers || 0}</div>
                        <div class="overview-stat-label">论文总数</div>
                    </div>
                    <div class="overview-stat-item">
                        <div class="overview-stat-value">${overview.active_periods || 0}</div>
                        <div class="overview-stat-label">活跃年份</div>
                    </div>
                    <div class="overview-stat-item">
                        <div class="overview-stat-value">${overview.avg_impact_factor || 'N/A'}</div>
                        <div class="overview-stat-label">平均影响力</div>
                    </div>
                    <div class="overview-stat-item">
                        <div class="overview-stat-value">${overview.breakthrough_count || 0}</div>
                        <div class="overview-stat-label">突破性工作</div>
                    </div>
                </div>
                ${overview.top_methods && overview.top_methods.length > 0 ? `
                    <div class="overview-methods">
                        <div class="overview-methods-title">🔧 核心方法</div>
                        <div class="overview-methods-tags">
                            ${overview.top_methods.map(m => `<span class="method-tag">${m}</span>`).join('')}
                        </div>
                    </div>
                ` : ''}
            </div>
        `;
    }

    // Top论文榜单
    const topPapers = data.top_papers || [];
    if (topPapers.length > 0) {
        html += `
            <div class="top-papers-section">
                <div class="top-papers-header">
                    <div class="top-papers-title">
                        <span class="top-papers-icon">🏆</span>
                        <span>领域 Top ${topPapers.length} 最具影响力论文</span>
                    </div>
                    <div class="top-papers-subtitle">按影响力因子 + 引用量 + 创新性综合排名</div>
                </div>
                <div class="top-papers-grid">
                    ${topPapers.map(paper => renderTopPaperCard(paper)).join('')}
                </div>
            </div>
        `;
    }

    // 新增功能面板（Tab切换）
    html += renderAnalysisPanels(data);

    // 筛选排序工具栏
    html += `
        <div class="filter-toolbar">
            <div class="filter-left">
                <button class="filter-btn" onclick="toggleFilter('breakthrough')" id="filterBT">
                    ⚡ 只看突破
                </button>
                <button class="filter-btn" onclick="toggleFilter('favorite')" id="filterFav">
                    ⭐ 只看收藏
                </button>
            </div>
            <div class="filter-right">
                <button class="filter-btn export-btn" onclick="exportPapers('bibtex')">
                    📑 BibTeX
                </button>
                <button class="filter-btn export-btn" onclick="exportPapers('csv')">
                    📊 CSV
                </button>
                <span class="filter-label">排序：</span>
                <select class="filter-select" onchange="sortPapers(this.value)">
                    <option value="impact_desc">影响力 ↓</option>
                    <option value="citations_desc">引用量 ↓</option>
                    <option value="novelty_desc">创新性 ↓</option>
                    <option value="date_desc">时间 ↓</option>
                    <option value="date_asc">时间 ↑</option>
                    <option value="title">标题 A-Z</option>
                </select>
            </div>
        </div>
    `;

    // 时间线轨道
    html += '<div class="timeline-track">';
    html += '<div class="timeline-inner">';
    html += '<div class="timeline-line"></div>';

    periods.forEach((period, idx) => {
        const hasBreakthrough = period.breakthroughs && period.breakthroughs.length > 0;
        const breakthroughIds = new Set(
            (period.breakthroughs || []).map(b => b.paper_id).filter(Boolean)
        );

        html += `
            <div class="timeline-period ${hasBreakthrough ? 'has-breakthrough' : ''}" id="period-${idx}">
                <div class="timeline-node" onclick="scrollToPeriod(${idx})" onmouseenter="showPeriodTooltip(event, ${idx})" onmouseleave="hidePeriodTooltip()">
                    <div class="timeline-period-label">${period.label}</div>
                    <div class="period-tooltip">
                        <div class="period-tooltip-title">${period.label}</div>
                        <div class="period-tooltip-stats">
                            <span>📄 ${period.paper_count} 篇论文</span>
                            ${hasBreakthrough ? `<span>⚡ ${period.breakthroughs.length} 个突破</span>` : ''}
                        </div>
                        <div class="period-tooltip-hint">点击滚动到此处</div>
                    </div>
                </div>
                <div class="period-card">
                    <div class="period-header" onclick="togglePeriod(${idx})">
                        <div class="period-header-left">
                            <div class="period-meta">
                                ${period.key_methods && period.key_methods.length > 0 ?
                                    period.key_methods.slice(0, 3).map(m => `<span class="period-meta-item">🏷️ ${m}</span>`).join('') : ''}
                            </div>
                            <div class="period-summary">${period.ai_summary || ''}</div>
                        </div>
                        <div class="period-header-right">
                            <span class="period-paper-count">${period.paper_count} 篇</span>
                            ${hasBreakthrough ? `<span class="period-badge breakthrough">⚡ ${period.breakthroughs.length}</span>` : ''}
                            <svg class="period-expand-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="6 9 12 15 18 9"/>
                            </svg>
                        </div>
                    </div>
        `;

        // 展开区域（突破性方法 + 趋势标签 + 论文列表）
        html += `<div class="period-expand-content">`;

        // 突破性方法区域
        if (hasBreakthrough) {
            html += `
                <div class="breakthrough-section">
                    <div class="breakthrough-title">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
                        突破性方法与关键创新
                    </div>
            `;
            period.breakthroughs.forEach(bt => {
                const impactClass = `impact-${bt.impact || 'medium'}`;
                const impactLabel = {high: '高影响', medium: '中影响', low: '低影响'}[bt.impact] || '中影响';
                html += `
                    <div class="breakthrough-item" onclick="event.stopPropagation(); showPaperDetail('${bt.paper_id}')">
                        <div class="breakthrough-icon">⚡</div>
                        <div class="breakthrough-content">
                            <div class="breakthrough-method">${bt.method_name || bt.paper_title || '未知方法'}</div>
                            <div class="breakthrough-desc">${bt.description || ''}</div>
                            <span class="breakthrough-impact ${impactClass}">${impactLabel}</span>
                        </div>
                    </div>
                `;
            });
            html += `</div>`;
        }

        // 趋势标签
        if (period.trends && period.trends.length > 0) {
            html += `<div class="period-trends">`;
            period.trends.forEach(trend => {
                html += `<span class="trend-tag hot">📈 ${trend}</span>`;
            });
            if (period.hot_topics) {
                period.hot_topics.forEach(topic => {
                    html += `<span class="trend-tag">🔥 ${topic}</span>`;
                });
            }
            html += `</div>`;
        }

        // 论文列表（精选论文）
        html += `<div class="period-papers"><div class="papers-list">`;
        const topPapers = period.top_papers || [];
        const morePapers = period.more_papers || [];
        const allPeriodPapers = [...topPapers, ...morePapers];

        topPapers.forEach((paper, pIdx) => {
            const isBT = breakthroughIds.has(paper.id) || paper.is_breakthrough;
            const authors = paper.authors ? paper.authors.join(', ') : 'Unknown';
            const date = paper.published ? new Date(paper.published).toLocaleDateString('zh-CN') : '';
            const impact = paper.impact_factor || 3.0;
            const citations = paper.estimated_citations || 0;
            const novelty = paper.novelty || 50;
            const typeBadge = renderPaperTypeBadge(paper.paper_type);
            const venueText = paper.venue ? `<span class="paper-venue" title="${paper.venue}">📍${paper.venue}</span>` : '';
            const citationSource = paper.citation_source === 'semantic_scholar' ? '<span class="citation-verified" title="真实引用量">✓</span>' : '';
            html += `
                <div class="paper-item ${isBT ? 'is-breakthrough' : ''}" onclick="showPaperDetail('${paper.id}')" data-impact="${impact}" data-citations="${citations}" data-novelty="${novelty}" data-date="${paper.published}" data-title="${paper.title}">
                    <div class="paper-index">${isBT ? '⚡' : pIdx + 1}</div>
                    <div class="paper-info">
                        <div class="paper-title">${typeBadge}${paper.title}</div>
                        <div class="paper-authors">${authors}</div>
                        <div class="paper-date">${date} ${venueText}</div>
                        <div class="paper-brief">${paper.summary || ''}</div>
                        <div class="paper-metrics">
                            <span class="metric-item metric-impact" title="影响力因子">📊 ${impact}</span>
                            <span class="metric-item metric-citations" title="引用量">📝 ${citations}${citationSource}</span>
                            <span class="metric-item metric-novelty" title="创新性评分">💡 ${novelty}</span>
                        </div>
                    </div>
                    <button class="paper-fav-btn ${isFavorite(paper.id) ? 'favorited' : ''}" data-fav-id="${paper.id}" onclick="event.stopPropagation(); toggleFavorite('${paper.id}')" title="${isFavorite(paper.id) ? '取消收藏' : '收藏'}">${isFavorite(paper.id) ? '⭐' : '☆'}</button>
                </div>
            `;
        });
        html += `</div>`;

        // 加载更多按钮
        if (morePapers.length > 0) {
            html += `
                <div class="load-more-container">
                    <button class="load-more-btn" onclick="event.stopPropagation(); toggleMorePapers(${idx})" id="more-btn-${idx}">
                        <span class="load-more-text">📚 查看更多 ${morePapers.length} 篇论文</span>
                        <svg class="load-more-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="6 9 12 15 18 9"/>
                        </svg>
                    </button>
                </div>
                <div class="more-papers-list" id="more-papers-${idx}" style="display:none;">
            `;
            morePapers.forEach((paper, pIdx) => {
                const isBT = breakthroughIds.has(paper.id) || paper.is_breakthrough;
                const authors = paper.authors ? paper.authors.join(', ') : 'Unknown';
                const date = paper.published ? new Date(paper.published).toLocaleDateString('zh-CN') : '';
                const impact = paper.impact_factor || 3.0;
                const citations = paper.estimated_citations || 0;
                const novelty = paper.novelty || 50;
                const typeBadge = renderPaperTypeBadge(paper.paper_type);
                const venueText = paper.venue ? `<span class="paper-venue" title="${paper.venue}">📍${paper.venue}</span>` : '';
                const citationSource = paper.citation_source === 'semantic_scholar' ? '<span class="citation-verified" title="真实引用量">✓</span>' : '';
                html += `
                    <div class="paper-item paper-item-more ${isBT ? 'is-breakthrough' : ''}" onclick="showPaperDetail('${paper.id}')" data-impact="${impact}" data-citations="${citations}" data-novelty="${novelty}" data-date="${paper.published}" data-title="${paper.title}">
                        <div class="paper-index">${isBT ? '⚡' : topPapers.length + pIdx + 1}</div>
                        <div class="paper-info">
                            <div class="paper-title">${typeBadge}${paper.title}</div>
                            <div class="paper-authors">${authors}</div>
                            <div class="paper-date">${date} ${venueText}</div>
                            <div class="paper-brief">${paper.summary || ''}</div>
                            <div class="paper-metrics">
                                <span class="metric-item metric-impact" title="影响力因子">📊 ${impact}</span>
                                <span class="metric-item metric-citations" title="引用量">📝 ${citations}${citationSource}</span>
                                <span class="metric-item metric-novelty" title="创新性评分">💡 ${novelty}</span>
                            </div>
                        </div>
                        <button class="paper-fav-btn ${isFavorite(paper.id) ? 'favorited' : ''}" data-fav-id="${paper.id}" onclick="event.stopPropagation(); toggleFavorite('${paper.id}')" title="${isFavorite(paper.id) ? '取消收藏' : '收藏'}">${isFavorite(paper.id) ? '⭐' : '☆'}</button>
                    </div>
                `;
            });
            html += `</div>`;
        }
        html += `</div>`;

        html += `</div></div></div>`;
    });

    html += '</div></div>';  // 关闭 inner 和 track

    content.innerHTML = html;

    // 初始化滚动提示
    initScrollHint();
}

function initScrollHint() {
    const track = document.querySelector('.timeline-track');
    if (!track) return;

    // 检查是否需要显示滚动提示
    const checkScrollHint = () => {
        const rightHint = document.querySelector('.scroll-hint-right');
        if (!rightHint) return;

        const isAtEnd = track.scrollLeft + track.clientWidth >= track.scrollWidth - 10;
        rightHint.style.opacity = isAtEnd ? '0' : '1';
        rightHint.style.pointerEvents = isAtEnd ? 'none' : 'auto';
    };

    // 检查是否溢出
    setTimeout(() => {
        if (track.scrollWidth > track.clientWidth + 10) {
            const hint = document.createElement('div');
            hint.className = 'scroll-hint-right';
            hint.innerHTML = `
                <div class="scroll-hint-arrow">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="9 18 15 12 9 6"/>
                    </svg>
                </div>
            `;
            hint.addEventListener('click', () => {
                track.scrollBy({ left: 400, behavior: 'smooth' });
            });
            track.parentElement.style.position = 'relative';
            track.parentElement.appendChild(hint);
            checkScrollHint();
        }
    }, 100);

    track.addEventListener('scroll', checkScrollHint);
}

// ============ 筛选与排序 ============

let currentFilter = { breakthrough: false, favorite: false };
let currentSort = 'date_desc';

function toggleFilter(type) {
    currentFilter[type] = !currentFilter[type];

    const btn = document.getElementById(type === 'breakthrough' ? 'filterBT' : 'filterFav');
    if (btn) {
        btn.classList.toggle('active', currentFilter[type]);
    }

    applyFilterSort();
}

function sortPapers(sortType) {
    currentSort = sortType;
    applyFilterSort();
}

function applyFilterSort() {
    if (!currentData || !currentData.papers) return;

    let papers = [...currentData.papers];

    // 筛选
    if (currentFilter.breakthrough) {
        const btIds = new Set();
        (currentData.timeline?.periods || []).forEach(p => {
            (p.breakthroughs || []).forEach(b => {
                if (b.paper_id) btIds.add(b.paper_id);
            });
        });
        papers = papers.filter(p => btIds.has(p.id));
    }
    if (currentFilter.favorite) {
        const favs = getFavorites();
        papers = papers.filter(p => favs[p.id]);
    }

    // 排序
    switch (currentSort) {
        case 'impact_desc':
            papers.sort((a, b) => (b.impact_factor || 0) - (a.impact_factor || 0));
            break;
        case 'citations_desc':
            papers.sort((a, b) => (b.estimated_citations || 0) - (a.estimated_citations || 0));
            break;
        case 'novelty_desc':
            papers.sort((a, b) => (b.novelty || 0) - (a.novelty || 0));
            break;
        case 'date_desc':
            papers.sort((a, b) => new Date(b.published) - new Date(a.published));
            break;
        case 'date_asc':
            papers.sort((a, b) => new Date(a.published) - new Date(b.published));
            break;
        case 'title':
            papers.sort((a, b) => a.title.localeCompare(b.title));
            break;
    }

    // 重建时间线数据
    const timeline = rebuildTimeline(papers, currentData.timeline);
    const newData = { ...currentData, papers, timeline, total: papers.length };

    // 重新渲染（只重渲时间线部分，保留顶部筛选栏）
    const track = document.querySelector('.timeline-track');
    if (track) {
        const trackParent = track.parentElement;
        track.remove();

        const newHtml = buildTimelineTrack(newData);
        trackParent.insertAdjacentHTML('beforeend', newHtml);
    }
}

function rebuildTimeline(papers, originalTimeline) {
    const periodMap = {};
    (originalTimeline?.periods || []).forEach((p, i) => {
        periodMap[p.label] = { ...p, _order: i, _papers: [] };
    });

    papers.forEach(paper => {
        const year = new Date(paper.published).getFullYear();
        const label = `${year}年`;
        if (periodMap[label]) {
            periodMap[label]._papers.push(paper);
        }
    });

    const periods = Object.values(periodMap)
        .filter(p => p._papers.length > 0)
        .sort((a, b) => a._order - b._order)
        .map(p => {
            const sorted = [...p._papers].sort((a, b) => {
                const aImpact = a.impact_factor || 0;
                const bImpact = b.impact_factor || 0;
                if (bImpact !== aImpact) return bImpact - aImpact;
                const aCit = a.estimated_citations || 0;
                const bCit = b.estimated_citations || 0;
                if (bCit !== aCit) return bCit - aCit;
                return (b.novelty || 0) - (a.novelty || 0);
            });

            const top_n = 3;
            const topPapers = sorted.slice(0, top_n);
            const morePapers = sorted.slice(top_n);

            return {
                ...p,
                paper_count: sorted.length,
                top_papers: topPapers.map(p2 => ({
                    id: p2.id,
                    title: p2.title,
                    authors: p2.authors || [],
                    published: p2.published || '',
                    summary: (p2.summary || '').slice(0, 200),
                    novelty: p2.novelty || 50,
                    estimated_citations: p2.estimated_citations || 20,
                    impact_factor: p2.impact_factor || 3.0,
                    is_breakthrough: p2.is_breakthrough || false
                })),
                more_papers: morePapers.map(p2 => ({
                    id: p2.id,
                    title: p2.title,
                    authors: p2.authors || [],
                    published: p2.published || '',
                    summary: (p2.summary || '').slice(0, 200),
                    novelty: p2.novelty || 50,
                    estimated_citations: p2.estimated_citations || 20,
                    impact_factor: p2.impact_factor || 3.0,
                    is_breakthrough: p2.is_breakthrough || false
                })),
                paper_ids: sorted.map(p2 => p2.id)
            };
        });

    return { ...originalTimeline, periods };
}

// ============ 论文导出 ============

function exportPapers(format) {
    if (!currentData || !currentData.papers) {
        alert('没有可导出的论文');
        return;
    }

    // 获取当前筛选后的论文
    let papers = [...currentData.papers];
    if (currentFilter.breakthrough) {
        const btIds = new Set();
        (currentData.timeline?.periods || []).forEach(p => {
            (p.breakthroughs || []).forEach(b => {
                if (b.paper_id) btIds.add(b.paper_id);
            });
        });
        papers = papers.filter(p => btIds.has(p.id));
    }
    if (currentFilter.favorite) {
        const favs = getFavorites();
        papers = papers.filter(p => favs[p.id]);
    }

    if (papers.length === 0) {
        alert('没有可导出的论文');
        return;
    }

    let content = '';
    let filename = '';
    let mimeType = '';

    if (format === 'bibtex') {
        content = papers.map(p => {
            const authors = (p.authors || []).map(a => a.split(', ').reverse().join(' ')).join(' and ');
            const year = p.published ? new Date(p.published).getFullYear() : '2024';
            const firstAuthor = (p.authors || ['Unknown'])[0].split(', ')[0];
            const key = `${firstAuthor}${year}${p.title.split(' ')[0].toLowerCase()}`;
            return `@article{${key},
  title={${p.title}},
  author={${authors}},
  journal={arXiv preprint arXiv:${p.id}},
  year={${year}},
  url={${p.abs_url || p.pdf_url || ''}}
}`;
        }).join('\n\n');
        filename = `papers_${currentQuery || 'export'}.bib`;
        mimeType = 'text/x-bibtex';
    } else if (format === 'csv') {
        const headers = ['ID', '标题', '作者', '日期', '摘要', '分类', '链接'];
        const rows = papers.map(p => [
            p.id,
            `"${(p.title || '').replace(/"/g, '""')}"`,
            `"${(p.authors || []).join('; ').replace(/"/g, '""')}"`,
            p.published || '',
            `"${(p.summary || '').replace(/"/g, '""')}"`,
            `"${(p.categories || []).join('; ').replace(/"/g, '""')}"`,
            p.abs_url || p.pdf_url || ''
        ]);
        content = '\uFEFF' + [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
        filename = `papers_${currentQuery || 'export'}.csv`;
        mimeType = 'text/csv;charset=utf-8';
    }

    // 下载文件
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

function renderAnalysisPanels(data) {
    return `
        <div class="analysis-panels">
            <div class="analysis-tabs">
                <button class="analysis-tab active" onclick="switchAnalysisTab('evolution')" id="tab-evolution">
                    📈 技术演进
                </button>
                <button class="analysis-tab" onclick="switchAnalysisTab('researchers')" id="tab-researchers">
                    👥 核心研究者
                </button>
                <button class="analysis-tab" onclick="switchAnalysisTab('reading')" id="tab-reading">
                    📚 入门阅读路径
                </button>
                <button class="analysis-tab" onclick="switchAnalysisTab('gaps')" id="tab-gaps">
                    🔬 研究空白
                </button>
            </div>
            <div class="analysis-content">
                <div class="analysis-panel active" id="panel-evolution">
                    ${renderTechEvolution(data.tech_evolution || {})}
                </div>
                <div class="analysis-panel" id="panel-researchers">
                    ${renderResearcherGraph(data.researcher_graph || {})}
                </div>
                <div class="analysis-panel" id="panel-reading">
                    ${renderReadingPath(data.reading_path || {})}
                </div>
                <div class="analysis-panel" id="panel-gaps">
                    ${renderResearchGaps(data.research_gaps || {})}
                </div>
            </div>
        </div>
    `;
}

function switchAnalysisTab(tab) {
    document.querySelectorAll('.analysis-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.analysis-panel').forEach(p => p.classList.remove('active'));
    document.getElementById('tab-' + tab).classList.add('active');
    document.getElementById('panel-' + tab).classList.add('active');
}

function renderTechEvolution(data) {
    const milestones = data.milestones || [];
    if (milestones.length === 0) return '<div class="empty-panel">暂无技术演进数据</div>';

    let html = '<div class="evolution-timeline">';
    const years = [...new Set(milestones.map(m => m.first_seen))].sort();

    years.forEach(year => {
        const yearMilestones = milestones.filter(m => m.first_seen === year);
        html += `
            <div class="evolution-year">
                <div class="evolution-year-label">${year}</div>
                <div class="evolution-milestones">
                    ${yearMilestones.map(m => `
                        <div class="evolution-milestone ${m.type}">
                            <div class="milestone-method">${m.method}</div>
                            <div class="milestone-meta">
                                <span class="milestone-count">${m.count}篇</span>
                                <span class="milestone-impact">⭐${m.avg_impact}</span>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    });

    html += '</div>';
    return html;
}

function renderResearcherGraph(data) {
    const researchers = data.researchers || [];
    if (researchers.length === 0) return '<div class="empty-panel">暂无研究者数据</div>';

    return `
        <div class="researcher-grid">
            ${researchers.slice(0, 15).map(r => `
                <div class="researcher-card ${r.tier}">
                    <div class="researcher-name">${r.name}</div>
                    <div class="researcher-stats">
                        <span class="researcher-stat">📄 ${r.paper_count}</span>
                        <span class="researcher-stat">⭐ ${r.avg_impact}</span>
                        <span class="researcher-stat">📝 ${r.total_citations}</span>
                    </div>
                    ${r.breakthroughs > 0 ? `<div class="researcher-badge">⚡ ${r.breakthroughs}个突破</div>` : ''}
                </div>
            `).join('')}
        </div>
    `;
}

function renderReadingPath(data) {
    const path = data.path || [];
    if (path.length === 0) return '<div class="empty-panel">暂无阅读路径数据</div>';

    return `
        <div class="reading-path">
            ${path.map(stage => `
                <div class="reading-stage">
                    <div class="reading-stage-header">
                        <div class="reading-stage-order">${stage.order}</div>
                        <div class="reading-stage-info">
                            <div class="reading-stage-title">${stage.stage}</div>
                            <div class="reading-stage-desc">${stage.description}</div>
                        </div>
                    </div>
                    <div class="reading-stage-papers">
                        ${stage.papers.map(p => `
                            <div class="reading-paper" onclick="showPaperDetail('${p.id}')">
                                <div class="reading-paper-title">${p.title}</div>
                                <div class="reading-paper-meta">
                                    <span>${p.year}</span>
                                    <span>⭐ ${p.impact}</span>
                                    <span>💡 ${p.novelty}</span>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

function renderResearchGaps(data) {
    const gaps = data.gaps || [];
    if (gaps.length === 0) return '<div class="empty-panel">暂无研究空白数据</div>';

    return `
        <div class="research-gaps">
            <div class="gaps-header">
                <div class="gaps-title">🔍 潜在研究方向</div>
                <div class="gaps-subtitle">基于方法共现分析，发现未被充分探索的交叉领域</div>
            </div>
            <div class="gaps-list">
                ${gaps.map(g => `
                    <div class="gap-item ${g.potential}">
                        <div class="gap-type">${g.type === 'cross_method' ? '🔀 方法交叉' : '🔄 经典复兴'}</div>
                        <div class="gap-description">${g.description}</div>
                        <div class="gap-methods">${g.methods.join(' + ')}</div>
                    </div>
                `).join('')}
            </div>
            <div class="gaps-suggestions">
                <div class="suggestions-title">💡 研究建议</div>
                <ul class="suggestions-list">
                    ${(data.suggestions || []).map(s => `<li>${s}</li>`).join('')}
                </ul>
            </div>
        </div>
    `;
}

function renderTopPaperCard(paper) {
    const authors = paper.authors ? paper.authors.join(', ') : 'Unknown';
    const date = paper.published ? new Date(paper.published).toLocaleDateString('zh-CN') : '';
    const year = paper.year || (paper.published ? new Date(paper.published).getFullYear() : '');
    const impact = paper.impact_factor || 3.0;
    const citations = paper.estimated_citations || 0;
    const novelty = paper.novelty || 50;
    const isClassic = paper.is_classic;
    const isBT = paper.is_breakthrough;
    const typeBadge = renderPaperTypeBadge(paper.paper_type);
    const venueText = paper.venue ? `<span class="top-paper-venue" title="${paper.venue}">📍${paper.venue}</span>` : '';
    const citationSource = paper.citation_source === 'semantic_scholar' ? '<span class="citation-verified" title="真实引用量">✓</span>' : '';

    const rankColors = ['#fbbf24', '#9ca3af', '#d97706', '#3b82f6', '#3b82f6', '#3b82f6', '#6b7280', '#6b7280', '#6b7280', '#6b7280'];
    const rankColor = rankColors[paper.rank - 1] || '#6b7280';
    const rankBadge = paper.rank <= 3 ? ['🥇', '🥈', '🥉'][paper.rank - 1] : `#${paper.rank}`;

    return `
        <div class="top-paper-card ${isClassic ? 'is-classic' : ''} ${isBT ? 'is-breakthrough' : ''}" onclick="showPaperDetail('${paper.id}')">
            <div class="top-paper-rank" style="background: ${rankColor};">
                <span>${rankBadge}</span>
            </div>
            <div class="top-paper-body">
                <div class="top-paper-main">
                    <div class="top-paper-title">
                        ${isClassic ? '<span class="classic-badge" title="经典必读">🏆</span>' : ''}
                        ${isBT ? '<span class="bt-badge" title="突破性工作">⚡</span>' : ''}
                        ${typeBadge}
                        ${paper.title}
                    </div>
                    <div class="top-paper-authors">${authors}</div>
                    <div class="top-paper-meta-row">
                        <span class="top-paper-year">${year}</span>
                        ${venueText}
                        <div class="top-paper-metrics">
                            <span class="metric-item metric-impact">📊${impact}</span>
                            <span class="metric-item metric-citations">📝${citations}${citationSource}</span>
                            <span class="metric-item metric-novelty">💡${novelty}</span>
                        </div>
                    </div>
                </div>
            </div>
            <button class="paper-fav-btn ${isFavorite(paper.id) ? 'favorited' : ''}" onclick="event.stopPropagation(); toggleFavorite('${paper.id}')" title="${isFavorite(paper.id) ? '取消收藏' : '收藏'}">${isFavorite(paper.id) ? '⭐' : '☆'}</button>
        </div>
    `;
}

// 论文类型标签：期刊/会议/综述/预印本
function renderPaperTypeBadge(paperType) {
    const typeMap = {
        'journal': { icon: '📑', label: '期刊', cls: 'type-journal' },
        'conference': { icon: '🎤', label: '会议', cls: 'type-conference' },
        'review': { icon: '📚', label: '综述', cls: 'type-review' },
        'preprint': { icon: '📄', label: '预印本', cls: 'type-preprint' }
    };
    const t = typeMap[paperType] || typeMap['preprint'];
    return `<span class="paper-type-badge ${t.cls}" title="${t.label}">${t.icon}${t.label}</span>`;
}

// 来源统计：期刊/会议/综述/预印本数量
function renderSourceStats(papers) {
    if (!papers || !papers.length) return '';
    const counts = { journal: 0, conference: 0, review: 0, preprint: 0 };
    papers.forEach(p => {
        const t = p.paper_type || 'preprint';
        counts[t] = (counts[t] || 0) + 1;
    });
    const parts = [];
    if (counts.journal) parts.push(`<span title="期刊论文">📑 ${counts.journal}</span>`);
    if (counts.conference) parts.push(`<span title="会议论文">🎤 ${counts.conference}</span>`);
    if (counts.review) parts.push(`<span title="综述论文">📚 ${counts.review}</span>`);
    if (counts.preprint) parts.push(`<span title="预印本">📄 ${counts.preprint}</span>`);
    return parts.join('');
}

function buildTimelineTrack(data) {
    const periods = data.timeline?.periods || [];
    let html = '<div class="timeline-track">';
    html += '<div class="timeline-inner">';
    html += '<div class="timeline-line"></div>';

    periods.forEach((period, idx) => {
        const hasBreakthrough = period.breakthroughs && period.breakthroughs.length > 0;
        const breakthroughIds = new Set(
            (period.breakthroughs || []).map(b => b.paper_id).filter(Boolean)
        );

        html += `
            <div class="timeline-period ${hasBreakthrough ? 'has-breakthrough' : ''}" id="period-${idx}">
                <div class="timeline-node" onclick="scrollToPeriod(${idx})" onmouseenter="showPeriodTooltip(event, ${idx})" onmouseleave="hidePeriodTooltip()">
                    <div class="timeline-period-label">${period.label}</div>
                    <div class="period-tooltip">
                        <div class="period-tooltip-title">${period.label}</div>
                        <div class="period-tooltip-stats">
                            <span>📄 ${period.paper_count} 篇论文</span>
                            ${hasBreakthrough ? `<span>⚡ ${period.breakthroughs.length} 个突破</span>` : ''}
                        </div>
                        <div class="period-tooltip-hint">点击滚动到此处</div>
                    </div>
                </div>
                <div class="period-card">
                    <div class="period-header" onclick="togglePeriod(${idx})">
                        <div class="period-header-left">
                            <div class="period-meta">
                                ${period.key_methods && period.key_methods.length > 0 ?
                                    period.key_methods.slice(0, 3).map(m => `<span class="period-meta-item">🏷️ ${m}</span>`).join('') : ''}
                            </div>
                            <div class="period-summary">${period.ai_summary || ''}</div>
                        </div>
                        <div class="period-header-right">
                            <span class="period-paper-count">${period.paper_count} 篇</span>
                            ${hasBreakthrough ? `<span class="period-badge breakthrough">⚡ ${period.breakthroughs.length}</span>` : ''}
                            <svg class="period-expand-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="6 9 12 15 18 9"/>
                            </svg>
                        </div>
                    </div>
        `;

        // 展开区域
        html += `<div class="period-expand-content">`;

        if (hasBreakthrough) {
            html += `
                <div class="breakthrough-section">
                    <div class="breakthrough-title">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
                        突破性方法与关键创新
                    </div>
            `;
            period.breakthroughs.forEach(bt => {
                const impactClass = `impact-${bt.impact || 'medium'}`;
                const impactLabel = {high: '高影响', medium: '中影响', low: '低影响'}[bt.impact] || '中影响';
                html += `
                    <div class="breakthrough-item" onclick="event.stopPropagation(); showPaperDetail('${bt.paper_id}')">
                        <div class="breakthrough-icon">⚡</div>
                        <div class="breakthrough-content">
                            <div class="breakthrough-method">${bt.method_name || bt.paper_title || '未知方法'}</div>
                            <div class="breakthrough-desc">${bt.description || ''}</div>
                            <span class="breakthrough-impact ${impactClass}">${impactLabel}</span>
                        </div>
                    </div>
                `;
            });
            html += `</div>`;
        }

        if (period.trends && period.trends.length > 0) {
            html += `<div class="period-trends">`;
            period.trends.forEach(trend => {
                html += `<span class="trend-tag hot">📈 ${trend}</span>`;
            });
            if (period.hot_topics) {
                period.hot_topics.forEach(topic => {
                    html += `<span class="trend-tag">🔥 ${topic}</span>`;
                });
            }
            html += `</div>`;
        }

        html += `<div class="period-papers"><div class="papers-list">`;
        period.papers.forEach((paper, pIdx) => {
            const isBT = breakthroughIds.has(paper.id);
            const authors = paper.authors ? paper.authors.join(', ') : 'Unknown';
            const date = paper.published ? new Date(paper.published).toLocaleDateString('zh-CN') : '';
            html += `
                <div class="paper-item ${isBT ? 'is-breakthrough' : ''}" onclick="showPaperDetail('${paper.id}')">
                    <div class="paper-index">${isBT ? '⚡' : pIdx + 1}</div>
                    <div class="paper-info">
                        <div class="paper-title">${paper.title}</div>
                        <div class="paper-authors">${authors}</div>
                        <div class="paper-date">${date}</div>
                        <div class="paper-brief">${paper.summary || ''}</div>
                    </div>
                    <button class="paper-fav-btn ${isFavorite(paper.id) ? 'favorited' : ''}" data-fav-id="${paper.id}" onclick="event.stopPropagation(); toggleFavorite('${paper.id}')" title="${isFavorite(paper.id) ? '取消收藏' : '收藏'}">${isFavorite(paper.id) ? '⭐' : '☆'}</button>
                </div>
            `;
        });
        html += `</div></div>`;

        html += `</div></div></div>`;
    });

    html += '</div></div>';  // 关闭 inner 和 track
    return html;
}

function togglePeriod(idx) {
    const period = document.getElementById(`period-${idx}`);
    period.classList.toggle('expanded');
}

function toggleMorePapers(idx) {
    const moreList = document.getElementById(`more-papers-${idx}`);
    const btn = document.getElementById(`more-btn-${idx}`);
    if (!moreList || !btn) return;

    if (moreList.style.display === 'none') {
        moreList.style.display = 'block';
        btn.querySelector('.load-more-text').textContent = '收起更多论文';
        btn.querySelector('.load-more-icon').style.transform = 'rotate(180deg)';
    } else {
        moreList.style.display = 'none';
        btn.querySelector('.load-more-text').textContent = `📚 查看更多 ${moreList.children.length} 篇论文`;
        btn.querySelector('.load-more-icon').style.transform = 'rotate(0deg)';
    }
}

// 时间线节点交互
function scrollToPeriod(idx) {
    const period = document.getElementById(`period-${idx}`);
    const track = document.querySelector('.timeline-track');
    if (!period || !track) return;

    const trackRect = track.getBoundingClientRect();
    const periodRect = period.getBoundingClientRect();
    const scrollLeft = track.scrollLeft + periodRect.left - trackRect.left - (trackRect.width - periodRect.width) / 2;

    track.scrollTo({ left: scrollLeft, behavior: 'smooth' });
}

function showPeriodTooltip(event, idx) {
    // tooltip已经在HTML中，通过CSS控制显示
}

function hidePeriodTooltip() {
    // tooltip通过CSS控制显示
}

// ============ 视图切换 ============

function switchView(view) {
    currentView = view;
    document.getElementById('timelineBtn').classList.toggle('active', view === 'timeline');
    document.getElementById('graphBtn').classList.toggle('active', view === 'graph');
    document.getElementById('timelineView').classList.toggle('hidden', view !== 'timeline');
    document.getElementById('graphView').classList.toggle('hidden', view !== 'graph');

    if (view === 'graph' && currentData && currentData.graph) {
        setTimeout(() => {
            initGraph();
            renderGraph(currentData.graph);
        }, 100);
    }
}

// ============ 论文详情弹窗 ============

function showPaperDetail(paperId) {
    const paper = currentPaperData[paperId];
    if (!paper) {
        console.error('Paper not found:', paperId);
        return;
    }

    const modal = document.getElementById('paperModal');
    const body = document.getElementById('modalBody');

    const authors = paper.authors ? paper.authors.join(', ') : 'Unknown';
    const date = paper.published ? new Date(paper.published).toLocaleDateString('zh-CN') : '';
    const categories = paper.categories || [];

    body.innerHTML = `
        <div class="detail-title">${paper.title}</div>
        <div class="detail-meta">
            <span class="detail-meta-item">📅 ${date}</span>
            ${renderPaperTypeBadge(paper.paper_type)}
            ${paper.venue ? `<span class="detail-meta-item">📍 ${paper.venue}</span>` : ''}
            ${categories.map(c => `<span class="detail-meta-item">🏷️ ${c}</span>`).join('')}
            ${paper.doi ? `<span class="detail-meta-item">🔗 DOI: ${paper.doi}</span>` : ''}
            ${paper.estimated_citations ? `<span class="detail-meta-item">📝 引用: ${paper.estimated_citations}${paper.citation_source === 'semantic_scholar' ? ' ✓' : ''}</span>` : ''}
        </div>
        <div class="detail-authors">👥 ${authors}</div>

        <div class="detail-section">
            <div class="detail-section-title">📝 论文摘要</div>
            <div class="detail-abstract">${paper.summary || '暂无摘要'}</div>
        </div>

        <div id="modalAiSection" class="detail-section">
            <div class="detail-section-title">🤖 AI 智能分析</div>
            <div id="modalAiContent" style="text-align: center; padding: 30px;">
                <div class="loading-spinner" style="width: 32px; height: 32px; border-width: 3px; margin: 0 auto 12px;"></div>
                <div style="font-size: 14px; color: var(--text-secondary);">DeepSeek 正在分析论文...</div>
            </div>
        </div>

        <div id="modalDesignSection" class="detail-section hidden">
            <div class="detail-section-title">📋 复现设计文档</div>
            <div id="modalDesignContent" style="text-align: center; padding: 30px;">
                <div class="loading-spinner" style="width: 32px; height: 32px; border-width: 3px; margin: 0 auto 12px;"></div>
                <div style="font-size: 14px; color: var(--text-secondary);">正在生成设计文档...</div>
            </div>
        </div>

        <div class="detail-actions">
            <button class="detail-btn ${isFavorite(paperId) ? 'btn-warning' : 'btn-outline'}" data-fav-id="${paperId}" onclick="toggleFavorite('${paperId}'); this.innerHTML = isFavorite('${paperId}') ? '⭐ 已收藏' : '☆ 收藏'; this.classList.toggle('btn-warning', isFavorite('${paperId}')); this.classList.toggle('btn-outline', !isFavorite('${paperId}'));">
                ${isFavorite(paperId) ? '⭐ 已收藏' : '☆ 收藏'}
            </button>
            <button class="detail-btn btn-primary" onclick="generatePaperSummary('${paperId}')">
                🤖 生成AI摘要
            </button>
            <button class="detail-btn btn-success" onclick="generatePaperDesign('${paperId}')">
                📋 生成设计文档
            </button>
            <button class="detail-btn btn-warning" onclick="downloadPaper('${paperId}')">
                📥 下载PDF
            </button>
            <button class="detail-btn btn-outline" onclick="window.open('${paper.abs_url || paper.pdf_url}', '_blank')">
                🔗 查看原文
            </button>
        </div>
    `;

    modal.classList.remove('hidden');
    // 自动生成AI摘要
    generatePaperSummary(paperId);
}

function closeModal() {
    document.getElementById('paperModal').classList.add('hidden');
}

// ============ AI摘要 ============

function generatePaperSummary(paperId) {
    const container = document.getElementById('modalAiContent');
    if (!container) return;

    container.innerHTML = `
        <div class="loading-spinner" style="width: 32px; height: 32px; border-width: 3px; margin: 0 auto 12px;"></div>
        <div style="font-size: 14px; color: var(--text-secondary);">DeepSeek 正在分析论文...</div>
    `;

    fetch(`/api/paper/${encodeURIComponent(paperId)}/summary?q=${encodeURIComponent(currentQuery)}`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                container.innerHTML = `<div style="color: var(--danger); font-size: 14px;">${data.error}</div>`;
                return;
            }
            displayPaperSummary(data.summary, container);
        })
        .catch(error => {
            console.error('Summary error:', error);
            const paper = currentPaperData[paperId];
            container.innerHTML = `<div style="color: var(--text-secondary); font-size: 14px;">AI分析暂时不可用，请稍后重试</div>`;
        });
}

function displayPaperSummary(summary, container) {
    const methods = (summary.methods || []).map(m => `<li>${m}</li>`).join('');
    const contributions = (summary.contributions || []).map(c => `<li>${c}</li>`).join('');
    const datasets = (summary.datasets || []).map(d => `<li>${d}</li>`).join('');
    const novelty = summary.novelty || 50;

    let html = `
        <div class="ai-summary-content">
            <div class="ai-brief">${summary.brief || '暂无总结'}</div>
    `;

    if (summary.is_breakthrough) {
        html += `
            <div class="breakthrough-badge">
                ⚡ 突破性工作 — ${summary.breakthrough_reason || '具有显著创新性'}
            </div>
        `;
    }

    html += `
        <div class="detail-section">
            <div class="detail-section-title">🔧 核心方法</div>
            <ul class="detail-list">${methods || '<li>暂无</li>'}</ul>
        </div>
        <div class="detail-section">
            <div class="detail-section-title">💡 主要贡献</div>
            <ul class="detail-list">${contributions || '<li>暂无</li>'}</ul>
        </div>
        <div class="detail-section">
            <div class="detail-section-title">📊 使用数据集</div>
            <ul class="detail-list">${datasets || '<li>暂无</li>'}</ul>
        </div>
        <div class="detail-section">
            <div class="detail-section-title">📊 影响力指标</div>
            <div class="detail-metrics">
                <div class="detail-metric-item">
                    <div class="detail-metric-label">影响力因子</div>
                    <div class="detail-metric-value">${summary.impact_factor || 'N/A'}${summary.impact_factor ? '/10' : ''}</div>
                </div>
                <div class="detail-metric-item">
                    <div class="detail-metric-label">估算引用量</div>
                    <div class="detail-metric-value">${summary.estimated_citations || 'N/A'}</div>
                </div>
                <div class="detail-metric-item">
                    <div class="detail-metric-label">创新性评分</div>
                    <div class="detail-metric-value">${novelty}/100</div>
                </div>
            </div>
            <div class="detail-novelty">
                <div class="novelty-bar"><div class="novelty-fill" style="width: ${novelty}%"></div></div>
            </div>
        </div>
        <div class="detail-section">
            <div class="detail-section-title">🔬 研究领域</div>
            <p style="font-size: 14px; color: var(--text-secondary);">${summary.field || 'Unknown'}</p>
        </div>
    `;

    html += `</div>`;
    container.innerHTML = html;
}

// ============ 设计文档 ============

function generatePaperDesign(paperId) {
    const section = document.getElementById('modalDesignSection');
    const container = document.getElementById('modalDesignContent');
    if (!section || !container) return;

    section.classList.remove('hidden');
    container.innerHTML = `
        <div class="loading-spinner" style="width: 32px; height: 32px; border-width: 3px; margin: 0 auto 12px;"></div>
        <div style="font-size: 14px; color: var(--text-secondary);">DeepSeek 正在生成设计文档...</div>
    `;

    // 滚动到设计文档区域
    section.scrollIntoView({ behavior: 'smooth', block: 'start' });

    fetch(`/api/paper/${encodeURIComponent(paperId)}/design?q=${encodeURIComponent(currentQuery)}`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                container.innerHTML = `<div style="color: var(--danger); font-size: 14px;">${data.error}</div>`;
                return;
            }
            displayDesignDoc(data.design_doc, container);
        })
        .catch(error => {
            console.error('Design doc error:', error);
            container.innerHTML = `<div style="color: var(--text-secondary); font-size: 14px;">设计文档生成暂时不可用</div>`;
        });
}

function displayDesignDoc(doc, container) {
    const arch = (doc.architecture || []).map(a => `<li>${a}</li>`).join('');
    const steps = (doc.implementation_steps || []).map(s => `<li>${s}</li>`).join('');
    const challenges = (doc.key_challenges || []).map(c => `<li>${c}</li>`).join('');
    const metrics = (doc.evaluation_metrics || []).map(m => `<li>${m}</li>`).join('');
    const techStack = (doc.tech_stack || []).map(t => `<span class="tech-tag">${t}</span>`).join('');

    container.innerHTML = `
        <div class="design-content">
            <div class="design-section-block">
                <h4>📌 项目概述</h4>
                <p>${doc.overview || '-'}</p>
            </div>
            <div class="design-section-block">
                <h4>💡 核心思想</h4>
                <p>${doc.core_idea || '-'}</p>
            </div>
            <div class="design-section-block">
                <h4>🏗️ 架构设计</h4>
                <ul class="detail-list">${arch || '<li>暂无</li>'}</ul>
            </div>
            <div class="design-section-block">
                <h4>📝 实现步骤</h4>
                <ul class="detail-list">${steps || '<li>暂无</li>'}</ul>
            </div>
            <div class="design-section-block">
                <h4>⚡ 关键挑战</h4>
                <ul class="detail-list">${challenges || '<li>暂无</li>'}</ul>
            </div>
            <div class="design-section-block">
                <h4>📊 评估指标</h4>
                <ul class="detail-list">${metrics || '<li>暂无</li>'}</ul>
            </div>
            <div class="design-section-block">
                <h4>🛠️ 推荐技术栈</h4>
                <div class="tech-stack-tags">${techStack || '<span class="tech-tag">Python</span>'}</div>
            </div>
            <div class="design-section-block">
                <h4>⏱️ 预估工作量</h4>
                <p style="color: var(--success); font-weight: 600;">${doc.estimated_workload || '-'}</p>
            </div>
        </div>
    `;
}

// ============ 下载 ============

function downloadPaper(paperId) {
    window.open(`https://arxiv.org/pdf/${paperId}.pdf`, '_blank');
}

// ============ 加载动画 ============

function showLoading(show) {
    const overlay = document.getElementById('loadingOverlay');
    overlay.classList.toggle('hidden', !show);
}

function updateLoadingSteps(steps) {
    const container = document.getElementById('loadingSteps');
    container.innerHTML = steps.map((s, i) =>
        `<div class="loading-step ${i === 0 ? 'active' : ''}" id="step-${i}">${s}</div>`
    ).join('');

    // 模拟步骤推进
    let currentStep = 0;
    const interval = setInterval(() => {
        const stepEl = document.getElementById(`step-${currentStep}`);
        if (stepEl) {
            stepEl.classList.remove('active');
            stepEl.classList.add('done');
        }
        currentStep++;
        const nextEl = document.getElementById(`step-${currentStep}`);
        if (nextEl) {
            nextEl.classList.add('active');
        } else {
            clearInterval(interval);
        }
    }, 1500);
}
