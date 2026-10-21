"""ledger.py 自测（python3 scripts/ledger.py selftest）。全部在临时目录里跑：临时数据根目录、临时平台 bot 目录、
临时删除记录、临时 git 仓库（复制本克隆的 schema/templates/skills/build/scripts 后打 tag），备份远端是本地裸仓库。
不碰 /home/box/flow-data，不联网。"""
import contextlib, hashlib, io, json, multiprocessing, os, shutil, sqlite3, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ledger as L  # noqa: E402

COS = "c0500000-0000-0000-0000-000000000001"
QA = "9a000000-0000-0000-0000-000000000002"
DEP = "de900000-0000-0000-0000-000000000003"
DEP2 = "de900000-0000-0000-0000-000000000004"
GONE = "90e00000-0000-0000-0000-000000000005"
FAKE = "fa4e0000-0000-0000-0000-000000000006"


class T:
    def __init__(self):
        self.ok, self.n, self.fail = True, 0, []

    def check(self, name, cond, detail=""):
        self.n += 1
        if not cond:
            self.ok = False
            self.fail.append(name)
        print(("通过 " if cond else "失败 ") + name + ("" if cond or not detail else f"  ←  {detail}"))


def make_repo(root, src=L.DEFAULT_REPO, tag="v1.0.0"):
    """复制本克隆的工作区到临时 git 仓库并打 tag。"""
    repo = os.path.join(root, "repo")
    for d in ("schema", "templates", "skills", "build", "scripts"):
        if os.path.isdir(os.path.join(src, d)):
            shutil.copytree(os.path.join(src, d), os.path.join(repo, d),
                            ignore=shutil.ignore_patterns("__pycache__"))
    g = lambda *a: subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, check=True)
    subprocess.run(["git", "init", "-q", repo], check=True)
    g("config", "user.email", "t@t"); g("config", "user.name", "t")
    open(os.path.join(repo, ".gitignore"), "w").write("__pycache__/\n")
    g("add", "-A"); g("commit", "-qm", "selftest")
    if tag:
        g("tag", tag)
    return repo


def make_bot(env, bid, name, desc):
    os.makedirs(os.path.join(env.agents_dir, bid), exist_ok=True)
    json.dump({"name": name, "description": desc}, open(os.path.join(env.agents_dir, bid, "profile.json"), "w",
                                                        encoding="utf-8"), ensure_ascii=False)


