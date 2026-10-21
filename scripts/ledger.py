#!/usr/bin/env python3
"""台账写入脚本 ledger.py——纯标准库 Python 3，放在本项目仓库 scripts/ 下，跟着本机克隆的版本生效。
台账（一项目一个 SQLite 库：<数据根目录>/<项目名>/ledger.db）只能经本脚本写。规则见 schema/schema.sql。

写命令（都要 --actor <bot ID>）：init  genesis  add  update（核心列只改错字加 --typo）  dep add|void  apply  meta set  degrade on|off  migrate
只读命令：migrate-dryrun（在拷贝上演练迁移，报前后行数和结构差异）  frictions（跨库按节号汇总摩擦 M 表）  where  show  dump  changes  deps  query  snapshot  backup-status
备份：backup（补推）  backup-init --remote <已存在的仓库地址>  restore
自测：selftest（临时目录，不碰真库、不联网）

可配置（环境变量，默认值是正式位置；自测全部指向临时目录）：
  FLOW_DATA_ROOT       数据根目录，默认 /home/box/flow-data
  FLOW_AGENTS_DIR      平台 bot 目录，默认 /home/box/agent-data/agents
  FLOW_DELETED_AGENTS  平台删除记录，默认 /home/box/sand-data/deleted-agents.json
  FLOW_BACKUP_TIMEOUT  每次推备份的总超时秒数，默认 60
备份仓库的本机克隆固定是 <数据根目录>/.backup-repo，远端就是 backup-init 时给的地址（可以是本地裸仓库）。
本脚本从不建远端仓库。

退出码：0 成功（备份失败也是 0）；1 被规则拒绝，什么都没写；2 环境问题，什么都没写；3 用法错误。
"""
import argparse, csv, datetime, hashlib, json, os, re, sqlite3, subprocess, sys, time, uuid
import urllib.parse

os.environ["TZ"] = "Asia/Shanghai"  # 库里时间一律北京时间（schema.sql 文件头），不随机器时区变
if hasattr(time, "tzset"):
    time.tzset()

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(DEFAULT_REPO, "build"))
import hash as H  # noqa: E402

GOV = "流程治理"
TABLES = ("F", "D", "R", "S", "P", "A", "B", "M")
LOG_TABLES = ("change_log", "check_log", "backup_log")
ALL_TABLES = TABLES + ("dep", "meta") + LOG_TABLES
SYSTEM_COLS = {"seq", "code", "rid", "版本代号", "created_at", "created_by", "id"}
DEFAULT_COLS = {"F": ["编号", "内容", "状态", "有效期"], "D": ["编号", "决定", "状态", "谁拍板"],
                "R": ["编号", "风险", "影响", "状态"], "S": ["编号", "节", "结论"],
                "P": ["编号", "步骤", "状态", "执行人"], "A": ["版本代号", "标准", "级别", "状态"],
                "B": ["编号", "名称", "类型", "状态"], "M": ["编号", "日期", "节号", "类别", "摩擦"]}
META_SETTABLE = {"项目仓库", "流程版本", "状态"}
SOFT_WORDS = ["银行卡", "信用卡", "借记卡", "卡号", "身份证", "护照", "驾照", "社保", "妻子", "丈夫", "老婆", "老公",
              "配偶", "父母", "孩子", "家人", "名下", "住址", "收款账户"]
ALIASES = {"onboarding": ["上手"], "genesis": ["创世"], "chief-of-staff-governance": ["参谋长治理"],
           "general-flow": ["通用流程"]}


class Reject(Exception):      # 退出码 1
    pass


class EnvError(Exception):    # 退出码 2
    pass


class Usage(Exception):       # 退出码 3
    pass


def now():
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def today():
    return datetime.date.today().isoformat()


# ---------- 环境 ----------
class Env:
    def __init__(self, data_root=None, agents_dir=None, deleted=None, repo=None, backup_timeout=None):
        self.data_root = os.path.abspath(data_root or os.environ.get("FLOW_DATA_ROOT") or "/home/box/flow-data")
        self.agents_dir = agents_dir or os.environ.get("FLOW_AGENTS_DIR") or "/home/box/agent-data/agents"
        self.deleted = deleted or os.environ.get("FLOW_DELETED_AGENTS") or "/home/box/sand-data/deleted-agents.json"
        self.repo = os.path.abspath(repo or os.environ.get("FLOW_REPO") or DEFAULT_REPO)
        self.backup_timeout = float(backup_timeout or os.environ.get("FLOW_BACKUP_TIMEOUT") or 60)

    def proj_dir(self, project):
        return os.path.join(self.data_root, project)

    def db(self, project):
        return os.path.join(self.data_root, project, "ledger.db")

    @property
    def backup_repo(self):
        return os.path.join(self.data_root, ".backup-repo")

    @property
    def backup_lock(self):
        return os.path.join(self.data_root, ".backup.lock")

    def runs_dir(self, project, actor):
        d = os.path.join(self.data_root, project, "runs",
                         datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + (actor or "anon")[:8])
        os.makedirs(d, exist_ok=True)
        return d


def check_project_name(p):
    if not p or len(p) > 40 or "/" in p or "\\" in p or p.startswith(".") or p.strip() != p:
        raise Usage(f"项目名不合规：{p!r}（1–40 个字，不含 / \\，不以 . 开头，首尾无空白）")
    return p


# ---------- 仓库 ----------
def git(repo, *args, timeout=30):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip() or f"git {' '.join(args)} 失败")
    return r.stdout


def _vkey(tag):
    m = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", tag or "")
    return tuple(int(x) for x in m.groups()) if m else None


def repo_info(repo):
    """{tag, commit, clean, label, ref}。label：在 tag 上是 tag，不在是 draft-<提交号前 12 位>。ref：tag 或完整提交号。"""
    try:
        commit = git(repo, "rev-parse", "HEAD").strip()
        clean = git(repo, "status", "--porcelain").strip() == ""
        tags = [t for t in git(repo, "tag", "--points-at", "HEAD").split() if _vkey(t)]
    except Exception as e:
        raise EnvError(f"读不到克隆 {repo} 的 git 信息：{e}")
    tag = max(tags, key=_vkey) if tags else None
    return {"tag": tag, "commit": commit, "clean": clean, "label": tag or f"draft-{commit[:12]}", "ref": tag or commit}


def schema_text(repo):
    p = os.path.join(repo, "schema", "schema.sql")
    try:
        return open(p, encoding="utf-8").read()
    except OSError as e:
        raise EnvError(f"读不到 {p}：{e}")


def schema_version_of(text):
    m = re.search(r"^-- schema_version:\s*(\d+)\s*$", text, re.M)
    if not m:
        raise EnvError("schema.sql 头部缺「-- schema_version: N」")
    return int(m.group(1))


def _only_comments(s):
    return all(l.strip().startswith("--") or not l.strip() for l in s.splitlines())


def split_sql(text):
    """按完整语句切分（触发器里的分号不切），去掉语句前的整行注释。"""
    out, buf = [], ""
    for line in text.splitlines(keepends=True):
        if not buf.strip() and line.strip().startswith("--"):
            continue
        buf += line
        if sqlite3.complete_statement(buf):
            if not _only_comments(buf):
                out.append(buf.strip())
            buf = ""
    if buf.strip() and not _only_comments(buf):
        raise EnvError("SQL 文件结尾有不完整的语句")
    return out


# ---------- 连接 ----------
def connect_rw(path):
    c = sqlite3.connect(path, timeout=10, isolation_level=None)
    c.execute("PRAGMA busy_timeout=10000")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def connect_ro(path):
    if not os.path.exists(path):
        raise EnvError(f"库不存在：{path}")
    c = sqlite3.connect("file:" + urllib.parse.quote(path) + "?mode=ro", uri=True, timeout=10, isolation_level=None)
    c.execute("PRAGMA busy_timeout=10000")
    c.execute("PRAGMA query_only=ON")
    return c


def meta_of(c):
    return dict(c.execute("SELECT key,value FROM meta"))


def norm_sql(s):
    return re.sub(r"\s+", " ", s or "").strip()


def structure(c):
    """库结构指纹：sqlite_master 每条（类型、名字、所属表、规范化 SQL）+ enum + f_default_ttl 每行。"""
    objs = {(t, n): (tb, norm_sql(s)) for t, n, tb, s in
            c.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
    try:
        enum = set(c.execute("SELECT tbl,col,val,ord,默认隐藏 FROM enum"))
        ttl = set(c.execute("SELECT 类别,天数,写法 FROM f_default_ttl"))
    except sqlite3.Error:
        enum, ttl = set(), set()
    return {"objs": objs, "enum": enum, "ttl": ttl}


def reference_structure(schema_sql):
    m = sqlite3.connect(":memory:")
    m.executescript(schema_sql)
    s = structure(m)
    m.close()
    return s


def diff_structure(have, want):
    """返回 [(类别, 名字, 说明)]。"""
    out = []
    for k in sorted(set(want["objs"]) - set(have["objs"])):
        out.append(("少了", f"{k[0]} {k[1]}", "库里没有"))
    for k in sorted(set(have["objs"]) - set(want["objs"])):
        out.append(("多了", f"{k[0]} {k[1]}", "标准里没有"))
    for k in sorted(set(have["objs"]) & set(want["objs"])):
        if have["objs"][k] != want["objs"][k]:
            out.append(("改了", f"{k[0]} {k[1]}", "SQL 和标准不同"))
    for name in ("enum", "ttl"):
        for r in sorted(want[name] - have[name], key=str):
            out.append(("少了", f"{name} 行", "|".join(map(str, r))))
        for r in sorted(have[name] - want[name], key=str):
            out.append(("多了", f"{name} 行", "|".join(map(str, r))))
    return out


# ---------- 平台 bot ----------
def deleted_ids(env):
    try:
        d = json.load(open(env.deleted, encoding="utf-8"))
    except FileNotFoundError:
        return set()
    except Exception as e:
        raise EnvError(f"读不到删除记录 {env.deleted}：{e}")
    if isinstance(d, dict):
        a = d.get("agents", d)
        return set(a.keys()) if isinstance(a, dict) else set(a)
    return set(d)


def profile(env, bot_id):
    p = os.path.join(env.agents_dir, bot_id, "profile.json")
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception as e:
        raise EnvError(f"读不到 {p}：{e}")


def bot_alive(env, bot_id):
    return profile(env, bot_id) is not None and bot_id not in deleted_ids(env)


def platform_bots(env):
    """{bot_id: profile}，已去掉删除记录里的。"""
    out, dele = {}, deleted_ids(env)
    if not os.path.isdir(env.agents_dir):
        raise EnvError(f"平台 bot 目录不存在：{env.agents_dir}")
    for bid in sorted(os.listdir(env.agents_dir)):
        if bid in dele:
            continue
        p = profile(env, bid)
        if p is not None:
            out[bid] = p
    return out


def roster(env):
    """流程治理库 B 表全部行（dict）；库不在返回 None。"""
    p = env.db(GOV)
    if not os.path.exists(p):
        return None
    c = connect_ro(p)
    try:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute("SELECT * FROM B ORDER BY seq")]
    finally:
        c.close()


