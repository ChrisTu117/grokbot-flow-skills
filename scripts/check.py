#!/usr/bin/env python3
"""检查脚本 check.py——纯标准库 Python 3，放在本项目仓库 scripts/ 下，直接在本机克隆（/home/box/flow-repo）里运行。
台账在 SQLite 库里（<数据根目录>/<项目名>/ledger.db），本脚本只读打开；只有 --log 时最后用 check 模式写一行检查日志。
通用流程第 10 节机械项 1–11 不归本脚本，由人工按清单检查（用 ledger.py 的只读命令）。

用法：
  python3 check.py run --project <项目名> --actor <bot ID> --trigger <创世|每日扫描|工作日巡检|关口一|关口二|关口三|执行前|迁移后|手动>
                       [--governance] [--log] [--out 结果.json] [--prev 上次结果.json]
  python3 check.py inventory --actor <bot ID> [--out 结果.json]      # 创世盘点，只读
  python3 check.py selftest

检查项（run）：克隆在 tag 上且干净；库能只读打开、完整性；schema 版本；规则齐全（库结构和 schema_tag 那版 schema 逐条比，
含枚举和默认有效期）；编号连续；行数不减；修改记录写入者在名册里；备份推成功；个人信息原文；meta 与克隆一致；降级标记。
--governance 再加：本机 skill 对克隆；名册 bot 设定对模板；名册对平台（平台有而名册没有、名册有而平台没有、名称不一致）；
名册登记的库路径存在且能只读打开；参谋长自己的在用行。
结论三类：有发现（退出码 1）、降级（退出码 2）、正常（退出码 0）。
数据根目录、平台 bot 目录、删除记录的位置和 ledger.py 用同一组环境变量（FLOW_DATA_ROOT、FLOW_AGENTS_DIR、FLOW_DELETED_AGENTS）。
"""
import argparse, datetime, glob, json, os, platform, re, sqlite3, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(DEFAULT_REPO, "build"))
sys.path.insert(0, HERE)
import hash as H  # noqa: E402  仓库 build/hash.py
import ledger as L  # noqa: E402  同目录 ledger.py（连接约定、结构比对、个人信息模式、名册读取）

CURRENT_STATES = {"在用", "暂停", "退役"}   # 名册里不是「已废弃」的状态
PLACEHOLDER = "〈项目名〉"
MARKER = "【项目专有补充】"
COUNT_TABLES = ("F", "D", "R", "S", "P", "A", "B", "M", "dep", "change_log", "backup_log")
TRIGGERS = ("创世", "每日扫描", "工作日巡检", "关口一", "关口二", "关口三", "执行前", "迁移后", "手动")
FLOW_NAME = re.compile(r"^(参谋长|副官·.+|专职·.+)$")


def norm_hash(text: str) -> str:
    return H.norm_hash_text(text)


# ---------- 本机克隆（git，只读） ----------
def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip() or f"git {' '.join(args)} 失败")
    return r.stdout


_vkey = L._vkey


def repo_state(repo):
    """返回 {tag, commit, clean, tags(新→旧), latest, label, refs}。refs：[(标签, git ref)]，克隆不在 tag 上时
    把当前提交当作 draft-<提交号前 12 位> 放在最前（草稿演练用）。"""
    st = {"tag": None, "commit": git(repo, "rev-parse", "HEAD").strip()}
    st["clean"] = git(repo, "status", "--porcelain").strip() == ""
    tags = [t for t in git(repo, "tag", "--points-at", "HEAD").split() if _vkey(t)]
    st["tag"] = max(tags, key=_vkey) if tags else None
    all_tags = [t for t in git(repo, "tag").split() if _vkey(t)]
    st["tags"] = sorted(all_tags, key=_vkey, reverse=True)
    st["latest"] = st["tags"][0] if st["tags"] else None
    st["label"] = st["tag"] or f"draft-{st['commit'][:12]}"
    st["refs"] = ([] if st["tag"] else [(st["label"], st["commit"])]) + [(t, t) for t in st["tags"]]
    try:
        st["origin"] = git(repo, "remote", "get-url", "origin").strip()
    except RuntimeError:
        st["origin"] = None
    return st


def show(repo, ref, path):
    """某个 ref 下的文件内容；不存在返回 None。"""
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


def matching_tags(repo, refs, path, want_hash, transform=lambda s: s):
    """在 refs（[(标签, ref)]，新→旧）里找 transform(文件) 的哈希等于 want_hash 的，返回标签列表。"""
    hits = []
    for label, ref in refs:
        s = show(repo, ref, path)
        if s is None:
            continue
        try:
            if norm_hash(transform(s)) == want_hash:
                hits.append(label)
        except H.FrontmatterError:
            continue
    return hits


def norm_url(u):
    u = (u or "").strip().rstrip("/")
    return u[:-4] if u.endswith(".git") else u


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


