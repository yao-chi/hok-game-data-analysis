# -*- coding: utf-8 -*-
"""
生成《王者荣耀》风格的模拟对局数据（用于数据分析演示）。

为什么用模拟数据：王者荣耀官方不提供开放对局数据集，本项目基于公开的
游戏机制认知（分路模板、经济成长、胜负决定因素等）构造"足够真实"的样
本，重点展示的是**数据处理与分析的完整流程**，结论的价值在于方法而非
数据来源。

生成逻辑（数值关系均来自公开认知，非真实运营数据）：
  - 每位玩家有隐藏实力 latent ~ N(0,1)，决定段位与大部分对局表现；
  - 每局为镜像阵容：双方各 1 射手 / 1 法师 / 1 刺客 / 1 辅助 + 1 边路
    （战士或坦克），英雄在该分路池内按人气权重抽取；
  - 每个分路有独立的每分钟模板（经济、输出、承伤、治疗、击杀、视野…）；
  - 胜负由 团队实力差（主）+ 团队经济差 + 推塔数 决定（sigmoid 模型）；
  - 胜负结果回馈个人数据（胜方击杀↑ 死亡↓、经济略高）。

种子固定 → 可复现。用法：python -m src.generate_data
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SEED = 42
N_MATCHES = 4200
N_PLAYERS = 900
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")

# --------------------------------------------------------------------------
# 分路英雄池（英雄 -> 风格修正，其余英雄取模板默认）
# --------------------------------------------------------------------------
POOLS = {
    "射手": ["孙尚香", "后羿", "虞姬", "狄仁杰", "伽罗", "鲁班七号", "马可波罗", "公孙离"],
    "法师": ["王昭君", "甄姬", "安琪拉", "张良", "周瑜", "貂蝉", "武则天", "干将莫邪"],
    "刺客": ["澜", "李白", "韩信", "阿轲", "兰陵王", "镜", "裴擒虎"],
    "战士": ["吕布", "宫本武藏", "花木兰", "老夫子", "典韦", "关羽", "刘备", "铠"],
    "坦克": ["白起", "廉颇", "钟馗", "张飞", "夏侯惇", "项羽", "猪八戒"],
    "辅助": ["瑶", "蔡文姬", "孙膑", "大乔", "明世隐", "牛魔", "太乙真人"],
}

POPULAR = {  # 分路内的人气权重（1.0 最高，0.3 最低）
    "孙尚香": 1.0, "公孙离": 0.9, "鲁班七号": 0.9, "后羿": 0.85, "虞姬": 0.75,
    "狄仁杰": 0.65, "伽罗": 0.6, "马可波罗": 0.7,
    "貂蝉": 1.0, "王昭君": 0.95, "张良": 0.9, "安琪拉": 0.9, "甄姬": 0.8,
    "周瑜": 0.7, "干将莫邪": 0.6, "武则天": 0.45,
    "澜": 1.0, "李白": 0.95, "韩信": 0.95, "兰陵王": 0.75, "镜": 0.8,
    "裴擒虎": 0.7, "阿轲": 0.7,
    "吕布": 1.0, "关羽": 0.9, "铠": 0.85, "典韦": 0.8, "花木兰": 0.7,
    "宫本武藏": 0.65, "老夫子": 0.55, "刘备": 0.6,
    "张飞": 1.0, "白起": 0.85, "廉颇": 0.8, "钟馗": 0.65, "夏侯惇": 0.6,
    "项羽": 0.55, "猪八戒": 0.5,
    "瑶": 1.0, "蔡文姬": 0.95, "孙膑": 0.8, "大乔": 0.7, "牛魔": 0.7,
    "太乙真人": 0.55, "明世隐": 0.45,
}

STYLE = {  # 英雄对模板的温和偏移（真实版本里英雄强度差异通常 ±3% 以内）
    "孙尚香": {"dmg": 1.06, "gpm": 1.05},
    "鲁班七号": {"dmg": 1.10, "deaths": 1.08},
    "后羿": {"dmg": 1.06},
    "干将莫邪": {"dmg": 1.08, "gpm": 0.97},
    "貂蝉": {"dmg": 1.05, "taken": 0.92},
    "武则天": {"gpm": 1.06, "dmg": 1.03},
    "张良": {"assists": 1.12, "dmg": 0.97},
    "典韦": {"dmg": 1.08, "kills": 1.06},
    "李白": {"kills": 1.06},
    "澜": {"kills": 1.10, "gpm": 1.04},
    "镜": {"kills": 1.07},
    "阿轲": {"kills": 1.07},
    "瑶": {"assists": 1.10, "healing": 1.18, "deaths": 0.93},
    "蔡文姬": {"healing": 1.25, "assists": 1.06},
    "明世隐": {"healing": 1.25, "dmg": 0.9},
    "孙膑": {"assists": 1.12, "dmg": 0.92},
    "大乔": {"assists": 1.18, "gpm": 0.95},
    "太乙真人": {"assists": 1.12, "healing": 1.10},
    "白起": {"taken": 1.10},
    "廉颇": {"taken": 1.10},
    "张飞": {"taken": 1.12},
    "牛魔": {"taken": 1.08, "assists": 1.06},
    "猪八戒": {"taken": 1.12, "healing": 1.06},
}

TMPL = {  # 分路模板：每 17.5 分钟一局的期望值（随时长线性缩放）
    "射手": dict(gpm=800, dmg=6100, taken=2000, heal=150,
                 kills=1.35, deaths=1.10, assists=0.90, cs=8.5, vision=0.95),
    "法师": dict(gpm=700, dmg=5400, taken=1950, heal=450,
                 kills=1.40, deaths=1.10, assists=1.10, cs=7.2, vision=1.2),
    "战士": dict(gpm=700, dmg=4250, taken=3600, heal=260,
                 kills=1.85, deaths=1.15, assists=0.80, cs=6.5, vision=1.1),
    "刺客": dict(gpm=690, dmg=3850, taken=1900, heal=120,
                 kills=2.50, deaths=1.30, assists=0.70, cs=6.0, vision=1.1),
    "坦克": dict(gpm=610, dmg=2100, taken=5200, heal=520,
                 kills=0.90, deaths=1.10, assists=1.50, cs=5.0, vision=1.6),
    "辅助": dict(gpm=575, dmg=1600, taken=2500, heal=2500,
                 kills=0.80, deaths=1.00, assists=1.95, cs=4.5, vision=2.3),
}

FLEX_ROLES = [("战士", 0.72), ("坦克", 0.28)]  # 边路（第 5 个位置）
FIXED_ROLES = ["射手", "法师", "刺客", "辅助"]

TIERS = ["铂金", "钻石", "星耀", "最强王者", "荣耀王者"]


def tier_of(latent: float) -> str:
    if latent > 1.15:
        return "荣耀王者"
    if latent > 0.5:
        return "最强王者"
    if latent > 0.0:
        return "星耀"
    if latent > -0.55:
        return "钻石"
    return "铂金"


def main() -> None:
    rng = np.random.default_rng(SEED)
    os.makedirs(OUT_DIR, exist_ok=True)

    latent = np.clip(rng.normal(0, 1, N_PLAYERS), -2.2, 2.2)
    player_ids = [f"P{i:04d}" for i in range(1, N_PLAYERS + 1)]

    # 各分路英雄池 + 人气权重
    pools = {r: [] for r in POOLS}
    for role, heroes in POOLS.items():
        w = np.array([POPULAR.get(h, 0.5) for h in heroes], dtype=float)
        pools[role] = (heroes, w / w.sum())

    start = date(2024, 1, 1)
    days = (date(2024, 12, 31) - start).days + 1
    day_weights = np.array([1.0 if (start + timedelta(days=i)).weekday() < 5 else 1.45
                            for i in range(days)])
    day_weights /= day_weights.sum()

    def season_of(d: date) -> str:
        if d.month <= 3:
            return "S32"
        if d.month <= 6:
            return "S33"
        if d.month <= 9:
            return "S34"
        return "S35"

    rows: list[dict] = []
    for m in range(1, N_MATCHES + 1):
        match_id = f"M2024{m:05d}"
        d = start + timedelta(days=int(rng.choice(days, p=day_weights)))
        duration = float(np.clip(rng.normal(17.5, 4.5), 7.0, 38.0))
        dur_f = duration / 17.5

        # 镜像阵容：双方同一套分路
        blue_roles = FIXED_ROLES + [rng.choice([r for r, _ in FLEX_ROLES],
                                               p=[w for _, w in FLEX_ROLES])]
        red_roles = FIXED_ROLES + [rng.choice([r for r, _ in FLEX_ROLES],
                                              p=[w for _, w in FLEX_ROLES])]

        players = rng.choice(N_PLAYERS, 10, replace=False)
        recs: list[dict] = []
        for i in range(10):
            role = (blue_roles + red_roles)[i]
            heroes, w = pools[role]
            hero = heroes[int(rng.choice(len(heroes), p=w))]
            pid = player_ids[players[i]]
            lat = latent[players[i]]
            tmpl = TMPL[role]
            st = STYLE.get(hero, {})
            sf = 1 + 0.12 * lat
            team = 0 if i < 5 else 1

            def pick(key: str) -> float:
                return tmpl[key] * st.get(key, 1.0) * sf

            kills = rng.poisson(pick("kills") * dur_f)
            deaths = rng.poisson(pick("deaths") * dur_f)
            assists = rng.poisson(pick("assists") * dur_f)
            gold = max(0, int(rng.normal(pick("gpm") * duration, 900)))
            dmg = max(0, int(rng.normal(pick("dmg") * dur_f, 1500)))
            taken = max(0, int(rng.normal(pick("taken") * dur_f, 1800)))
            heal = max(0, int(rng.normal(pick("heal") * dur_f * (1 + 0.15 * lat), 500)))
            cs = max(0, int(rng.normal(pick("cs") * dur_f, 6)))
            vision = max(0.0, round(rng.normal(pick("vision") * dur_f, 0.5), 1))

            recs.append(dict(match_id=match_id, game_date=d.isoformat(),
                             season=season_of(d), mode="排位赛-5v5",
                             duration_min=round(duration, 1),
                             team=team, player_id=pid, hero=hero, role=role,
                             lane={"射手": "发育路", "法师": "中路", "刺客": "打野",
                                   "战士": "对抗路", "坦克": "对抗路",
                                   "辅助": "游走"}[role],
                             tier=tier_of(lat),
                             kills=int(kills), deaths=int(deaths), assists=int(assists),
                             gold=gold, gpm=round(gold / duration, 1),
                             damage_dealt=dmg, damage_taken=taken,
                             healing=heal, cs=cs, vision_score=vision, _lat=lat))

        bg = sum(r["gold"] for r in recs if r["team"] == 0)
        rg = sum(r["gold"] for r in recs if r["team"] == 1)
        bk = sum(r["kills"] for r in recs if r["team"] == 0)
        rk = sum(r["kills"] for r in recs if r["team"] == 1)
        bskill = float(np.mean([recs[i]["_lat"] for i in range(5)]))
        rskill = float(np.mean([recs[i]["_lat"] for i in range(5, 10)]))

        bt = int(np.clip(round(2.5 + 5.6 + bskill * 1.2 + rng.normal(0, 1.2)), 0, 11))
        rt = int(np.clip(round(2.5 + rskill * 1.2 + rng.normal(0, 1.2)), 0, 11))

        # 胜率模型：实力差为主，经济/推塔为辅
        x = 0.95 * (bskill - rskill) + (bg - rg) / 28000 + 0.12 * (bt - rt)
        p_blue = 1 / (1 + np.exp(-x))
        blue_win = bool(rng.random() < p_blue)

        bb = int(np.clip(round(rng.normal(2.3, 1.1)), 0, 6))
        rb = int(np.clip(round(rng.normal(1.2, 0.9)), 0, 6))

        for team_id, win in ((0, blue_win), (1, not blue_win)):
            wmul, dmul, gm = (1.16, 0.76, 1.05) if win else (0.84, 1.24, 0.96)
            for r in recs:
                if r["team"] != team_id:
                    continue
                r["kills"] = max(0, int(r["kills"] * wmul * rng.uniform(0.92, 1.08)))
                r["deaths"] = max(0, int(r["deaths"] * dmul * rng.uniform(0.92, 1.08)))
                r["gold"] = max(0, int(r["gold"] * gm))
                r["win"] = int(win)
                share = {"辅助": 0.30, "坦克": 0.24, "刺客": 0.20, "战士": 0.12,
                         "法师": 0.09, "射手": 0.05}[r["role"]]
                r["buffs"] = int(rng.poisson((bb if team_id == 0 else rb) * share))
                r["towers"] = int(rng.poisson(max(0, (bt if team_id == 0 else rt)
                                                  * (0.30 if r["role"] == "射手" else 0.14))))
        # 用回馈后的实际值重算团队汇总
        bg2 = sum(r["gold"] for r in recs if r["team"] == 0)
        rg2 = sum(r["gold"] for r in recs if r["team"] == 1)
        bk2 = sum(r["kills"] for r in recs if r["team"] == 0)
        rk2 = sum(r["kills"] for r in recs if r["team"] == 1)
        for r in recs:
            r["team_gold"] = (bg2 if r["team"] == 0 else rg2)
            r["team_kills_total"] = (bk2 if r["team"] == 0 else rk2)
            r["team_towers"] = (bt if r["team"] == 0 else rt)

        # 胜/败方 MVP
        for team_id in (0, 1):
            sub = [r for r in recs if r["team"] == team_id]
            win = sub[0]["win"] == 1
            best = max(sub, key=lambda r: (r["kills"] + 0.55 * r["assists"]
                                           - 0.45 * r["deaths"]
                                           + r["damage_dealt"] / 15000
                                           + 4 * r["gold"] / r["team_gold"]))
            for r in sub:
                r["mvp"] = 1 if r is best else 0
                r["mvp_label"] = ("胜方MVP" if win else "败方MVP") if r is best else ""

        for r in recs:
            r.pop("_lat", None)
        rows.extend(recs)

    df = pd.DataFrame(rows)
    out = os.path.join(OUT_DIR, "matches.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[generate_data] 已生成 {len(df):,} 条玩家对局记录（{N_MATCHES} 场）→ {out}")
    print("  场均总击杀:", round(df.groupby('match_id')['kills'].sum().mean(), 2))
    print("  平均 KDA   :", round(df.assign(
        k=(df.kills + df.assists) / df.deaths.clip(lower=1))['k'].mean(), 2))
    print("  分路取人   :", df.groupby('role')['win'].mean().round(3).to_dict())


if __name__ == "__main__":
    main()