def run_cli(env, *argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = L.main(list(argv), env=env)
    return code, buf.getvalue()


def raw(path):
    """直接连库（模拟绕过 ledger.py）。"""
    c = sqlite3.connect(path, isolation_level=None)
    c.execute("PRAGMA busy_timeout=10000")
    return c


def expect_block(c, sql, params=(), ctx=("x", "t", "write"), want=None):
    """在一个事务里设 _ctx 后执行 sql，期望被拒；返回 (被拒, 报错)。总是回滚。"""
    c.execute("BEGIN")
    try:
        if ctx:
            c.execute("UPDATE _ctx SET actor=?,reason=?,mode=? WHERE id=1", ctx)
        c.execute(sql, params)
        return False, ""
    except sqlite3.Error as e:
        return (want is None or want in str(e)), str(e)
    finally:
        c.execute("ROLLBACK")


def genesis_plan(env, info, path, **over):
    p = {"仓库": {"地址": "https://github.com/test/flow-governance", "方式": "直接用", "可见性": "公开",
                 "tag": info["label"], "提交号": info["commit"][:12]},
         "备份仓库": {"地址": "local-bare", "方式": "新建私有"}, "库": {"方式": "新建"},
         "专职": [{"bot_id": QA, "名称": "专职·流程QA", "模板": "qa.md@v1.0.0"}],
         "定时任务": [{"名称": "流程治理·每日扫描", "时间": "08:30"}],
         "用户确认": {"原话": "确认，按清单执行", "时间": "2026-10-21T10:12"}}
    p.update(over)
    json.dump(p, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return path


def _worker(args):
    root, n = args
    env = L.Env(data_root=os.path.join(root, "data"), agents_dir=os.path.join(root, "agents"),
                deleted=os.path.join(root, "deleted.json"), repo=os.path.join(root, "repo"))
    errs = 0
    for i in range(n):
        try:
            L.run_write(env, "记账", DEP, "并发测试",
                        lambda c: {"新建": [L.do_add(c, "F", DEP, {"内容": f"并发{i}", "类别": "其他", "状态": "待查证"})]})
        except Exception:
            errs += 1
    return errs


def _holder(path, secs, ready):
    c = raw(path)
    c.execute("BEGIN IMMEDIATE")
    ready.set()
    time.sleep(secs)
    c.execute("ROLLBACK")
    c.close()


def run():
    t = T()
    root = tempfile.mkdtemp(prefix="ledger-selftest-")
    try:
        _run(t, root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print(f"ledger.py 自测：{t.n} 项，" + ("全部通过" if t.ok else f"失败 {len(t.fail)} 项：{'；'.join(t.fail)}"))
    return 0 if t.ok else 1


def _run(t, root):
    repo = make_repo(root)
    env = L.Env(data_root=os.path.join(root, "data"), agents_dir=os.path.join(root, "agents"),
                deleted=os.path.join(root, "deleted.json"), repo=repo, backup_timeout=20)
    assert env.data_root.startswith(tempfile.gettempdir()), "自测数据根目录必须在临时目录"
    json.dump({"version": 1, "agents": {GONE: {"upstream": "done"}}}, open(env.deleted, "w"))
    cos_desc = open(os.path.join(repo, "templates", "chief-of-staff.md"), encoding="utf-8").read()
    make_bot(env, COS, "参谋长", cos_desc)
    make_bot(env, QA, "专职·流程QA", "qa")
    make_bot(env, DEP, "副官·记账", "dep")
    make_bot(env, DEP2, "副官·旅行", "dep2")
    make_bot(env, GONE, "副官·旧", "gone")
    make_bot(env, FAKE, "参谋长", "随便写的设定")
    info = L.repo_info(repo)
    schema = L.schema_text(repo)

    # 1 建库结构
    m = sqlite3.connect(":memory:")
    for st in L.split_sql(schema):
        m.execute(st)
    t.check("1 split_sql 逐条建库 = executescript 建库（结构逐条一致）",
            not L.diff_structure(L.structure(m), L.reference_structure(schema)))
    t.check("1 schema 头部版本号可读", L.schema_version_of(schema) == 2)

    # 5 创世引导例外
    plan = genesis_plan(env, info, os.path.join(root, "plan.json"))
    code, out = run_cli(env, "genesis", "--actor", FAKE, "--plan", plan)
    t.check("5 创世引导：名字是参谋长但设定不等于模板 → 拒", code == 1 and "chief-of-staff.md" in out, out)
    bad = genesis_plan(env, info, os.path.join(root, "bad.json"), 多余={"x": 1})
    code, out = run_cli(env, "genesis", "--actor", COS, "--plan", bad)
    t.check("3.4 计划里有清单之外的键 → 退出码 3", code == 3 and "清单之外" in out, out)
    bad = genesis_plan(env, info, os.path.join(root, "bad2.json"),
                       仓库={"地址": "x", "方式": "直接用", "可见性": "公开", "tag": "v9.9.9", "提交号": info["commit"][:12]})
    code, out = run_cli(env, "genesis", "--actor", COS, "--plan", bad)
    t.check("3.4 计划 tag 与克隆不符 → 拒", code == 1 and "不一致" in out, out)
    t0 = time.time()
    code, out = run_cli(env, "genesis", "--actor", COS, "--plan", plan)
    t.check("5 创世引导例外放行；一个事务写完", code == 0 and "创世引导例外" in out, out)
    t.check("3.4 genesis 打印分类计数",
            "补录：D 1、F 1｜新增：R 1｜名册：新增 2（专职 1、参谋长 1），状态变更 0" in out, out)
    t.check("3.6 备份仓库未初始化：写入照样成功，最后一行报备份失败", code == 0 and "备份：失败（备份仓库未初始化" in out, out)
    gov = env.db(L.GOV)
    c = L.connect_ro(gov)
    b = c.execute("SELECT code,bot_id,类型,库路径 FROM B ORDER BY seq").fetchall()
    last_b = c.execute("SELECT max(id) FROM change_log WHERE tbl='B'").fetchone()[0]
    self_b = c.execute("SELECT id FROM change_log WHERE tbl='B' AND code=?", (b[-1][0],)).fetchone()[0]
    t.check("12 genesis：自己那一行是最后一条 B，修改记录编号最大", b[-1][1] == COS and last_b == self_b
            and self_b == L.max_change(c), str(b))
    t.check("名册：参谋长登记了库路径 = 流程治理库", L.same_path(b[-1][3], gov))
    f1 = c.execute("SELECT 内容,有效期,有效期依据,登记方式 FROM F WHERE seq=1").fetchone()
    t.check("N1：仓库文件类 F 自动填默认有效期", f1[1] == "到本项目仓库下一个 tag 发布" and f1[2].startswith("类别默认值")
            and f1[3] == "补录" and "schema/schema.sql" in f1[0], str(f1[1:]))
    t.check("meta：库类型、流程版本、schema_tag", L.meta_of(c)["库类型"] == "治理" and L.meta_of(c)["流程版本"] == "v1.0.0"
            and L.meta_of(c)["schema_tag"] == "v1.0.0")
    c.close()
    code, out = run_cli(env, "genesis", "--actor", FAKE, "--plan", plan)
    t.check("5 创世引导：已有在用参谋长且平台还在 → 拒", code == 1 and "已有在用参谋长" in out, out)

    # 名册：第一个副官（库路径）
    dbp = env.db("记账")
    code, out = run_cli(env, "add", "B", "--project", L.GOV, "--actor", COS, "--reason", "建副官",
                        "--set", f"bot_id={DEP}", "名称=副官·记账", "类型=副官", "所属项目=记账", "所用模板=deputy.md@v1.0.0", "状态=在用")
    t.check("名册：在用副官不登记库路径 → 拒", code == 1 and "必须登记库路径" in out, out)
    code, out = run_cli(env, "add", "B", "--project", L.GOV, "--actor", COS, "--reason", "建副官",
                        "--set", f"bot_id={DEP}", "名称=副官·记账", "类型=副官", "所属项目=记账", "所用模板=deputy.md@v1.0.0",
                        "状态=在用", f"库路径={env.db('旅行')}")
    t.check("名册：库路径和所属项目对不上 → 拒", code == 1 and "库路径必须是" in out, out)
    code, out = run_cli(env, "add", "B", "--project", L.GOV, "--actor", COS, "--reason", "建副官",
                        "--set", f"bot_id={DEP}", "名称=副官·记账", "类型=副官", "所属项目=记账", "所用模板=deputy.md@v1.0.0",
                        "状态=在用", f"库路径={dbp}")
    t.check("名册：登记副官和库路径", code == 0, out)
    code, out = run_cli(env, "add", "B", "--project", L.GOV, "--actor", COS, "--reason", "建副官",
                        "--set", f"bot_id={DEP2}", "名称=副官·旅行", "类型=副官", "所属项目=旅行", "所用模板=deputy.md@v1.0.0",
                        "状态=在用", f"库路径={env.db('旅行')}")
    t.check("名册：登记第二个副官", code == 0, out)
    code, out = run_cli(env, "add", "B", "--project", L.GOV, "--actor", COS, "--reason", "再来一个",
                        "--set", f"bot_id={FAKE}", "名称=参谋长", "类型=参谋长", "所属项目=流程治理",
                        "所用模板=chief-of-staff.md@v1.0.0", "状态=在用", f"库路径={gov}")
    t.check("唯一索引报错翻成中文：在用参谋长只能有一个", code == 1 and "在用参谋长只能有一个" in out, out)
    code, out = run_cli(env, "add", "F", "--project", L.GOV, "--actor", COS, "--reason", "x", "--json",
                        "--set", "内容=治理事实", "类别=平台行为", "状态=待查证")
    j = json.loads(out)
    t.check("--json：机器可读输出", code == 0 and j["状态"] == "成功" and j["新建"] == ["F-2"], out)

    # init
    ho = {"项目名": "记账", "想法原话": "做一个记账小工具", "来源": "参谋长对话 2026-10-21T10:02",
          "用户确认": {"原话": "就这个，开干", "时间": "2026-10-21T10:05"}, "流程版本": info["label"],
          "提交号": info["commit"][:12], "共享记忆可用条目": [{"日期": "2026-10-15", "条目名": "一个人做产品"}]}
    hp = os.path.join(root, "handoff.json")
    json.dump(ho, open(hp, "w", encoding="utf-8"), ensure_ascii=False)
    code, out = run_cli(env, "init", "--project", "记账", "--actor", COS, "--handoff", hp)
    t.check("J6 参谋长不能建/写副官库", code == 1 and "参谋长不写副官的库" in out, out)
    code, out = run_cli(env, "init", "--project", "记账", "--actor", DEP2, "--handoff", hp)
    t.check("J6 副官写别的项目 → 拒", code == 1 and "不是项目「记账」的在用副官" in out, out)
    code, out = run_cli(env, "init", "--project", "记账", "--actor", DEP, "--handoff", hp)
    t.check("init：交接单建库，写 D-1、D-2", code == 0 and "D-1, D-2" in out, out)
    c = L.connect_ro(dbp)
    d = c.execute("SELECT 决定,谁拍板,状态,类型 FROM D ORDER BY seq").fetchall()
    t.check("init：D-1 是想法原话，D-2 是流程版本", d[0][0] == "做一个记账小工具" and d[1][3] == "版本" and "v1.0.0" in d[1][0], str(d))
    c.close()
    code, out = run_cli(env, "init", "--project", "记账", "--actor", DEP, "--handoff", hp)
    t.check("init：库已存在 → 拒", code == 1 and "已存在" in out, out)
    code, out = run_cli(env, "add", "F", "--project", "记账", "--actor", GONE, "--reason", "x",
                        "--set", "内容=a", "类别=其他", "状态=待查证")
    t.check("J6 已删 bot（删除记录里）→ 拒", code == 1 and "平台上不存在" in out, out)
    code, out = run_cli(env, "add", "F", "--project", "记账", "--actor", QA, "--reason", "x",
                        "--set", "内容=a", "类别=其他", "状态=待查证")
    t.check("J6 专职 bot 写项目库 → 拒", code == 1 and "在用副官" in out, out)
    code, out = run_cli(env, "add", "F", "--project", L.GOV, "--actor", DEP, "--reason", "x",
                        "--set", "内容=a", "类别=其他", "状态=待查证")
    t.check("J6 副官写流程治理库 → 拒", code == 1 and "在用参谋长" in out, out)
    code, out = run_cli(env, "add", "F", "--project", "记账", "--actor", DEP, "--reason", "澄清",
                        "--set", "内容=用户每天记三笔", "类别=用户情况", "状态=已查证", "来源=用户原话", "查证日期=2026-10-21")
    c = L.connect_ro(dbp)
    f = c.execute("SELECT 有效期,有效期依据 FROM F WHERE seq=1").fetchone()
    c.close()
    t.check("N1：用户情况 = 查证日期起 180 天", code == 0 and f[0].startswith("2027-04-19") and "类别默认值" in f[1], str(f))

    # 2 规则：直接连库的反例（每一项都应被拦）
    c = raw(dbp)
    A = DEP
    cases = [
        ("不设 _ctx 直接写", "INSERT INTO F(seq,内容,类别,状态,created_by) VALUES(2,'a','其他','待查证','x')", (), None, "只能经 ledger.py"),
        ("删行", "DELETE FROM F WHERE seq=1", (), (A, "t", "write"), "只增不删"),
        ("改核心列", "UPDATE F SET 内容='改' WHERE seq=1", (), (A, "t", "write"), "核心列"),
        ("非法状态", "INSERT INTO F(seq,内容,类别,状态,created_by) VALUES(2,'a','其他','乱写',?)", (A,), (A, "t", "write"), "不是规定值"),
        ("跳号", "INSERT INTO F(seq,内容,类别,状态,created_by) VALUES(5,'a','其他','待查证',?)", (A,), (A, "t", "write"), "连续"),
        ("冒充 created_by", "INSERT INTO F(seq,内容,类别,状态,created_by) VALUES(2,'a','其他','待查证','别人')", (), (A, "t", "write"), "created_by"),
        ("已查证不写来源", "INSERT INTO F(seq,内容,类别,状态,created_by) VALUES(2,'a','其他','已查证',?)", (A,), (A, "t", "write"), "来源"),
        ("bot 自定却标生效", "INSERT INTO D(seq,日期,决定,理由,谁拍板,状态,created_by) VALUES(3,'2026-10-21','a','b','bot','生效',?)", (A,), (A, "t", "write"), "bot 自定"),
        ("谁拍板从用户改成 bot", "UPDATE D SET 谁拍板='bot',状态='生效（待用户确认）' WHERE seq=1", (), (A, "t", "write"), "只能从 bot 改成用户"),
        ("作废不写理由", "UPDATE D SET 状态='作废' WHERE seq=1", (), (A, "t", "write"), "作废理由"),
        ("影响高没对策", "INSERT INTO R(seq,风险,可能性,影响,状态,created_by) VALUES(1,'a','高','高','监控中',?)", (A,), (A, "t", "write"), "对策"),
        ("依赖不存在的编号", "INSERT INTO dep(依赖方,被依赖,created_by) VALUES('D-1','F-99',?)", (A,), (A, "t", "write"), "不存在"),
        ("改修改记录", "UPDATE change_log SET actor='x' WHERE id=1", (), (A, "t", "write"), "不可改"),
        ("不在迁移时改 schema_version", "UPDATE meta SET value='9' WHERE key='schema_version'", (), (A, "t", "write"), "迁移"),
        ("改库类型", "UPDATE meta SET value='治理' WHERE key='库类型'", (), (A, "t", "write"), "不能改"),
        ("不在迁移时加枚举", "INSERT INTO enum VALUES('F','状态','新状态',9,0)", (), (A, "t", "write"), "迁移"),
        ("普通写入写检查日志", "INSERT INTO check_log(run_at,actor,触发,exit_code,状态,change_log_upto,stdout,result_json) VALUES('t','x','手动',0,'正常',0,'','{}')", (), (A, "t", "write"), "check.py"),
        ("普通写入写备份记录", "INSERT INTO backup_log(actor,结果,change_log_upto) VALUES('x','成功',0)", (), (A, "t", "write"), "备份"),
        ("A 用户已确认没写确认日期", "INSERT INTO A(编号,版本号,标准,依据,级别,检查方法,检查人,状态,created_by) VALUES(1,1,'a','b','必须','c','d','用户已确认',?)", (A,), (A, "t", "write"), "确认日期"),
        ("A 跳版本号", "INSERT INTO A(编号,版本号,标准,依据,级别,检查方法,检查人,状态,created_by) VALUES(1,2,'a','b','必须','c','d','草稿',?)", (A,), (A, "t", "write"), "版本号"),
        ("项目库写 B 表", "INSERT INTO B(seq,bot_id,名称,类型,所属项目,所用模板,状态,创建日期,created_by) VALUES(1,'abcdefgh','x','专职','共用','qa.md@v1.0.0','在用','2026',?)", (A,), (A, "t", "write"), "只在流程治理库"),
        ("项目库写「候选」", "INSERT INTO D(seq,日期,决定,理由,谁拍板,状态,类型,created_by) VALUES(3,'2026','a','b','用户','生效','候选',?)", (A,), (A, "t", "write"), "候选"),
    ]
    for name, sql, params, ctx, want in cases:
        blocked, err = expect_block(c, sql, params, ctx, want)
        t.check(f"2 拦住：{name}", blocked, err)
    c.close()
    c = raw(gov)
    for name, sql, params, want in [
        ("第二个在用参谋长", "INSERT INTO B(seq,bot_id,名称,类型,所属项目,所用模板,库路径,状态,创建日期,created_by) VALUES(5,'zzzzzzzz','参谋长','参谋长','流程治理','chief-of-staff.md@v1.0.0',?,'在用','2026',?)", (gov, COS), "UNIQUE constraint failed: B.类型"),
        ("所用模板不是 x.md@v…", "INSERT INTO B(seq,bot_id,名称,类型,所属项目,所用模板,状态,创建日期,created_by) VALUES(5,'zzzzzzzz','x','专职','共用','qa.md','在用','2026',?)", (COS,), "CHECK"),
        ("改 bot_id", "UPDATE B SET bot_id='zzzzzzzz' WHERE seq=1", (), "核心列"),
    ]:
        blocked, err = expect_block(c, sql, params, (COS, "t", "write"), want)
        t.check(f"2 拦住：{name}", blocked, err)
    c.close()
    c = raw(dbp)
    c.execute("BEGIN")
    c.execute("UPDATE _ctx SET actor=?,reason='t',mode='write' WHERE id=1", (A,))
    c.execute("INSERT INTO A(编号,版本号,标准,依据,级别,检查方法,检查人,状态,确认日期,created_by) VALUES(1,1,'a','b','必须','c','d','用户已确认','2026-10-21',?)", (A,))
    c.execute("INSERT INTO A(编号,版本号,标准,依据,级别,检查方法,检查人,状态,created_by) VALUES(1,2,'a2','b','必须','c','d','草稿',?)", (A,))
    try:
        c.execute("UPDATE A SET 状态='用户已确认',确认日期='2026-10-22' WHERE 版本号=2")
        two = False
    except sqlite3.Error:
        two = True
    c.execute("ROLLBACK")
    c.close()
    t.check("2 拦住：A 同一编号两行用户已确认", two)

    # 6 个人信息
    hard = {"银行卡号": "号码 4111 1111 1111 1111 别忘了",
            "身份证号": "证件 11010519491231002X", "手机号": "电话13800138000", "钱包地址": "0x" + "ab" * 20}
    for k, s in hard.items():
        t.check(f"6 硬拦：{k}", L.pii_hard(s) == [k], str(L.pii_hard(s)))
    t.check("6 不误拦：时间戳 20261021101200、快照名 20261021-101200、提交号、bot ID",
            not L.pii_hard("快照 20261021-101200-关口一.db 时间 20261021101200 提交 6b5536708c34a1e2f9d0c7b6a5e4d3c2b1a09876 " + COS))
    code, out = run_cli(env, "add", "F", "--project", "记账", "--actor", DEP, "--reason", "x", "--pii-checked", "就要写",
                        "--set", "内容=手机 13800138000", "类别=其他", "状态=待查证")
    t.check("6 硬拦带 --pii-checked 也不放行", code == 1 and "不能放行" in out, out)
    code, out = run_cli(env, "add", "D", "--project", "记账", "--actor", DEP, "--reason", "x",
                        "--set", "决定=帮家人记账", "理由=用户说的", "谁拍板=用户", "状态=生效")
    t.check("6 软拦：不带参数被拒", code == 1 and "敏感词" in out, out)
    code, out = run_cli(env, "add", "D", "--project", "记账", "--actor", DEP, "--reason", "立项范围",
                        "--pii-checked", "项目本身是家庭记账，没有原文细节",
                        "--set", "决定=帮家人记账", "理由=用户说的", "谁拍板=用户", "状态=生效", "--dep", "F-1")
    c = L.connect_ro(dbp)
    rs = c.execute("SELECT reason FROM change_log WHERE code='D-3'").fetchone()
    c.close()
    t.check("6 软拦：带理由放行，理由留在修改记录", code == 0 and rs and rs[0].startswith("[pii-checked] 项目本身是家庭记账"), out)

    # 3 并发
    ctx = multiprocessing.get_context("fork")
    with ctx.Pool(4) as pool:
        errs = sum(pool.map(_worker, [(root, 100)] * 4))
    c = L.connect_ro(dbp)
    seqs = [r[0] for r in c.execute("SELECT seq FROM F ORDER BY seq")]
    c.close()
    t.check("3 并发：4 进程 × 100 次 add，0 错、编号连续", errs == 0 and seqs == list(range(1, 402)), f"错 {errs}，行 {len(seqs)}")

    # 4 锁
    ready = ctx.Event()
    p = ctx.Process(target=_holder, args=(dbp, 3, ready))
    p.start()
    ready.wait(5)
    t0 = time.time()
    code, out = run_cli(env, "add", "S", "--project", "记账", "--actor", DEP, "--reason", "锁测试", "--set", "节=1", "结论=a", "状态=生效")
    el = time.time() - t0
    p.join()
    t.check("4 锁：别人占锁 3 秒，写者 5 秒内成功", code == 0 and 2.5 < el < 5, f"{el:.1f}s {out}")

    # apply / update / dep / meta / degrade
    ap = os.path.join(root, "apply.json")
    json.dump({"items": [{"op": "add", "table": "R", "set": {"风险": "r1", "可能性": "低", "影响": "低", "状态": "监控中"}},
                         {"op": "add", "table": "P", "set": {"步骤": "s", "执行人": "副官", "完成标准": "A-1", "自验证方式": "看",
                                                             "可逆性": "可逆", "状态": "未开始"}, "dep": ["$1"]},
                         {"op": "update", "code": "$1", "set": {"状态": "已消除"}},
                         {"op": "dep", "from": "$2", "to": "F-1"}]}, open(ap, "w", encoding="utf-8"), ensure_ascii=False)
    code, out = run_cli(env, "apply", ap, "--project", "记账", "--actor", DEP, "--reason", "批量导入")
    t.check("apply：一个事务批量写，$n 引用同批编号", code == 0 and "R-1, P-1, R-1, dep-" in out, out)
    json.dump({"items": [{"op": "add", "table": "R", "set": {"风险": "r2", "可能性": "低", "影响": "低", "状态": "监控中"}},
                         {"op": "update", "code": "D-1", "set": {"决定": "改核心列"}}]}, open(ap, "w", encoding="utf-8"), ensure_ascii=False)
    code, out = run_cli(env, "apply", ap, "--project", "记账", "--actor", DEP, "--reason", "批量导入")
    c = L.connect_ro(dbp)
    nr = c.execute("SELECT count(*) FROM R").fetchone()[0]
    c.close()
    t.check("apply：中途一条被拒，整批不写", code == 1 and "第 2 条" in out and nr == 1, out)
    json.dump({"items": [{"op": "add", "table": "A", "set": {"标准": "能记一笔", "依据": "用户原话", "级别": "必须", "检查方法": "手测",
                                                             "检查人": "专职·流程QA", "状态": "草稿"}},
                         {"op": "add", "table": "R", "set": {"风险": "r3", "可能性": "低", "影响": "低", "状态": "监控中"}, "dep": ["$1"]}]},
              open(ap, "w", encoding="utf-8"), ensure_ascii=False)
    code, out = run_cli(env, "apply", ap, "--project", "记账", "--actor", DEP, "--reason", "标准和依赖")
    c = L.connect_ro(dbp)
    dr = c.execute("SELECT 被依赖 FROM dep WHERE 依赖方=(SELECT code FROM R WHERE 风险='r3')").fetchall()
    c.close()
    t.check("apply：$n 指向 A 的版本代号时，依赖按 A 编号记", code == 0 and dr and dr[0][0].startswith("A-") and "v" not in dr[0][0], f"{out} {dr}")
    code, out = run_cli(env, "add", "R", "--project", "记账", "--actor", DEP, "--reason", "重复 --set",
                        "--set", "风险=r4", "--set", "可能性=低", "--set", "影响=低", "--set", "状态=监控中")
    t.check("add：--set 写多次也全部生效", code == 0, out)
    code, out = run_cli(env, "update", "D-1", "--project", "记账", "--actor", DEP, "--reason", "错别字", "--set", "决定=做一个记账工具")
    t.check("update：改核心列 → 退出码 1，报中文原因", code == 1 and "核心列" in out, out)
    c = L.connect_ro(dbp)
    old = c.execute("SELECT 决定 FROM D WHERE seq=1").fetchone()[0]
    c.close()
    typo = old[:-1] + ("帐" if old[-1] != "帐" else "账")
    code, out = run_cli(env, "update", "D-1", "--typo", "--project", "记账", "--actor", DEP, "--reason", "帐→账", "--set", f"决定={typo}")
    c = L.connect_ro(dbp)
    now = c.execute("SELECT 决定 FROM D WHERE seq=1").fetchone()[0]
    rs = c.execute("SELECT reason FROM change_log WHERE tbl='D' AND code='D-1' AND op='update' ORDER BY id DESC LIMIT 1").fetchone()
    c.close()
    t.check("update --typo：核心列改 1 个字 → 成功，修改记录原因以「仅错字」开头", code == 0 and now == typo and rs and rs[0].startswith("仅错字"), f"{out} {rs}")
    code, out = run_cli(env, "update", "D-1", "--typo", "--project", "记账", "--actor", DEP, "--reason", "x", "--set", "决定=完全换了一个意思的决定")
    t.check("update --typo：改动超过 2 个字 → 退出码 1", code == 1 and "仅错字" in out, out)
    code, out = run_cli(env, "update", "D-1", "--typo", "--project", "记账", "--actor", DEP, "--reason", "x", "--set", "类型=候选")
    t.check("update --typo：非文字核心列（类型）→ 退出码 1", code == 1 and "只能改" in out, out)
    code, out = run_cli(env, "update", "D-1", "--typo", "--project", "记账", "--actor", DEP, "--reason", "x", "--set", "状态=待定")
    t.check("update --typo：普通列也不许混进来 → 退出码 1", code == 1, out)
    c = raw(dbp)
    try:
        c.execute("BEGIN")
        c.execute("UPDATE _ctx SET actor=?,reason='x',mode='typo' WHERE id=1", (DEP,))
        c.execute("UPDATE D SET 类型='候选' WHERE seq=1")
        ok_trig = False
    except sqlite3.DatabaseError:
        ok_trig = True
    finally:
        c.execute("ROLLBACK")
        c.close()
    t.check("触发器：typo 模式下非文字核心列照样拦", ok_trig)
    code, out = run_cli(env, "dep", "void", "P-1", "F-1", "--project", "记账", "--actor", DEP, "--reason", "不再依赖")
    t.check("dep void：有效 → 作废", code == 0, out)
    code, out = run_cli(env, "meta", "set", "库类型", "治理", "--project", "记账", "--actor", DEP, "--reason", "x")
    t.check("meta set：只允许项目仓库/流程版本/状态", code == 3, out)
    code, out = run_cli(env, "degrade", "on", "--project", "记账", "--actor", DEP, "--reason", "克隆不在 tag 上")
    c = L.connect_ro(dbp)
    mm = L.meta_of(c)["降级模式"]
    dd = c.execute("SELECT 类型,谁拍板,状态 FROM D ORDER BY seq DESC LIMIT 1").fetchone()
    rr = c.execute("SELECT 可能性,影响,状态 FROM R ORDER BY seq DESC LIMIT 1").fetchone()
    c.close()
    t.check("3.7 degrade on：meta + D（降级、bot、待确认）+ R（高高已发生）", code == 0 and mm.startswith("是（克隆不在 tag 上")
            and dd == ("降级", "bot", "生效（待用户确认）") and rr == ("高", "高", "已发生"), f"{mm} {dd} {rr}")
    code, out = run_cli(env, "degrade", "off", "--project", "记账", "--actor", DEP)
    t.check("3.7 degrade off", code == 0, out)

    # 11 show / dump
    code, out = run_cli(env, "add", "F", "--project", "记账", "--actor", DEP, "--reason", "转义",
                        "--set", "内容=甲|乙\n丙", "类别=其他", "状态=已推翻")
    code, out = run_cli(env, "show", "F", "--project", "记账", "--where", "内容=甲|乙\n丙")
    t.check("11 show：隐藏状态默认不显示", code == 0 and "（0 行）" in out, out)
    code, out = run_cli(env, "show", "F", "--project", "记账", "--all", "--where", "内容=甲|乙\n丙")
    t.check("11 show --all：显示；| 和换行转义", "甲\\|乙<br>丙" in out and "（1 行）" in out, out)
    code, out = run_cli(env, "dump", "S", "--project", "记账", "--actor", DEP)
    t.check("11 dump：太宽（>6 列）只贴前 4 列，附 CSV 和快照", code == 0 and "太宽" in out and "dump-S.csv" in out and "快照.db" in out, out[:300])
    csvs = [os.path.join(dp, f) for dp, _, fs in os.walk(env.proj_dir("记账")) for f in fs if f == "dump-S.csv"]
    t.check("11 dump：CSV 是 UTF-8 BOM、行数对", csvs and open(csvs[0], "rb").read(3) == b"\xef\xbb\xbf")
    code, out = run_cli(env, "dump", "meta", "--project", "记账")
    t.check("11 dump：不宽时整表原样贴，第一行带 sha256", code == 0 and "太宽" not in out and "sha256" in out and "库ID" in out, out[:300])
    code, out = run_cli(env, "changes", "D-1", "--project", "记账")
    t.check("changes：按编号列修改记录（含一次仅错字修改）", code == 0 and "D-1" in out and "（2 行）" in out and "仅错字" in out, out)
    code, out = run_cli(env, "deps", "R-1", "--project", "记账", "--recursive")
    t.check("deps：递归下游", code == 0 and "P-1" in out, out)
    code, out = run_cli(env, "query", "--project", "记账", "--sql", "DELETE FROM F")
    t.check("query：只允许 SELECT", code == 3, out)
    code, out = run_cli(env, "query", "--project", "记账", "--sql", "SELECT count(*) AS n FROM D")
    t.check("query：只读查询", code == 0 and "| n |" in out, out)

    # 7 快照
    h0 = hashlib.sha256(open(dbp, "rb").read()).hexdigest()
    code, out = run_cli(env, "snapshot", "--project", "记账", "--label", "关口一", "--actor", DEP)
    snap = [l.split("：", 1)[1] for l in out.splitlines() if l.startswith("快照：")]
    t.check("7 快照：备份接口生成，完整性 ok", code == 0 and snap and os.path.exists(snap[0]) and "完整性：ok" in out, out)
    t.check("7 快照：不改库", hashlib.sha256(open(dbp, "rb").read()).hexdigest() == h0)

    # 8 备份：本地裸仓库当远端（绝不推 GitHub）
    bare = os.path.join(root, "bare.git")
    subprocess.run(["git", "init", "-q", "--bare", bare], check=True)
    code, out = run_cli(env, "backup-init", "--remote", bare)
    t.check("8 backup-init：克隆已存在的仓库", code == 0 and os.path.isdir(os.path.join(env.backup_repo, ".git")), out)
    remote = L.git(env.backup_repo, "remote", "get-url", "origin").strip()
    assert remote.startswith(root), "自测远端必须是临时目录里的本地裸仓库"
    code, out = run_cli(env, "add", "F", "--project", "记账", "--actor", DEP, "--reason", "备份测试",
                        "--set", "内容=b", "类别=其他", "状态=待查证")
    c = L.connect_ro(dbp)
    bl = c.execute("SELECT 结果,change_log_upto,commit_id FROM backup_log ORDER BY id DESC LIMIT 1").fetchone()
    mx = L.max_change(c)
    c.close()
    pushed = subprocess.run(["git", "-C", bare, "log", "--oneline", "-1"], capture_output=True, text=True).stdout
    t.check("8 备份：推送成功，backup_log 记成功并覆盖到最新修改记录", code == 0 and "备份：成功" in out and bl[0] == "成功"
            and bl[1] == mx and bl[2] in pushed, f"{out} {bl} {pushed}")
    files = subprocess.run(["git", "-C", bare, "-c", "core.quotepath=off", "ls-tree", "-r", "--name-only", "HEAD"], capture_output=True, text=True).stdout.split()
    t.check("8 备份：一项目一子目录，ledger.sql + 库ID", "记账/ledger.sql" in files and "记账/库ID" in files, str(files))
    code, out = run_cli(env, "backup", "--project", L.GOV, "--actor", COS)
    t.check("8 backup 手动补推（流程治理）", code == 0 and "备份：成功" in out, out)
    os.chmod(bare, 0o500)
    for dp, dn, fn in os.walk(bare):
        for x in dn + fn:
            os.chmod(os.path.join(dp, x), 0o500 if os.path.isdir(os.path.join(dp, x)) else 0o400)
    code, out = run_cli(env, "add", "F", "--project", "记账", "--actor", DEP, "--reason", "远端不可写",
                        "--set", "内容=c", "类别=其他", "状态=待查证")
    c = L.connect_ro(dbp)
    bl = c.execute("SELECT 结果,error FROM backup_log ORDER BY id DESC LIMIT 1").fetchone()
    inserted = c.execute("SELECT count(*) FROM F WHERE 内容='c'").fetchone()[0]
    c.close()
    t.check("8 远端不可写：写入照样成功、退出码 0、backup_log 记失败", code == 0 and inserted == 1 and bl[0] == "失败"
            and "备份：失败" in out and "不要重试写入" in out, f"{out} {bl}")
    t.check("8 远端不可写：本地留下没推出去的提交", L.unpushed(env.backup_repo) >= 1)
    for dp, dn, fn in os.walk(bare):
        for x in dn + fn:
            os.chmod(os.path.join(dp, x), 0o700 if os.path.isdir(os.path.join(dp, x)) else 0o600)
    os.chmod(bare, 0o700)
    code, out = run_cli(env, "backup", "--project", "记账", "--actor", DEP)
    t.check("8 远端恢复后 backup 补推成功，没推出去的提交清零", code == 0 and L.unpushed(env.backup_repo) == 0, out)
    idf = os.path.join(env.backup_repo, "记账", "库ID")
    open(idf, "w").write("另一个库\n")
    L.git(env.backup_repo, "commit", "-qam", "模拟同名项目")
    code, out = run_cli(env, "add", "F", "--project", "记账", "--actor", DEP, "--reason", "库ID",
                        "--set", "内容=d", "类别=其他", "状态=待查证")
    t.check("8 备份里同名项目库ID不同 → 不覆盖、记失败", code == 0 and "库ID 和本库不一致" in out and
            open(idf).read().strip() == "另一个库", out)
    L.git(env.backup_repo, "reset", "-q", "--hard", "HEAD~1")
    code, out = run_cli(env, "backup-status")
    t.check("backup-status：列各项目最近一次备份", code == 0 and "记账" in out and "流程治理" in out, out)

    # 9 恢复
    code, out = run_cli(env, "backup", "--project", "记账", "--actor", DEP)
    sql_text = L.dump_sql(dbp)
    env2 = L.Env(data_root=os.path.join(root, "data2"), agents_dir=env.agents_dir, deleted=env.deleted, repo=repo)
    os.makedirs(env2.data_root)
    shutil.copytree(env.backup_repo, env2.backup_repo)
    code, out = run_cli(env2, "restore", "--project", "记账")
    c1, c2 = L.connect_ro(dbp), L.connect_ro(env2.db("记账"))
    same = not L.diff_structure(L.structure(c2), L.structure(c1))
    data_same = all(c1.execute(f"SELECT * FROM {x} ORDER BY rowid").fetchall() == c2.execute(f"SELECT * FROM {x} ORDER BY rowid").fetchall()
                    for x in ("F", "D", "R", "S", "P", "A", "dep", "meta", "change_log"))
    c1.close(); c2.close()
    t.check("9 恢复：从备份重建，结构和数据逐条一致", code == 0 and same and data_same, out)
    code, out = run_cli(env2, "restore", "--project", "记账")
    t.check("9 恢复：目标已存在 → 拒", code == 1 and "不覆盖" in out, out)
    env3 = L.Env(data_root=os.path.join(root, "data3"), agents_dir=env.agents_dir, deleted=env.deleted, repo=repo)
    dst, diff = L.restore(env3, "x", sql_text=sql_text)
    t.check("9 恢复：iterdump 文本全量恢复（含生成列和触发器）", not diff)
    c = raw(dst)
    blocked, _ = expect_block(c, "DELETE FROM F WHERE seq=1", (), (DEP, "t", "write"), "只增不删")
    c.close()
    t.check("9 恢复后规则仍有效", blocked)

    # 9b 摩擦 M 表（schema 2）
    code, out = run_cli(env, "add", "M", "--project", "记账", "--actor", DEP, "--reason", "记摩擦",
                        "--set", "节号=flow-general 10", "类别=被脚本拦", "摩擦=每日扫描要贴 60 行输出，用户嫌长", "证据=C-3 终端输出")
    c = L.connect_ro(dbp)
    mrow = c.execute("SELECT code,bot,日期 FROM M WHERE seq=1").fetchone()
    c.close()
    t.check("9b 记摩擦：M-1，bot 默认写入者，日期默认今天", code == 0 and mrow and mrow[0] == "M-1" and mrow[1] == DEP
            and mrow[2] == L.today(), out)
    bad = [run_cli(env, "add", "M", "--project", "记账", "--actor", DEP, "--reason", "x", "--set", *kv)
           for kv in (["节号=第10节", "类别=其他", "摩擦=x", "证据=y"],
                      ["节号=flow-general 10", "类别=其他", "摩擦=第一行\n第二行", "证据=y"],
                      ["节号=flow-general 10", "类别=随便", "摩擦=x", "证据=y"],
                      ["节号=flow-general 10", "类别=其他", "摩擦=x", "证据= "])]
    t.check("9b 摩擦格式：节号不合写法、多行、类别不对、证据空 → 拒绝", all(cd == 1 for cd, _ in bad), str([o[-80:] for _, o in bad]))
    code, out = run_cli(env, "update", "M-1", "--project", "记账", "--actor", DEP, "--reason", "x", "--set", "摩擦=改一下")
    t.check("9b 摩擦只增不改", code == 1 and "只增不改" in out, out)
    run_cli(env, "add", "M", "--project", L.GOV, "--actor", COS, "--reason", "记摩擦",
            "--set", "节号=flow-general 10", "类别=规矩不顺", "摩擦=参谋长也嫌长", "证据=C-1")
    code, out = run_cli(env, "frictions")
    t.check("9b 摩擦汇总：跨库按节号聚合（记账 + 流程治理）", code == 0 and "| flow-general 10 | 2 |" in out
            and "记账 M-1" in out and "流程治理 M-1" in out, out)
    run_cli(env, "add", "D", "--project", L.GOV, "--actor", COS, "--reason", "摩擦汇总转候选",
            "--set", "类型=候选", "状态=待定", "谁拍板=bot", "决定=每日扫描输出太长", "理由=两处摩擦", "来源=记账 M-1")
    code, out = run_cli(env, "frictions")
    code2, out2 = run_cli(env, "frictions", "--all")
    t.check("9b 已进候选的默认不列，--all 列出并标注", "记账 M-1" not in out and "流程治理 M-1" in out
            and "记账 M-1（已进候选）" in out2, out + out2)
    # 9c 真实迁移文件 002：旧版 schema 1 的库演练迁到当前 schema = 新建库
    oldp = env.db("旧库")
    os.makedirs(os.path.dirname(oldp))
    c = raw(oldp)
    c.executescript(open(os.path.join(repo, "schema", "history", "v1.sql"), encoding="utf-8").read())
    c.execute("BEGIN")
    c.execute("UPDATE _ctx SET actor=?,reason='旧库',mode='init' WHERE id=1", (DEP,))
    c.execute("INSERT INTO meta VALUES('schema_version','1')")
    c.execute("INSERT INTO F(seq,内容,类别,状态,created_by) VALUES(1,'旧事实','其他','待查证',?)", (DEP,))
    c.execute("UPDATE _ctx SET actor=NULL,reason=NULL,mode=NULL WHERE id=1")
    c.execute("COMMIT")
    c.close()
    dr = L.migrate_dryrun(env, "旧库", [(2, open(os.path.join(repo, "schema", "migrations", "002.sql"), encoding="utf-8").read())],
                          schema, "draft", os.path.join(root, "dryrun2"))
    t.check("9c 迁移文件 002：schema 1 库迁到 2 = 新建库，F 行数不少", dr["通过"] and not dr["结构差异"]
            and ("F", 1, 1) in [tuple(x) for x in dr["行数"]], str(dr)[:400])
    shutil.rmtree(os.path.dirname(oldp))

    # 10 迁移 v1 → 测试用 v2（加一个枚举值 + 重建 F 表加一列）
    v2 = schema.replace("-- schema_version: 2", "-- schema_version: 3")  # 测试用 v3（变量名沿用 v2）
    v2 = v2.replace("INSERT INTO enum VALUES('F','状态','已合并',7,1);",
                    "INSERT INTO enum VALUES('F','状态','已合并',7,1);\nINSERT INTO enum VALUES('F','状态','已归档',8,1);")
    v2 = v2.replace("  登记方式 TEXT NOT NULL DEFAULT '新增',\n  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),\n  created_by TEXT NOT NULL\n) STRICT;\nCREATE TABLE D(",
                    "  登记方式 TEXT NOT NULL DEFAULT '新增',\n  备查 TEXT,\n  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),\n  created_by TEXT NOT NULL\n) STRICT;\nCREATE TABLE D(", 1)
    assert "备查 TEXT" in v2
    f_create = [s for s in L.split_sql(v2) if s.startswith("CREATE TABLE F(")][0]
    fcols = "seq,内容,类别,状态,来源,查证日期,有效期,有效期依据,说明,放行确认日期,最晚解决步骤,登记方式,created_at,created_by"
    mig = ("-- 从 1 到 2\nINSERT INTO enum VALUES('F','状态','已归档',8,1);\nALTER TABLE F RENAME TO F_old;\n" + f_create + "\n"
           f"INSERT INTO F({fcols}) SELECT {fcols} FROM F_old;\nDROP TABLE F_old;\n")
    c = L.connect_ro(dbp)
    nF = c.execute("SELECT count(*) FROM F").fetchone()[0]
    s_before = L.structure(c)
    c.close()
    h0 = hashlib.sha256(open(dbp, "rb").read()).hexdigest()
    dr = L.migrate_dryrun(env, "记账", [(3, mig)], v2, "v1.1.0", os.path.join(root, "dryrun"))
    t.check("10 迁移演练：拷贝上通过、行数不少、真库一字不动", dr["通过"] and not dr["结构差异"]
            and hashlib.sha256(open(dbp, "rb").read()).hexdigest() == h0 and os.path.exists(dr["拷贝"]), str(dr)[:300])
    dr = L.migrate_dryrun(env, "记账", [(3, mig + "INSERT INTO 不存在的表 VALUES(1);\n")], v2, "v1.1.0", os.path.join(root, "dryrun"))
    t.check("10 迁移演练：迁移文件出错 → 不通过并报错误", not dr["通过"] and dr["错误"], str(dr)[:300])
    try:
        L.migrate_db(env, "记账", DEP, "用户原话：同意迁移 2026-10-21", [(3, mig + "INSERT INTO 不存在的表 VALUES(1);\n")], v2, "v1.1.0")
        failed = False
    except L.Reject:
        failed = True
    c = L.connect_ro(dbp)
    unchanged = not L.diff_structure(L.structure(c), s_before) and L.meta_of(c)["schema_version"] == "2"
    c.close()
    t.check("10 迁移中途出错整体回滚（结构、版本都不变）", failed and unchanged)
    r = L.migrate_db(env, "记账", DEP, "用户原话：同意迁移 2026-10-21", [(3, mig)], v2, "v1.1.0")
    c = L.connect_ro(dbp)
    eq = not L.diff_structure(L.structure(c), L.reference_structure(v2))
    m2 = L.meta_of(c)
    n2 = c.execute("SELECT count(*) FROM F").fetchone()[0]
    dv = c.execute("SELECT 类型,决定 FROM D ORDER BY seq DESC LIMIT 1").fetchone()
    c.close()
    t.check("10 迁移后结构 = 新建 v2 库；数据一行不少；版本和 tag 已改", eq and n2 == nF and m2["schema_version"] == "3"
            and m2["schema_tag"] == "v1.1.0", f"{n2}/{nF} {m2.get('schema_version')}")
    t.check("10 迁移：先快照、记一条 D（版本）、推备份", os.path.exists(r["快照"]) and dv[0] == "版本" and "2→3" in dv[1]
            and r["备份"]["结果"] == "成功", str(r))
    c = raw(dbp)
    blocked, _ = expect_block(c, "DELETE FROM F WHERE seq=1", (), (DEP, "t", "write"), "只增不删")
    c.close()
    t.check("10 迁移后禁删仍有效", blocked)

    # 13 库版本和克隆不符
    code, out = run_cli(env, "add", "F", "--project", "记账", "--actor", DEP, "--reason", "x",
                        "--set", "内容=e", "类别=其他", "状态=待查证")
    t.check("13 库版本比克隆高 → 写入退出码 2", code == 2 and "克隆比库旧" in out, out)
    c = raw(gov)
    c.execute("BEGIN")
    c.execute("UPDATE _ctx SET actor=?,reason='模拟旧库',mode='migrate' WHERE id=1", (COS,))
    c.execute("UPDATE meta SET value='0' WHERE key='schema_version'")
    c.execute("UPDATE _ctx SET actor=NULL,reason=NULL,mode=NULL WHERE id=1")
    c.execute("COMMIT")
    c.close()
    code, out = run_cli(env, "add", "F", "--project", L.GOV, "--actor", COS, "--reason", "x",
                        "--set", "内容=e", "类别=其他", "状态=待查证")
    code2, out2 = run_cli(env, "show", "B", "--project", L.GOV)
    t.check("13 库版本比克隆低 → 写入退出码 2（提示先迁移），读照常", code == 2 and "先按发布顺序迁移" in out and code2 == 0, out)
    code, out = run_cli(env, "add", "F", "--project", "../x", "--actor", COS, "--reason", "x", "--set", "内容=e")
    t.check("用法错误 → 退出码 3（项目名带 /）", code == 3, out)