def check_repo(rep, st):
    if not st["tag"]:
        rep.degrade("仓库", "克隆", f"不在任何 tag 上（草稿提交 {st['commit'][:12]}）")
    if not st["clean"]:
        rep.degrade("仓库", "克隆", "有本地改动，不是发布版")
    if st["tag"] and st["latest"] and _vkey(st["latest"]) > _vkey(st["tag"]):
        rep.find("落后", "仓库", "本机克隆", f"本机 {st['tag']}，仓库最新 {st['latest']}")
    elif st["tag"]:
        rep.good("仓库", "本机克隆", f"停在 {st['tag']}，是已知最新")


def skill_status(repo, st, skills, slug, name, want, rel):
    """返回 (状态, 详情)。状态：一致 / 缺失 / 多份 / 无法解析 / 落后 / 被改过。中英文名互认（J2：frontmatter name、目录名、旧中文名）。"""
    names = list(dict.fromkeys([name, slug] + L.ALIASES.get(slug, [])))
    loc = [x for n in names for x in skills.get(n, [])]
    if not loc:
        return "缺失", "workflows 下没有 frontmatter name 为「" + "」或「".join(names) + "」的 SKILL.md"
    if len(loc) > 1:
        return "多份", "；".join(x for x, _ in loc)
    if loc[0][1].startswith("frontmatter"):
        return "无法解析", f"{loc[0][0]}：{loc[0][1]}"
    if loc[0][1] == want:
        return "一致", f"本机与克隆一致 {want[:12]}"
    hits = matching_tags(repo, st["refs"], rel, loc[0][1])
    if hits:
        return "落后", f"本机等于 {hits[0]}，克隆是 {st['label']}"
    return "被改过", f"本机 {loc[0][1][:12]} 对不上仓库任何版本"


def check_skills(rep, repo, st, workflows_dir):
    skills = local_skills(workflows_dir)
    kinds = {"缺失": "本机缺 skill", "多份": "本机同名 skill 多份", "无法解析": "skill frontmatter 无法解析",
             "落后": "落后", "被改过": "本机被改过"}
    for p in sorted(glob.glob(os.path.join(repo, "skills", "*", "SKILL.md"))):
        rel = os.path.relpath(p, repo)
        slug = os.path.basename(os.path.dirname(p))
        text = open(p, encoding="utf-8-sig").read()
        try:
            name, want = fm_name(text), norm_hash(text)
        except H.FrontmatterError as e:
            rep.find("仓库 skill frontmatter 无法解析", "skill", rel, str(e))
            continue
        s, d = skill_status(repo, st, skills, slug, name, want, rel)
        if s == "一致":
            rep.good("skill", name, d)
        else:
            rep.find(kinds[s], "skill", name, d)


def check_bots(rep, repo, st, rows, agents_dir, prev_supp):
    """rows：B 表行（dict，键 bot_id、名称、所属项目、所用模板、状态、code）。"""
    supp, by = {}, {}
    for r in rows:
        if str(r.get("状态", "")).strip() in CURRENT_STATES:
            by.setdefault(str(r.get("bot_id", "")).strip(), []).append(r)
    for bid, rs in by.items():
        obj = f"{rs[0].get('名称')}（{bid}）"
        if len(rs) > 1:
            rep.find("同一 bot 多行没废弃", "B", obj, ",".join(str(r.get("code", "")) for r in rs))
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
        if used.startswith("http"):
            continue  # 模板库导入的 bot 记链接，脚本不核对，也不降级；由每周复盘人工看
        m = re.fullmatch(r"([\w.-]+\.md)(?:@(\S+))?", used)
        if not m:
            rep.degrade("B", obj, f"所用模板「{used}」不是 templates/ 里的文件，脚本不核对")
            continue
        path, project = f"templates/{m.group(1)}", str(r.get("所属项目", "")).strip()
        body, sup = split_supplement(desc or "")
        cur = norm_hash(body)
        hits = matching_tags(repo, st["refs"], path, cur, lambda s: split_supplement(fill(s, project))[0])
        if not hits:
            rep.find("设定被改过", "B", obj, f"模板部分 {cur[:12]} 对不上 {path} 的任何版本")
        elif st["label"] in hits:
            rep.good("B", obj, f"设定等于 {path}@{st['label']}")
        else:
            rep.find("落后", "B", obj, f"设定等于 {path}@{hits[0]}，克隆是 {st['label']}")
        if hits and m.group(2) and m.group(2) not in hits:
            rep.find("名册所用模板与实际不符", "B", obj, f"名册写 {used}，实际等于 @{hits[0]}")
        if sup is not None:
            h = norm_hash(sup)
            supp[bid] = h
            if bid in prev_supp and prev_supp[bid] != h:
                rep.find("补充段有变化", "B", obj, f"{prev_supp[bid][:12]} → {h[:12]}")
    return supp


def template_hashes(repo, st):
    """各模板在各版本的模板部分哈希 → 「文件@版本」。"""
    out = {}
    for label, ref in st["refs"]:
        try:
            names = git(repo, "ls-tree", "--name-only", f"{ref}:templates").split()
        except RuntimeError:
            continue
        for n in names:
            if not n.endswith(".md") or n == "README.md" or n == "routines.md":
                continue
            s = show(repo, ref, f"templates/{n}")
            if s is not None:
                out.setdefault(norm_hash(split_supplement(s)[0]), f"{n}@{label}")
    return out


