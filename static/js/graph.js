let svg, simulation, g, link, node, label;
let graphData = null;
let zoom;
let nodeScale = 1;
let forceRunning = true;
let clusterMode = true;

const colorMap = {
    'transformer': '#4f46e5',
    'diffusion': '#ec4899',
    'cnn': '#10b981',
    'graph': '#f59e0b',
    'gan': '#8b5cf6',
    'rnn': '#06b6d4',
    'reinforcement': '#ef4444',
    'bayesian': '#14b8a6',
    'optimization': '#84cc16',
    'self-supervised': '#f97316',
    'deep learning': '#64748b',
    'default': '#64748b'
};

function initGraph() {
    const container = d3.select('.graph-container');
    const width = container.node().clientWidth;
    const height = container.node().clientHeight;

    svg = d3.select('#graphSvg')
        .attr('width', width)
        .attr('height', height);

    svg.selectAll('*').remove();

    const defs = svg.append('defs');

    const gradient = defs.append('radialGradient')
        .attr('id', 'bgGlow')
        .attr('cx', '50%')
        .attr('cy', '50%')
        .attr('r', '50%');

    gradient.append('stop')
        .attr('offset', '0%')
        .attr('stop-color', 'rgba(99, 102, 241, 0.05)');

    gradient.append('stop')
        .attr('offset', '100%')
        .attr('stop-color', 'transparent');

    svg.append('rect')
        .attr('width', '100%')
        .attr('height', '100%')
        .attr('fill', 'url(#bgGlow)');

    g = svg.append('g');

    zoom = d3.zoom()
        .scaleExtent([0.1, 4])
        .on('zoom', (event) => {
            g.attr('transform', event.transform);
        });

    svg.call(zoom);

    link = g.append('g').attr('class', 'links');
    node = g.append('g').attr('class', 'nodes');
    label = g.append('g').attr('class', 'labels');
}

function getCategoryKey(d) {
    const category = d.category || d.methods?.[0] || 'default';
    const catLower = category.toLowerCase();
    for (const key of Object.keys(colorMap)) {
        if (catLower.includes(key)) return key;
    }
    return 'default';
}

function getCategoryCenter(catKey, width, height) {
    const categories = Object.keys(colorMap).filter(k => k !== 'default');
    const index = categories.indexOf(catKey);
    if (index === -1) return { x: width / 2, y: height / 2 };

    const cols = Math.ceil(Math.sqrt(categories.length));
    const rows = Math.ceil(categories.length / cols);
    const col = index % cols;
    const row = Math.floor(index / cols);

    const margin = 120;
    const cellW = (width - margin * 2) / Math.max(cols - 1, 1);
    const cellH = (height - margin * 2) / Math.max(rows - 1, 1);

    return {
        x: margin + col * cellW,
        y: margin + row * cellH
    };
}

