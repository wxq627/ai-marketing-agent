"""
知识图谱可视化引擎 v3 — kg_viz.py
================================
Plotly 交互式力导向图: 彩色关系边 | 方向箭头 | 深度颜色渐变
"""
import networkx as nx
import plotly.graph_objects as go
import numpy as np
from typing import Dict, Optional, List, Tuple

TYPE_COLORS = {
    "product": "#4A90D9", "benefit": "#52C41A", "campaign": "#FA8C16",
    "customer": "#F5222D", "card": "#722ED1", "document": "#8C8C8C",
    "installment_rule": "#13C2C2",
}
TYPE_LABELS_ZH = {
    "product": "产品", "benefit": "权益", "campaign": "活动",
    "customer": "客户", "card": "信用卡", "document": "文档",
    "installment_rule": "分期条款",
}

# 关系 → 颜色 + 中文 (仅直接关系)
RELATION_STYLES = {
    "INCLUDES":        ("rgba(82,196,26,0.55)",  "包含权益"),
    "APPLIES_TO":      ("rgba(250,140,22,0.55)",  "活动适用"),
    "TARGETS":         ("rgba(245,34,45,0.50)",   "面向客户"),
    "HOLDS":           ("rgba(114,46,209,0.55)",  "持有"),
    "BELONGS_TO":      ("rgba(114,46,209,0.40)",  "属于产品"),
    "GOVERNED_BY":     ("rgba(19,194,194,0.45)",  "分期规则"),
    "RELATES_TO":      ("rgba(140,140,140,0.35)", "关联文档"),
}
RELATION_LABELS_ZH = {k: v[1] for k, v in RELATION_STYLES.items()}

DEPTH_ALPHA = {0: 1.0, 1: 0.85, 2: 0.55, 3: 0.35}


def _depth_color(base_color: str, depth: int) -> str:
    alpha = DEPTH_ALPHA.get(depth, 0.3)
    if base_color.startswith("#"):
        r, g, b = int(base_color[1:3], 16), int(base_color[3:5], 16), int(base_color[5:7], 16)
        return f"rgba({r},{g},{b},{alpha})"
    return base_color