def platform_vs_roster(rep, env, repo, st, rows, platform):
    """Q15：①平台有而名册没有（名字像流程 bot，或设定能对上任一模板）；③名称不一致。②在 check_bots 里。"""
    live = {r["bot_id"]: r for r in rows if r["状态"] != "已废弃"}
    th = template_hashes(repo, st) if st else {}
    orphans = []
    for bid, prof in platform.items():
        name = prof.get("name") or ""
        if bid in live:
            if live[bid]["名称"] != name:
                rep.find("名称不一致", "B", f"{live[bid]['名称']}（{bid}）", f"名册「{live[bid]['名称']}」，平台现在叫「{name}」")
            continue
        desc = prof.get("description") or ""
        why = None
        if FLOW_NAME.match(name):
            why = f"名字是「{name}」"
        else:
            h = norm_hash(split_supplement(desc)[0])
            if h in th:
                why = f"设定等于 {th[h]}"
        if why:
            rep.find("平台有而名册没有", "B", f"{name}（{bid}）", why + "；未登记，可能是已删 bot 残留，由用户定：收编进名册 / 忽略")
            orphans.append({"bot_id": bid, "名称": name, "原因": why})
    return orphans


def check_roster_paths(rep, env, rows):
    """名册登记的库路径：在用参谋长、副官的库文件存在且能只读打开（参谋长巡检按名册路径逐个打开，不用 ATTACH）。"""
    for r in rows:
        if r["状态"] != "在用" or r["类型"] not in ("参谋长", "副官"):
            continue
        obj = f"{r['名称']}（{r['code']}）"
        p = r.get("库路径")
        if not p:
            rep.find("名册没登记库路径", "B", obj, "在用参谋长/副官必须登记库路径")
            continue
        if not L.same_path(p, env.db(r["所属项目"])):
            rep.find("库路径不是标准位置", "B", obj, f"名册 {p}，标准位置 {env.db(r['所属项目'])}")
        if not os.path.exists(p):
            rep.find("名册登记的库不存在", "B", obj, p)
            continue
        try:
            c = L.connect_ro(p)
            try:
                qc = c.execute("PRAGMA quick_check").fetchone()[0]
                sv = L.meta_of(c).get("schema_version")
            finally:
                c.close()
        except Exception as e:
            rep.find("名册登记的库打不开", "B", obj, f"{p}：{e}")
            continue
        if qc != "ok":
            rep.find("名册登记的库完整性不过", "B", obj, f"{p}：{qc}")
        else:
            rep.good("B", obj, f"库 {p} 能只读打开（schema {sv}）")


CHIEF_IDLE_DAYS = 2   # 参谋长多少个工作日没跑定时检查就报「参谋长可能停了」


def working_days_between(d0, d1):
    """d0 之后（不含）到 d1（含）之间的工作日数（周一到周五，不扣法定节假日）。"""
    n, d = 0, d0
    while d < d1:
        d += datetime.timedelta(days=1)
        n += d.weekday() < 5
    return n


def check_chief_alive(rep, env, rows, today=None):
    """副官跑自己的项目时顺带只读看一眼流程治理库：在用参谋长最近一次定时检查日志（每日扫描或工作日巡检）
    距今超过 CHIEF_IDLE_DAYS 个工作日就报发现，让副官告诉用户「参谋长可能停了」。"""
    p = env.db(L.GOV)
    if rows is None or not os.path.exists(p):
        return  # 名册读不到已另报降级
    live = [r for r in rows if r["类型"] == "参谋长" and r["状态"] == "在用"]
    today = today or datetime.date.today()
    try:
        c = L.connect_ro(p)
        try:
            ids = [r["bot_id"] for r in live]
            last = None
            if ids:
                q = ("SELECT code, run_at FROM check_log WHERE 触发 IN ('每日扫描','工作日巡检') AND actor IN (%s) "
                     "ORDER BY id DESC LIMIT 1" % ",".join("?" * len(ids)))
                last = c.execute(q, ids).fetchone()
            created = L.meta_of(c).get("created_at") or ""
        finally:
            c.close()
    except Exception as e:
        rep.degrade("check_log", "流程治理", f"读不到参谋长的检查日志：{e}")
        return
    if not live:
        rep.find("参谋长可能停了", "B", "流程治理", "名册里没有在用参谋长：告诉用户「参谋长可能停了」")
        return
    ref, what = (last[1], f"最近一次是 {last[0]}（{last[1][:16]}）") if last else (created, f"建库（{created[:16]}）以来一次都没有")
    try:
        d0 = datetime.date.fromisoformat(str(ref)[:10])
    except ValueError:
        rep.degrade("check_log", "流程治理", f"参谋长检查日志时间读不懂：{ref}")
        return
    n = working_days_between(d0, today)
    if n > CHIEF_IDLE_DAYS:
        rep.find("参谋长可能停了", "check_log", "流程治理",
                 f"参谋长的定时检查（每日扫描/工作日巡检）{what}，已过 {n} 个工作日（上限 {CHIEF_IDLE_DAYS}）："
                 "告诉用户「参谋长可能停了」")
    else:
        rep.good("check_log", "流程治理", f"参谋长定时检查{what}，{n} 个工作日内")