function renderGraph(data) {
    graphData = data;
    const container = d3.select('.graph-container');
    const width = container.node().clientWidth;
    const height = container.node().clientHeight;

    d3.select('#graphPlaceholder').style('display', 'none');

    g.selectAll('*').remove();
    link = g.append('g').attr('class', 'links');
    node = g.append('g').attr('class', 'nodes');
    label = g.append('g').attr('class', 'labels');

    const nodes = data.nodes.map(d => ({
        ...d,
        _cat: getCategoryKey(d),
        size: d.size || (d.breakthrough ? 28 : 18)
    }));
    const links = data.links.map(d => ({...d}));

    const strongLinks = links.filter(l => (l.value || 1) >= 1).slice(0, Math.min(links.length, 80));

    simulation = d3.forceSimulation(nodes)
        .force('link', d3.forceLink(strongLinks).id(d => d.id).distance(d => {
            if (d.type === 'method') return 100;
            if (d.type === 'topic') return 130;
            if (d.type === 'author') return 150;
            if (d.type === 'timeline') return 180;
            return 140;
        }).strength(d => {
            if (d.type === 'method') return 0.5;
            if (d.type === 'topic') return 0.3;
            return 0.2;
        }))
        .force('charge', d3.forceManyBody().strength(d => -(d.size || 20) * 8))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(d => (d.size || 20) * nodeScale + 8));

    if (clusterMode) {
        simulation.force('x', d3.forceX(d => getCategoryCenter(d._cat, width, height).x).strength(0.15));
        simulation.force('y', d3.forceY(d => getCategoryCenter(d._cat, width, height).y).strength(0.15));
    }

    const linkGroup = link.selectAll('line')
        .data(strongLinks)
        .enter().append('line')
        .attr('class', d => `link link-${d.type}`)
        .attr('stroke-width', d => Math.min(Math.sqrt(d.value || 1) * 1.5, 3))
        .attr('stroke-opacity', 0.25)
        .on('mouseover', function(event, d) {
            d3.select(this).attr('stroke-opacity', 0.8);
            const typeMap = { method: '方法关联', author: '作者关联', timeline: '时间线', topic: '主题关联' };
            showTooltip(event, `<div class="tooltip-title">${typeMap[d.type] || '关联'}</div><div class="tooltip-desc">${d.label || ''}</div>`);
        })
        .on('mousemove', moveTooltip)
        .on('mouseout', function() {
            d3.select(this).attr('stroke-opacity', 0.25);
            hideTooltip();
        });

    const nodeGroup = node.selectAll('g')
        .data(nodes)
        .enter().append('g')
        .attr('class', 'node')
        .attr('data-id', d => d.id)
        .call(d3.drag()
            .on('start', dragstarted)
            .on('drag', dragged)
            .on('end', dragended));

    nodeGroup.append('circle')
        .attr('r', d => (d.size || 20) * nodeScale)
        .attr('fill', d => getNodeColor(d))
        .attr('stroke', d => d.breakthrough ? '#fbbf24' : '#fff')
        .attr('stroke-width', d => d.breakthrough ? 3 : 2)
        .on('mouseover', function(event, d) {
            showNodeTooltip(event, d);
            highlightConnected(d);
        })
        .on('mousemove', moveTooltip)
        .on('mouseout', function() {
            hideTooltip();
            resetHighlight();
        })
        .on('click', function(event, d) {
            selectNode(d);
        });

    nodeGroup.append('text')
        .attr('dy', d => -((d.size || 20) * nodeScale + 5))
        .text(d => (d.size || 20) >= 22 ? truncateTitle(d.title, 3) : '')
        .style('font-size', '10px')
        .style('fill', 'var(--text-primary)')
        .style('text-anchor', 'middle')
        .style('pointer-events', 'none')
        .style('opacity', d => (d.size || 20) >= 22 ? 0.9 : 0)
        .style('font-weight', '500');

    simulation.on('tick', () => {
        linkGroup
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);

        nodeGroup.attr('transform', d => `translate(${d.x},${d.y})`);
    });

    updateGraphInfo(nodes.length, strongLinks.length);
    forceRunning = true;
    document.getElementById('forceBtn').innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>';
}

function getNodeColor(d) {
    return colorMap[getCategoryKey(d)] || colorMap.default;
}

function truncateTitle(title, maxWords) {
    const words = title.split(' ');
    if (words.length <= maxWords) return title;
    return words.slice(0, maxWords).join(' ') + '...';
}

function showNodeTooltip(event, d) {
    const authors = d.authors?.join(', ') || 'Unknown';
    const date = d.published ? new Date(d.published).toLocaleDateString('zh-CN') : 'Unknown';
    const methods = d.methods?.join(', ') || '';

    const html = `
        <div class="tooltip-title">${d.title}</div>
        <div class="tooltip-meta">📅 ${date} | 👥 ${truncateText(authors, 30)}</div>
        ${methods ? `<div class="tooltip-meta">🏷️ ${truncateText(methods, 30)}</div>` : ''}
        ${d.breakthrough ? '<div class="tooltip-meta" style="color:#f59e0b">⭐ 突破性论文</div>' : ''}
        <div class="tooltip-desc">${truncateText(d.summary || '', 100)}</div>
    `;
    showTooltip(event, html);
}

