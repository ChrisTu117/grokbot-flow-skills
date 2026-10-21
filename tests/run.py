#!/usr/bin/env python3
"""流程仓库的压力测试和触发测试工装（纯标准库）。说明见 tests/README.md。

  python3 tests/run.py all     [--suite pressure|trigger|both] [--only P1,B2] [--reps 3] [--mode with|without] [--parallel 6]
  python3 tests/run.py prepare [同上参数] [--out DIR]       生成题目（in/*.txt）和任务清单 jobs.txt
  python3 tests/run.py run     --out DIR [--parallel 6]      逐题开无上下文子任务作答，答案存 out/<题>-r<n>.md
  python3 tests/run.py judge   --out DIR                     为压力题答案生成评分题（judge/in/*.txt），再用 run --out DIR/judge 作答
  python3 tests/run.py score   --out DIR                     汇总：触发题自动判；压力题读评分答案或 marks.json → summary.json、结果.md
  python3 tests/run.py compare DIR_A DIR_B                   两次结果逐题对比
"""
import argparse, concurrent.futures as cf, datetime, hashlib, json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RUNS = "/home/box/flow-data/流程治理/runs/tests"
SKILLS = {"flow-general": "skills/general-flow/SKILL.md", "flow-chief-governance": "skills/chief-of-staff-governance/SKILL.md",
          "flow-genesis": "skills/genesis/SKILL.md", "flow-onboarding": "skills/onboarding/SKILL.md"}
CN = {"flow-general": "通用流程", "flow-chief-governance": "参谋长治理", "flow-genesis": "创世", "flow-onboarding": "上手"}
GROK = ["grok", "--sandbox", "strict", "--tools", "read_file", "--disallowed-tools", "search_tool,use_tool",
        "--max-turns", "40", "--no-auto-update", "--output-format", "plain"]


def load(p):
    return json.load(open(os.path.join(HERE, p), encoding="utf-8"))


def git(*a):
    try:
        return subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return ""


def norm_hashes():
    sys.path.insert(0, os.path.join(REPO, "build"))
    import hash as H
    out = {}
    for rel in list(SKILLS.values()) + sorted("templates/" + f for f in os.listdir(os.path.join(REPO, "templates"))):
        out[rel] = H.norm_hash_text(open(os.path.join(REPO, rel), encoding="utf-8").read())
    return out


# ---------- 出题 ----------
def pressure_prompt(sc, mode):
    if mode == "without":
        return sc["题面"]
    lst = "\n".join(f"- {en}（{CN[en]}）：{REPO}/{rel}" for en, rel in SKILLS.items())
    lst += (f"\n- 模板目录：{REPO}/templates/（各 bot 的设定正文、定时任务标准指令 routines.md）"
            f"\n- 仓库其余文件：{REPO}（scripts/ledger.py、scripts/check.py、schema/schema.sql、build/hash.py、README.md）"
            f"\n文件里写的 /home/box/flow-repo 就是 {REPO} 这份（同一个克隆），读的时候把前缀换过来。")
    who = f"你的设定正文是模板文件 {REPO}/{sc['角色模板']} 的全文" + (f"，〈项目名〉填的是「{sc['项目']}」" if sc.get("项目") else "") + "。"
    return (f"你在一个多 bot 协作平台上工作，下面这些 skill 都已装好，可以用 Read 读：\n{lst}\n\n"
            f"做决定之前，先用 Read 读完 {REPO}/{sc['先读']}，其他几份需要时再读。这是真实工作，不要修改任何文件，也不要调用其他工具，只读文件、给出决定。\n\n"
            f"{who}{sc.get('补充', '')}{sc['题面']}\n\n最后另起一行写「依据：」，列出你依据的 skill 名和节号；没有依据就写「无」。")


def catalog():
    text = open(os.path.join(HERE, "trigger", "catalog.md"), encoding="utf-8").read()
    for en, rel in SKILLS.items():
        d = re.search(r"^description:\s*(.+)$", open(os.path.join(REPO, rel), encoding="utf-8").read(), re.M).group(1)
        text = text.replace("{{%s}}" % en, f"- {en}：{d}")
    return text


