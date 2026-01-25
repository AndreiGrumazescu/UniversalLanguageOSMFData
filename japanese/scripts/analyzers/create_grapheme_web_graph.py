#!/usr/bin/env python3
"""
visualize_grapheme_graph.py

Creates a layered graph visualization of grapheme composition relationships.
Generates an HTML file with CSS Grid for layout and SVG for edges.
Each tree is separate, layers are strict horizontal bands by stroke count.
Nodes are ordered by barycentric heuristic to minimize edge crossings.

Usage:
    python UL-Content/japanese/scripts/analyzers/grapheme_graph.py
"""

import html
import json
import sys
from collections import defaultdict
from pathlib import Path

# Add parent directory to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import REPORTS_DIR
from lib.grapheme_io import load_graphemes, load_dependencies

OUTPUT_FILE = REPORTS_DIR / "grapheme-graph.html"
POPULARITY_JSON = REPORTS_DIR / "component-popularity.json"


def load_popularity_data() -> dict | None:
    """Load popularity data from JSON file if it exists."""
    if not POPULARITY_JSON.exists():
        return None
    with open(POPULARITY_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def find_connected_components(all_nodes: set[str], deps: dict[str, list[str]], reverse_deps: dict[str, list[str]]) -> list[set[str]]:
    """Find all connected components (trees) in the graph."""
    visited = set()
    components = []

    def dfs(node: str, component: set[str]):
        if node in visited:
            return
        visited.add(node)
        component.add(node)
        for child in deps.get(node, []):
            dfs(child, component)
        for parent in reverse_deps.get(node, []):
            dfs(parent, component)

    for node in all_nodes:
        if node not in visited:
            component = set()
            dfs(node, component)
            components.append(component)

    return sorted(components, key=len, reverse=True)


def get_stroke_count(grapheme_id: str, graphemes: dict[str, dict]) -> int:
    """Get stroke count, defaulting to 999 if unknown."""
    if grapheme_id in graphemes:
        return graphemes[grapheme_id].get("strokeCount") or 999
    return 999


def node_id_safe(grapheme_id: str) -> str:
    """Convert grapheme ID to a safe HTML/CSS id."""
    return grapheme_id.replace(":", "_").replace("+", "_")


def stroke_color(strokes: int) -> str:
    """Get background color for a stroke layer."""
    if strokes == 999:
        return "#F5F5F5"
    colors = [
        "#E3F2FD", "#E8F5E9", "#FFF3E0", "#F3E5F5",
        "#E0F7FA", "#FBE9E7", "#F1F8E9", "#EDE7F6",
    ]
    return colors[(strokes - 1) % len(colors)]


def compute_layer_ordering(
    by_strokes: dict[int, list[str]],
    stroke_counts: list[int],
    deps: dict[str, list[str]],
    reverse_deps: dict[str, list[str]],
    graphemes: dict[str, dict],
) -> dict[int, tuple[list[str], list[str], list[str]]]:
    """
    Order nodes in each layer by category, sorted by child count descending.

    Returns dict mapping stroke count to (primitives, composites, finals) tuple.
    - primitives: nodes that don't use any other graphemes (no parents in deps)
    - composites: nodes that use others AND are used by others
    - finals: nodes that use others but nothing uses them

    Within each category, nodes are sorted by child count (most children first).
    """
    ordered = {}

    for strokes in stroke_counts:
        layer_nodes = by_strokes[strokes]

        # Split into three categories based on parent/child relationships
        primitives = []  # No parents (not in deps or empty deps)
        composites = []  # Has parents AND has children
        finals = []      # Has parents but no children

        for gid in layer_nodes:
            has_parents = bool(deps.get(gid))  # Uses other graphemes
            has_children = bool(reverse_deps.get(gid))  # Is used by other graphemes

            if not has_parents:
                primitives.append(gid)
            elif has_children:
                composites.append(gid)
            else:
                finals.append(gid)

        def child_count(gid):
            return len(reverse_deps.get(gid, []))

        def parent_count(gid):
            return len(deps.get(gid, []))

        # Sort by child count desc, then parent count desc, then symbol for ties
        sort_key = lambda x: (-child_count(x), -parent_count(x), graphemes.get(x, {}).get("symbol", ""))

        primitives_sorted = sorted(primitives, key=sort_key)
        composites_sorted = sorted(composites, key=sort_key)
        finals_sorted = sorted(finals, key=sort_key)

        ordered[strokes] = (primitives_sorted, composites_sorted, finals_sorted)

    return ordered


def generate_popularity_view(graphemes: dict[str, dict], popularity_data: dict) -> str:
    """Generate the popularity view HTML showing graphemes sorted by popularity."""
    if not popularity_data:
        return '<div class="no-data">No popularity data available. Run analyze_component_popularity.py first.</div>'

    # Filter to only graphemes (is_grapheme=true) and group by stroke count
    by_strokes: dict[int, list[dict]] = defaultdict(list)

    for entry in popularity_data.get("entries", []):
        if entry.get("is_grapheme"):
            stroke = entry.get("stroke_count", 999)
            by_strokes[stroke].append(entry)

    # Sort each group by popularity descending
    for stroke in by_strokes:
        by_strokes[stroke].sort(key=lambda e: e.get("popularity", -1), reverse=True)

    # Find max nodes in any layer
    max_nodes = max(len(by_strokes[s]) for s in by_strokes) if by_strokes else 1
    total_layer_width = max(max_nodes * 70, 400)

    layers_html = []
    for strokes in sorted(by_strokes.keys()):
        entries = by_strokes[strokes]
        total_nodes = len(entries)

        stroke_label = f"{strokes} stroke{'s' if strokes != 1 else ''}" if strokes != 999 else "Unknown"
        bg_color = stroke_color(strokes)

        nodes_html = []
        for i, entry in enumerate(entries):
            char = entry.get("char", "?")
            symbol = html.escape(char)
            grapheme_id = entry.get("grapheme_id", "")
            popularity = entry.get("popularity", -1)

            # Try to get name from graphemes dict
            name = ""
            if grapheme_id and grapheme_id in graphemes:
                name = html.escape(graphemes[grapheme_id].get("name", ""))

            if total_nodes > 1:
                left_pct = (i / (total_nodes - 1)) * 100
            else:
                left_pct = 50

            pop_str = str(popularity) if popularity >= 0 else "N/A"
            pop_badge = f'<span class="badge pop-count">{pop_str}</span>'

            nodes_html.append(f'''
                <div class="node pop-node" style="left: {left_pct:.2f}%;" title="{symbol} - popularity: {pop_str}">
                    {pop_badge}
                    <span class="symbol">{symbol}</span>
                    <span class="name">{name}</span>
                </div>
            ''')

        layers_html.append(f'''
            <div class="layer" style="background-color: {bg_color};">
                <div class="layer-label">{stroke_label}</div>
                <div class="layer-content" style="width: {total_layer_width}px;">
                    <div class="nodes-container">
                        {''.join(nodes_html)}
                    </div>
                </div>
            </div>
        ''')

    metadata = popularity_data.get("metadata", {})
    total_kanji = metadata.get("total_kanji", 0)
    from_chise = metadata.get("from_chise", 0) + metadata.get("from_chise_atomic", 0)
    from_kanjivg = metadata.get("from_kanjivg", 0) + metadata.get("from_kanjivg_atomic", 0)
    grapheme_count = metadata.get("graphemes", 0)

    return f'''
        <div class="popularity-header">
            <p>Graphemes sorted by how often they appear as components in kanji (CHISE IDS primary, KanjiVG fallback)</p>
            <p class="stats">Total kanji: {total_kanji:,} | CHISE: {from_chise:,} | KanjiVG: {from_kanjivg:,} | Graphemes: {grapheme_count}</p>
        </div>
        <div class="tree">
            <div class="tree-header">Graphemes by Popularity</div>
            <div class="tree-content">
                <div class="tree-layers popularity-layers">
                    {''.join(layers_html)}
                </div>
            </div>
        </div>
    '''


def generate_html(trees: list[set[str]], graphemes: dict[str, dict], deps: dict[str, list[str]], reverse_deps: dict[str, list[str]], orphans: set[str] = None, popularity_data: dict = None) -> str:
    """Generate the complete HTML document."""

    # Generate popularity view HTML
    popularity_html = generate_popularity_view(graphemes, popularity_data)

    # Collect all edges for JavaScript
    all_edges = []
    for tree_nodes in trees:
        for parent_id in tree_nodes:
            if parent_id in deps:
                for component_id in deps[parent_id]:
                    if component_id in tree_nodes:
                        all_edges.append((node_id_safe(component_id), node_id_safe(parent_id)))

    edges_json = json.dumps(all_edges)

    # Build tree HTML
    trees_html = []
    for tree_idx, tree_nodes in enumerate(trees):
        by_strokes = defaultdict(list)
        for gid in tree_nodes:
            strokes = get_stroke_count(gid, graphemes)
            by_strokes[strokes].append(gid)

        stroke_counts = sorted(by_strokes.keys())

        # Compute layer ordering (by child count within each category)
        ordered_layers = compute_layer_ordering(
            by_strokes, stroke_counts, deps, reverse_deps, graphemes
        )

        # Find max total nodes in any layer (determines overall width)
        max_total_nodes = max(
            len(ordered_layers[s][0]) + len(ordered_layers[s][1]) + len(ordered_layers[s][2])
            for s in stroke_counts
        )
        # 70px per node slot + padding on edges
        total_layer_width = max(max_total_nodes * 70, 400)

        layers_html = []
        for strokes in stroke_counts:
            primitives, composites, finals = ordered_layers[strokes]
            all_nodes = primitives + composites + finals
            total_nodes = len(all_nodes)

            stroke_label = f"{strokes} stroke{'s' if strokes != 1 else ''}" if strokes != 999 else "Unknown"
            bg_color = stroke_color(strokes)

            # Build all nodes with positions across the full layer
            nodes_html = []
            for i, gid in enumerate(all_nodes):
                g = graphemes.get(gid, {})
                symbol = html.escape(g.get("symbol", "?"))
                name = html.escape(g.get("name", "?"))
                safe_id = node_id_safe(gid)

                # Calculate position as percentage across full layer
                if total_nodes > 1:
                    left_pct = (i / (total_nodes - 1)) * 100
                else:
                    left_pct = 50

                # Count parents (components this grapheme uses) and children (graphemes that use this)
                parent_count = len(deps.get(gid, []))
                child_count = len(reverse_deps.get(gid, []))

                parent_badge = f'<span class="badge parent-count">{parent_count}</span>' if parent_count > 0 else ''
                child_badge = f'<span class="badge child-count">{child_count}</span>' if child_count > 0 else ''

                nodes_html.append(f'''
                    <div class="node" id="{safe_id}" style="left: {left_pct:.2f}%;" title="{symbol} - {name}">
                        {parent_badge}
                        <span class="symbol">{symbol}</span>
                        <span class="name">{name}</span>
                        {child_badge}
                    </div>
                ''')

            layers_html.append(f'''
                <div class="layer" style="background-color: {bg_color};">
                    <div class="layer-label">{stroke_label}</div>
                    <div class="layer-content" style="width: {total_layer_width}px;">
                        <div class="nodes-container">
                            {''.join(nodes_html)}
                        </div>
                    </div>
                </div>
            ''')

        trees_html.append(f'''
            <div class="tree">
                <div class="tree-header">Tree {tree_idx + 1} ({len(tree_nodes)} graphemes)</div>
                <div class="tree-content">
                    <div class="tree-layers" data-tree="{tree_idx}">
                        <svg class="edges" data-tree="{tree_idx}"></svg>
                        {''.join(layers_html)}
                    </div>
                </div>
            </div>
        ''')

    # Add orphans tree if there are any
    if orphans:
        by_strokes = defaultdict(list)
        for gid in orphans:
            strokes = get_stroke_count(gid, graphemes)
            by_strokes[strokes].append(gid)

        stroke_counts = sorted(by_strokes.keys())

        # Find max nodes in any layer
        max_total_nodes = max(len(by_strokes[s]) for s in stroke_counts)
        total_layer_width = max(max_total_nodes * 70, 400)

        layers_html = []
        for strokes in stroke_counts:
            layer_nodes = sorted(by_strokes[strokes], key=lambda x: graphemes.get(x, {}).get("symbol", ""))
            total_nodes = len(layer_nodes)

            stroke_label = f"{strokes} stroke{'s' if strokes != 1 else ''}" if strokes != 999 else "Unknown"
            bg_color = stroke_color(strokes)

            nodes_html = []
            for i, gid in enumerate(layer_nodes):
                g = graphemes.get(gid, {})
                symbol = html.escape(g.get("symbol", "?"))
                name = html.escape(g.get("name", "?"))
                safe_id = node_id_safe(gid)

                if total_nodes > 1:
                    left_pct = (i / (total_nodes - 1)) * 100
                else:
                    left_pct = 50

                nodes_html.append(f'''
                    <div class="node" id="{safe_id}" style="left: {left_pct:.2f}%;" title="{symbol} - {name}">
                        <span class="symbol">{symbol}</span>
                        <span class="name">{name}</span>
                    </div>
                ''')

            layers_html.append(f'''
                <div class="layer" style="background-color: {bg_color};">
                    <div class="layer-label">{stroke_label}</div>
                    <div class="layer-content" style="width: {total_layer_width}px;">
                        <div class="nodes-container">
                            {''.join(nodes_html)}
                        </div>
                    </div>
                </div>
            ''')

        trees_html.append(f'''
            <div class="tree orphans-tree">
                <div class="tree-header">Orphans ({len(orphans)} graphemes with no relationships)</div>
                <div class="tree-content">
                    <div class="tree-layers" data-tree="orphans">
                        {''.join(layers_html)}
                    </div>
                </div>
            </div>
        ''')

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Grapheme Composition Graph</title>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f0f0f0;
            padding: 20px;
        }}

        h1 {{
            text-align: center;
            margin-bottom: 10px;
            color: #333;
        }}

        .tab-buttons {{
            display: flex;
            justify-content: center;
            gap: 10px;
            margin-bottom: 20px;
        }}

        .tab-btn {{
            padding: 10px 24px;
            font-size: 14px;
            font-weight: 600;
            border: 2px solid #ccc;
            border-radius: 6px;
            background: #fff;
            color: #666;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .tab-btn:hover {{
            border-color: #999;
            color: #333;
        }}

        .tab-btn.active {{
            background: #333;
            border-color: #333;
            color: #fff;
        }}

        .tab-content {{
            display: none;
        }}

        .tab-content.active {{
            display: block;
        }}

        .popularity-header {{
            text-align: center;
            margin-bottom: 20px;
            color: #666;
        }}

        .popularity-header .stats {{
            font-size: 12px;
            margin-top: 5px;
        }}

        .no-data {{
            text-align: center;
            padding: 40px;
            color: #666;
            font-style: italic;
        }}

        .pop-node .pop-count {{
            top: -5px;
            left: 50%;
            transform: translateX(-50%);
            background: #E65100;
            color: #fff;
        }}

        .container {{
        }}

        .tree-layers {{
            display: inline-block;
            min-width: 100%;
            position: relative;
            padding: 15px;
        }}

        svg.edges {{
            position: absolute;
            top: 0;
            left: 0;
            pointer-events: none;
            z-index: 2;
        }}

        .tree {{
            background: #fff;
            border-radius: 8px;
            margin-bottom: 30px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            overflow: hidden;
        }}

        .tree-header {{
            background: #333;
            color: #fff;
            padding: 12px 20px;
            font-size: 16px;
            font-weight: 600;
        }}

        .orphans-tree .tree-header {{
            background: #757575;
        }}

        .tree-content {{
            padding: 0;
            overflow-x: auto;
        }}

        .layer {{
            display: flex;
            align-items: center;
            padding: 20px 20px;
            margin-bottom: 15px;
            border-radius: 6px;
            min-height: 80px;
        }}

        .layer:last-child {{
            margin-bottom: 0;
        }}

        .layer-label {{
            width: 100px;
            flex-shrink: 0;
            font-size: 12px;
            font-weight: 600;
            color: #666;
        }}

        .layer-content {{
            position: relative;
            height: 70px;
            flex-shrink: 0;
        }}

        .nodes-container {{
            position: absolute;
            top: 0;
            left: 30px;   /* Padding so edge nodes don't overflow */
            right: 30px;
            bottom: 0;
            z-index: 3;
        }}

        svg.edges path {{
            opacity: 0.06;
            stroke: #999;
            stroke-width: 1.5;
        }}

        svg.edges path.highlighted {{
            opacity: 0.9;
            stroke: #2196F3;
            stroke-width: 2;
        }}

        .node {{
            position: absolute;
            top: 50%;
            transform: translate(-50%, -50%);
            background: #fff;
            border: 2px solid #ccc;
            border-radius: 6px;
            padding: 4px 6px;
            text-align: center;
            width: 60px;
            cursor: default;
            transition: border-color 0.15s, box-shadow 0.15s;
        }}

        .node:hover {{
            border-color: #666;
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
            z-index: 20;
        }}

        .node .symbol {{
            display: block;
            font-size: 18px;
            font-family: "Noto Sans CJK JP", "Hiragino Sans", sans-serif;
            line-height: 1.2;
            cursor: text;
            user-select: text;
        }}

        .node .name {{
            display: block;
            font-size: 7px;
            color: #666;
            margin-top: 2px;
            width: 100%;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: normal;
            word-wrap: break-word;
            line-height: 1.2;
            max-height: 2.4em;  /* 2 lines max */
            cursor: text;
            user-select: text;
        }}

        .node .badge {{
            position: absolute;
            font-size: 9px;
            font-weight: 600;
            min-width: 14px;
            height: 14px;
            line-height: 14px;
            text-align: center;
            border-radius: 7px;
            padding: 0 3px;
        }}

        .node .parent-count {{
            top: -5px;
            left: -5px;
            background: #7B1FA2;
            color: #fff;
        }}

        .node .child-count {{
            bottom: -5px;
            right: -5px;
            background: #1976D2;
            color: #fff;
        }}

        .node.highlighted {{
            border-color: #2196F3;
            box-shadow: 0 0 0 3px rgba(33, 150, 243, 0.3);
            z-index: 20;
        }}

        .node.faded {{
            opacity: 0.15;
        }}

        .node.selected {{
            border-color: #1976D2;
            box-shadow: 0 0 0 4px rgba(25, 118, 210, 0.4);
            z-index: 21;
        }}

        svg.edges path.faded {{
            opacity: 0.02;
        }}
    </style>