# ---------- 库 ----------
def seq_gaps(c, table):
    col = "id" if table in ("change_log", "check_log", "backup_log", "dep") else "seq"
    nums = [r[0] for r in c.execute(f"SELECT {col} FROM {table} ORDER BY {col}")]
    return [n for n in range(1, (nums[-1] if nums else 0) + 1) if n not in set(nums)]


def check_db(rep, env, st, project, actor, c, prev, rows_gov):
    """库内检查。返回 (表行数, change_log 最大编号, meta)。"""
    m = L.meta_of(c)
    tables = {t: c.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in COUNT_TABLES}
    upto = L.max_change(c)
    # schema 版本
    try:
        want_v = L.schema_version_of(L.schema_text(env.repo))
    except L.EnvError as e:
        rep.degrade("库", "schema", str(e))
        want_v = None
    have_v = int(m.get("schema_version") or 0)
    if want_v is not None:
        if have_v < want_v:
            rep.find("需迁移", "库", project, f"库 schema {have_v}，克隆 schema {want_v}")
        elif have_v > want_v:
            rep.degrade("库", project, f"克隆比库旧：库 schema {have_v}，克隆 schema {want_v}")
        else:
            rep.good("库", project, f"schema {have_v} 与克隆一致")
    # 规则齐全（Q7）
    tag = m.get("schema_tag")
    ref_sql = show(env.repo, tag, "schema/schema.sql") if tag else None
    if ref_sql is None:
        rep.degrade("库", "规则", f"读不到 schema_tag（{tag}）对应的 schema/schema.sql")
    else:
        try:
            diff = L.diff_structure(L.structure(c), L.reference_structure(ref_sql))
        except sqlite3.Error as e:
            diff = [("出错", "标准库", str(e))]
        for kind, name, detail in diff:
            rep.find("规则被改动", "库", name, f"{kind}：{detail}")
        if not diff:
            rep.good("库", "规则", f"结构、枚举、默认有效期与 {tag} 的 schema 逐条一致")
    # 编号连续
    for t in ("F", "D", "R", "S", "P", "B", "dep", "change_log", "check_log", "backup_log"):
        g = seq_gaps(c, t)
        if g:
            rep.find("编号缺号", t, t, "缺 " + ",".join(map(str, g[:20])))
    an = [r[0] for r in c.execute("SELECT DISTINCT 编号 FROM A ORDER BY 编号")]
    if an and an != list(range(1, an[-1] + 1)):
        rep.find("编号缺号", "A", "A", f"编号 {an}")
    for n, vs in c.execute("SELECT 编号, group_concat(版本号) FROM A GROUP BY 编号"):
        v = sorted(int(x) for x in vs.split(","))
        if v != list(range(1, len(v) + 1)):
            rep.find("编号缺号", "A", f"A-{n}", f"版本号 {v}")
    # 行数不减
    for t, n in tables.items():
        p = (prev.get("表") or {}).get(t)
        if p is not None and n < p:
            rep.find("行数减少", t, t, f"{p} → {n}")
    # 写入者（J6 机械复核）
    since = int(prev.get("修改记录到") or 0)
    if rows_gov is None:
        rep.find("无法核对写入者", "change_log", project, "流程治理库打不开，名册读不到")
    else:
        if project == L.GOV:
            allowed = {r["bot_id"] for r in rows_gov if r["类型"] == "参谋长" and r["状态"] != "已废弃"}
        else:
            allowed = {r["bot_id"] for r in rows_gov if r["类型"] == "副官" and r["所属项目"] == project and r["状态"] != "已废弃"}
        bad = c.execute("SELECT id,actor FROM change_log WHERE id>? ORDER BY id", (since,)).fetchall()
        bad = [(i, a) for i, a in bad if a not in allowed]
        for a in sorted({a for _, a in bad}):
            ids = [i for i, x in bad if x == a]
            rep.find("写入者不在名册", "change_log", a, f"change_log #{ids[0]}" + (f" 等 {len(ids)} 条" if len(ids) > 1 else ""))
        if not bad:
            rep.good("change_log", project, f"#{since + 1}–#{upto} 的写入者都在名册里")
    # 备份（J1）
    br = env.backup_repo
    last = c.execute("SELECT at,结果,error,change_log_upto FROM backup_log ORDER BY id DESC LIMIT 1").fetchone()
    ok_last = c.execute("SELECT at,change_log_upto FROM backup_log WHERE 结果='成功' ORDER BY id DESC LIMIT 1").fetchone()
    if not os.path.isdir(os.path.join(br, ".git")):
        rep.find("备份仓库未初始化", "备份", br, "没有备份仓库的本机克隆")
    elif last is None:
        rep.find("备份未推成功", "备份", project, "还没有任何备份记录")
    elif last[1] == "失败":
        rep.find("备份未推成功", "备份", project, f"{last[0]}，{(last[2] or '')[-200:]}")
    elif ok_last and ok_last[1] < upto:
        rep.find("备份未推成功", "备份", project, f"最近一次成功（{ok_last[0]}）只覆盖到修改记录 #{ok_last[1]}，当前 #{upto}")
    else:
        rep.good("备份", project, f"最近一次备份成功（{last[0]}），覆盖到 #{last[3]}")
    if os.path.isdir(os.path.join(br, ".git")):
        n = L.unpushed(br)
        if n:
            rep.find("备份未推成功", "备份", br, f"本机有 {n} 个没推出去的提交")
    # 个人信息原文（只报位置）
    for t in ("F", "D", "R", "S", "P", "A", "B", "dep"):
        cols = [r[1] for r in c.execute(f"PRAGMA table_xinfo({t})") if r[2].upper() == "TEXT"]
        key = "版本代号" if t == "A" else ("'dep-'||id" if t == "dep" else "code")
        for row in c.execute(f"SELECT {key},{','.join(cols)} FROM {t}"):
            for col, v in zip(cols, row[1:]):
                h = L.pii_hard(v)
                if h:
                    rep.find("疑似个人信息原文", t, f"{row[0]}.{col}", "、".join(h))
    for k, v in m.items():
        if L.pii_hard(v):
            rep.find("疑似个人信息原文", "meta", k, "、".join(L.pii_hard(v)))
    # meta 与实际
    if st:
        if m.get("流程版本") != st["label"]:
            rep.find("登记与实际不符", "meta", "流程版本", f"登记 {m.get('流程版本')}，克隆 {st['label']}")
        if project == L.GOV and st.get("origin") and norm_url(m.get("项目仓库")) != norm_url(st["origin"]):
            rep.find("登记与实际不符", "meta", "项目仓库", f"登记 {m.get('项目仓库')}，克隆 origin {st['origin']}")
    return tables, upto, m


