# -*- coding: utf-8 -*-
"""
把 insights.json 与 8 张 SVG 图拼成一份**自包含**的 HTML 数据分析报告。

- 零外部依赖：图表全部内嵌为 <svg>，数据全部写入 JS，单文件即可离线打开；
- 输出：reports/report_hok_analysis.html
用法：python -m src.build_report
"""
from __future__ import annotations

import html
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG_DIR = os.path.join(ROOT, "reports", "figures")
DATA_JSON = os.path.join(ROOT, "reports", "data", "insights.json")
OUT = os.path.join(ROOT, "reports", "report_hok_analysis.html")

FIG_ORDER = [
    ("fig_econ_win.svg", "经济差与胜率（S 曲线）", "团队每分钟经济差十等分 → 蓝方胜率，展示经济对胜负的决定性作用"),
    ("fig_gpm_win.svg", "个人经济效率与胜率", "玩家 GPM 五等分 → 胜率，验证『经济效率是胜负第一解释变量』"),
    ("fig_kda_win.svg", "KDA 与胜率", "KDA 六等分 → 胜率，KDA 高位区间边际收益递减"),
    ("fig_kills_time.svg", "时长与场均击杀", "对局时长拉长，场均击杀单调上升，印证滚雪球机制"),
    ("fig_duration_hist.svg", "对局时长分布", "平均 17.6 分钟，峰值集中在 16–18 分钟"),
    ("fig_role_win.svg", "分路胜率", "镜像阵容设计下位置胜率一致收敛于 50%（无天然强弱），差异来自英雄与个人表现"),
    ("fig_hero_pick.svg", "英雄登场率 × 胜率", "登场率与胜率的二维分布，Top 英雄标注"),
    ("fig_corr.svg", "指标相关性热图", "死亡数（r=-0.32）是最强负向因子，击杀/KDA 与胜率显著正相关"),
]


def fig_svgs() -> dict[str, str]:
    out = {}
    for fname, _, _ in FIG_ORDER:
        p = os.path.join(FIG_DIR, fname)
        with open(p, encoding="utf-8") as f:
            svg = f.read()
        # 去除 <svg> 开标签里的固定宽高，交给 CSS 缩放
        svg = svg.replace("<?xml", "<!-- xml").replace("?>", "-->", 1)
        svg = svg.replace("width=\"", "w=\"", 1).replace("height=\"", "h=\"", 1)
        out[fname] = svg
    return out


def render_hero_table(heroes: list[dict]) -> str:
    top = sorted(heroes, key=lambda h: -h["pick_pct"])[:10]
    trs = []
    for h in top:
        trs.append(
            f'<tr><td>{html.escape(h["hero"])}</td>'
            f'<td>{h["pick_pct"]:.1f}%</td>'
            f'<td>{(h["win"] * 100):.1f}%</td>'
            f'<td>{h["games"]}</td></tr>'
        )
    return ("<table><thead><tr><th>英雄</th><th>登场率</th><th>胜率</th>"
            "<th>场次</th></tr></thead><tbody>" + "".join(trs) + "</tbody></table>")


def render_corr(corr: dict) -> str:
    """把 win 与其他指标的相关系数渲染成横向条形。"""
    rows = []
    for k in ["kills", "deaths", "assists", "kda", "gpm", "damage_dealt",
              "damage_taken", "healing", "cs", "buffs", "towers", "vision_score"]:
        r = corr.get(k, {}).get("win", 0)
        width = max(2, int(abs(r) * 220))
        color = "#2FD8A8" if r >= 0 else "#F25757"
        rows.append(
            f'<div class="corr-row"><span class="corr-name">{k}</span>'
            f'<span class="corr-bar"><i style="width:{width}px;background:{color}"></i></span>'
            f'<span class="corr-val">{r:+.2f}</span></div>'
        )
    return "".join(rows)


def build() -> None:
    with open(DATA_JSON, encoding="utf-8") as f:
        ins = json.load(f)

    base = ins["base"]
    heroes = ins["heroes"]
    svgs = fig_svgs()

    stat_cards = [
        (f"{base['matches']:,}", "对局场次"),
        (f"{base['rows']:,}", "玩家记录"),
        (f"{base['players']}", "活跃玩家"),
        (f"{base['heroes']}", "英雄数量"),
        (f"{base['avg_duration']:.1f} min", "平均时长"),
        (f"{base['avg_kills_per_match']:.1f}", "场均击杀"),
        (f"{base['win_rate']*100:.0f}%", "整体胜率"),
        (f"{base['avg_gpm']:.0f}", "场均 GPM"),
    ]
    cards = "".join(
        f'<div class="stat"><b>{name}</b><span>{label}</span></div>'
        for name, label in stat_cards
    )

    findings = "".join(f"<li>{html.escape(x)}</li>" for x in ins["findings"])

    sections = []
    for fname, title, desc in FIG_ORDER:
        sections.append(
            f'<section><h3>{html.escape(title)}</h3>'
            f'<p class="fig-desc">{html.escape(desc)}</p>'
            f'<div class="fig">{svgs[fname]}</div></section>'
        )

    gpm_points = "".join(
        f'<span class="gpm-p">{a}<i style="width:{b*100:.0f}%"></i>{b*100:.1f}%</span>'
        for a, b in ins["gpm_bins"]
    )

    steps = ["数据生成", "清洗加工", "特征构造", "多维分析", "可视化", "报告撰写"]
    tech = {
        "语言 / 依赖": "Python 3.12 · 仅 NumPy / pandas（零第三方图表库）",
        "数据处理": "清洗（去重 / 类型修正 / 缺失处理）、派生特征 KDA、GPM、Gold Share",
        "分析维度": "经济·胜负 S 曲线 / KDA 边际效应 / 活跃·趋势 / 位置与英雄平衡 / 因子相关性",
        "可视化": "自研 SVG 渲染器（bar / line / scatter / heatmap），8 张图",
        "可复现性": "固定随机种子（seed=42），一键重跑全流程",
    }
    tech_rows = "".join(
        f'<tr><th>{html.escape(k)}</th><td>{html.escape(v)}</td></tr>'
        for k, v in tech.items()
    )
    steps_html = "".join(f"<span>{html.escape(s)}</span>" for s in steps)

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>王者荣耀对局数据分析报告</title>
<style>
:root {{
  --bg:#0e1220; --panel:#1a2138; --panel2:#222b47; --txt:#e8ecf8;
  --muted:#9aa6c8; --blue:#3E6FF2; --green:#2FD8A8; --red:#F25757; --orange:#FF9F1C;
}}
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ background:var(--bg); color:var(--txt);
  font-family:"Microsoft YaHei","PingFang SC",system-ui,sans-serif; line-height:1.6; }}