</head>
<body>
    <h1>Grapheme Composition Graph</h1>

    <div class="tab-buttons">
        <button class="tab-btn active" data-tab="composition">Composition Trees</button>
        <button class="tab-btn" data-tab="popularity">Popularity View</button>
    </div>

    <div id="composition-tab" class="tab-content active">
        <div class="container" id="container">
            {''.join(trees_html)}
        </div>
    </div>

    <div id="popularity-tab" class="tab-content">
        {popularity_html}
    </div>

    <script>
        const edges = {edges_json};
        let currentHoveredNode = null;

        function drawEdges() {{
            // Draw edges for each tree
            document.querySelectorAll('.tree-layers').forEach(treeLayers => {{
                const svg = treeLayers.querySelector('svg.edges');
                if (!svg) return;

                const layersRect = treeLayers.getBoundingClientRect();

                svg.setAttribute('width', treeLayers.scrollWidth);
                svg.setAttribute('height', treeLayers.scrollHeight);
                svg.innerHTML = '';

                edges.forEach(([fromId, toId]) => {{
                    const fromEl = document.getElementById(fromId);
                    const toEl = document.getElementById(toId);

                    if (!fromEl || !toEl) return;
                    // Only draw if both nodes are in this tree
                    if (!treeLayers.contains(fromEl) || !treeLayers.contains(toEl)) return;

                    const fromRect = fromEl.getBoundingClientRect();
                    const toRect = toEl.getBoundingClientRect();

                    // Calculate center points relative to tree-layers
                    const x1 = fromRect.left + fromRect.width / 2 - layersRect.left;
                    const y1 = fromRect.bottom - layersRect.top;
                    const x2 = toRect.left + toRect.width / 2 - layersRect.left;
                    const y2 = toRect.top - layersRect.top;

                    // Create curved path
                    const midY = (y1 + y2) / 2;
                    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                    path.setAttribute('d', `M ${{x1}} ${{y1}} C ${{x1}} ${{midY}}, ${{x2}} ${{midY}}, ${{x2}} ${{y2}}`);
                    path.setAttribute('fill', 'none');
                    path.dataset.from = fromId;
                    path.dataset.to = toId;

                    svg.appendChild(path);
                }});
            }});

            // Re-apply highlighting if a node is currently hovered
            if (currentHoveredNode) {{
                highlightNode(currentHoveredNode);
            }}
        }}

        function highlightNode(nodeId) {{
            document.querySelectorAll('path').forEach(path => {{
                if (path.dataset.from === nodeId || path.dataset.to === nodeId) {{
                    path.classList.add('highlighted');

                    const otherId = path.dataset.from === nodeId ? path.dataset.to : path.dataset.from;
                    const otherNode = document.getElementById(otherId);
                    if (otherNode) otherNode.classList.add('highlighted');
                }}
            }});
        }}

        function clearHighlights() {{
            document.querySelectorAll('path.highlighted').forEach(path => {{
                path.classList.remove('highlighted');
            }});
            document.querySelectorAll('.node.highlighted').forEach(n => {{
                n.classList.remove('highlighted');
            }});

            // Re-apply selection highlights if a node is selected
            if (selectedNode) {{
                document.querySelectorAll('path').forEach(path => {{
                    if (path.dataset.from === selectedNode || path.dataset.to === selectedNode) {{
                        path.classList.add('highlighted');
                    }}
                }});
            }}
        }}

        let pendingClear = null;
        let selectedNode = null;

        function getConnectedNodes(nodeId) {{
            const connected = new Set([nodeId]);
            document.querySelectorAll('path').forEach(path => {{
                if (path.dataset.from === nodeId) {{
                    connected.add(path.dataset.to);
                }} else if (path.dataset.to === nodeId) {{
                    connected.add(path.dataset.from);
                }}
            }});
            return connected;
        }}

        function selectNode(nodeId) {{
            // Clear previous selection
            clearSelection();

            selectedNode = nodeId;
            const connected = getConnectedNodes(nodeId);

            // Mark selected node
            const selectedEl = document.getElementById(nodeId);
            if (selectedEl) selectedEl.classList.add('selected');

            // Fade unconnected nodes and paths, highlight connected paths
            document.querySelectorAll('.node').forEach(node => {{
                if (!connected.has(node.id)) {{
                    node.classList.add('faded');
                }}
            }});

            document.querySelectorAll('path').forEach(path => {{
                if (path.dataset.from === nodeId || path.dataset.to === nodeId) {{
                    path.classList.add('highlighted');
                }} else {{
                    path.classList.add('faded');
                }}
            }});
        }}

        function clearSelection() {{
            selectedNode = null;
            document.querySelectorAll('.node.selected').forEach(n => n.classList.remove('selected'));
            document.querySelectorAll('.node.faded').forEach(n => n.classList.remove('faded'));
            document.querySelectorAll('path.faded').forEach(p => p.classList.remove('faded'));
            document.querySelectorAll('path.highlighted').forEach(p => p.classList.remove('highlighted'));
        }}

        // Highlight connected nodes on hover
        document.querySelectorAll('.node').forEach(node => {{
            node.addEventListener('mouseenter', () => {{
                // Cancel any pending clear
                if (pendingClear) {{
                    clearTimeout(pendingClear);
                    pendingClear = null;
                }}

                // Only update if hovering a different node
                if (currentHoveredNode !== node.id) {{
                    clearHighlights();
                    currentHoveredNode = node.id;
                    highlightNode(node.id);
                }}
            }});

            node.addEventListener('mouseleave', (e) => {{
                // Check if we're moving to another node or its children
                const relatedTarget = e.relatedTarget;
                if (relatedTarget && relatedTarget.closest && relatedTarget.closest('.node')) {{
                    // Moving to another node - let that node's mouseenter handle it
                    return;
                }}

                // Debounce the clear to prevent flicker
                pendingClear = setTimeout(() => {{
                    currentHoveredNode = null;
                    clearHighlights();
                    pendingClear = null;
                }}, 50);
            }});

            // Click to select/deselect
            node.addEventListener('click', (e) => {{
                e.stopPropagation();
                if (selectedNode === node.id) {{
                    // Clicking same node deselects
                    clearSelection();
                }} else {{
                    selectNode(node.id);
                }}
            }});
        }});

        // Click outside nodes to clear selection
        document.addEventListener('click', (e) => {{
            if (!e.target.closest('.node')) {{
                clearSelection();
            }}
        }});

        // Draw edges on load and resize
        window.addEventListener('load', drawEdges);
        window.addEventListener('resize', drawEdges);

        // Tab switching
        document.querySelectorAll('.tab-btn').forEach(btn => {{
            btn.addEventListener('click', () => {{
                const tabName = btn.dataset.tab;

                // Update button states
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');

                // Update content visibility
                document.querySelectorAll('.tab-content').forEach(content => {{
                    content.classList.remove('active');
                }});
                document.getElementById(tabName + '-tab').classList.add('active');

                // Redraw edges when switching to composition tab
                if (tabName === 'composition') {{
                    setTimeout(drawEdges, 50);
                }}
            }});
        }});
    </script>