def build_output(st, project, sv, tables, upto, rep, status, log_code):
    v = f"{st['label']}，提交 {st['commit'][:12]}{'' if st['clean'] else '，有本地改动'}" if st else "未知"
    lines = [f"检查脚本（仓库版本 {v}）：{status}。" + (f"检查日志 {log_code}。" if log_code else "") +
             f"库 {project}（schema {sv}），{len(tables)} 张表 {sum(tables.values())} 行，修改记录到 #{upto}；"
             f"发现 {len(rep.findings)} 条，降级 {len(rep.degraded)} 条，正常 {len(rep.ok)} 项。"]
    lines += [f"- 发现｜{x['表']}｜{x['对象']}｜{x['类型']}：{x['详情']}" for x in rep.findings]
    lines += [f"- 降级｜{x['表']}｜{x['对象']}：{x['原因']}" for x in rep.degraded]
    return "\n".join(lines)


def run_check(env, project, actor, trigger, governance=False, log=False, out=None, prev_path=None,
              workflows_dir="/home/box/agent-data/workflows"):
    """返回 (退出码, 终端输出全文, result dict, out 路径)。"""
    rep = Report()
    repo = env.repo
    try:
        st = repo_state(repo)
    except Exception as e:
        st = None
        rep.degrade("仓库", repo, f"读不到 git 信息：{e}")
    if st:
        check_repo(rep, st)
    path = env.db(project)
    tables, upto, meta, sv, prev, supp = {}, 0, {}, "?", {}, {}
    try:
        rows_gov = L.roster(env)
    except Exception as e:
        rows_gov = None
        rep.degrade("B", "流程治理库", f"读不到名册：{e}")
    c = None
    try:
        c = L.connect_ro(path)
        ic = c.execute("PRAGMA integrity_check").fetchone()[0]
        if ic != "ok":
            raise sqlite3.DatabaseError(f"integrity_check：{ic}")
        L.meta_of(c)
    except Exception as e:
        rep.degrade("库", path, f"库打不开或完整性检查不过：{e}")
        if c:
            c.close()
        c = None
    if c:
        try:
            if prev_path:
                prev = json.load(open(prev_path, encoding="utf-8"))
            else:
                r = c.execute("SELECT result_json FROM check_log ORDER BY id DESC LIMIT 1").fetchone()
                prev = json.loads(r[0]) if r else {}
            tables, upto, meta = check_db(rep, env, st, project, actor, c, prev, rows_gov)
            sv = meta.get("schema_version", "?")
        finally:
            c.close()
    if project != L.GOV:
        check_chief_alive(rep, env, rows_gov)
    if governance:
        rows = rows_gov or []
        if rows_gov is None:
            rep.degrade("B", "bot 名册", "流程治理库打不开，bot 设定未核对")
        if st:
            check_skills(rep, repo, st, workflows_dir)
            supp = check_bots(rep, repo, st, rows, env.agents_dir, prev.get("补充段哈希", {}))
        try:
            plat = L.platform_bots(env)
        except L.EnvError as e:
            plat = None
            rep.degrade("B", "平台 bot", f"读不到 profile.json：{e}")
        if plat is not None:
            platform_vs_roster(rep, env, repo, st, rows, plat)
        check_roster_paths(rep, env, rows)
        prof = (L.profile(env, actor) or {}) if actor else {}
        is_cos = prof.get("name") == "参谋长" or any(r["bot_id"] == actor and r["类型"] == "参谋长" for r in rows)
        if is_cos:
            live = [r for r in rows if r["类型"] == "参谋长" and r["状态"] == "在用"]
            if len(live) != 1 or live[0]["bot_id"] != actor:
                rep.find("名册里没有本参谋长在用行", "B", actor, f"在用参谋长：{[r['bot_id'] for r in live] or '无'}")
            else:
                rep.good("B", "参谋长", f"{live[0]['code']} 是本参谋长的在用行")
    status = "降级" if rep.degraded else ("有发现" if rep.findings else "正常")
    marked = str(meta.get("降级模式", "")).startswith("是")
    if marked and status != "降级":
        rep.good("meta", "降级模式", "标着降级，本次结果不是降级（按降级方案可以 degrade off）")
    elif not marked and status == "降级" and meta:
        rep.good("meta", "降级模式", "本次降级，meta 还没标（按降级方案 degrade on）")
    if out is None:
        out = os.path.join(env.runs_dir(project, actor), "result.json")
    ver = {"tag": st["tag"], "标签": st["label"], "提交号": st["commit"], "干净": st["clean"],
           "已知最新 tag": st["latest"]} if st else None

    def assemble(log_code, extra_line=None, status_=status):
        stdout = build_output(st, project, sv, tables, upto, rep, status_, log_code)
        if extra_line:
            stdout += "\n" + extra_line
        result = {"脚本": "检查脚本", "仓库版本": ver, "运行时间": run_at, "运行者": actor, "触发": trigger,
                  "项目": project, "库": path, "schema": sv, "状态": status_, "检查日志": log_code,
                  "人工检查项": "通用流程第 10 节机械项 1–11 不归本脚本，由人工按清单检查（不算降级）",
                  "表": tables, "修改记录到": upto, "发现": rep.findings, "降级": rep.degraded,
                  "正常项数": len(rep.ok), "正常项": rep.ok, "补充段哈希": supp, "终端输出": stdout}
        return stdout, result
    run_at = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    code_map = {"正常": 0, "有发现": 1, "降级": 2}
    if not log:
        stdout, result = assemble(None)
    else:
        try:
            if not os.path.exists(path):
                raise L.EnvError(f"库不存在：{path}")
            L.verify_actor(env, project, actor)
            w = L.connect_rw(path)
            try:
                w.execute("BEGIN IMMEDIATE")
                nid = w.execute("SELECT coalesce(max(id),0)+1 FROM check_log").fetchone()[0]
                stdout, result = assemble(f"C-{nid}")
                rj = json.dumps(result, ensure_ascii=False, indent=1)
                L.set_ctx(w, actor, f"check.py --log（{trigger}）", "check")
                w.execute("INSERT INTO check_log(id,run_at,actor,触发,repo_tag,repo_commit,repo_clean,exit_code,状态,"
                          "change_log_upto,stdout,result_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                          (nid, run_at, actor, trigger, st["label"] if st else None, st["commit"] if st else None,
                           int(st["clean"]) if st else None, code_map[status], status, upto, stdout, rj))
                L.clear_ctx(w)
                w.execute("COMMIT")
            except BaseException:
                w.execute("ROLLBACK")
                raise
            finally:
                w.close()
        except Exception as e:
            status = "降级"
            stdout, result = assemble(None, f"检查日志写入失败：{e}；本次结果在 {out}", status_="降级")
    rj = json.dumps(result, ensure_ascii=False, indent=1)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(rj)
    return code_map[status], stdout, result, out


