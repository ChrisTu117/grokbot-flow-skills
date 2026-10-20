#!/usr/bin/env python3
"""检查脚本——纯标准库 Python 3，放在本项目仓库的 scripts/ 下，直接在本机克隆（/home/box/flow-repo）里运行。
只做两件事：导出完整性（含编号缺号、行数不减）；带 --governance 时再做本机对仓库比对（含落后清单）。
通用流程第 10 节机械项 1–11 不归本脚本，由人工按清单检查。

用法：
  python3 check.py run [--export-dir 导出目录] [--governance] [--repo DIR] [--agents-dir DIR] [--workflows-dir DIR]
                       [--prev 上次结果.json] [--out 结果.json]
  python3 check.py selftest [--fixtures DIR]

导出目录（每次运行建一个带时间戳的子目录）：
  manifest.json  {"project": "流程治理", "exported_at": "...",
                  "tables": [{"role": "B", "name": "bot 名册", "view_url": "view://..."} , ...]}
  <role>-db.txt                    该数据库的 notion-fetch 结果（用来确认所用视图不带筛选）
  <role>-p1.txt, <role>-p2.txt ...   每页一个文件：CallDynamicTool(write_to_file) 的原样结果
  role：F D R S P A（项目表）、B bot 名册（只在「流程治理」）

本机对仓库比对（--governance；版本 = 克隆当前所在的 git tag）：
  - 克隆：是否停在 tag 上、有没有本地改动、比本地已知的最新 tag 旧多少（最新 tag 由 bot 事先 git fetch --tags 取得，脚本不联网）。
  - skill：本机每个 skill（按 frontmatter name）与克隆 skills/<slug>/SKILL.md 比；不一致时在各 tag 里找能对上的。
  - bot：名册里每个没废弃的 bot，设定与它所用模板在各 tag 的版本比。模板里「〈项目名〉」换成所属项目；
    设定里有「【项目专有补充】」一行的，只比到这一行（含），后面的补充段只和 --prev 的上次结果比。
哈希一律调用克隆里的 build/hash.py。
结论分三类：发现（确定不一致或落后）、降级（导出不完整、克隆不在 tag 上或有本地改动等，不算不一致）、正常。
"""
import argparse, datetime, glob, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(DEFAULT_REPO, "build"))
import hash as H  # noqa: E402  仓库 build/hash.py

ID_RE = re.compile(r"([0-9a-f]{32})")
CURRENT_STATES = {"在用", "暂停", "退役"}   # 名册里不是「已废弃」的状态
PLACEHOLDER = "〈项目名〉"
MARKER = "【项目专有补充】"
PREFIX = {"F": "F", "D": "D", "R": "R", "S": "S", "P": "P", "A": "A", "B": "B"}

def norm_hash(text: str) -> str:
    return H.norm_hash_text(text)

# ---------- 导出文件解析 ----------
def page_id(url_or_id: str):
    m = ID_RE.search((url_or_id or "").replace("-", ""))
    return m.group(1) if m else None

# ---------- 导出文件解析 ----------
def load_export(path: str) -> dict:
    """兼容有/无首尾包裹标记：取第一个 { 到最后一个 }。"""
    with open(path, encoding="utf-8") as f:
        s = f.read()
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j < i:
        raise ValueError("文件里没有 JSON")
    return json.loads(s[i:j + 1])

def page_no(path):
    m = re.search(r"-p(\d+)\.txt$", path)
    return int(m.group(1)) if m else 10**9