def render_interactive(kg, center_id: str, depth: int = 1, height: int = 650) -> go.Figure:
    """渲染交互式知识图谱 (Plotly 力导向图).

    特性:
      - 彩色关系边(9种关系各有独立颜色和线型)
      - 方向箭头(小三角形)
      - 深度颜色渐变(中心亮→边缘淡)
      - 悬停显示节点详情
    """
    sub = kg.get_subgraph(center_id, depth)
    nodes, edges = sub["nodes"], sub["edges"]
    if not nodes:
        return None

    G = nx.Graph()
    for n in nodes:
        G.add_node(n["id"])
    for e in edges:
        G.add_edge(e["from"], e["to"])
    if len(G) == 0:
        return None

    pos = nx.spring_layout(G, k=1.5, iterations=100, seed=42, scale=5)

    # ═══ 边 — 每种关系一个独立彩色trace ═══
    traces = []

    # 按关系类型分组
    edges_by_rel = {}
    for e in edges:
        rel = e.get("label", "")
        edges_by_rel.setdefault(rel, []).append(e)

    for rel, rel_edges in edges_by_rel.items():
        style = RELATION_STYLES.get(rel, ("rgba(255,255,255,0.25)", rel))
        color, zh_name = style

        line_x, line_y = [], []
        text_x, text_y, text_str = [], [], []

        for e in rel_edges:
            if e["from"] not in pos or e["to"] not in pos:
                continue
            x0, y0 = pos[e["from"]]
            x1, y1 = pos[e["to"]]

            # 主线
            line_x.extend([x0, x1, None])
            line_y.extend([y0, y1, None])

            # 中点文字
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            text_x.append(mx)
            text_y.append(my)
            text_str.append(zh_name)

            # 方向箭头 (from → to)
            dx, dy = x1 - x0, y1 - y0
            length = np.sqrt(dx**2 + dy**2) + 1e-8
            ux, uy = dx / length, dy / length
            tip_x = x1 - ux * 0.18
            tip_y = y1 - uy * 0.18
            w1x = tip_x - ux * 0.1 - uy * 0.06
            w1y = tip_y - uy * 0.1 + ux * 0.06
            w2x = tip_x - ux * 0.1 + uy * 0.06
            w2y = tip_y - uy * 0.1 - ux * 0.06
            line_x.extend([tip_x, w1x, None, tip_x, w2x, None])
            line_y.extend([tip_y, w1y, None, tip_y, w2y, None])

        # 每种关系: 边线 + 文字标注 (两条trace共享同一图例)
        traces.append(go.Scatter(
            x=line_x, y=line_y,
            mode="lines",
            line=dict(width=1.2, color=color),
            hoverinfo="text",
            hovertext=zh_name,
            name=zh_name,
            showlegend=True,
            legendgroup=rel,
        ))
        if text_x:
            traces.append(go.Scatter(
                x=text_x, y=text_y,
                mode="text",
                text=text_str,
                textfont=dict(size=6, color=color.replace("0.6", "0.5").replace("0.55", "0.45").replace("0.5", "0.4").replace("0.45", "0.35")),
                hoverinfo="none",
                showlegend=False,
                legendgroup=rel,
            ))

    # ═══ 节点 — 按类型分组，每个类型一个trace ═══
    center_name = ""
    for ntype, base_color in TYPE_COLORS.items():
        type_nodes_all = [n for n in nodes if n.get("type") == ntype and n["id"] in pos]
        if not type_nodes_all:
            continue

        xs, ys, sizes, labels, hover_texts, colors = [], [], [], [], [], []
        for n in type_nodes_all:
            d = n.get("depth", 1)
            xs.append(pos[n["id"]][0])
            ys.append(pos[n["id"]][1])
            sizes.append(32 if n["id"] == center_id else (18 if d <= 1 else 11))
            colors.append(_depth_color(base_color, d))

            name = str(n.get("name", n["id"]))
            if n["id"] == center_id:
                labels.append(name[:15])
                center_name = name[:15]
            elif d <= 1:
                labels.append(name[:8])
            else:
                labels.append("")

            # 悬停信息
            zh_type = TYPE_LABELS_ZH.get(ntype, ntype)
            parts = [f"<b>{zh_type}</b>: {name[:30]}", f"深度: {d}"]
            for k, v in list(n.get("attrs", {}).items())[:4]:
                if v and not isinstance(v, (dict, list)):
                    parts.append(f"{k}: {str(v)[:40]}")
            hover_texts.append("<br>".join(parts[:6]))

        traces.append(go.Scatter(
            x=xs, y=ys,
            mode="markers+text",
            name=TYPE_LABELS_ZH.get(ntype, ntype),
            text=labels,
            textposition="middle right",
            textfont=dict(size=7.5, color="#ccc"),
            marker=dict(
                size=sizes, color=colors,
                line=dict(width=1.5, color="rgba(255,255,255,0.3)"),
                symbol="circle",
            ),
            hovertext=hover_texts,
            hoverinfo="text",
            hovertemplate="%{hovertext}<extra></extra>",
        ))

    # ═══ 布局 ═══
    fig = go.Figure(data=traces)
    fig.update_layout(
        title=dict(
            text=f"<b>{center_name}</b> (深度={depth}) | {len(nodes)}节点 {len(edges)}边",
            font=dict(color="#ccc", size=14),
        ),
        showlegend=True,
        legend=dict(
            x=0.01, y=0.99,
            bgcolor="rgba(15,15,25,0.9)",
            font=dict(color="#ccc", size=9),
            bordercolor="rgba(255,255,255,0.1)", borderwidth=1,
            title=dict(text="图例: 关系类型", font=dict(color="#ccc", size=10)),
        ),
        height=height,
        margin=dict(l=20, r=20, t=50, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-7.5, 7.5]),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-7.5, 7.5]),
        hovermode="closest",
    )
    return fig


def render_graph_summary(kg, center_id: str, depth: int = 1) -> Tuple[List[Dict], Dict]:
    """生成图谱文字摘要 (用于搜索结果)。"""
    sub = kg.get_subgraph(center_id, depth)
    nodes, edges = sub["nodes"], sub["edges"]
    paths_by_rel = {}
    for e in edges:
        rel = e.get("label", "")
        from_n = next((n for n in nodes if n["id"] == e["from"]), None)
        to_n = next((n for n in nodes if n["id"] == e["to"]), None)
        if from_n and to_n:
            zh = RELATION_LABELS_ZH.get(rel, rel)
            paths_by_rel.setdefault(zh, []).append({
                "from": from_n.get("name", e["from"])[:25],
                "to": to_n.get("name", e["to"])[:25],
            })
    stats = {"total_nodes": len(nodes), "total_edges": len(edges)}
    return paths_by_rel, stats


def export_cypher(kg, output_path: str = "init_graph.cypher"):
    """导出 Neo4j Cypher 脚本。"""
    lines = [
        "// Neo4j 知识图谱初始化脚本",
        f"// {kg.G.number_of_nodes()} 节点, {kg.G.number_of_edges()} 边",
        "",
    ]
    for n, d in kg.G.nodes(data=True):
        ntype = d.get("type", "unknown")
        label = ntype.capitalize()
        name = str(d.get("name", n)).replace("'", "\\'")[:100]
        props = ", ".join([
            f"{k}: '{str(v)[:100]}'" for k, v in d.items()
            if k not in ("type", "label") and v and not isinstance(v, (dict, list))
        ])
        lines.append(f"CREATE (:{label} {{id: '{n}', name: '{name}', {props}}});")
    for u, v, k, data in kg.G.edges(data=True, keys=True):
        rel = data.get("relation", "RELATES_TO").upper()
        lines.append(f"MATCH (a {{id: '{u}'}}), (b {{id: '{v}'}}) CREATE (a)-[:{rel}]->(b);")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return output_path