def same_path(a, b):
    return bool(a) and bool(b) and os.path.realpath(a) == os.path.realpath(b)


def verify_actor(env, project, actor, genesis=False):
    """J6（严格）：bot 在平台上存在；项目库只认本项目在用副官，流程治理库只认在用参谋长；名册登记的库路径必须是本库。"""
    if not actor or not re.fullmatch(r"[0-9A-Za-z-]{8,64}", actor):
        raise Usage("--actor 必须是 bot ID")
    if not bot_alive(env, actor):
        raise Reject(f"写入者 {actor} 在平台上不存在（没有 profile.json 或已在删除记录里）")
    rows = roster(env)
    target = env.db(project)
    live_cos = [r for r in (rows or []) if r["类型"] == "参谋长" and r["状态"] == "在用"]
    if project == GOV:
        if genesis:
            if live_cos and live_cos[0]["bot_id"] != actor and bot_alive(env, live_cos[0]["bot_id"]):
                raise Reject(f"已有在用参谋长 {live_cos[0]['bot_id']}（{live_cos[0]['code']}），平台上还在；创世引导不接受别的写入者")
            if live_cos and live_cos[0]["bot_id"] == actor:
                return "名册：在用参谋长"
            prof = profile(env, actor) or {}
            if prof.get("name") != "参谋长":
                raise Reject("创世引导例外：写入者在平台上的名字不是「参谋长」")
            tpl = os.path.join(env.repo, "templates", "chief-of-staff.md")
            try:
                want = H.norm_hash_text(open(tpl, encoding="utf-8-sig").read())
            except OSError as e:
                raise EnvError(f"读不到 {tpl}：{e}")
            if H.norm_hash_text(prof.get("description") or "") != want:
                raise Reject("创世引导例外：写入者的设定和克隆里的 templates/chief-of-staff.md 不一致")
            return "创世引导例外（名字是参谋长、设定等于克隆模板）"
        if rows is None:
            raise EnvError(f"流程治理库不存在：{target}")
        if not any(r["bot_id"] == actor for r in live_cos):
            raise Reject(f"写入者 {actor} 不是名册里的在用参谋长；流程治理库只认在用参谋长")
        r = live_cos[0]
        if not same_path(r.get("库路径"), target):
            raise Reject(f"名册 {r['code']} 登记的库路径 {r.get('库路径')} 不是本库 {target}")
        return f"名册 {r['code']}：在用参谋长"
    if rows is None:
        raise EnvError(f"流程治理库不存在，无法核对名册：{env.db(GOV)}")
    mine = [r for r in rows if r["bot_id"] == actor and r["状态"] != "已废弃"]
    if any(r["类型"] == "参谋长" for r in mine):
        raise Reject("参谋长不写副官的库（项目库只认本项目在用副官）")
    ok = [r for r in mine if r["类型"] == "副官" and r["状态"] == "在用" and r["所属项目"] == project]
    if not ok:
        raise Reject(f"写入者 {actor} 不是项目「{project}」的在用副官；项目库只认本项目在用副官")
    if not same_path(ok[0].get("库路径"), target):
        raise Reject(f"名册 {ok[0]['code']} 登记的库路径 {ok[0].get('库路径')} 不是本库 {target}")
    return f"名册 {ok[0]['code']}：项目「{project}」在用副官"


# ---------- 个人信息（N2 方案 a） ----------
_B = r"(?<![0-9A-Za-z])"
_E = r"(?![0-9A-Za-z])"
RE_CARD = re.compile(_B + r"(\d{13,19}|\d{4}(?:[ -]\d{4}){2}[ -]\d{1,7}|\d{4}[ -]\d{6}[ -]\d{5})" + _E)
RE_ID = re.compile(_B + r"(\d{17}[0-9Xx])" + _E)
RE_MOBILE = re.compile(_B + r"(1[3-9]\d{9})" + _E)
RE_WALLET = re.compile(_B + r"(0x[0-9a-fA-F]{40})" + _E)


def luhn(d):
    s, alt = 0, False
    for ch in reversed(d):
        n = int(ch)
        if alt:
            n = n * 2 - 9 if n > 4 else n * 2
        s += n
        alt = not alt
    return s % 10 == 0


def id_ok(s):
    w = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    try:
        datetime.date(int(s[6:10]), int(s[10:12]), int(s[12:14]))
    except ValueError:
        return False
    return "10X98765432"[sum(int(a) * b for a, b in zip(s[:17], w)) % 11] == s[17].upper()


def _is_timestamp(d):
    if len(d) != 14 or not d.startswith("20"):
        return False
    try:
        datetime.datetime.strptime(d, "%Y%m%d%H%M%S")
        return True
    except ValueError:
        return False


def pii_hard(text):
    """返回命中的类别列表（不返回原文）。"""
    hits = []
    if not isinstance(text, str) or not text:
        return hits
    for m in RE_CARD.finditer(text):
        d = re.sub(r"[ -]", "", m.group(1))
        if 13 <= len(d) <= 19 and luhn(d) and not _is_timestamp(d) and not (len(d) == 18 and id_ok(d)):
            hits.append("银行卡号")
            break
    for m in RE_ID.finditer(text):
        if id_ok(m.group(1)):
            hits.append("身份证号")
            break
    if RE_MOBILE.search(text):
        hits.append("手机号")
    if RE_WALLET.search(text):
        hits.append("钱包地址")
    return hits


def pii_soft(text):
    return [w for w in SOFT_WORDS if isinstance(text, str) and w in text]


def walk_strings(obj, path=""):
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk_strings(k, f"{path}.键")
            yield from walk_strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from walk_strings(v, f"{path}[{i}]")


def pii_gate(values, pii_checked):
    """硬拦 4 类不能放行；敏感词默认拦，带 --pii-checked 理由才写。返回要加到 reason 前面的留痕前缀。"""
    hard, soft = [], []
    for p, s in walk_strings(values):
        for h in pii_hard(s):
            hard.append(f"{p or '值'}：{h}")
        for w in pii_soft(s):
            soft.append(f"{p or '值'}：「{w}」")
    if hard:
        raise Reject("个人信息拦截（不能放行）：" + "；".join(hard) +
                     "。原文不进台账，改写成「共享记忆 + 日期 + 条目名」，例如：共享记忆 2026-10-14「可用企业主体」")
    if pii_checked is not None and pii_hard(pii_checked):
        raise Reject("个人信息拦截：--pii-checked 的理由里本身含个人信息原文")
    if soft:
        if not (pii_checked and pii_checked.strip()):
            raise Reject("个人信息敏感词拦截：" + "；".join(soft) +
                         "。确认没有原文细节的话，加 --pii-checked \"理由\" 再写（理由会留在修改记录里）；"
                         "否则改写成「共享记忆 + 日期 + 条目名」")
        return f"[pii-checked] {pii_checked.strip()}；"
    return ""


# ---------- 写事务 ----------
def cols_of(c, table):
    return [r[1] for r in c.execute(f"PRAGMA table_xinfo({table})")]


def writable_cols(c, table):
    return [r[1] for r in c.execute(f"PRAGMA table_xinfo({table})") if r[6] == 0 and r[1] not in SYSTEM_COLS]


def check_version(env, c):
    want = schema_version_of(schema_text(env.repo))
    m = meta_of(c)
    have = int(m.get("schema_version") or 0)
    if have < want:
        raise EnvError(f"库 schema {have} 比克隆的 schema {want} 低：先按发布顺序迁移（ledger.py migrate），只读命令照常能用")
    if have > want:
        raise EnvError(f"库 schema {have} 比克隆的 schema {want} 高：克隆比库旧，先更新克隆")
    return m


def set_ctx(c, actor, reason, mode):
    c.execute("UPDATE _ctx SET actor=?,reason=?,mode=? WHERE id=1", (actor, reason, mode))


def clear_ctx(c):
    c.execute("UPDATE _ctx SET actor=NULL,reason=NULL,mode=NULL WHERE id=1")


def max_change(c):
    return c.execute("SELECT coalesce(max(id),0) FROM change_log").fetchone()[0]