def read_table(export_dir: str, role: str) -> dict:
    """读一张表的全部分页，检查完整性。返回 {rows, pages, complete, issues}。"""
    files = sorted(glob.glob(os.path.join(export_dir, f"{role}-p*.txt")), key=page_no)
    out = {"pages": len(files), "rows": [], "complete": False, "issues": []}
    if not files:
        out["issues"].append("没有导出文件")
        return out
    if [page_no(f) for f in files] != list(range(1, len(files) + 1)):
        out["issues"].append("页号不连续：" + ",".join(os.path.basename(f) for f in files))
    seen, prev_cursor, dups = {}, None, []
    for n, f in enumerate(files, 1):
        try:
            j = load_export(f)
        except Exception as e:
            out["issues"].append(f"第{n}页解析失败：{e}")
            return out
        if "error" in j:
            out["issues"].append(f"第{n}页是错误返回：{j['error'].get('code')}")
            return out
        if "results" not in j or "has_more" not in j:
            out["issues"].append(f"第{n}页缺 results/has_more（不是 view 模式结果？）")
            return out
        rows = j["results"]
        if prev_cursor is not None:      # 实测：next_cursor 末尾是下一页第一行的 id
            first = page_id(rows[0]["url"]) if rows else None
            cur_id = page_id(prev_cursor.split(":")[-1])
            if first != cur_id:
                out["issues"].append(f"第{n}页首行与上一页 next_cursor 不衔接")
        for r in rows:
            pid = page_id(r.get("url", ""))
            if pid is None:
                out["issues"].append(f"第{n}页有行缺 url")
                continue
            if pid in seen:
                dups.append((pid, seen[pid], n))
                continue
            seen[pid] = n
            r["_id"] = pid
            out["rows"].append(r)
        last = n == len(files)
        if last and j["has_more"]:
            out["issues"].append("最后一页 has_more=true，没翻完")
        if not last and not (j["has_more"] and j.get("next_cursor")):
            out["issues"].append(f"第{n}页 has_more=false 或无 next_cursor，但后面还有页")
        prev_cursor = j.get("next_cursor")
    if dups:
        out["issues"].append(f"页间重复 {len(dups)} 行（如 {dups[0][0]}，第{dups[0][1]}页与第{dups[0][2]}页）")
    out["complete"] = not out["issues"]
    return out

def view_filter_issue(export_dir, role, view_url):
    """<role>-db.txt 是该数据库的 notion-fetch 结果；确认所用视图不带筛选。返回问题字符串或 None。"""
    f = os.path.join(export_dir, f"{role}-db.txt")
    if not os.path.exists(f):
        return "缺数据库结构文件，无法确认所用视图不带筛选"
    if not view_url:
        return "manifest 没写所用视图"
    try:
        t = load_export(f).get("text", "")
    except Exception as e:
        return f"数据库结构文件解析失败：{e}"
    vid = view_url.replace("view://", "").strip("{}")
    m = re.search(r'<view url="\{\{view://' + re.escape(vid) + r'\}\}">\n(\{.*?\})\n</view>', t, re.S)
    if not m:
        return "数据库结构里找不到所用视图"
    v = json.loads(m.group(1))
    k = filter_key(v)
    if k:
        return f"所用视图「{v.get('name')}」带筛选（{k}），不是全量"
    return None

def filter_key(obj, path=""):
    """视图定义里任何键名含 filter（不分大小写）且值非空，就返回该键路径；没有返回 None。"""
    if isinstance(obj, dict):
        for k, val in obj.items():
            p = f"{path}.{k}" if path else k
            if "filter" in k.lower() and val not in (None, "", [], {}, False):
                return p
            r = filter_key(val, p)
            if r:
                return r
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            r = filter_key(val, f"{path}[{i}]")
            if r:
                return r
    return None

def numbering_gaps(rows, prefix):
    nums = sorted(int(m.group(1)) for r in rows
                  for m in [re.fullmatch(prefix + r"-(\d+)", str(r.get("编号", "")).strip())] if m)
    if not nums:
        return []
    return [f"{prefix}-{i}" for i in range(1, nums[-1] + 1) if i not in set(nums)]

# ---------- 本机克隆（git，只读） ----------
def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip() or f"git {' '.join(args)} 失败")
    return r.stdout

def _vkey(tag):
    m = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", tag)
    return tuple(int(x) for x in m.groups()) if m else None

def repo_state(repo):
    """返回 {tag, commit, clean, tags(新→旧), latest}。"""
    st = {"tag": None, "commit": git(repo, "rev-parse", "HEAD").strip()}
    st["clean"] = git(repo, "status", "--porcelain").strip() == ""
    tags = [t for t in git(repo, "tag", "--points-at", "HEAD").split() if _vkey(t)]
    st["tag"] = max(tags, key=_vkey) if tags else None
    all_tags = [t for t in git(repo, "tag").split() if _vkey(t)]
    st["tags"] = sorted(all_tags, key=_vkey, reverse=True)
    st["latest"] = st["tags"][0] if st["tags"] else None
    return st

