"""AST -> 可交互 HTML 可视化（实验一验收项）。

不依赖任何前端框架或 CDN，生成单文件 HTML：把 AST 的 JSON 内嵌到页面里，
用一小段原生 JavaScript 做 tidy-tree 布局并绘制 SVG，支持节点折叠与搜索。
可以直接双击打开，满足「在浏览器中可视化展示」的要求。
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from .ast_json import node_to_dict

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root { --bg:#0f1420; --fg:#e6edf3; --muted:#8b98a9; --line:#2c3648; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--fg);
         font-family: "Segoe UI", "Microsoft YaHei", system-ui, sans-serif; }
  header { padding:14px 20px; border-bottom:1px solid var(--line);
           display:flex; align-items:center; gap:16px; flex-wrap:wrap; position:sticky; top:0;
           background:var(--bg); z-index:2; }
  h1 { font-size:16px; margin:0; font-weight:600; }
  .meta { color:var(--muted); font-size:12px; }
  .tools { margin-left:auto; display:flex; gap:8px; }
  input, button { background:#1a2231; color:var(--fg); border:1px solid var(--line);
                  border-radius:6px; padding:6px 10px; font-size:12px; }
  button { cursor:pointer; }
  button:hover { border-color:#4d7cfe; }
  #stage { padding:20px; overflow:auto; }
  svg { display:block; }
  .node rect { rx:8; ry:8; }
  .node .title { font-size:13px; font-weight:600; }
  .node .attr { font-size:11px; fill:var(--muted); }
  .edge { stroke:var(--line); fill:none; }
  .node.dim { opacity:0.15; }
  .node.hit rect { stroke:#4d7cfe; stroke-width:2px; }
  footer { padding:10px 20px; color:var(--muted); font-size:12px; border-top:1px solid var(--line); }
  pre.src { background:#151b28; border:1px solid var(--line); border-radius:8px;
            padding:12px; color:#c9d4e4; font-size:12px; overflow:auto; }
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <span class="meta" id="meta"></span>
  <div class="tools">
    <input id="search" type="text" placeholder="搜索节点类型或字段..." />
    <button id="expand">全部展开</button>
    <button id="collapse">折叠到 2 层</button>
  </div>
</header>
<div id="stage"></div>
<footer>Mini-ArkTS 编译器 · 实验一 AST 可视化 · 生成时间 __GENERATED__</footer>
<script>
const AST = __AST_JSON__;
const SOURCE = __SOURCE_JSON__;

const NODE_W = 190, GAP_X = 34, LEVEL_H = 92, PAD = 30;
const COLLAPSED_H = 46;

const CATEGORY = (t) => {
  if (t.endsWith('Declaration')) return {fill:'#16351f', stroke:'#3fb950', text:'#7ee787'};
  if (t.endsWith('Statement') || t === 'Block' || t === 'Program')
    return {fill:'#3a2a12', stroke:'#d29922', text:'#e3b341'};
  if (t.endsWith('Expression') || t === 'Identifier' || t === 'Property')
    return {fill:'#12233f', stroke:'#58a6ff', text:'#79c0ff'};
  if (t === 'Literal' || t === 'TypeAnnotation' || t === 'Decorator' || t === 'Parameter')
    return {fill:'#2b1e3a', stroke:'#a371f7', text:'#d2a8ff'};
  if (t === 'UiContainer') return {fill:'#3a1520', stroke:'#f778ba', text:'#ff9bce'};
  return {fill:'#1c2431', stroke:'#30363d', text:'#c9d1d9'};
};

function isAstNode(o) { return o && typeof o === 'object' && !Array.isArray(o) && typeof o.type === 'string'; }

function build(node) {
  const label = node.type;
  const attrs = [];
  const children = [];
  for (const k of Object.keys(node)) {
    if (k === 'type' || k === 'line' || k === 'column') continue;
    const v = node[k];
    if (Array.isArray(v)) {
      for (const item of v) {
        if (isAstNode(item)) children.push(build(item));
        else attrs.push(k + '=[' + v.length + ']');
      }
    } else if (isAstNode(v)) {
      children.push(build(v));
    } else if (v !== null && v !== '' && v !== undefined) {
      attrs.push(k + '=' + JSON.stringify(v));
    }
  }
  const loc = 'L' + node.line + ':' + node.column;
  return { label, attrs, loc, children };
}

function visibleChildren(n) {
  return n.collapsed ? [] : n.children;
}

function layout(root) {
  let cursor = 0;
  let maxDepth = 0;
  (function walk(n, depth) {
    n.depth = depth;
    maxDepth = Math.max(maxDepth, depth);
    n.height = COLLAPSED_H + (n.collapsed ? 0 : n.attrs.length * 15 + 8);
    const kids = visibleChildren(n);
    if (kids.length === 0) {
      n.x = cursor;
      cursor += NODE_W + GAP_X;
    } else {
      kids.forEach(c => walk(c, depth + 1));
      n.x = (kids[0].x + kids[kids.length - 1].x) / 2;
    }
  })(root, 0);
  return maxDepth;
}

function render() {
  const stage = document.getElementById('stage');
  stage.innerHTML = '';
  const root = build(AST);
  const maxDepth = layout(root);

  let maxX = 0;
  (function scan(n) { maxX = Math.max(maxX, n.x); visibleChildren(n).forEach(scan); })(root);

  const width = maxX + NODE_W + PAD * 2;
  const height = maxDepth * LEVEL_H + 160;
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('width', width);
  svg.setAttribute('height', height);

  const nodes = [];
  const edges = [];

  function emit(n) {
    nodes.push(n);
    for (const c of visibleChildren(n)) {
      edges.push([n, c]);
      emit(c);
    }
  }
  emit(root);

  for (const [p, c] of edges) {
    const x1 = p.x + PAD + NODE_W / 2, y1 = p.depth * LEVEL_H + PAD + p.height;
    const x2 = c.x + PAD + NODE_W / 2, y2 = c.depth * LEVEL_H + PAD;
    const mid = (y1 + y2) / 2;
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('class', 'edge');
    path.setAttribute('d', `M${x1},${y1} C${x1},${mid} ${x2},${mid} ${x2},${y2}`);
    svg.appendChild(path);
  }

  for (const n of nodes) {
    const c = CATEGORY(n.label);
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('class', 'node');
    g.setAttribute('data-label', n.label);
    g.setAttribute('transform', `translate(${n.x + PAD}, ${n.depth * LEVEL_H + PAD})`);
    g.style.cursor = n.children.length ? 'pointer' : 'default';
    if (n.children.length) {
      g.addEventListener('click', () => { n.collapsed = !n.collapsed; render(); });
    }

    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('width', NODE_W);
    rect.setAttribute('height', n.height);
    rect.setAttribute('fill', c.fill);
    rect.setAttribute('stroke', c.stroke);
    g.appendChild(rect);

    const title = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    title.setAttribute('x', 12);
    title.setAttribute('y', 22);
    title.setAttribute('fill', c.text);
    title.setAttribute('class', 'title');
    title.textContent = n.label + (n.children.length ? '  ▸' : '');
    g.appendChild(title);

    const loc = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    loc.setAttribute('x', NODE_W - 12);
    loc.setAttribute('y', 22);
    loc.setAttribute('text-anchor', 'end');
    loc.setAttribute('fill', '#5c6b7f');
    loc.setAttribute('class', 'attr');
    loc.textContent = n.loc;
    g.appendChild(loc);

    if (!n.collapsed) {
      n.attrs.forEach((a, i) => {
        const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        t.setAttribute('x', 12);
        t.setAttribute('y', 42 + i * 15);
        t.setAttribute('class', 'attr');
        t.setAttribute('fill', '#8b98a9');
        t.textContent = a.length > 26 ? a.slice(0, 25) + '…' : a;
        g.appendChild(t);
      });
    }
    svg.appendChild(g);
  }

  stage.appendChild(svg);

  const count = (function c(n){ return 1 + n.children.reduce((s,ch)=>s+c(ch),0); })(root);
  document.getElementById('meta').textContent = `节点 ${count} 个 · 深度 ${maxDepth + 1} 层`;
}

document.getElementById('search').addEventListener('input', (e) => {
  const q = e.target.value.trim().toLowerCase();
  document.querySelectorAll('.node').forEach(g => {
    const hit = q && g.getAttribute('data-label').toLowerCase().includes(q);
    g.classList.toggle('hit', !!hit);
    g.classList.toggle('dim', !!q && !hit);
  });
});
document.getElementById('collapse').addEventListener('click', () => {
  const root = build(AST);
  (function walk(n, d) { if (d >= 2) n.collapsed = true; n.children.forEach(c => walk(c, d + 1)); })(root, 0);
  window.__forced = root;
  render();
});
document.getElementById('expand').addEventListener('click', render);

render();
if (SOURCE) {
  const pre = document.createElement('pre');
  pre.className = 'src';
  pre.textContent = SOURCE;
  document.getElementById('stage').prepend(pre);
}
</script>
</body>
</html>
"""


def to_html(ast: Any, title: str = "Mini-ArkTS AST", source: str = "", generated: str = "") -> str:
    """把 AST 渲染为 HTML 字符串。"""
    ast_json = json.dumps(node_to_dict(ast), ensure_ascii=False)
    source_json = json.dumps(source, ensure_ascii=False)
    return (
        _HTML_TEMPLATE.replace("__TITLE__", title)
        .replace("__AST_JSON__", ast_json)
        .replace("__SOURCE_JSON__", source_json)
        .replace("__GENERATED__", generated or "—")
    )


def write_html(ast: Any, path: str | pathlib.Path, title: str = "Mini-ArkTS AST",
               source: str = "", generated: str = "") -> pathlib.Path:
    """把 AST 可视化页面写入文件，返回该路径。"""
    out = pathlib.Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(to_html(ast, title=title, source=source, generated=generated), encoding="utf-8")
    return out