def run_write(env, project, actor, reason, body, mode="write", create=False, genesis=False):
    """一条命令一个事务：核对写入者 → BEGIN IMMEDIATE → 设 _ctx → body(c) → 清 _ctx → 提交 → 推备份（事务外）。"""
    check_project_name(project)
    if not reason or not reason.strip():
        raise Usage("--reason 不能为空")
    path = env.db(project)
    who = verify_actor(env, project, actor, genesis=genesis)
    if create:
        if os.path.exists(path):
            raise Reject(f"库已存在：{path}")
        os.makedirs(os.path.dirname(path), exist_ok=True)
    elif not os.path.exists(path):
        raise EnvError(f"库不存在：{path}")
    c = connect_rw(path)
    try:
        if create:
            c.execute("PRAGMA journal_mode=DELETE")
        c.execute("BEGIN IMMEDIATE")
        try:
            if create:
                for st in split_sql(schema_text(env.repo)):
                    c.execute(st)
            else:
                check_version(env, c)
            before = max_change(c)
            set_ctx(c, actor, reason, mode)
            res = body(c) or {}
            clear_ctx(c)
            after = max_change(c)
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            if create:
                c.close()
                for suf in ("", "-journal"):
                    if os.path.exists(path + suf):
                        os.remove(path + suf)
            raise
    except sqlite3.IntegrityError as e:
        raise Reject(friendly(e))
    except sqlite3.OperationalError as e:
        if "locked" in str(e) or "busy" in str(e):
            raise EnvError(f"锁等待超时：{e}")
        raise Reject(str(e))
    finally:
        try:
            c.close()
        except Exception:
            pass
    res.update({"写入者": actor, "身份": who, "修改记录": [before + 1, after] if after > before else []})
    res["备份"] = backup_project(env, project, actor, reason)
    return res


UNIQUE_MSG = {"B.类型": "在用参谋长只能有一个", "B.bot_id": "同一 bot ID 只能有一行不是「已废弃」",
              "A.编号": "同一 A 编号只能有一行「用户已确认」", "S.节": "每节只能有一条不是作废的结论",
              "dep.依赖方, dep.被依赖": "这条依赖已经存在"}


def friendly(e):
    s = str(e)
    m = re.match(r"UNIQUE constraint failed: (.+)$", s)
    if m and m.group(1) in UNIQUE_MSG:
        return f"{UNIQUE_MSG[m.group(1)]}（{s}）"
    return s


def ins(c, table, actor, values):
    vals = {k: v for k, v in values.items() if v is not None}
    if table == "A":
        if "编号" not in vals:
            vals["编号"] = c.execute("SELECT coalesce(max(编号),0)+1 FROM A").fetchone()[0]
        vals["编号"] = int(vals["编号"])
        vals["版本号"] = c.execute("SELECT coalesce(max(版本号),0)+1 FROM A WHERE 编号=?", (vals["编号"],)).fetchone()[0]
    elif table != "dep":
        vals["seq"] = c.execute(f"SELECT coalesce(max(seq),0)+1 FROM {table}").fetchone()[0]
    vals["created_by"] = actor
    ks = list(vals)
    cur = c.execute(f"INSERT INTO {table}({','.join(ks)}) VALUES({','.join('?' * len(ks))})", [vals[k] for k in ks])
    rowid = cur.lastrowid
    if table == "A":
        return c.execute("SELECT 版本代号 FROM A WHERE rid=?", (rowid,)).fetchone()[0]
    if table == "dep":
        return f"dep-{rowid}"
    return c.execute(f"SELECT code FROM {table} WHERE rowid=?", (rowid,)).fetchone()[0]


def fill_f_defaults(c, vals):
    """N1：有效期空着时按类别默认值填，依据写「类别默认值」。"""
    if vals.get("有效期"):
        return
    r = c.execute("SELECT 天数,写法 FROM f_default_ttl WHERE 类别=?", (vals.get("类别"),)).fetchone()
    if not r:
        return
    days, how = r
    v = how
    if days is not None and vals.get("查证日期"):
        try:
            d = datetime.date.fromisoformat(str(vals["查证日期"])[:10]) + datetime.timedelta(days=days)
            v = f"{d.isoformat()}（{how}）"
        except ValueError:
            pass
    vals["有效期"] = v
    vals["有效期依据"] = vals.get("有效期依据") or f"类别默认值（{vals.get('类别')}）"


def coerce(c, table, vals):
    allowed = set(writable_cols(c, table))
    if table == "A":
        allowed.add("编号")
    bad = [k for k in vals if k not in allowed]
    if bad:
        raise Usage(f"{table} 没有这些可写列：{','.join(bad)}（可写：{','.join(sorted(allowed))}）")
    out = {}
    for k, v in vals.items():
        v = None if v == "" else v
        if k in ("节", "编号") and v is not None:
            try:
                v = int(v)
            except (TypeError, ValueError):
                raise Reject(f"{k} 必须是整数")
        out[k] = v
    return out


def do_add(c, table, actor, vals, deps=()):
    if table not in TABLES:
        raise Usage(f"表只能是 {' '.join(TABLES)}")
    vals = coerce(c, table, vals)
    if table == "F":
        fill_f_defaults(c, vals)
    if table == "D":
        vals.setdefault("日期", today())
    if table == "B":
        vals.setdefault("创建日期", today())
    if table == "M":
        vals.setdefault("日期", today())
        vals.setdefault("bot", actor)
    code = ins(c, table, actor, vals)
    for d in deps:
        ins(c, "dep", actor, {"依赖方": base_code(code), "被依赖": base_code(d)})
    return code


def locate(c, code):
    m = re.fullmatch(r"A-(\d+)v(\d+)", code or "")
    if m:
        r = c.execute("SELECT rid FROM A WHERE 编号=? AND 版本号=?", (int(m[1]), int(m[2]))).fetchone()
        if not r:
            raise Reject(f"{code} 不存在")
        return "A", "rid", r[0]
    m = re.fullmatch(r"([FDRSPBM])-(\d+)", code or "")
    if not m:
        raise Usage(f"编号写法不对：{code}（A 用 A-3v2 这种写法）")
    r = c.execute(f"SELECT seq FROM {m[1]} WHERE seq=?", (int(m[2]),)).fetchone()
    if not r:
        raise Reject(f"{code} 不存在")
    return m[1], "seq", r[0]


def do_update(c, code, vals):
    table, key, k = locate(c, code)
    vals = coerce(c, table, vals)
    if table == "A":
        vals.pop("编号", None)
    if not vals:
        raise Usage("没有要改的列")
    sets = ",".join(f"{x}=?" for x in vals)
    c.execute(f"UPDATE {table} SET {sets} WHERE {key}=?", list(vals.values()) + [k])
    return code


TYPO_COLS = {"F": ["内容"], "D": ["决定", "理由"], "R": ["风险", "对策"], "S": ["结论"], "P": ["自验证方式"],
             "A": ["标准", "依据", "检查方法"]}
TYPO_MAX = 2  # 每列最多改几个字（编辑距离）


def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def do_typo(c, code, vals):
    """核心列只改错字（意思不变）：只许文字核心列，每列改动 1–2 个字；其余列一律不在这里改。"""
    table, key, k = locate(c, code)
    allowed = TYPO_COLS.get(table)
    if not allowed:
        raise Reject(f"{table} 表没有可按「仅错字」改的列")
    if not vals:
        raise Usage("没有要改的列")
    bad = [x for x in vals if x not in allowed]
    if bad:
        raise Reject(f"--typo 只能改 {table} 表的 {'、'.join(allowed)}；{'、'.join(bad)} 不行（非核心列用普通 update）")
    row = c.execute(f"SELECT {','.join(vals)} FROM {table} WHERE {key}=?", (k,)).fetchone()
    for (col, new), old in zip(vals.items(), row):
        d = edit_distance(str(old or ""), str(new))
        if d == 0:
            raise Reject(f"{col} 没有变化")
        if d > TYPO_MAX:
            raise Reject(f"{col} 改了 {d} 个字，超过「仅错字」上限 {TYPO_MAX}：意思有变就新建一条并标记旧条目")
    sets = ",".join(f"{x}=?" for x in vals)
    c.execute(f"UPDATE {table} SET {sets} WHERE {key}=?", list(vals.values()) + [k])
    return code


def base_code(s):
    """A 的版本代号（A-1v2）在依赖里一律按 A 编号（A-1）记：依赖指向在用版本。"""
    m = re.fullmatch(r"(A-\d+)v\d+", s.strip()) if isinstance(s, str) else None
    return m.group(1) if m else s


def do_dep(c, actor, op, a, b, note=None):
    a, b = base_code(a), base_code(b)
    if op == "add":
        return ins(c, "dep", actor, {"依赖方": a, "被依赖": b, "说明": note})
    r = c.execute("SELECT id FROM dep WHERE 依赖方=? AND 被依赖=?", (a, b)).fetchone()
    if not r:
        raise Reject(f"依赖 {a} → {b} 不存在")
    c.execute("UPDATE dep SET 状态='作废' WHERE id=?", (r[0],))
    return f"dep-{r[0]}"


def parse_sets(items):
    out = {}
    for it in items or []:
        if "=" not in it:
            raise Usage(f"--set 要写成 列=值：{it}")
        k, v = it.split("=", 1)
        out[k.strip()] = v
    return out


# ---------- 备份（J1） ----------
class FileLock:
    def __init__(self, path, wait=30):
        self.path, self.wait, self.f = path, wait, None

    def __enter__(self):
        import fcntl
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.f = open(self.path, "a")
        t0 = time.time()
        while True:
            try:
                fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if time.time() - t0 > self.wait:
                    self.f.close()
                    raise TimeoutError(f"等备份锁超过 {self.wait} 秒")
                time.sleep(0.1)

    def __exit__(self, *a):
        import fcntl
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


def dump_sql(path):
    c = connect_ro(path)
    try:
        return "\n".join(c.iterdump()) + "\n"
    finally:
        c.close()


def _branch(br):
    try:
        return git(br, "symbolic-ref", "--short", "HEAD").strip()
    except RuntimeError:
        return "main"