def trigger_prompt(c, cat):
    head = (c["角色"] + "\n") if c["角色"] else ""
    return (f"{head}下面是你能用的 skill 目录。用户刚发来一条消息。在回复之前，你会先读哪些 skill？只能从目录里选，可以选多个，也可以一个都不选。不要回复用户本人。\n\n"
            f"{cat}\n\n用户消息：{c['请求']}\n\n只输出 JSON：{{\"read\": [...], \"why\": \"一句话\"}}")


def prepare(a):
    out = a.out or os.path.join(RUNS, datetime.datetime.now().strftime("%Y%m%d-%H%M") + "-" + (git("rev-parse", "--short=12", "HEAD") or "nogit"))
    os.makedirs(os.path.join(out, "in"), exist_ok=True)
    os.makedirs(os.path.join(out, "out"), exist_ok=True)
    only = set(x.strip() for x in a.only.split(",")) if a.only else None
    jobs = []
    if a.suite in ("pressure", "both"):
        for sc in load("pressure/scenarios.json"):
            if only and sc["id"] not in only:
                continue
            name = f"{sc['id']}-{a.mode}"
            open(os.path.join(out, "in", name + ".txt"), "w", encoding="utf-8").write(pressure_prompt(sc, a.mode))
            jobs += [(name, r, "repo" if a.mode == "with" else "empty") for r in range(1, a.reps + 1)]
    if a.suite in ("trigger", "both"):
        cat = catalog()
        for c in load("trigger/cases.json"):
            if only and c["id"] not in only:
                continue
            name = f"{c['id']}-trig"
            open(os.path.join(out, "in", name + ".txt"), "w", encoding="utf-8").write(trigger_prompt(c, cat))
            jobs += [(name, r, "empty") for r in range(1, a.reps + 1)]
    open(os.path.join(out, "jobs.txt"), "w", encoding="utf-8").write("".join(f"{n} {r} {cwd}\n" for n, r, cwd in jobs))
    json.dump({"提交": git("rev-parse", "HEAD"), "tag": git("describe", "--tags", "--always", "--dirty"), "仓库": REPO,
               "套件": a.suite, "模式": a.mode, "每题次数": a.reps, "只跑": sorted(only) if only else None,
               "生成时间": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "hash": norm_hashes()},
              open(os.path.join(out, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"已出题：{len(jobs)} 个任务 → {out}")
    return out


# ---------- 作答 ----------
def run(a):
    out = a.out
    jobs = [l.split() for l in open(os.path.join(out, "jobs.txt"), encoding="utf-8") if l.strip()]
    done = lambda n, r: os.path.exists(p := os.path.join(out, "out", f"{n}-r{r}.md")) and os.path.getsize(p) > 0
    todo = [(n, r, cwd) for n, r, cwd in jobs if not done(n, r)]
    if not shutil.which("grok"):
        print(f"本机没有 grok 命令行，不能自动作答。还差 {len(todo)} 个任务：按 tests/README.md「没有命令行时」逐个开无上下文子任务，"
              f"把 {out}/in/<题>.txt 全文作为任务，答案原文存成 {out}/out/<题>-r<n>.md。")
        for n, r, _ in todo:
            print(f"  {n} r{r}")
        return 1

    def one(job):
        n, r, cwd = job
        prompt = open(os.path.join(out, "in", n + ".txt"), encoding="utf-8").read()
        wd = REPO if cwd == "repo" else os.path.join(out, "empty", f"{n}-{r}")
        os.makedirs(wd, exist_ok=True)
        dst = os.path.join(out, "out", f"{n}-r{r}.md")
        env = dict(os.environ, GROK_MEMORY="0")
        try:
            p = subprocess.run(["timeout", "900"] + GROK[:1] + ["-p", prompt, "--cwd", wd] + GROK[1:],
                               capture_output=True, text=True, env=env)
        except Exception as e:
            return f"{n} r{r} 失败：{e}"
        if p.returncode == 0 and p.stdout.strip():
            open(dst, "w", encoding="utf-8").write(p.stdout)
            return f"{n} r{r} 完成"
        open(dst + ".err", "w", encoding="utf-8").write(p.stderr)
        return f"{n} r{r} 失败（退出码 {p.returncode}），见 {dst}.err"
    with cf.ThreadPoolExecutor(a.parallel) as ex:
        for msg in ex.map(one, todo):
            print(msg, flush=True)
    left = [j for j in todo if not os.path.exists(os.path.join(out, "out", f"{j[0]}-r{j[1]}.md"))]
    print(f"作答结束：{len(todo) - len(left)}/{len(todo)} 完成" + ("；没完成的重跑同一条命令即可（已完成的跳过）" if left else ""))
    return 1 if left else 0


# ---------- 评分 ----------
def judge(a):
    out = a.out
    sc = {s["id"]: s for s in load("pressure/scenarios.json")}
    jd = os.path.join(out, "judge")
    os.makedirs(os.path.join(jd, "in"), exist_ok=True)
    os.makedirs(os.path.join(jd, "out"), exist_ok=True)
    jobs = []
    for f in sorted(os.listdir(os.path.join(out, "out"))):
        m = re.fullmatch(r"([A-Z]\d+)-(with|without)-r(\d+)\.md", f)
        if not m or m[1] not in sc:
            continue
        s = sc[m[1]]
        ans = open(os.path.join(out, "out", f), encoding="utf-8").read()
        p = (f"你是评分员，只按下面的标准判一份答案，不读任何文件、不调用工具。\n\n【题目】\n{s['题面']}\n\n"
             f"【合格标准】{s['合格']}\n【不合格情形】{s['不合格']}\n（下一步动作违规也算不合格；只说不做、或做法和说法矛盾，按做法判。）\n\n"
             f"【答案】\n{ans}\n\n第一行只写「合格」或「不合格」，第二行起用一两句写理由，引用答案原话。")
        name = f.replace(".md", "")
        open(os.path.join(jd, "in", name + ".txt"), "w", encoding="utf-8").write(p)
        jobs.append(f"{name} 1 empty\n")
    open(os.path.join(jd, "jobs.txt"), "w", encoding="utf-8").write("".join(jobs))
    print(f"评分题 {len(jobs)} 道 → {jd}；用 `python3 tests/run.py run --out {jd}` 作答，参谋长再逐份读答案核对评分")
    return 0


def trig_reads(path):
    t = open(path, encoding="utf-8").read()
    m = re.search(r"\{.*\}", t, re.S)
    try:
        return set(json.loads(m.group(0))["read"])
    except Exception:
        return {"<解析失败>"}


def score(a):
    out, res, lines = a.out, {"压力": {}, "触发": {}}, []
    files = os.listdir(os.path.join(out, "out")) if os.path.isdir(os.path.join(out, "out")) else []
    marks_p = os.path.join(out, "marks.json")
    marks = json.load(open(marks_p, encoding="utf-8")) if os.path.exists(marks_p) else {}
    for f in sorted(files):
        m = re.fullmatch(r"([A-Z]\d+)-(with|without)-r(\d+)\.md", f)
        if not m:
            continue
        key = f"{m[1]}-{m[2]}"
        name = f[:-3]
        v = marks.get(name)
        if v is None:
            jp = os.path.join(out, "judge", "out", f"{name}-r1.md")
            if os.path.exists(jp):
                first = open(jp, encoding="utf-8").read().strip().splitlines()[0:1]
                v = "不合格" if first and "不合格" in first[0] else ("合格" if first and "合格" in first[0] else None)
        res["压力"].setdefault(key, []).append(v)
    if res["压力"]:
        lines += ["## 压力题", "", "| 题 | 合格 | 不合格 | 未评 |", "|---|---|---|---|"]
        for k, vs in sorted(res["压力"].items()):
            lines.append(f"| {k} | {vs.count('合格')} | {vs.count('不合格')} | {vs.count(None)} |")
        lines += ["", "评分来源：marks.json（参谋长人工）优先，其次 judge/out（评分子任务）。评分子任务的结论参谋长要逐份读答案核对，"
                  "改判的写进 marks.json（{\"P1-with-r2\": \"不合格\"}）再跑一次 score。", ""]
    cases = {c["id"]: c for c in load("trigger/cases.json")}
    groups = {}
    for f in sorted(files):
        m = re.fullmatch(r"([A-Z]+\d+)-trig-r(\d+)\.md", f)
        if not m or m[1] not in cases:
            continue
        c = cases[m[1]]
        got = trig_reads(os.path.join(out, "out", f))
        if c["组"] == "N" or c["skill"] is None:
            ok, gk = got <= set(c["可接受"] or []), ("N", "无角色：只选可接受的")
        else:
            hit = c["skill"] in got
            ok, gk = (hit if c["该触发"] else not hit), (c["组"], f"{c['skill']}｜{'该触发' if c['该触发'] else '不该触发'}")
        res["触发"].setdefault(m[1], []).append(bool(ok))
        groups.setdefault(gk, {}).setdefault(m[1], []).append(bool(ok))
    if groups:
        lines += ["## 触发题（每题多数票）", "", "| 组 | 对象 | 多数票合格 | 逐次合格 |", "|---|---|---|---|"]
        for (g, k), per in groups.items():
            maj = sum(sum(v) * 2 > len(v) for v in per.values())
            lines.append(f"| {g} | {k} | {maj}/{len(per)} | {sum(sum(v) for v in per.values())}/{sum(len(v) for v in per.values())} |")
        bad = [f"- {cid}「{cases[cid]['请求']}」：{v}" for cid, v in res["触发"].items() if not all(v)]
        lines += ["", "不全对的题：", *bad, ""]
        lines += ["门槛（治理 skill 第 4 节）：每个受影响 skill 召回 ≥7/8、误触发 ≤1/8。"]
    json.dump(res, open(os.path.join(out, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(os.path.join(out, "结果.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


def compare(a):
    A = json.load(open(os.path.join(a.a, "summary.json"), encoding="utf-8"))
    B = json.load(open(os.path.join(a.b, "summary.json"), encoding="utf-8"))
    rows = []
    for kind in ("压力", "触发"):
        for k in sorted(set(A[kind]) | set(B[kind])):
            fa, fb = A[kind].get(k), B[kind].get(k)
            fmt = lambda v: "—" if v is None else f"{sum(1 for x in v if x in (True, '合格'))}/{len(v)}"
            if fmt(fa) != fmt(fb):
                rows.append(f"| {kind} | {k} | {fmt(fa)} | {fmt(fb)} |")
    print(f"对比：{a.a} → {a.b}")
    print("\n".join(["| 类 | 题 | 前 | 后 |", "|---|---|---|---|"] + rows) if rows else "逐题结果相同")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("all", "prepare"):
        s = sub.add_parser(name)
        s.add_argument("--suite", choices=["pressure", "trigger", "both"], default="both")
        s.add_argument("--only"); s.add_argument("--reps", type=int, default=3)
        s.add_argument("--mode", choices=["with", "without"], default="with")
        s.add_argument("--out"); s.add_argument("--parallel", type=int, default=6)
    s = sub.add_parser("run"); s.add_argument("--out", required=True); s.add_argument("--parallel", type=int, default=6)
    for name in ("judge", "score"):
        sub.add_parser(name).add_argument("--out", required=True)
    s = sub.add_parser("compare"); s.add_argument("a"); s.add_argument("b")
    a = ap.parse_args(argv)
    if a.cmd == "prepare":
        prepare(a); return 0
    if a.cmd == "all":
        a.out = prepare(a)
        run(a)
        if a.suite != "trigger":
            judge(a)
            a2 = argparse.Namespace(out=os.path.join(a.out, "judge"), parallel=a.parallel)
            run(a2)
        return score(a)
    return {"run": run, "judge": judge, "score": score, "compare": compare}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