function truncateText(text, maxLen) {
    if (!text) return '';
    if (text.length <= maxLen) return text;
    return text.slice(0, maxLen) + '...';
}

function showTooltip(event, html) {
    const tooltip = document.getElementById('tooltip');
    tooltip.innerHTML = html;
    tooltip.classList.remove('hidden');
    moveTooltip(event);
}

function moveTooltip(event) {
    const tooltip = document.getElementById('tooltip');
    const x = event.clientX + 15;
    const y = event.clientY + 15;
    tooltip.style.left = x + 'px';
    tooltip.style.top = y + 'px';
}

function hideTooltip() {
    document.getElementById('tooltip').classList.add('hidden');
}

function highlightConnected(d) {
    if (!graphData) return;

    const connected = new Set([d.id]);
    const connectedLinks = new Set();
    graphData.links.forEach(l => {
        const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
        const targetId = typeof l.target === 'object' ? l.target.id : l.target;
        if (sourceId === d.id) {
            connected.add(targetId);
            connectedLinks.add(l);
        }
        if (targetId === d.id) {
            connected.add(sourceId);
            connectedLinks.add(l);
        }
    });

    node.selectAll('circle')
        .attr('opacity', n => connected.has(n.id) ? 1 : 0.15);

    node.selectAll('text')
        .attr('opacity', n => {
            if (connected.has(n.id)) {
                return (n.size || 20) >= 18 ? 0.9 : 0;
            }
            return 0;
        });

    link.selectAll('line')
        .attr('stroke-opacity', l => {
            const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
            const targetId = typeof l.target === 'object' ? l.target.id : l.target;
            return (sourceId === d.id || targetId === d.id) ? 0.8 : 0.05;
        });
}

function resetHighlight() {
    if (!node || !link) return;
    node.selectAll('circle').attr('opacity', 1);
    node.selectAll('text').attr('opacity', d => (d.size || 20) >= 22 ? 0.9 : 0);
    link.selectAll('line').attr('stroke-opacity', 0.25);
}

function searchGraphNode(query) {
    if (!graphData || !node) return;

    const q = query.toLowerCase().trim();

    if (!q) {
        node.selectAll('circle').attr('opacity', 1);
        node.selectAll('text').attr('opacity', d => (d.size || 20) >= 22 ? 0.9 : 0);
        link.selectAll('line').attr('stroke-opacity', 0.25);
        return;
    }

    const matched = new Set();
    graphData.nodes.forEach(n => {
        if (n.title.toLowerCase().includes(q) ||
            (n.authors || []).some(a => a.toLowerCase().includes(q)) ||
            (n.methods || []).some(m => m.toLowerCase().includes(q))) {
            matched.add(n.id);
        }
    });

    node.selectAll('circle')
        .attr('opacity', n => matched.has(n.id) ? 1 : 0.1)
        .attr('stroke-width', n => matched.has(n.id) ? 4 : 2);

    node.selectAll('text')
        .attr('opacity', n => matched.has(n.id) ? 1 : 0);

    link.selectAll('line')
        .attr('stroke-opacity', l => {
            const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
            const targetId = typeof l.target === 'object' ? l.target.id : l.target;
            return (matched.has(sourceId) && matched.has(targetId)) ? 0.6 : 0.05;
        });

    if (matched.size > 0) {
        const firstMatch = graphData.nodes.find(n => matched.has(n.id));
        if (firstMatch && svg) {
            const container = d3.select('.graph-container');
            const width = container.node().clientWidth;
            const height = container.node().clientHeight;
            svg.transition().duration(500).call(
                zoom.transform,
                d3.zoomIdentity.translate(width / 2 - firstMatch.x, height / 2 - firstMatch.y).scale(1.5)
            );
        }
    }
}