def backup_project(env, project, actor, reason):
    """写入提交之后调用：导出 SQL → 本地提交 → 推送 → 写 backup_log。失败不抛异常、不回滚写入，返回结果。"""
    path, br = env.db(project), env.backup_repo
    res = {"结果": "失败", "提交": None, "错误": None}
    remote = None
    t0 = time.time()
    try:
        with FileLock(env.backup_lock):
            if not os.path.isdir(os.path.join(br, ".git")):
                raise RuntimeError("备份仓库未初始化（先 backup-init --remote <已存在的仓库地址>）")
            remote = git(br, "remote", "get-url", "origin").strip()
            c = connect_ro(path)
            try:
                m = meta_of(c)
                upto = max_change(c)
            finally:
                c.close()
            d = os.path.join(br, project)
            idf = os.path.join(d, "库ID")
            if os.path.exists(idf) and open(idf, encoding="utf-8").read().strip() != m.get("库ID"):
                raise RuntimeError(f"备份仓库里的 {project}/库ID 和本库不一致（同名项目是另一个库），不覆盖，等用户决定")
            os.makedirs(d, exist_ok=True)
            open(os.path.join(d, "ledger.sql"), "w", encoding="utf-8").write(dump_sql(path))
            open(idf, "w", encoding="utf-8").write(m.get("库ID", "") + "\n")
            git(br, "add", "-A", "--", project)
            if git(br, "status", "--porcelain", "--", project).strip():
                git(br, "commit", "-q", "-m", f"{project} change_log≤{upto} {actor}：{reason}"[:300])
            left = lambda: max(5, env.backup_timeout - (time.time() - t0))
            b = _branch(br)
            git(br, "fetch", "-q", "origin", timeout=left())
            if git(br, "ls-remote", "--heads", "origin", b, timeout=left()).strip():
                git(br, "rebase", "-q", f"origin/{b}", timeout=left())
            git(br, "push", "-q", "origin", f"HEAD:{b}", timeout=left())
            res["提交"] = git(br, "rev-parse", "--short", "HEAD").strip()
            res["结果"] = "成功"
            res["change_log_upto"] = upto
    except Exception as e:
        res["错误"] = (str(e) or e.__class__.__name__)[-500:]
    try:
        c = connect_rw(path)
        try:
            c.execute("BEGIN IMMEDIATE")
            set_ctx(c, actor, reason, "backup")
            c.execute("INSERT INTO backup_log(actor,结果,change_log_upto,remote,commit_id,error) VALUES(?,?,?,?,?,?)",
                      (actor, res["结果"], res.get("change_log_upto", max_change(c)), remote, res["提交"], res["错误"]))
            clear_ctx(c)
            c.execute("COMMIT")
        finally:
            c.close()
    except Exception as e:
        res["错误"] = (res["错误"] or "") + f"；backup_log 也没写进去：{e}"
    return res


def backup_line(b):
    if b["结果"] == "成功":
        return f"备份：成功（提交 {b['提交']}）"
    return f"备份：失败（{b['错误']}）。写入已完成，不要重试写入；每日扫描会报，可以用 backup 手动补推"


def unpushed(br):
    """备份仓库本机有几个没推出去的提交（只看本地 refs，不联网）。"""
    b = _branch(br)
    try:
        git(br, "rev-parse", "--verify", "-q", f"refs/remotes/origin/{b}", timeout=10)
        return int(git(br, "rev-list", "--count", f"origin/{b}..HEAD").strip())
    except RuntimeError:
        try:
            return int(git(br, "rev-list", "--count", "HEAD").strip())
        except RuntimeError:
            return 0


# ---------- 快照 / 恢复 ----------
def snapshot(env, project, label, actor=None):
    src = env.db(project)
    label = re.sub(r"[^\w.-]+", "_", label or "手动")[:40]
    d = os.path.join(env.proj_dir(project), "snapshots")
    s = connect_ro(src)
    os.makedirs(d, exist_ok=True)
    base = os.path.join(d, datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{label}")
    dst, n = base + ".db", 1
    while os.path.exists(dst):
        dst, n = f"{base}-{n}.db", n + 1
    t = sqlite3.connect(dst)
    try:
        s.backup(t)
        ok = t.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        s.close()
        t.close()
    if ok != "ok":
        raise EnvError(f"快照完整性检查不过：{ok}")
    return dst, hashlib.sha256(open(dst, "rb").read()).hexdigest()


def restore(env, project, commit=None, sql_text=None):
    dst = env.db(project)
    if os.path.exists(dst):
        raise Reject(f"目标库已存在，不覆盖：{dst}")
    if sql_text is None:
        if not os.path.isdir(os.path.join(env.backup_repo, ".git")):
            raise EnvError("备份仓库未初始化")
        try:
            sql_text = git(env.backup_repo, "show", f"{commit or 'HEAD'}:{project}/ledger.sql")
        except RuntimeError as e:
            raise EnvError(f"备份里没有 {project}/ledger.sql：{e}")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    c = sqlite3.connect(dst, isolation_level=None)
    try:
        c.execute("PRAGMA journal_mode=DELETE")
        c.executescript(sql_text)
        ok = c.execute("PRAGMA integrity_check").fetchone()[0]
        diff = diff_structure(structure(c), reference_structure(schema_text(env.repo)))
    except Exception:
        c.close()
        os.remove(dst)
        raise
    c.close()
    if ok != "ok":
        raise EnvError(f"恢复后完整性检查不过：{ok}（文件留在 {dst}）")
    return dst, diff


# ---------- 迁移 ----------
def migrate_db(env, project, actor, approved, steps, target_schema, target_ref):
    """steps：[(版本号, 迁移 SQL)]。单事务：删全部触发器/视图/显式索引 → 跑迁移 SQL → 按目标 schema 重建
    触发器/视图/索引 → 写 meta → 记一条 D（类型「版本」）→ 和新建库逐条比，不一致整体回滚。"""
    path = env.db(project)
    who = verify_actor(env, project, actor)
    target_v = schema_version_of(target_schema)
    c0 = connect_ro(path)
    cur_v = int(meta_of(c0).get("schema_version") or 0)
    c0.close()
    if [v for v, _ in steps] != list(range(cur_v + 1, target_v + 1)):
        raise Usage(f"迁移步骤不连续：库 {cur_v}，目标 {target_v}，给了 {[v for v, _ in steps]}")
    if not (approved or "").strip():
        raise Usage("--approved 要写用户原话和日期")
    pii_gate(approved, None)
    snap, _ = snapshot(env, project, f"migrate-to-{target_v}", actor)
    want = reference_structure(target_schema)
    c = connect_rw(path)
    try:
        c.execute("BEGIN IMMEDIATE")
        try:
            set_ctx(c, actor, f"迁移 schema {cur_v}→{target_v}：{approved}", "migrate")
            for t, n in c.execute("SELECT type,name FROM sqlite_master WHERE type IN ('trigger','view') "
                                  "OR (type='index' AND sql IS NOT NULL)").fetchall():
                c.execute(f'DROP {t.upper()} IF EXISTS "{n}"')
            for _, sql in steps:
                for st in split_sql(sql):
                    c.execute(st)
            for st in split_sql(target_schema):
                if re.match(r"CREATE\s+(UNIQUE\s+)?(TRIGGER|VIEW|INDEX)\b", st, re.I):
                    c.execute(st)
            c.execute("UPDATE meta SET value=? WHERE key='schema_version'", (str(target_v),))
            c.execute("UPDATE meta SET value=? WHERE key='schema_tag'", (target_ref,))
            ins(c, "D", actor, {"日期": today(), "决定": f"表结构迁移 schema {cur_v}→{target_v}（{target_ref}）",
                                "理由": f"用户批准：{approved}", "来源": f"迁移前快照 {os.path.basename(snap)}",
                                "谁拍板": "用户", "状态": "生效", "类型": "版本"})
            clear_ctx(c)
            diff = diff_structure(structure(c), want)
            if diff:
                raise Reject("迁移后结构和新建库不一致，已整体回滚：" + "；".join(f"{a} {b}" for a, b, _ in diff[:10]))
            fk = c.execute("PRAGMA foreign_key_check").fetchall()
            if fk:
                raise Reject(f"迁移后 foreign_key_check 不过，已整体回滚：{fk[:3]}")
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise
        ok = c.execute("PRAGMA integrity_check").fetchone()[0]
    except sqlite3.Error as e:
        raise Reject(f"迁移出错，已整体回滚：{e}")
    finally:
        c.close()
    if ok != "ok":
        raise EnvError(f"迁移后 integrity_check 不过：{ok}；迁移前快照 {snap}")
    return {"快照": snap, "从": cur_v, "到": target_v, "身份": who,
            "备份": backup_project(env, project, actor, f"迁移 schema {cur_v}→{target_v}")}


def migrate_dryrun(env, project, steps, target_schema, target_ref, out_dir):
    """迁移演练（只读）：用备份接口把真库拷到 out_dir，在拷贝上按 migrate_db 同样的步骤迁移，
    报迁移前后 schema 版本、各表行数、结构差异、foreign_key_check、integrity_check。真库一字不动。"""
    src = env.db(project)
    if not os.path.exists(src):
        raise EnvError(f"库不存在：{src}")
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, f"{project}-dryrun.db")
    if os.path.exists(dst):
        os.remove(dst)
    s0 = connect_ro(src)
    d = sqlite3.connect(dst)
    s0.backup(d)
    s0.close()
    d.close()
    def counts(c):
        names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {n: c.execute(f'SELECT count(*) FROM "{n}"').fetchone()[0] for n in names}
    c = sqlite3.connect(dst, isolation_level=None)
    c.execute("PRAGMA foreign_keys=ON")
    before = counts(c)
    cur_v = int(meta_of(c).get("schema_version") or 0)
    target_v = schema_version_of(target_schema)
    if [v for v, _ in steps] != list(range(cur_v + 1, target_v + 1)):
        c.close()
        raise Usage(f"迁移步骤不连续：库 {cur_v}，目标 {target_v}，给了 {[v for v, _ in steps]}")
    err = None
    try:
        c.execute("BEGIN IMMEDIATE")
        set_ctx(c, "迁移演练", f"迁移演练 schema {cur_v}→{target_v}", "migrate")
        for t, n in c.execute("SELECT type,name FROM sqlite_master WHERE type IN ('trigger','view') "
                              "OR (type='index' AND sql IS NOT NULL)").fetchall():
            c.execute(f'DROP {t.upper()} IF EXISTS "{n}"')
        for _, sql in steps:
            for st in split_sql(sql):
                c.execute(st)
        for st in split_sql(target_schema):
            if re.match(r"CREATE\s+(UNIQUE\s+)?(TRIGGER|VIEW|INDEX)\b", st, re.I):
                c.execute(st)
        c.execute("UPDATE meta SET value=? WHERE key='schema_version'", (str(target_v),))
        c.execute("UPDATE meta SET value=? WHERE key='schema_tag'", (target_ref,))
        clear_ctx(c)
        c.execute("COMMIT")
    except sqlite3.Error as e:
        err = str(e)
        c.execute("ROLLBACK")
    diff = [] if err else diff_structure(structure(c), reference_structure(target_schema))
    fk = [] if err else c.execute("PRAGMA foreign_key_check").fetchall()
    ok = c.execute("PRAGMA integrity_check").fetchone()[0]
    after = counts(c)
    c.close()
    rows = [(t, before.get(t, "—"), after.get(t, "—")) for t in sorted(set(before) | set(after))]
    passed = not err and not diff and not fk and ok == "ok" and all(
        isinstance(b, int) and isinstance(a2, int) and a2 >= b for t, b, a2 in rows if t in before and t in after)
    return {"拷贝": dst, "从": cur_v, "到": target_v, "错误": err, "结构差异": diff, "外键": fk, "完整性": ok,
            "行数": rows, "通过": passed}