def show(repo, ref, path):
    """某个 tag 下的文件内容；不存在返回 None。"""
    try:
        return git(repo, "show", f"{ref}:{path}")
    except RuntimeError:
        return None

def fm_name(text):
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return H._frontmatter(lines[1:i])["name"]
    return None

def split_supplement(text):
    """按「【项目专有补充】」一行拆成（模板部分含该行, 补充段或 None）。"""
    lines = text.replace("\r\n", "\n").split("\n")
    for i, l in enumerate(lines):
        if l.strip() == MARKER:
            return "\n".join(lines[:i + 1]), "\n".join(lines[i + 1:])
    return text, None

def fill(template, project):
    return template.replace(PLACEHOLDER, project or PLACEHOLDER)

def matching_tags(repo, tags, path, want_hash, transform=lambda s: s):
    """在 tags（新→旧）里找 transform(文件) 的哈希等于 want_hash 的 tag。"""
    hits = []
    for t in tags:
        s = show(repo, t, path)
        if s is None:
            continue
        try:
            if norm_hash(transform(s)) == want_hash:
                hits.append(t)
        except H.FrontmatterError:
            continue
    return hits

# ---------- 本机当前值 ----------
def local_skills(workflows_dir):
    """frontmatter name → [(路径, 规范化哈希)]"""
    res = {}
    for p in glob.glob(os.path.join(workflows_dir, "*", "SKILL.md")):
        try:
            with open(p, encoding="utf-8-sig") as f:
                s = f.read()
        except OSError:
            continue
        m = re.search(r"^name:\s*(.+?)\s*$", s.split("\n---", 1)[0], re.M)
        if m:
            try:
                h = norm_hash(s)
            except H.FrontmatterError as e:
                h = f"frontmatter 无法解析：{e}"
            res.setdefault(m.group(1).strip().strip("'\""), []).append((p, h))
    return res

def agent_description(agents_dir, bot_id):
    p = os.path.join(agents_dir, bot_id, "profile.json")
    if not os.path.isdir(os.path.join(agents_dir, bot_id)):
        return None, "bot 目录不存在"
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("description"), None
    except Exception as e:
        return None, f"读不到 profile.json：{e}"

# ---------- 检查 ----------
class Report:
    def __init__(self):
        self.findings, self.degraded, self.ok = [], [], []
    def find(self, kind, table, obj, detail):
        self.findings.append({"类型": kind, "表": table, "对象": obj, "详情": detail})
    def degrade(self, table, obj, reason):
        self.degraded.append({"表": table, "对象": obj, "原因": reason})
    def good(self, table, obj, detail):
        self.ok.append({"表": table, "对象": obj, "详情": detail})

def current_rows(rows, key):
    by = {}
    for r in rows:
        if str(r.get("状态", "")).strip() in CURRENT_STATES:
            by.setdefault(str(r.get(key, "")).strip(), []).append(r)
    return by

def check_repo(rep, st):
    if not st["tag"]:
        rep.degrade("仓库", "克隆", f"不在任何 tag 上（提交 {st['commit'][:12]}）")
    if not st["clean"]:
        rep.degrade("仓库", "克隆", "有本地改动，不是发布版")
    if st["tag"] and st["latest"] and _vkey(st["latest"]) > _vkey(st["tag"]):
        rep.find("落后", "仓库", "本机克隆", f"本机 {st['tag']}，仓库最新 {st['latest']}")
    elif st["tag"]:
        rep.good("仓库", "本机克隆", f"停在 {st['tag']}，是已知最新")