function selectNode(d) {
    if (typeof showPaperDetail === 'function') {
        if (!currentPaperData[d.id] && d) {
            currentPaperData[d.id] = d;
        }
        showPaperDetail(d.id);
    }
}

function dragstarted(event, d) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
}

function dragged(event, d) {
    d.fx = event.x;
    d.fy = event.y;
}

function dragended(event, d) {
    if (!event.active) simulation.alphaTarget(0);
    d.fx = null;
    d.fy = null;
}

function zoomIn() {
    svg.transition().duration(300).call(zoom.scaleBy, 1.3);
}

function zoomOut() {
    svg.transition().duration(300).call(zoom.scaleBy, 0.7);
}

function resetZoom() {
    svg.transition().duration(300).call(zoom.transform, d3.zoomIdentity);
}

function toggleForce() {
    if (!simulation) return;
    if (forceRunning) {
        simulation.stop();
        forceRunning = false;
        document.getElementById('forceBtn').innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>';
    } else {
        simulation.alpha(0.3).restart();
        forceRunning = true;
        document.getElementById('forceBtn').innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>';
    }
}

function toggleCluster() {
    if (!simulation || !graphData) return;
    clusterMode = !clusterMode;

    const container = d3.select('.graph-container');
    const width = container.node().clientWidth;
    const height = container.node().clientHeight;

    const btn = document.getElementById('clusterBtn');
    btn.style.background = clusterMode ? 'var(--primary-lighter)' : '';
    btn.style.color = clusterMode ? 'var(--primary)' : '';

    if (clusterMode) {
        simulation.force('x', d3.forceX(d => getCategoryCenter(d._cat, width, height).x).strength(0.15));
        simulation.force('y', d3.forceY(d => getCategoryCenter(d._cat, width, height).y).strength(0.15));
    } else {
        simulation.force('x', null);
        simulation.force('y', null);
    }

    simulation.alpha(0.5).restart();
}

function updateFilter() {
    if (!link) return;

    const showMethod = document.getElementById('showMethodLinks').checked;
    const showAuthor = document.getElementById('showAuthorLinks').checked;
    const showTimeline = document.getElementById('showTimelineLinks').checked;
    const showTopic = document.getElementById('showTopicLinks').checked;

    link.selectAll('line')
        .style('display', d => {
            if (d.type === 'method' && !showMethod) return 'none';
            if (d.type === 'author' && !showAuthor) return 'none';
            if (d.type === 'timeline' && !showTimeline) return 'none';
            if (d.type === 'topic' && !showTopic) return 'none';
            return null;
        });
}

function updateNodeSize() {
    nodeScale = parseFloat(document.getElementById('nodeSizeSlider').value);
    document.getElementById('nodeSizeValue').textContent = nodeScale.toFixed(1);

    if (node) {
        node.selectAll('circle')
            .attr('r', d => (d.size || 20) * nodeScale);
        node.selectAll('text')
            .attr('dy', d => -((d.size || 20) * nodeScale + 5));

        if (simulation) {
            simulation.force('collision', d3.forceCollide().radius(d => (d.size || 20) * nodeScale + 8));
            simulation.alpha(0.3).restart();
        }
    }
}

function updateGraphInfo(nodes, links) {
    document.getElementById('graphInfo').textContent = `${nodes} 节点 / ${links} 边`;
}

window.addEventListener('resize', () => {
    if (svg) {
        const container = d3.select('.graph-container');
        const width = container.node().clientWidth;
        const height = container.node().clientHeight;
        svg.attr('width', width).attr('height', height);
        if (simulation) {
            simulation.force('center', d3.forceCenter(width / 2, height / 2));
            simulation.alpha(0.1).restart();
        }
    }
});