# ---------- 摩擦汇总（只读，跨库） ----------
def frictions(env, since=None, include_cited=False):
    """名册登记的每个库（不是「已废弃」、有库路径的；含流程治理库）只读取 M 表，按节号汇总。
    已被流程治理库 D 表（类型「候选」）的来源或理由引用过的「项目 M-n」默认不列（include_cited 时列出并标注）。"""
    rows = roster(env) or []
    dbs, seen = [], set()
    for r in rows:
        p = r.get("库路径")
        if not p or r["状态"] == "已废弃" or os.path.realpath(p) in seen:
            continue
        seen.add(os.path.realpath(p))
        dbs.append((r["所属项目"], p))
    gp = env.db(GOV)
    if os.path.exists(gp) and os.path.realpath(gp) not in seen:
        dbs.append((GOV, gp))
    cited_text = ""
    if os.path.exists(gp):
        c = connect_ro(gp)
        try:
            cited_text = "\n".join(f"{a or ''} {b or ''}" for a, b in
                                   c.execute("SELECT 来源,理由 FROM D WHERE 类型='候选'"))
        finally:
            c.close()
    items, errors = [], []
    for proj, p in dbs:
        try:
            c = connect_ro(p)
        except Exception as e:
            errors.append((proj, f"打不开：{e}"))
            continue
        try:
            if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='M'").fetchone():
                errors.append((proj, "库里没有 M 表（schema 低于 2，需迁移）"))
                continue
            q = "SELECT code,日期,bot,节号,类别,摩擦,证据 FROM M"
            args = ()
            if since:
                q += " WHERE 日期>=?"
                args = (since,)
            for code, d, bot, sec, kind, text, ev in c.execute(q + " ORDER BY seq", args):
                ref = f"{proj} {code}"
                cited = re.search(re.escape(ref) + r"(?!\d)", cited_text) is not None
                if cited and not include_cited:
                    continue
                items.append({"项目": proj, "编号": code, "日期": d, "bot": bot, "节号": sec, "类别": kind,
                              "摩擦": text, "证据": ev, "已进候选": cited})
        finally:
            c.close()
    groups = {}
    for it in items:
        groups.setdefault(it["节号"], []).append(it)
    summary = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    return {"库数": len(dbs), "条目": items, "按节号": summary, "读不了": errors}


# ---------- 只读输出（J7、Q6） ----------
def md_cell(v):
    if v is None:
        return ""
    return str(v).replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>")


