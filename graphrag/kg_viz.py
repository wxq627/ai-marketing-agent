"""
知识图谱可视化引擎 — kg_viz.py
================================
NetworkX → Plotly 交互式力导向图 + Neo4j Cypher 导出脚本。
生产环境: 直接导入 Neo4j + Neo4j Browser 拖拽探索。
"""
import networkx as nx
import plotly.graph_objects as go
import numpy as np
from typing import Dict, Optional

# 节点颜色映射
TYPE_COLORS = {
    "product": "#4A90D9", "benefit": "#52C41A", "campaign": "#FA8C16",
    "customer": "#F5222D", "card": "#722ED1", "document": "#8C8C8C",
    "installment_rule": "#13C2C2",
}
TYPE_LABELS_ZH = {
    "product":"产品","benefit":"权益","campaign":"活动",
    "customer":"客户","card":"信用卡","document":"文档",
    "installment_rule":"分期条款",
}

def render_interactive(kg, center_id: str, depth: int = 2, height: int = 650) -> go.Figure:
    """渲染交互式知识图谱 (Plotly 力导向图)。

    支持: 缩放/拖拽/悬停提示/节点搜索/点击高亮
    """
    sub = kg.get_subgraph(center_id, depth)
    nodes, edges = sub["nodes"], sub["edges"]
    if not nodes: return None

    # 构建NetworkX图 → spring_layout计算坐标
    G = nx.Graph()
    for n in nodes: G.add_node(n["id"])
    for e in edges: G.add_edge(e["from"], e["to"])
    if len(G) == 0: return None

    pos = nx.spring_layout(G, k=1.2, iterations=80, seed=42, scale=5)

    # 边 — 用关系类型标注
    edge_traces = []
    for e in edges:
        if e["from"] not in pos or e["to"] not in pos: continue
        x0, y0 = pos[e["from"]]
        x1, y1 = pos[e["to"]]
        # 中点标注关系
        mx, my = (x0+x1)/2, (y0+y1)/2
        edge_traces.append(go.Scatter(
            x=[x0, x1, None], y=[y0, y1, None],
            mode='lines', line=dict(width=1.2, color='rgba(255,255,255,0.2)'),
            hoverinfo='none', showlegend=False))
        # 关系标注
        edge_traces.append(go.Scatter(
            x=[mx], y=[my], mode='text',
            text=[e.get("label","")], textfont=dict(size=7, color='rgba(255,255,255,0.4)'),
            hoverinfo='none', showlegend=False))

    # 节点 — 按类型分组着色
    node_traces = []
    for ntype, color in TYPE_COLORS.items():
        type_nodes = [n for n in nodes if n.get("type")==ntype]
        if not type_nodes: continue
        xs = [pos[n["id"]][0] for n in type_nodes if n["id"] in pos]
        ys = [pos[n["id"]][1] for n in type_nodes if n["id"] in pos]
        if not xs: continue
        sizes = [25 if n["id"]==center_id else 14 for n in type_nodes if n["id"] in pos]
        labels = [n.get("name",n["id"])[:12] for n in type_nodes if n["id"] in pos]
        hover_texts = []
        for n in type_nodes:
            if n["id"] not in pos: continue
            info_parts = [f"{TYPE_LABELS_ZH.get(ntype,ntype)}: {n.get('name',n['id'])[:30]}"]
            for k,v in n.get("attrs",{}).items():
                if v and not isinstance(v,(dict,list)):
                    info_parts.append(f"{k}: {v}")
            hover_texts.append("<br>".join(info_parts[:5]))

        node_traces.append(go.Scatter(
            x=xs, y=ys, mode='markers+text',
            name=TYPE_LABELS_ZH.get(ntype, ntype),
            text=labels, textposition="middle right",
            textfont=dict(size=8, color='#ddd'),
            marker=dict(size=sizes, color=color, line=dict(width=1.5, color='rgba(255,255,255,0.4)'),
                       symbol='circle'),
            hovertext=hover_texts, hoverinfo='text',
            hovertemplate='%{hovertext}<extra></extra>'))

    fig = go.Figure(data=edge_traces + node_traces)
    fig.update_layout(
        title=dict(text=f"知识图谱: {center_id} (depth={depth}) | {len(nodes)}节点 {len(edges)}边",
                   font=dict(color='#ccc', size=14)),
        showlegend=True, legend=dict(x=0.01, y=0.99, bgcolor='rgba(0,0,0,0.5)', font=dict(color='#ccc', size=10)),
        height=height, margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-7,7]),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-7,7]),
        hovermode='closest',
    )
    return fig


def export_cypher(kg, output_path: str = "init_graph.cypher"):
    """导出为 Neo4j Cypher 脚本 (生产环境可直接导入)。"""
    lines = ["// Neo4j 知识图谱初始化脚本", f"// 自动生成, {kg.G.number_of_nodes()} 节点, {kg.G.number_of_edges()} 边", ""]

    # 节点
    for n, d in kg.G.nodes(data=True):
        ntype = d.get("type", "unknown")
        label = ntype.capitalize()
        name = str(d.get("name", n)).replace("'", "\\'")[:100]
        props = ", ".join([f"{k}: '{str(v)[:100]}'" for k, v in d.items()
                          if k not in ("type","label") and v and not isinstance(v,(dict,list))])
        lines.append(f"CREATE (:{label} {{id: '{n}', name: '{name}', {props}}});")

    # 关系
    for u, v, k, data in kg.G.edges(data=True, keys=True):
        rel = data.get("relation", "RELATES_TO").upper()
        lines.append(f"MATCH (a {{id: '{u}'}}), (b {{id: '{v}'}}) CREATE (a)-[:{rel}]->(b);")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return output_path