def check_skills(rep, repo, st, workflows_dir):
    skills = local_skills(workflows_dir)
    for p in sorted(glob.glob(os.path.join(repo, "skills", "*", "SKILL.md"))):
        rel = os.path.relpath(p, repo)
        text = open(p, encoding="utf-8-sig").read()
        try:
            name, want = fm_name(text), norm_hash(text)
        except H.FrontmatterError as e:
            rep.find("仓库 skill frontmatter 无法解析", "skill", rel, str(e))
            continue
        loc = skills.get(name, [])
        if not loc:
            rep.find("本机缺 skill", "skill", name, "workflows 下没有 frontmatter name 为该名的 SKILL.md")
        elif len(loc) > 1:
            rep.find("本机同名 skill 多份", "skill", name, "；".join(x for x, _ in loc))
        elif loc[0][1].startswith("frontmatter"):
            rep.find("skill frontmatter 无法解析", "skill", name, f"{loc[0][0]}：{loc[0][1]}")
        elif loc[0][1] == want:
            rep.good("skill", name, f"本机与克隆一致 {want[:12]}")
        else:
            hits = matching_tags(repo, st["tags"], rel, loc[0][1])
            if hits:
                rep.find("落后", "skill", name, f"本机等于 {hits[0]}，克隆是 {st['tag'] or st['commit'][:12]}")
            else:
                rep.find("本机被改过", "skill", name, f"本机 {loc[0][1][:12]} 对不上仓库任何 tag")

def check_bots(rep, repo, st, rows, agents_dir, prev_supp):
    supp = {}
    by = {}
    for r in rows:
        if str(r.get("状态", "")).strip() in CURRENT_STATES:
            by.setdefault(str(r.get("bot ID", "")).strip(), []).append(r)
    for bid, rs in by.items():
        obj = f"{rs[0].get('名称')}（{bid}）"
        if len(rs) > 1:
            rep.find("同一 bot 多行没废弃", "B", obj, ",".join(str(r.get("编号", "")) for r in rs))
            continue
        r = rs[0]
        desc, err = agent_description(agents_dir, bid)
        if err:
            if "不存在" in err:
                rep.find("名册有而平台没有", "B", obj, err)
            else:
                rep.degrade("B", obj, err)
            continue
        if str(r.get("状态", "")).strip() != "在用":
            continue
        used = str(r.get("所用模板", "")).strip()
        m = re.fullmatch(r"([\w.-]+\.md)(?:@(\S+))?", used)
        if not m:
            rep.degrade("B", obj, f"所用模板「{used}」不是 templates/ 里的文件，脚本不核对")
            continue
        path, project = f"templates/{m.group(1)}", str(r.get("所属项目", "")).strip()
        body, sup = split_supplement(desc or "")
        cur = norm_hash(body)
        hits = matching_tags(repo, st["tags"], path, cur, lambda s: split_supplement(fill(s, project))[0])
        if not hits:
            rep.find("设定被改过", "B", obj, f"模板部分 {cur[:12]} 对不上 {path} 的任何 tag")
        elif st["tag"] in hits:
            rep.good("B", obj, f"设定等于 {path}@{st['tag']}")
        else:
            rep.find("落后", "B", obj, f"设定等于 {path}@{hits[0]}，克隆是 {st['tag'] or st['commit'][:12]}")
        if hits and m.group(2) and m.group(2) not in hits:
            rep.find("名册所用模板与实际不符", "B", obj, f"名册写 {used}，实际等于 @{hits[0]}")
        if sup is not None:
            h = norm_hash(sup)
            supp[bid] = h
            if bid in prev_supp and prev_supp[bid] != h:
                rep.find("补充段有变化", "B", obj, f"{prev_supp[bid][:12]} → {h[:12]}")
    return supp