# ---------- 创世盘点（只读） ----------
def inventory(env, actor, out=None, workflows_dir="/home/box/agent-data/workflows"):
    """查四处真相：仓库克隆、本机 skill 和平台 bot、本机库、备份。返回 (退出码, 终端输出, result, out 路径)。"""
    rows = []

    def add(obj, now_, act, why):
        rows.append((obj, now_, act, why))
    # 1 环境
    add("python3", platform.python_version(), "—", "")
    add("sqlite", sqlite3.sqlite_version, "—", "")
    dr = env.data_root
    if os.path.isdir(dr):
        try:
            fd, tp = tempfile.mkstemp(dir=dr, prefix=".probe-")
            os.close(fd)
            os.remove(tp)
            add("数据根目录", f"{dr} 存在、可写", "复用", "")
        except OSError as e:
            add("数据根目录", f"{dr} 不可写：{e}", "停", "台账写不进去")
    else:
        par = os.path.dirname(dr)
        while par and not os.path.isdir(par) and par != os.path.dirname(par):
            par = os.path.dirname(par)
        w = os.access(par, os.W_OK)
        add("数据根目录", f"{dr} 不存在；最近的上级 {par} {'可写' if w else '不可写'}", "新建" if w else "停", "" if w else "建不了库")
    # 2 仓库
    st = None
    try:
        st = repo_state(env.repo)
        add("本机克隆", f"{st['label']}（提交 {st['commit'][:12]}，{'干净' if st['clean'] else '有本地改动'}，origin {st['origin']}，"
            f"已知最新 tag {st['latest']}）",
            "问用户：按这个提交继续 / 切到最新 tag" if not st["tag"] else
            ("停" if not st["clean"] else
             (f"停，问用户：按 {st['tag']} 继续 / 切到 {st['latest']}" if st["latest"] and st["latest"] != st["tag"] else "复用")),
            "草稿提交（不在 tag 上）" if not st["tag"] else
            ("有本地改动" if not st["clean"] else
             (f"克隆落后：停在 {st['tag']}，已知最新 {st['latest']}；不自己切换" if st["latest"] and st["latest"] != st["tag"] else "")))
    except Exception as e:
        add("本机克隆", f"读不到：{e}", "停", "")
    # 3 skill
    if st:
        skills = local_skills(workflows_dir)
        act = {"一致": "复用", "缺失": "补建", "落后": "更新", "被改过": "停", "多份": "停", "无法解析": "停"}
        for p in sorted(glob.glob(os.path.join(env.repo, "skills", "*", "SKILL.md"))):
            rel = os.path.relpath(p, env.repo)
            slug = os.path.basename(os.path.dirname(p))
            text = open(p, encoding="utf-8-sig").read()
            try:
                name, want = fm_name(text), norm_hash(text)
            except H.FrontmatterError as e:
                add(f"skill {rel}", f"仓库 frontmatter 无法解析：{e}", "停", "")
                continue
            s, d = skill_status(env.repo, st, skills, slug, name, want, rel)
            a = act[s] + (f"（到 {st['label']}）" if s == "落后" else "")
            old = [(n, x) for n in dict.fromkeys([slug] + L.ALIASES.get(slug, [])) if n != name for x, _ in skills.get(n, [])]
            if s in ("一致", "落后") and len(old) == 1 and not skills.get(name):
                sid = os.path.basename(os.path.dirname(old[0][1]))
                a = (f"改英文名：按 {name} 新装；旧那份「{old[0][0]}」（skill-id {sid}）列进清单问用户删不删"
                     "（删除全局生效，不默认勾）")
            add(f"skill {name}", f"{s}：{d}", a, "")
    # 4 流程治理库
    gov = env.db(L.GOV)
    rows_gov = None
    if os.path.exists(gov):
        try:
            c = L.connect_ro(gov)
            ic = c.execute("PRAGMA integrity_check").fetchone()[0]
            m = L.meta_of(c)
            c.close()
            rows_gov = L.roster(env)
            live = [r for r in rows_gov if r["类型"] == "参谋长" and r["状态"] == "在用"]
            cos_alive = bool(live) and L.bot_alive(env, live[0]["bot_id"])
            mine = bool(live) and live[0]["bot_id"] == actor
            add("流程治理库", f"{gov}：完整性 {ic}，schema {m.get('schema_version')}，名册 {len(rows_gov)} 行，"
                f"在用参谋长 {live[0]['bot_id'] if live else '无'}" + ("（平台上已不在）" if live and not cos_alive else ""),
                "不执行创世（已有本参谋长在用行）" if mine else ("停：已有在用参谋长" if cos_alive else "复用"),
                "" if ic == "ok" else "完整性不过")
            for r in rows_gov:
                if r["状态"] != "已废弃":
                    add(f"名册 {r['code']}", f"{r['名称']}（{r['bot_id']}）{r['类型']} {r['状态']} {r['所用模板']}",
                        "—" if L.bot_alive(env, r["bot_id"]) else "问用户：改已废弃",
                        "" if L.bot_alive(env, r["bot_id"]) else "平台上已不在")
        except Exception as e:
            add("流程治理库", f"{gov} 打不开：{e}", "停", "")
    # 6 备份（先查，决定库不在时的建议）
    br = env.backup_repo
    bk = {"本机克隆": os.path.isdir(os.path.join(br, ".git")), "有流程治理备份": False, "库ID": None}
    if bk["本机克隆"]:
        sqlp = os.path.join(br, L.GOV, "ledger.sql")
        bk["有流程治理备份"] = os.path.exists(sqlp)
        idf = os.path.join(br, L.GOV, "库ID")
        bk["库ID"] = open(idf, encoding="utf-8").read().strip() if os.path.exists(idf) else None
        add("备份仓库", f"{br}（远端 {L.git(br, 'remote', 'get-url', 'origin').strip()}）"
            + (f"；有流程治理备份，库ID {bk['库ID']}" if bk["有流程治理备份"] else "；没有流程治理备份"), "复用", "")
    else:
        add("备份仓库", f"{br} 不存在", "先 gh repo view <账号>/flow-ledger-backup：在就 backup-init，不在就列进清单新建",
            "脚本不联网，远端在不在由 bot 另查")
    if not os.path.exists(gov):
        if bk["有流程治理备份"]:
            add("流程治理库", f"{gov} 不存在，但备份里有", "问用户：从备份恢复 / 新建（旧备份移到归档目录）", "")
        else:
            add("流程治理库", f"{gov} 不存在，备份里也没有", "新建", "")
    # 5 平台 bot
    orphans = []
    try:
        plat = L.platform_bots(env)
        rep = Report()
        if st:
            orphans = platform_vs_roster(rep, env, env.repo, st, rows_gov or [], plat)
        for o in orphans:
            if o["bot_id"] == actor:
                add(f"平台 bot {o['名称']}（自己）", f"{actor}，名册里还没有", "不收编：genesis 最后写自己那一行",
                    "本次 --actor 就是自己")
                continue
            add(f"平台 bot {o['名称']}", f"{o['bot_id']}，{o['原因']}，名册里没有：未登记，可能是已删 bot 残留",
                "由用户定：收编进名册 / 忽略（不默认）", "本机目录在不等于平台上还在；不新建同名 bot")
        for f in rep.findings:
            if f["类型"] == "名称不一致":
                add(f"平台 bot {f['对象']}", f["详情"], "问用户：改名册名称", "")
        th = template_hashes(env.repo, st) if st else {}
        orphan_ids = {o["bot_id"] for o in orphans}
        for bid, prof in plat.items():
            name = prof.get("name") or ""
            if name.startswith("专职·") and st and bid not in orphan_ids:
                h = norm_hash(split_supplement(prof.get("description") or "")[0])
                hit = th.get(h)
                now_ = f"设定等于 {hit}" if hit else "设定对不上任何模板版本"
                a = "复用" if hit and hit.endswith("@" + st["label"]) else ("落后：按清单更新" if hit else "问用户：设定不一致")
                add(f"专职设定 {name}（{bid}）", now_, a, "")
    except L.EnvError as e:
        add("平台 bot", f"读不到：{e}", "停", "")
    result = {"脚本": "检查脚本 inventory", "运行时间": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
              "运行者": actor, "仓库": {k: st[k] for k in ("tag", "label", "commit", "clean", "latest", "origin")} if st else None,
              "备份": bk, "孤儿 bot": orphans, "表": [dict(zip(("对象", "现状", "建议动作", "原因"), r)) for r in rows],
              "提醒": "参谋长自己的定时任务脚本看不到，请按 templates/routines.md 自己对照填进清单"}
    text = "创世盘点（只读）\n" + L.md_table(["对象", "现状", "建议动作", "原因"], rows) + \
           "\n提醒：参谋长自己的定时任务脚本看不到，请按 templates/routines.md 自己对照填进清单。"
    if out is None:
        out = os.path.join(env.runs_dir(L.GOV, actor), "inventory.json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False, indent=1))
    result["终端输出"] = text
    return 0, text + f"\n结果文件：{out}", result, out


# ---------- CLI ----------
def make_env(a):
    return L.Env(data_root=a.data_root, agents_dir=a.agents_dir, deleted=a.deleted, repo=a.repo)


def main(argv=None):
    ap = argparse.ArgumentParser(description="流程检查脚本")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(s):
        s.add_argument("--repo", default=DEFAULT_REPO, help="本机克隆，默认是本脚本所在的仓库")
        s.add_argument("--data-root", default=None, help="默认取 FLOW_DATA_ROOT 或 /home/box/flow-data")
        s.add_argument("--agents-dir", default=None)
        s.add_argument("--deleted", default=None)
        s.add_argument("--workflows-dir", default="/home/box/agent-data/workflows")
        s.add_argument("--actor", required=True)
        s.add_argument("--out")
    r = sub.add_parser("run")
    common(r)
    r.add_argument("--project", required=True)
    r.add_argument("--trigger", required=True, choices=TRIGGERS)
    r.add_argument("--governance", action="store_true", help="参谋长用：skill、bot 设定、名册对平台、名册库路径")
    r.add_argument("--log", action="store_true", help="最后写一行检查日志（check_log）")
    r.add_argument("--prev")
    i = sub.add_parser("inventory")
    common(i)
    sub.add_parser("selftest")
    a = ap.parse_args(argv)
    if a.cmd == "selftest":
        import check_selftest
        return check_selftest.run()
    env = make_env(a)
    if a.cmd == "run":
        L.check_project_name(a.project)
        code, text, _, out = run_check(env, a.project, a.actor, a.trigger, a.governance, a.log, a.out, a.prev, a.workflows_dir)
        if "结果文件：" not in text:
            text += f"\n结果文件：{out}"
    else:
        code, text, _, _ = inventory(env, a.actor, a.out, a.workflows_dir)
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