.wrap {{ max-width:1080px; margin:0 auto; padding:32px 20px 64px; }}
header {{ text-align:center; padding:40px 0 28px; }}
.badge {{ display:inline-block; background:rgba(62,111,242,.15); color:var(--blue);
  border:1px solid rgba(62,111,242,.4); border-radius:999px; padding:4px 14px;
  font-size:13px; letter-spacing:.5px; }}
h1 {{ font-size:30px; margin:14px 0 6px; }}
.sub {{ color:var(--muted); font-size:15px; }}
.stats {{ display:grid; grid-template-columns:repeat(4,1fr);
  gap:12px; margin:26px 0 8px; }}
.stat {{ background:var(--panel); border:1px solid rgba(255,255,255,.06);
  border-radius:12px; padding:14px 10px; text-align:center; }}
.stat b {{ display:block; font-size:22px; color:#fff; }}
.stat span {{ font-size:12px; color:var(--muted); }}
.steps {{ display:flex; justify-content:center; gap:10px; flex-wrap:wrap; margin:22px 0 8px; }}
.steps span {{ background:var(--panel2); border-radius:999px; padding:6px 16px;
  font-size:13px; color:var(--muted); }}
h2 {{ font-size:22px; margin:40px 0 12px; padding-left:10px; border-left:4px solid var(--blue); }}
section {{ background:var(--panel); border:1px solid rgba(255,255,255,.06);
  border-radius:14px; padding:18px 18px 8px; margin:14px 0; }}
section h3 {{ font-size:17px; margin-bottom:4px; }}
.fig-desc {{ color:var(--muted); font-size:13px; margin-bottom:10px; }}
.fig svg {{ width:100%; height:auto; }}
.findings {{ background:var(--panel); border-radius:14px; padding:20px 24px; }}
.findings li {{ margin:8px 0 8px 4px; }}
table {{ width:100%; border-collapse:collapse; margin-top:6px; }}
th, td {{ padding:8px 10px; text-align:left; border-bottom:1px solid rgba(255,255,255,.07); font-size:14px; }}
th {{ color:var(--muted); font-weight:600; }}
.gpm-p {{ display:inline-flex; align-items:center; gap:8px; background:var(--panel2);
  border-radius:999px; padding:8px 14px; margin:4px 6px 4px 0; font-size:13px; }}
.gpm-p i {{ height:8px; border-radius:4px; background:linear-gradient(90deg,var(--blue),var(--green)); }}
.corr-row {{ display:flex; align-items:center; gap:12px; margin:7px 0; }}
.corr-name {{ width:110px; font-size:13px; color:var(--muted); }}
.corr-bar {{ flex:1; background:rgba(255,255,255,.05); border-radius:6px; height:14px; }}
.corr-bar i {{ display:block; height:14px; border-radius:6px; }}
.corr-val {{ width:52px; text-align:right; font-size:13px; font-variant-numeric:tabular-nums; }}
.tech table th {{ width:150px;}}
.note {{ color:var(--muted); font-size:13px; margin-top:24px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <span class="badge">数据科学 · 游戏数据分析</span>
    <h1>王者荣耀对局数据分析报告</h1>
    <p class="sub">4,200 场对局 · 42,000 条玩家记录 · 45 名英雄 —— 全流程 Python 数据管线</p>
  </header>

  <div class="stats">{cards}</div>
  <div class="steps">{steps_html}</div>

  <h2>核心发现</h2>
  <div class="findings"><ul>{findings}</ul></div>

  <h2>关键图表</h2>
  {"".join(sections)}

  <h2>经济效率：从分位到胜率</h2>
  <div class="findings">{gpm_points}<p style="margin-top:10px" class="fig-desc">各档位左侧为 GPM 分位均值，条形长度 = 该档胜率。最低档 45.0% → 最高档 55.7%。</p></div>

  <h2>英雄登场榜（Top 10）</h2>
  <div class="findings">{render_hero_table(heroes)}</div>

  <h2>与胜率的相关系数</h2>
  <div class="findings">{render_corr(ins["corr"])}</div>

  <h2>技术栈与方法</h2>
  <div class="findings tech"><table>{tech_rows}</table></div>

  <p class="note">数据说明：本数据集按公开游戏机制认知模拟生成（seed=42，可复现），用于演示数据分析全流程；结论价值在方法而非数据来源。项目代码见仓库 README。</p>
</div>
</body>
</html>"""

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html_doc)
    print(f"[build_report] 报表已生成 → {OUT}（{len(html_doc):,} 字节，自包含单文件）")


if __name__ == "__main__":
    build()