def run(args):
    rep, tables = Report(), {}
    repo = os.path.abspath(args.repo)
    prev = {}
    if args.prev and os.path.exists(args.prev):
        prev = json.load(open(args.prev, encoding="utf-8"))
    manifest = {}
    if args.export_dir:
        ed = args.export_dir
        manifest = json.load(open(os.path.join(ed, "manifest.json"), encoding="utf-8"))
        for t in manifest["tables"]:
            role = t["role"]
            info = read_table(ed, role)
            vi = None if args.skip_view_check else view_filter_issue(ed, role, t.get("view_url"))
            if vi:
                info["issues"].append(vi)
                info["complete"] = False
            tables[role] = {"名称": t.get("name"), "视图": t.get("view_url"), "行数": len(info["rows"]),
                            "页数": info["pages"], "完整": info["complete"], "问题": info["issues"]}
            if not info["complete"]:
                rep.degrade(role, t.get("name"), "导出不完整：" + "；".join(info["issues"]))
            gaps = numbering_gaps(info["rows"], PREFIX.get(role, role)) if info["complete"] else []
            if gaps:
                rep.find("编号缺号", role, t.get("name"), "缺 " + ",".join(gaps[:20]))
            tables[role]["_rows"] = info["rows"]
        for role, t in tables.items():   # 行数单调不减
            p = prev.get("表", {}).get(role, {})
            if t["完整"] and p.get("完整") and t["行数"] < p.get("行数", 0):
                rep.find("行数减少", role, t["名称"], f"{p['行数']} → {t['行数']}")
    try:
        st = repo_state(repo)
    except Exception as e:
        st = None
        rep.degrade("仓库", repo, f"读不到 git 信息：{e}")
    if st:
        check_repo(rep, st)
    supp = {}
    if args.governance and st:
        check_skills(rep, repo, st, args.workflows_dir)
        b = tables.get("B")
        if b and b["完整"]:
            supp = check_bots(rep, repo, st, b["_rows"], args.agents_dir, prev.get("补充段哈希", {}))
        elif args.export_dir and b is None:
            rep.degrade("B", "bot 名册", "导出里没有 B，bot 设定未核对")
    for t in tables.values():
        t.pop("_rows", None)
    status = "降级" if rep.degraded else ("有发现" if rep.findings else "正常")
    ver = ({"tag": st["tag"], "提交号": st["commit"], "干净": st["clean"], "已知最新 tag": st["latest"]}
           if st else None)
    result = {"脚本": "检查脚本", "仓库版本": ver,
              "运行时间": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
              "导出目录": os.path.abspath(args.export_dir) if args.export_dir else None,
              "项目": manifest.get("project"), "状态": status,
              "覆盖范围": "导出完整性、编号连续、行数不减" + ("、本机对仓库比对（参谋长治理第 5 节第 2 项）" if args.governance else ""),
              "人工检查项": "通用流程第 10 节机械项 1–11 不归本脚本，由人工按清单检查（不算降级）",
              "表": tables, "发现": rep.findings, "降级": rep.degraded, "正常项数": len(rep.ok), "正常项": rep.ok,
              "补充段哈希": supp}
    v = f"{st['tag'] or st['commit'][:12]}{'' if st['clean'] else '（有本地改动）'}" if st else "未知"
    lines = [f"检查脚本（仓库版本 {v}）：{status}。{len(tables)} 张表，"
             f"{sum(t['行数'] for t in tables.values())} 行；发现 {len(rep.findings)} 条，降级 {len(rep.degraded)} 条，正常 {len(rep.ok)} 项。"]
    lines += [f"- 发现｜{x['表']}｜{x['对象']}｜{x['类型']}：{x['详情']}" for x in rep.findings]
    lines += [f"- 降级｜{x['表']}｜{x['对象']}：{x['原因']}" for x in rep.degraded]
    result["摘要"] = "\n".join(lines)
    out = json.dumps(result, ensure_ascii=False, indent=1)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(out)
    print(result["摘要"])
    return {"正常": 0, "有发现": 1, "降级": 2}[status]