</body>
</html>
'''


def main():
    print("Loading graphemes...")
    graphemes = load_graphemes()
    print(f"  Loaded {len(graphemes)} graphemes")

    print("Loading dependencies...")
    deps, reverse_deps = load_dependencies()
    print(f"  Loaded {len(deps)} dependency documents")

    print("Loading popularity data...")
    popularity_data = load_popularity_data()
    if popularity_data:
        print(f"  Loaded popularity data for {popularity_data.get('metadata', {}).get('total_kanji', 0)} kanji")
    else:
        print("  No popularity data found (run analyze_component_popularity.py first)")

    # Find all involved graphemes
    all_components = set()
    for components in deps.values():
        all_components.update(components)
    all_involved = set(deps.keys()) | all_components

    # Find connected components (separate trees)
    trees = find_connected_components(all_involved, deps, reverse_deps)
    print(f"\nFound {len(trees)} separate trees")
    for i, tree in enumerate(trees[:5]):
        print(f"  Tree {i+1}: {len(tree)} nodes")
    if len(trees) > 5:
        print(f"  ... and {len(trees) - 5} more trees")

    # Find orphans (graphemes with no relationships)
    all_grapheme_ids = set(graphemes.keys())
    orphans = all_grapheme_ids - all_involved
    print(f"  Orphans: {len(orphans)} graphemes")

    # Generate HTML
    html_content = generate_html(trees, graphemes, deps, reverse_deps, orphans, popularity_data)

    # Write output
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"\nGraph written to: {OUTPUT_FILE}")
    print(f"\nSummary:")
    print(f"  Total nodes: {len(all_involved)}")
    print(f"  Total edges: {sum(len(c) for c in deps.values())}")
    print(f"  Separate trees: {len(trees)}")

    all_grapheme_ids = set(graphemes.keys())
    orphans = all_grapheme_ids - all_involved
    print(f"  Orphan graphemes (not shown): {len(orphans)}")


if __name__ == "__main__":
    main()