def md_table(headers, rows):
    out = ["| " + " | ".join(md_cell(h) for h in headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(md_cell(v) for v in r) + " |" for r in rows]
    return "\n".join(out)


def order_key(table):
    return {"A": "编号,版本号", "dep": "id", "meta": "key"}.get(table, "id" if table in LOG_TABLES else "seq")


def map_col(table, col):
    if col == "编号":
        return "版本代号" if table == "A" else ("id" if table == "dep" else "code")
    return col


def show(c, table, cols=None, all_=False, where=(), limit=None):
    if table not in TABLES + ("dep",):
        raise Usage(f"show 的表只能是 {' '.join(TABLES)} dep")
    real = cols_of(c, table)
    headers = cols or DEFAULT_COLS.get(table) or list(real)
    sel = []
    for h in headers:
        m = map_col(table, h)
        if m not in real:
            raise Usage(f"{table} 没有列 {h}（有：{','.join(real)}）")
        sel.append(m)
    conds, params = [], []
    if not all_ and "状态" in real:
        conds.append("状态 NOT IN (SELECT val FROM enum WHERE tbl=? AND col='状态' AND 默认隐藏=1)")
        params.append(table)
    for w in where:
        k, v = w.split("=", 1) if "=" in w else (None, None)
        if not k or map_col(table, k) not in real:
            raise Usage(f"--where 写法不对或没有该列：{w}")
        conds.append(f"{map_col(table, k)}=?")
        params.append(v)
    sql = f"SELECT {','.join(sel)} FROM {table}" + (" WHERE " + " AND ".join(conds) if conds else "") + \
          f" ORDER BY {order_key(table)}" + (f" LIMIT {int(limit)}" if limit else "")
    return headers, c.execute(sql, params).fetchall()


def dump_table(env, c, path, project, table, actor=None):
    """J7：整张表、全部列、全部行原样输出；列数超过 6 或超过 8000 字符时只贴前 4 列，另出 CSV 和快照附件。"""
    if table not in ALL_TABLES:
        raise Usage(f"dump 的表只能是 {' '.join(ALL_TABLES)}")
    cols = cols_of(c, table)
    rows = c.execute(f"SELECT {','.join(cols)} FROM {table} ORDER BY {order_key(table)}").fetchall()
    full = md_table(cols, rows)
    sha = hashlib.sha256(full.encode("utf-8")).hexdigest()
    sv = meta_of(c).get("schema_version")
    head = f"dump {table}：库 {path}｜schema {sv}｜{len(rows)} 行｜{len(cols)} 列｜生成 {now()}｜全表 sha256 {sha[:16]}"
    if len(cols) <= 6 and len(full) <= 8000:
        return head + "\n" + full, []
    d = env.runs_dir(project, actor)
    csvp = os.path.join(d, f"dump-{table}.csv")
    with open(csvp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    snap = os.path.join(d, f"dump-{table}-快照.db")
    t = sqlite3.connect(snap)
    c.backup(t)
    t.close()
    part = md_table(cols[:4], [r[:4] for r in rows])
    return (head + f"\n太宽（{len(cols)} 列，全表 {len(full)} 字符），下面只贴前 4 列；全表见附件：\n"
            f"- CSV：{csvp}\n- 快照：{snap}\n" + part), [csvp, snap]


def changes(c, code=None, since_check=False, since=None):
    conds, params = [], []
    if code:
        conds.append("code=?")
        params.append(code)
    if since_check:
        r = c.execute("SELECT change_log_upto FROM check_log ORDER BY id DESC LIMIT 1").fetchone()
        conds.append("id>?")
        params.append(r[0] if r else 0)
    if since:
        conds.append("at>=?")
        params.append(since)
    rows = c.execute("SELECT id,at,actor,reason,tbl,code,op,old,new FROM change_log" +
                     (" WHERE " + " AND ".join(conds) if conds else "") + " ORDER BY id", params).fetchall()
    out = []
    for i, at, actor, reason, tbl, cd, op, old, new in rows:
        if op == "update":
            o, n = json.loads(old or "{}"), json.loads(new or "{}")
            ch = "；".join(f"{k}：{o.get(k)} → {n.get(k)}" for k in n if o.get(k) != n.get(k))
        else:
            ch = "新建"
        out.append((f"#{i}", at, actor, reason, tbl, cd, op, ch))
    return ["#", "时间", "写入者", "原因", "表", "编号", "操作", "改动"], out


def deps(c, code, up=False, recursive=False):
    """默认列下游（谁依赖它）；--up 列上游（它依赖谁）。只看有效依赖。"""
    a, b = ("依赖方", "被依赖") if up else ("被依赖", "依赖方")
    if recursive:
        sql = (f"WITH RECURSIVE t(x,lvl) AS (SELECT ?,0 UNION SELECT dep.{b},t.lvl+1 FROM dep JOIN t ON dep.{a}=t.x "
               f"WHERE dep.状态='有效' AND t.lvl<50) SELECT x,min(lvl) FROM t WHERE lvl>0 GROUP BY x ORDER BY 2,1")
        rows = c.execute(sql, (code,)).fetchall()
    else:
        rows = [(r[0], 1) for r in c.execute(f"SELECT {b} FROM dep WHERE {a}=? AND 状态='有效' ORDER BY id", (code,))]
    return ["编号", "层级"], rows


def query(c, sql):
    s = re.sub(r"^\s*(--[^\n]*\n\s*)*", "", sql)
    if not re.match(r"(SELECT|WITH)\b", s, re.I):
        raise Usage("query 只允许 SELECT / WITH")
    cur = c.execute(sql)
    return [d[0] for d in cur.description], cur.fetchall()


# ---------- init / genesis ----------
HANDOFF_KEYS = {"项目名", "想法原话", "来源", "用户确认", "流程版本", "提交号", "共享记忆可用条目"}


def load_json(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except FileNotFoundError:
        raise Usage(f"文件不存在：{p}")
    except json.JSONDecodeError as e:
        raise Usage(f"{p} 不是合法 JSON：{e}")


def base_meta(c, env, info, kind, project, extra):
    vals = {"schema_version": str(schema_version_of(schema_text(env.repo))), "schema_tag": info["ref"],
            "库ID": str(uuid.uuid4()), "库类型": kind, "项目名": project, "created_at": now(),
            "流程版本": info["label"], "降级模式": "否", "状态": "在办", **extra}
    for k, v in vals.items():
        c.execute("INSERT INTO meta(key,value) VALUES(?,?)", (k, v))


def match_repo(info, label, commit):
    commit = str(commit or "")
    return label == info["label"] and len(commit) >= 7 and info["commit"].startswith(commit)


def cmd_init(env, project, actor, handoff_path, pii_checked=None):
    check_project_name(project)
    if project == GOV:
        raise Usage("流程治理库由 genesis 建")
    h = load_json(handoff_path)
    if not isinstance(h, dict):
        raise Usage("交接单必须是 JSON 对象")
    extra = set(h) - HANDOFF_KEYS
    miss = (HANDOFF_KEYS - {"共享记忆可用条目"}) - set(h)
    if extra or miss:
        raise Usage(f"交接单字段不对：多了 {sorted(extra)}，少了 {sorted(miss)}")
    if h["项目名"] != project:
        raise Reject(f"交接单项目名「{h['项目名']}」和 --project「{project}」不一致")
    info = repo_info(env.repo)
    if not match_repo(info, h["流程版本"], h["提交号"]):
        raise Reject(f"交接单的流程版本/提交号（{h['流程版本']} {h['提交号']}）和克隆（{info['label']} {info['commit'][:12]}）不一致")
    uc = h["用户确认"] if isinstance(h["用户确认"], dict) else {}
    if not uc.get("原话") or not uc.get("时间"):
        raise Usage("交接单「用户确认」要有原话和时间")
    prefix = pii_gate(h, pii_checked)
    reason = prefix + f"立项建库（交接单 {os.path.basename(handoff_path)}）"

    def body(c):
        base_meta(c, env, info, "项目", project, {})
        d1 = ins(c, "D", actor, {"日期": today(), "决定": h["想法原话"],
                                 "理由": f"用户提出并确认立项（交接单）：「{uc['原话']}」{uc['时间']}",
                                 "来源": h["来源"], "谁拍板": "用户", "状态": "生效", "类型": "决定"})
        d2 = ins(c, "D", actor, {"日期": today(), "决定": f"流程版本 {info['label']}（提交 {info['commit'][:12]}）",
                                 "理由": "立项时用户确认，按当前克隆版本", "来源": h["来源"],
                                 "谁拍板": "用户", "状态": "生效", "类型": "版本"})
        return {"新建": [d1, d2]}
    return run_write(env, project, actor, reason, body, mode="init", create=True)


PLAN_KEYS = {"仓库": {"地址", "方式", "可见性", "tag", "提交号"}, "备份仓库": {"地址", "方式"}, "库": {"方式"},
             "用户确认": {"原话", "时间"}}
PLAN_LISTS = {"专职": ({"bot_id", "名称", "模板"}, set()),
              "收编": ({"bot_id", "名称", "模板"}, {"类型", "所属项目", "库路径"}),
              "定时任务": ({"名称", "时间"}, set()), "skill": ({"名称", "动作"}, set())}
PLAN_IDS = ("退役", "改已废弃")
R1 = "共用 bot 不能开无上下文会话，项目隔离只靠派活单和自律"


def validate_plan(p):
    if not isinstance(p, dict):
        raise Usage("计划必须是 JSON 对象")
    extra = set(p) - set(PLAN_KEYS) - set(PLAN_LISTS) - set(PLAN_IDS)
    if extra:
        raise Usage(f"计划里有清单之外的键：{sorted(extra)}")
    for k, sub in PLAN_KEYS.items():
        if not isinstance(p.get(k), dict) or set(p[k]) != sub:
            raise Usage(f"计划「{k}」必须正好有这些键：{sorted(sub)}")
    for k, (need, opt) in PLAN_LISTS.items():
        v = p.get(k, [])
        if not isinstance(v, list):
            raise Usage(f"计划「{k}」必须是列表")
        for it in v:
            if not isinstance(it, dict) or not need <= set(it) or not set(it) <= need | opt:
                raise Usage(f"计划「{k}」的条目键不对：{it}（必须有 {sorted(need)}，可选 {sorted(opt)}）")
    for k in PLAN_IDS:
        v = p.get(k, [])
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise Usage(f"计划「{k}」只放 bot ID 列表")
    if p["库"]["方式"] not in ("新建", "复用", "恢复"):
        raise Usage("库.方式 只能是 新建 / 复用 / 恢复")


def cmd_genesis(env, actor, plan_path, pii_checked=None):
    """创世专用：一个事务写完 meta、D、F、R、名册，自己那一行最后写（Q16）。"""
    p = load_json(plan_path)
    validate_plan(p)
    info = repo_info(env.repo)
    if not match_repo(info, p["仓库"]["tag"], p["仓库"]["提交号"]):
        raise Reject(f"计划的 tag/提交号（{p['仓库']['tag']} {p['仓库']['提交号']}）和克隆（{info['label']} {info['commit'][:12]}）不一致")
    verify_actor(env, GOV, actor, genesis=True)
    prefix = pii_gate(p, pii_checked)
    way = p["库"]["方式"]
    path = env.db(GOV)
    if way == "新建" and os.path.exists(path):
        raise Reject(f"计划是新建，但流程治理库已存在：{path}")
    if way != "新建" and not os.path.exists(path):
        raise Reject(f"计划是{way}，但流程治理库不存在（恢复要先跑 restore）")
    if way != "新建":
        c0 = connect_ro(path)
        diff = diff_structure(structure(c0), reference_structure(schema_text(env.repo)))
        c0.close()
        if diff:
            raise Reject("流程治理库结构和克隆的 schema 不一致：" + "；".join(f"{a} {b}" for a, b, _ in diff[:5]))
    ls = git(env.repo, "ls-tree", "-r", "--name-only", info["ref"]).strip()
    uc = p["用户确认"]
    old_cos = [r for r in (roster(env) or []) if r["类型"] == "参谋长" and r["状态"] == "在用"]
    summary = [f"仓库 {p['仓库']['方式']} {p['仓库']['地址']}（{p['仓库']['可见性']}）",
               f"备份仓库 {p['备份仓库']['方式']} {p['备份仓库']['地址']}"]
    for k in ("专职", "收编"):
        if p.get(k):
            summary.append(f"{k} " + "、".join(f"{x['名称']}（{x['bot_id']}）" for x in p[k]))
    for k in PLAN_IDS:
        if p.get(k):
            summary.append(f"{k} " + "、".join(p[k]))
    if p.get("定时任务"):
        summary.append("定时任务 " + "、".join(f"{x['名称']} {x['时间']}" for x in p["定时任务"]))
    if p.get("skill"):
        summary.append("skill " + "、".join(f"{x['名称']} {x['动作']}" for x in p["skill"]))
    reason = prefix + f"创世（计划 {os.path.basename(plan_path)}，用户确认 {uc['时间']}）"
    counts = {"D": 0, "F": 0, "R": 0, "B新增": {}, "B状态": 0}

    def body(c):
        if way == "新建":
            base_meta(c, env, info, "治理", GOV, {"项目仓库": p["仓库"]["地址"]})
        else:
            m = meta_of(c)
            for k, v in (("项目仓库", p["仓库"]["地址"]), ("流程版本", info["label"])):
                if k not in m:
                    c.execute("INSERT INTO meta(key,value) VALUES(?,?)", (k, v))
                elif m[k] != v:
                    c.execute("UPDATE meta SET value=? WHERE key=?", (v, k))
        made = []
        if way == "新建":
            dec = (f"创世例外：按流程模板 {info['label']}（提交 {info['commit'][:12]}）建立流程治理；"
                   f"用户确认「{uc['原话']}」（{uc['时间']}）。本次动作：" + "；".join(summary))
            why = "创世时 skill 规定（创世例外，用户一次性批准）"
        else:
            olds = "、".join(r["bot_id"] for r in old_cos) or "无"
            dec = (f"创世（{'从备份恢复' if way == '恢复' else '复用历史'}）：旧参谋长 {olds} → 新参谋长 {actor}；"
                   f"流程模板 {info['label']}（提交 {info['commit'][:12]}）；用户确认「{uc['原话']}」（{uc['时间']}）。"
                   f"本次动作：" + "；".join(summary))
            why = "接手时已存在（创世复用，用户一次性批准）"
        made.append(ins(c, "D", actor, {"日期": today(), "决定": dec, "理由": why, "来源": f"创世确认清单 {uc['时间']}",
                                        "谁拍板": "用户", "状态": "生效", "类型": "版本", "登记方式": "补录"}))
        counts["D"] += 1
        mark = f"仓库文件清单（{info['label']}，"
        if not c.execute("SELECT 1 FROM F WHERE substr(内容,1,length(?))=?", (mark, mark)).fetchone():
            vals = {"内容": f"{mark}提交 {info['commit']}）：\n{ls}", "类别": "仓库文件", "状态": "已查证",
                    "来源": f"git ls-tree -r --name-only {info['ref']}", "查证日期": today(), "登记方式": "补录"}
            fill_f_defaults(c, vals)
            made.append(ins(c, "F", actor, vals))
            counts["F"] += 1
        if not c.execute("SELECT 1 FROM R WHERE 风险=?", (R1,)).fetchone():
            made.append(ins(c, "R", actor, {"风险": R1, "可能性": "中", "影响": "中", "状态": "监控中",
                                            "对策": "每次只给本单材料，巡检抽查回执是否引用了本单以外的信息"}))
            counts["R"] += 1
        for k, st in (("退役", "退役"), ("改已废弃", "已废弃")):
            for bid in p.get(k, []):
                r = c.execute("SELECT seq FROM B WHERE bot_id=? AND 状态<>'已废弃'", (bid,)).fetchone()
                if not r:
                    raise Reject(f"计划要把 {bid} 改成{st}，但名册里没有它的未废弃行")
                c.execute("UPDATE B SET 状态=? WHERE seq=?", (st, r[0]))
                counts["B状态"] += 1
        for x in p.get("专职", []):
            made.append(ins(c, "B", actor, {"bot_id": x["bot_id"], "名称": x["名称"], "类型": "专职", "所属项目": "共用",
                                            "所用模板": x["模板"], "状态": "在用", "创建日期": today()}))
            counts["B新增"]["专职"] = counts["B新增"].get("专职", 0) + 1
        for x in p.get("收编", []):
            t = x.get("类型", "专职")
            made.append(ins(c, "B", actor, {"bot_id": x["bot_id"], "名称": x["名称"], "类型": t,
                                            "所属项目": x.get("所属项目", "共用"), "所用模板": x["模板"],
                                            "库路径": x.get("库路径"), "状态": "在用", "创建日期": today(),
                                            "备注": "创世收编"}))
            counts["B新增"][t] = counts["B新增"].get(t, 0) + 1
        made.append(ins(c, "B", actor, {"bot_id": actor, "名称": "参谋长", "类型": "参谋长", "所属项目": GOV,
                                        "所用模板": f"chief-of-staff.md@{info['label']}", "库路径": path,
                                        "状态": "在用", "创建日期": today()}))
        counts["B新增"]["参谋长"] = counts["B新增"].get("参谋长", 0) + 1
        return {"新建": made}
    res = run_write(env, GOV, actor, reason, body, mode="init" if way == "新建" else "write",
                    create=(way == "新建"), genesis=True)
    bn = counts["B新增"]
    res["计数"] = (f"补录：D {counts['D']}、F {counts['F']}｜新增：R {counts['R']}｜名册：新增 {sum(bn.values())}（"
                 + "、".join(f"{k} {v}" for k, v in bn.items()) + f"），状态变更 {counts['B状态']}")
    return res


# ---------- apply ----------
def cmd_apply(env, project, actor, reason, path, pii_checked=None):
    j = load_json(path)
    if not isinstance(j, dict) or set(j) != {"items"} or not isinstance(j["items"], list):
        raise Usage('apply 文件格式：{"items": [{"op": "add", "table": "F", "set": {...}, "dep": ["$1"]}, '
                    '{"op": "update", "code": "D-1", "set": {...}}, {"op": "dep", "from": "$2", "to": "F-1"}]}；'
                    "$n 指本文件第 n 条新建或修改出来的编号")
    prefix = pii_gate(j, pii_checked)
    items = j["items"]

    def body(c):
        made = []

        def ref(s):
            if isinstance(s, str) and re.fullmatch(r"\$\d+", s):
                return made[int(s[1:]) - 1]
            return s
        for n, it in enumerate(items, 1):
            op = it.get("op") if isinstance(it, dict) else None
            try:
                if op == "add":
                    made.append(do_add(c, it["table"], actor, it.get("set", {}), [ref(d) for d in it.get("dep", [])]))
                elif op == "update":
                    made.append(do_update(c, ref(it["code"]), it.get("set", {})))
                elif op == "dep":
                    made.append(do_dep(c, actor, "add", ref(it["from"]), ref(it["to"]), it.get("说明")))
                else:
                    raise Usage(f"第 {n} 条 op 只能是 add / update / dep")
            except (KeyError, IndexError) as e:
                raise Usage(f"第 {n} 条缺字段或 $ 引用越界：{e}")
            except sqlite3.IntegrityError as e:
                raise Reject(f"第 {n} 条：{friendly(e)}")
            except Reject as e:
                raise Reject(f"第 {n} 条：{e}")
        return {"新建或修改": made}
    return run_write(env, project, actor, prefix + reason, body)


# ---------- degrade ----------
def cmd_degrade(env, project, actor, on, why):
    if on and not (why and why.strip()):
        raise Usage("degrade on 要写 --reason 原因")
    pii_gate(why or "", None)
    d = today()

    def body(c):
        made = []
        if on:
            c.execute("UPDATE meta SET value=? WHERE key='降级模式'", (f"是（{why}，{d}）",))
            made.append(ins(c, "D", actor, {"日期": d, "决定": f"进入降级模式：{why}",
                                            "理由": "检查脚本降级，按通用流程第 10 节降级方案",
                                            "谁拍板": "bot", "状态": "生效（待用户确认）", "类型": "降级"}))
            made.append(ins(c, "R", actor, {"风险": f"脚本修复：{why}", "可能性": "高", "影响": "高", "状态": "已发生",
                                            "对策": "降级期间按 J7 用 dump 人工看原始数据；修好脚本后 degrade off"}))
        else:
            c.execute("UPDATE meta SET value=? WHERE key='降级模式'", (f"否（{d} 恢复）",))
            made.append(ins(c, "D", actor, {"日期": d, "决定": "退出降级模式" + (f"：{why}" if why else ""),
                                            "理由": "检查脚本恢复正常", "谁拍板": "bot", "状态": "生效（待用户确认）",
                                            "类型": "降级"}))
        return {"新建": made}
    return run_write(env, project, actor, f"degrade {'on' if on else 'off'}：{why or ''}", body)


# ---------- CLI ----------
def header(env, path, status):
    try:
        i = repo_info(env.repo)
        v = f"{i['label']} / 提交 {i['commit'][:12]}" + ("" if i["clean"] else "，有本地改动")
    except EnvError:
        v = "未知"
    sv = "?"
    try:
        if os.path.exists(path):
            c = connect_ro(path)
            sv = meta_of(c).get("schema_version", "?")
            c.close()
    except Exception:
        pass
    return f"ledger.py（仓库版本 {v}，库 {path}，schema {sv}）：{status}"


def write_report(res):
    lines = []
    if res.get("身份"):
        lines.append(f"写入者：{res['写入者']}（{res['身份']}）")
    for k in ("新建", "新建或修改", "修改"):
        if res.get(k):
            lines.append(f"{k}：{', '.join(res[k])}")
    if res.get("计数"):
        lines.append(res["计数"])
    if res.get("修改记录"):
        lines.append(f"修改记录：#{res['修改记录'][0]}–#{res['修改记录'][1]}")
    lines.append(backup_line(res["备份"]))
    return lines


def build_parser():
    ap = argparse.ArgumentParser(prog="ledger.py", description="台账写入脚本（唯一写入口）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def P(name, project=True, actor=False, reason=False):
        s = sub.add_parser(name)
        if project:
            s.add_argument("--project", required=True)
        if actor:
            s.add_argument("--actor", required=True)
        if reason:
            s.add_argument("--reason", required=True)
        s.add_argument("--json", action="store_true")
        return s
    P("where")
    s = P("init", True, True); s.add_argument("--handoff", required=True); s.add_argument("--pii-checked")
    s = P("genesis", False, True); s.add_argument("--plan", required=True); s.add_argument("--pii-checked")
    s = P("add", True, True, True); s.add_argument("table"); s.add_argument("--set", nargs="+", action="extend", default=[])
    s.add_argument("--dep", default=""); s.add_argument("--pii-checked")
    s = P("update", True, True, True); s.add_argument("code"); s.add_argument("--set", nargs="+", action="extend", default=[])
    s.add_argument("--pii-checked"); s.add_argument("--typo", action="store_true", help="核心列只改错字（意思不变）")
    s = P("dep", True, True, True); s.add_argument("op", choices=["add", "void"]); s.add_argument("a"); s.add_argument("b")
    s = P("apply", True, True, True); s.add_argument("file"); s.add_argument("--pii-checked")
    s = P("meta", True, True, True); s.add_argument("op", choices=["set"]); s.add_argument("key"); s.add_argument("value")
    s.add_argument("--pii-checked")
    s = P("degrade", True, True); s.add_argument("op", choices=["on", "off"]); s.add_argument("--reason", default="")
    s = P("snapshot"); s.add_argument("--label", required=True); s.add_argument("--actor")
    s = P("backup", True, True); s.add_argument("--reason", default="手动补推备份")
    s = P("backup-init", False); s.add_argument("--remote", required=True)
    P("backup-status", False)
    s = P("restore"); s.add_argument("--commit")
    s = P("migrate", True, True); s.add_argument("--to", type=int, required=True); s.add_argument("--approved", required=True)
    s = P("migrate-dryrun"); s.add_argument("--to", type=int, required=True); s.add_argument("--out", required=True)
    s = P("frictions", False); s.add_argument("--since", help="只看这天（YYYY-MM-DD）及以后的")
    s.add_argument("--all", action="store_true", help="连已进候选的也列出")
    s = P("show"); s.add_argument("table"); s.add_argument("--all", action="store_true")
    s.add_argument("--cols"); s.add_argument("--where", action="append", default=[]); s.add_argument("--limit", type=int)
    s = P("dump"); s.add_argument("table"); s.add_argument("--actor")
    s = P("changes"); s.add_argument("code", nargs="?"); s.add_argument("--since-check", action="store_true")
    s.add_argument("--since")
    s = P("deps"); s.add_argument("code"); g = s.add_mutually_exclusive_group()
    g.add_argument("--down", action="store_true"); g.add_argument("--up", action="store_true")
    s.add_argument("--recursive", action="store_true")
    s = P("query"); s.add_argument("--sql", required=True)
    P("selftest", False)
    return ap


def dispatch(env, a):
    """返回 (退出码, 输出行, 数据)。"""
    project = getattr(a, "project", None) or GOV
    path = env.db(project)
    if getattr(a, "project", None):
        check_project_name(a.project)
    pc = getattr(a, "pii_checked", None)
    if a.cmd == "frictions":
        d = frictions(env, a.since, a.all)
        lines = [f"摩擦汇总：读了 {d['库数']} 个库，{len(d['条目'])} 条" + ("（含已进候选）" if a.all else "（不含已进候选）")]
        if d["按节号"]:
            lines.append(md_table(["节号", "条数", "涉及项目", "类别", "编号"],
                                  [(sec, len(v), "、".join(sorted({x["项目"] for x in v})),
                                    "、".join(sorted({x["类别"] for x in v})),
                                    "、".join(f"{x['项目']} {x['编号']}" + ("（已进候选）" if x["已进候选"] else "") for x in v))
                                   for sec, v in d["按节号"]]))
            lines.append(md_table(["项目", "编号", "日期", "bot", "节号", "类别", "摩擦", "证据"],
                                  [(x["项目"], x["编号"], x["日期"], x["bot"], x["节号"], x["类别"], x["摩擦"], x["证据"])
                                   for x in d["条目"]]))
        lines += [f"读不了：{p}：{e}" for p, e in d["读不了"]]
        d["按节号"] = [[k, v] for k, v in d["按节号"]]
        return 0, lines, d
    if a.cmd == "where":
        data = {"库": path, "快照": os.path.join(env.proj_dir(project), "snapshots"),
                "runs": os.path.join(env.proj_dir(project), "runs"), "备份仓库本机克隆": env.backup_repo,
                "备份锁": env.backup_lock, "库存在": os.path.exists(path)}
        return 0, [f"{k}：{v}" for k, v in data.items()], data
    if a.cmd == "init":
        d = cmd_init(env, project, a.actor, a.handoff, pc)
        return 0, write_report(d), d
    if a.cmd == "genesis":
        d = cmd_genesis(env, a.actor, a.plan, pc)
        return 0, write_report(d), d
    if a.cmd == "add":
        sets = parse_sets(a.set)
        dl = [x.strip() for x in a.dep.split(",") if x.strip()]
        pre = pii_gate({"set": sets, "reason": a.reason}, pc)
        d = run_write(env, project, a.actor, pre + a.reason, lambda c: {"新建": [do_add(c, a.table, a.actor, sets, dl)]})
        return 0, write_report(d), d
    if a.cmd == "update" and a.typo:
        sets = parse_sets(a.set)
        pre = pii_gate({"set": sets, "reason": a.reason}, pc)
        d = run_write(env, project, a.actor, "仅错字：" + pre + a.reason, lambda c: {"修改": [do_typo(c, a.code, sets)]}, mode="typo")
        return 0, write_report(d), d
    if a.cmd == "update":
        sets = parse_sets(a.set)
        pre = pii_gate({"set": sets, "reason": a.reason}, pc)
        d = run_write(env, project, a.actor, pre + a.reason, lambda c: {"修改": [do_update(c, a.code, sets)]})
        return 0, write_report(d), d
    if a.cmd == "dep":
        pii_gate(a.reason, None)
        d = run_write(env, project, a.actor, a.reason, lambda c: {"新建或修改": [do_dep(c, a.actor, a.op, a.a, a.b)]})
        return 0, write_report(d), d
    if a.cmd == "meta":
        if a.key not in META_SETTABLE:
            raise Usage(f"meta set 只允许：{'、'.join(sorted(META_SETTABLE))}")
        pre = pii_gate({"value": a.value, "reason": a.reason}, pc)

        def body(c):
            c.execute("UPDATE meta SET value=? WHERE key=?", (a.value, a.key))
            return {"修改": [f"meta.{a.key}"]}
        d = run_write(env, project, a.actor, pre + a.reason, body)
        return 0, write_report(d), d
    if a.cmd == "apply":
        d = cmd_apply(env, project, a.actor, a.reason, a.file, pc)
        return 0, write_report(d), d
    if a.cmd == "degrade":
        d = cmd_degrade(env, project, a.actor, a.op == "on", a.reason)
        return 0, write_report(d), d
    if a.cmd == "snapshot":
        p, sha = snapshot(env, project, a.label, a.actor)
        return 0, [f"快照：{p}", f"sha256：{sha}", "完整性：ok"], {"快照": p, "sha256": sha}
    if a.cmd == "backup":
        verify_actor(env, project, a.actor)
        if not os.path.exists(path):
            raise EnvError(f"库不存在：{path}")
        b = backup_project(env, project, a.actor, a.reason)
        return (0 if b["结果"] == "成功" else 2), [backup_line(b)], {"备份": b}
    if a.cmd == "backup-init":
        br = env.backup_repo
        if os.path.isdir(os.path.join(br, ".git")):
            cur = git(br, "remote", "get-url", "origin").strip()
            if cur != a.remote:
                raise Reject(f"{br} 已存在，远端是 {cur}，和 {a.remote} 不同；不改动")
            return 0, [f"已初始化：{br} → {cur}"], {"备份仓库": br}
        os.makedirs(env.data_root, exist_ok=True)
        r = subprocess.run(["git", "clone", "-q", a.remote, br], capture_output=True, text=True, timeout=120,
                           env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        if r.returncode != 0:
            raise EnvError(f"克隆备份仓库失败（本脚本不建仓库）：{(r.stderr or r.stdout).strip()}")
        if not subprocess.run(["git", "-C", br, "config", "user.email"], capture_output=True, text=True).stdout.strip():
            git(br, "config", "user.email", "flow-ledger@localhost")
            git(br, "config", "user.name", "flow-ledger")
        return 0, [f"已克隆：{a.remote} → {br}"], {"备份仓库": br}
    if a.cmd == "backup-status":
        rows = []
        if os.path.isdir(env.data_root):
            for pj in sorted(os.listdir(env.data_root)):
                p = env.db(pj)
                if pj.startswith(".") or not os.path.exists(p):
                    continue
                c = connect_ro(p)
                r = c.execute("SELECT at,结果,commit_id,error,change_log_upto FROM backup_log ORDER BY id DESC LIMIT 1").fetchone()
                mx = max_change(c)
                c.close()
                rows.append((pj, *(r or ("（无）", "", "", "", "")), mx))
        br = env.backup_repo
        init = os.path.isdir(os.path.join(br, ".git"))
        n = unpushed(br) if init else None
        data = {"备份仓库": br if init else None, "未推出去的本地提交": n, "项目": rows}
        return 0, [f"备份仓库本机克隆：{br if init else '未初始化'}" + (f"；未推出去的本地提交 {n} 个" if init else ""),
                   md_table(["项目", "最近备份时间", "结果", "提交", "错误", "覆盖到修改记录", "当前修改记录"], rows)], data
    if a.cmd == "restore":
        dst, diff = restore(env, project, a.commit)
        return 0, [f"已恢复：{dst}", "完整性：ok",
                   "结构：和克隆 schema 一致" if not diff else
                   "结构差异（库版本可能和克隆不同）：" + "；".join(f"{x} {y}" for x, y, _ in diff[:10])], \
            {"库": dst, "结构差异": diff}
    if a.cmd in ("migrate", "migrate-dryrun"):
        target = schema_text(env.repo)
        tv = schema_version_of(target)
        if a.to != tv:
            raise Usage(f"只能迁到克隆的 schema 版本 {tv}")
        c = connect_ro(path)
        cv = int(meta_of(c).get("schema_version") or 0)
        c.close()
        steps = []
        for v in range(cv + 1, tv + 1):
            f = os.path.join(env.repo, "schema", "migrations", f"{v:03d}.sql")
            try:
                steps.append((v, open(f, encoding="utf-8").read()))
            except OSError:
                raise EnvError(f"缺迁移文件 {f}")
        if not steps:
            raise Usage(f"库已经是 schema {cv}，不用迁移")
        if a.cmd == "migrate-dryrun":
            d = migrate_dryrun(env, project, steps, target, repo_info(env.repo)["ref"], a.out)
            lines = [f"迁移演练（真库未动）：{project} schema {d['从']} → {d['到']}，拷贝 {d['拷贝']}",
                     md_table(["表", "迁移前行数", "迁移后行数"], d["行数"]),
                     f"出错：{d['错误'] or '无'}；结构差异：{len(d['结构差异'])} 处；外键问题：{len(d['外键'])} 处；完整性：{d['完整性']}",
                     "结论：" + ("通过" if d["通过"] else "不通过")]
            return (0 if d["通过"] else 1), lines, d
        d = migrate_db(env, project, a.actor, a.approved, steps, target, repo_info(env.repo)["ref"])
        return 0, [f"迁移：schema {d['从']} → {d['到']}", f"迁移前快照：{d['快照']}", backup_line(d["备份"])], d
    c = connect_ro(path)
    try:
        if a.cmd == "dump":
            text, files = dump_table(env, c, path, project, a.table, a.actor)
            return 0, [text], {"附件": files}
        if a.cmd == "show":
            cols = [x.strip() for x in a.cols.split(",")] if a.cols else None
            hd, rows = show(c, a.table, cols, a.all, a.where, a.limit)
        elif a.cmd == "changes":
            hd, rows = changes(c, a.code, a.since_check, a.since)
        elif a.cmd == "deps":
            hd, rows = deps(c, a.code, up=a.up, recursive=a.recursive)
        else:
            hd, rows = query(c, a.sql)
        return 0, [md_table(hd, rows), f"（{len(rows)} 行）"], {"列": hd, "行": [list(r) for r in rows]}
    finally:
        c.close()


def main(argv=None, env=None):
    ap = build_parser()
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 0 if e.code in (0, None) else 3
    if a.cmd == "selftest":
        sys.path.insert(0, HERE)
        import ledger_selftest
        return ledger_selftest.run()
    env = env or Env()
    path = env.db(getattr(a, "project", None) or GOV)
    try:
        code, out, data = dispatch(env, a)
    except Reject as e:
        code, out, data = 1, [f"原因：{e}"], {"错误": str(e)}
    except EnvError as e:
        code, out, data = 2, [f"原因：{e}"], {"错误": str(e)}
    except Usage as e:
        code, out, data = 3, [f"用法：{e}"], {"错误": str(e)}
    except sqlite3.Error as e:
        code, out, data = 2, [f"原因：SQLite 出错：{e}"], {"错误": str(e)}
    status = {0: "成功", 1: "被拒", 2: "出错", 3: "用法错误"}[code]
    if getattr(a, "json", False):
        print(json.dumps({"状态": status, "退出码": code, **data}, ensure_ascii=False, default=str))
    else:
        print(header(env, path, status))
        for line in out:
            print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