# ---------- 自测 ----------
def selftest(args):
    import tempfile, shutil
    ok = True
    def check(name, cond):
        nonlocal ok
        ok &= bool(cond)
        print(("通过 " if cond else "失败 ") + name)
    check("包裹/无包裹都能解析", load_export_str('<x>\n\n{"a":1}\n\n</x>') == {"a": 1} and load_export_str('{"a":1}') == {"a": 1})
    check("page_id 两种 url", page_id("https://app.notion.com/p/3fbbfd313847814180a0da1b9ee091b5") ==
          page_id("https://app.notion.com/3fbbfd313847814180a0da1b9ee091b5") == "3fbbfd313847814180a0da1b9ee091b5")
    check("筛选识别：advancedFilter", filter_key({"advancedFilter": {"filters": [{"x": 1}]}}) == "advancedFilter")
    check("筛选识别：其他 filter 类键", filter_key({"quickFilters": [{"property": "状态"}]}) == "quickFilters"
          and filter_key({"format": {"filter": {"a": 1}}}) == "format.filter")
    check("筛选识别：分组/空值不算", filter_key({"groupBy": {"hideEmptyGroups": True}, "filter": None, "quickFilters": []}) is None)
    check("编号缺号", numbering_gaps([{"编号": "B-1"}, {"编号": "B-3"}], "B") == ["B-2"])
    fm1 = "---\nname: 甲\ndescription: 一 二 bot 三\n---\n正文\n"
    fm2 = "---\nname: 甲\ndescription: >-\n  一 二\n  bot 三\nmetadata:\n  k: v\n---\n正文  \n\n"
    check("调用 build/hash.py：描述同值不同写法哈希相同", norm_hash(fm1) == norm_hash(fm2))
    check("调用 build/hash.py：改描述哈希变", norm_hash(fm1) != norm_hash(fm1.replace("三", "四")))
    tpl = "你是副官·〈项目名〉，项目〈项目名〉。\n冲突时以守则为准。\n【项目专有补充】\n"
    body, sup = split_supplement(fill(tpl, "记账") + "说中文。\n不要打印密码。")
    check("填项目名并按补充行拆分", body.endswith("【项目专有补充】") and "〈项目名〉" not in body and sup.strip() == "说中文。\n不要打印密码。")
    check("没有补充行时整段当模板部分", split_supplement("甲\n乙") == ("甲\n乙", None))
    # 临时仓库：两个 tag
    tmp = tempfile.mkdtemp()
    try:
        repo, wf, ag = os.path.join(tmp, "repo"), os.path.join(tmp, "wf"), os.path.join(tmp, "agents")
        os.makedirs(os.path.join(repo, "skills", "gf")); os.makedirs(os.path.join(repo, "templates"))
        def w(p, s):
            os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "w", encoding="utf-8").write(s)
        g = lambda *a: subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, check=True)
        subprocess.run(["git", "init", "-q", repo], check=True)
        g("config", "user.email", "t@t"); g("config", "user.name", "t")
        sk1 = "---\nname: 通用流程\ndescription: 测试\n---\n旧正文\n"
        sk2 = sk1.replace("旧正文", "新正文")
        w(os.path.join(repo, "skills", "gf", "SKILL.md"), sk1); w(os.path.join(repo, "templates", "deputy.md"), tpl)
        g("add", "-A"); g("commit", "-qm", "a"); g("tag", "v1.0.0")
        w(os.path.join(repo, "skills", "gf", "SKILL.md"), sk2)
        w(os.path.join(repo, "templates", "deputy.md"), tpl.replace("冲突时", "冲突时一律"))
        g("add", "-A"); g("commit", "-qm", "b"); g("tag", "v1.1.0")
        st = repo_state(repo)
        check("tag 识别：停在 v1.1.0、干净、最新", st["tag"] == "v1.1.0" and st["clean"] and st["latest"] == "v1.1.0")
        w(os.path.join(wf, "s1", "SKILL.md"), sk1)        # 本机是旧版
        rep = Report(); check_skills(rep, repo, st, wf)
        check("skill 落后到旧 tag", any(f["类型"] == "落后" and "v1.0.0" in f["详情"] for f in rep.findings))
        w(os.path.join(wf, "s1", "SKILL.md"), sk2.replace("新正文", "乱改"))
        rep = Report(); check_skills(rep, repo, st, wf)
        check("skill 本机被改过", any(f["类型"] == "本机被改过" for f in rep.findings))
        w(os.path.join(wf, "s1", "SKILL.md"), sk2)
        rep = Report(); check_skills(rep, repo, st, wf)
        check("skill 与克隆一致", not rep.findings and rep.ok)
        def bot(bid, desc):
            w(os.path.join(ag, bid, "profile.json"), json.dumps({"description": desc}, ensure_ascii=False))
        bot("b1", fill(tpl, "记账") + "说中文。")                                   # 旧模板 + 补充
        bot("b2", fill(tpl.replace("冲突时", "冲突时一律"), "记账"))                 # 新模板
        bot("b3", "你是副官·记账，随便改的。\n【项目专有补充】\n")                     # 被改过
        rows = [{"编号": "B-1", "bot ID": "b1", "名称": "副官·记账", "所属项目": "记账", "所用模板": "deputy.md@v1.0.0", "状态": "在用"},
                {"编号": "B-2", "bot ID": "b2", "名称": "副官·记账2", "所属项目": "记账", "所用模板": "deputy.md@v1.0.0", "状态": "在用"},
                {"编号": "B-3", "bot ID": "b3", "名称": "副官·记账3", "所属项目": "记账", "所用模板": "deputy.md@v1.1.0", "状态": "在用"},
                {"编号": "B-4", "bot ID": "gone", "名称": "副官·旧", "所属项目": "旧", "所用模板": "deputy.md@v1.0.0", "状态": "在用"}]
        rep = Report(); supp = check_bots(rep, repo, st, rows, ag, {})
        kinds = {(f["对象"].split("（")[1].rstrip("）"), f["类型"]) for f in rep.findings}
        check("bot 停在旧模板 → 落后（补充段不参与）", ("b1", "落后") in kinds)
        check("bot 等于当前模板 → 正常；名册版本与实际不符 → 报", ("b2", "落后") not in kinds and ("b2", "名册所用模板与实际不符") in kinds)
        check("bot 模板部分被改 → 设定被改过", ("b3", "设定被改过") in kinds)
        check("名册有而平台没有", ("gone", "名册有而平台没有") in kinds)
        bot("b1", fill(tpl, "记账") + "说英文。")
        rep = Report(); check_bots(rep, repo, st, rows, ag, supp)
        check("补充段和上次比有变化 → 报", any(f["类型"] == "补充段有变化" and "b1" in f["对象"] for f in rep.findings))
        g("checkout", "-q", "v1.0.0")
        rep = Report(); check_repo(rep, repo_state(repo))
        check("克隆停在旧 tag → 落后", any(f["类型"] == "落后" and "v1.1.0" in f["详情"] for f in rep.findings))
        w(os.path.join(repo, "x.txt"), "脏")
        rep = Report(); check_repo(rep, repo_state(repo))
        check("克隆有本地改动 → 降级", any("本地改动" in d["原因"] for d in rep.degraded))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    fx = args.fixtures
    if fx:
        gfile = os.path.join(fx, "grouped", "db_fetch.txt")
        if os.path.exists(gfile):
            check("分组视图（隐藏空组）判为不带筛选", _vf_text(gfile, "3febfd31-3847-8194-b96d-000c27ae739e") is None)
            check("分组视图（显示空组）判为不带筛选", _vf_text(gfile, "3febfd31-3847-812a-9afd-000cb39f5d09") is None)
            check("默认（排除已废弃）判为带筛选", (_vf_text(gfile, "3febfd31-3847-8156-a3c6-000cd7920352") or "").startswith("advancedFilter"))
    print("自测" + ("全部通过" if ok else "有失败"))
    return 0 if ok else 1

def _vf_text(dbfile, vid):
    t = load_export(dbfile).get("text", "")
    m = re.search(r'<view url="\{\{view://' + re.escape(vid) + r'\}\}">\n(\{.*?\})\n</view>', t, re.S)
    return filter_key(json.loads(m.group(1))) if m else "找不到视图"

def load_export_str(s):
    i, j = s.find("{"), s.rfind("}")
    return json.loads(s[i:j + 1])

def main():
    ap = argparse.ArgumentParser(description="流程检查脚本")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--export-dir")
    r.add_argument("--governance", action="store_true", help="参谋长用：本机对仓库比对（skill、bot 设定、落后清单）")
    r.add_argument("--repo", default=DEFAULT_REPO, help="本机克隆，默认是本脚本所在的仓库")
    r.add_argument("--agents-dir", default="/home/box/agent-data/agents")
    r.add_argument("--workflows-dir", default="/home/box/agent-data/workflows")
    r.add_argument("--prev"); r.add_argument("--out")
    r.add_argument("--skip-view-check", action="store_true", help="只用于自测旧导出：不核对视图是否带筛选")
    s = sub.add_parser("selftest"); s.add_argument("--fixtures")
    a = ap.parse_args()
    return {"run": run, "selftest": selftest}[a.cmd](a)

if __name__ == "__main__":
    sys.exit(main())
