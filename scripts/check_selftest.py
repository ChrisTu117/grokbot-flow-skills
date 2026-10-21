"""check.py 自测（python3 scripts/check.py selftest）。全部在临时目录里跑，不碰 /home/box/flow-data，不联网。"""
import datetime, json, os, shutil, sqlite3, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check as C  # noqa: E402
import ledger as L  # noqa: E402
from ledger_selftest import T, make_repo, make_bot, run_cli, raw, genesis_plan, COS, QA, DEP, FAKE  # noqa: E402

ORPHAN = "0e9a0000-0000-0000-0000-000000000007"


def build(root):
    """完整、正常的环境：参谋长 + 专职·流程QA + 副官·记账，四个 skill 已装，备份仓库是本地裸仓库。"""
    os.makedirs(root)
    repo = make_repo(root)
    subprocess.run(["git", "-C", repo, "remote", "add", "origin", "https://github.com/test/flow-governance"], check=True)
    env = L.Env(data_root=os.path.join(root, "data"), agents_dir=os.path.join(root, "agents"),
                deleted=os.path.join(root, "deleted.json"), repo=repo, backup_timeout=20)
    json.dump({"version": 1, "agents": {}}, open(env.deleted, "w"))
    tpl = lambda n: open(os.path.join(repo, "templates", n), encoding="utf-8").read()
    make_bot(env, COS, "参谋长", tpl("chief-of-staff.md"))
    make_bot(env, QA, "专职·流程QA", tpl("qa.md"))
    make_bot(env, DEP, "副官·记账", C.fill(tpl("deputy.md"), "记账"))
    wf = os.path.join(root, "wf")
    for slug in os.listdir(os.path.join(repo, "skills")):
        os.makedirs(os.path.join(wf, slug))
        shutil.copy(os.path.join(repo, "skills", slug, "SKILL.md"), os.path.join(wf, slug, "SKILL.md"))
    bare = os.path.join(root, "bare.git")
    subprocess.run(["git", "init", "-q", "--bare", bare], check=True)
    assert run_cli(env, "backup-init", "--remote", bare)[0] == 0
    info = L.repo_info(repo)
    plan = genesis_plan(env, info, os.path.join(root, "plan.json"))
    assert run_cli(env, "genesis", "--actor", COS, "--plan", plan)[0] == 0
    assert run_cli(env, "add", "B", "--project", L.GOV, "--actor", COS, "--reason", "建副官", "--set", f"bot_id={DEP}",
                   "名称=副官·记账", "类型=副官", "所属项目=记账", "所用模板=deputy.md@v1.0.0", "状态=在用",
                   f"库路径={env.db('记账')}")[0] == 0
    ho = {"项目名": "记账", "想法原话": "做一个记账小工具", "来源": "参谋长对话", "用户确认": {"原话": "开干", "时间": "2026-10-21T10:05"},
          "流程版本": info["label"], "提交号": info["commit"][:12]}
    json.dump(ho, open(os.path.join(root, "h.json"), "w", encoding="utf-8"), ensure_ascii=False)
    assert run_cli(env, "init", "--project", "记账", "--actor", DEP, "--handoff", os.path.join(root, "h.json"))[0] == 0
    return env, wf


def chk(env, wf, project="记账", actor=DEP, gov=False, **kw):
    return C.run_check(env, project, actor, "手动", governance=gov, workflows_dir=wf,
                       out=kw.pop("out", os.path.join(env.data_root, "..", "r.json")), **kw)


def kinds(res):
    return {f["类型"] for f in res["发现"]}


def run():
    t = T()
    root = tempfile.mkdtemp(prefix="check-selftest-")
    try:
        _retained(t, root)
        _new(t, root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print(f"check.py 自测：{t.n} 项，" + ("全部通过" if t.ok else f"失败 {len(t.fail)} 项：{'；'.join(t.fail)}"))
    return 0 if t.ok else 1


def _retained(t, root):
    """v0.1.0 保留的 15 条（名册行改成读 B 表的字段名）。"""
    fm1 = "---\nname: 甲\ndescription: 一 二 bot 三\n---\n正文\n"
    fm2 = "---\nname: 甲\ndescription: >-\n  一 二\n  bot 三\nmetadata:\n  k: v\n---\n正文  \n\n"
    t.check("保留 调用 build/hash.py：描述同值不同写法哈希相同", C.norm_hash(fm1) == C.norm_hash(fm2))
    t.check("保留 调用 build/hash.py：改描述哈希变", C.norm_hash(fm1) != C.norm_hash(fm1.replace("三", "四")))
    d = C.H.first_diff(fm1, fm1.replace("正文", "正文。"))
    t.check("hash.py --diff：指出第一处不同的行号（规范化后）", d is not None and d[0] == 4 and C.H.first_diff(fm1, fm2) is None, str(d))
    hp = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "hash.py")
    r1 = subprocess.run([sys.executable, hp, "-"], input=fm1 + "  \n", capture_output=True, text=True)
    t.check("hash.py - 从标准输入读（bot 设定正文管道进来），结果与按文件算相同",
            r1.returncode == 0 and r1.stdout.split()[0] == C.norm_hash(fm1), r1.stdout + r1.stderr)
    tpl = "你是副官·〈项目名〉，项目〈项目名〉。\n冲突时以守则为准。\n【项目专有补充】\n"
    body, sup = C.split_supplement(C.fill(tpl, "记账") + "说中文。\n不要打印密码。")
    t.check("保留 填项目名并按补充行拆分", body.endswith("【项目专有补充】") and "〈项目名〉" not in body and sup.strip() == "说中文。\n不要打印密码。")
    t.check("保留 没有补充行时整段当模板部分", C.split_supplement("甲\n乙") == ("甲\n乙", None))
    tmp = os.path.join(root, "old")
    repo, wf, ag = os.path.join(tmp, "repo"), os.path.join(tmp, "wf"), os.path.join(tmp, "agents")
    os.makedirs(os.path.join(repo, "skills", "general-flow")); os.makedirs(os.path.join(repo, "templates"))

    def w(p, s):
        os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "w", encoding="utf-8").write(s)
    g = lambda *a: subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, check=True)
    subprocess.run(["git", "init", "-q", repo], check=True)
    g("config", "user.email", "t@t"); g("config", "user.name", "t")
    sk1 = "---\nname: 通用流程\ndescription: 测试\n---\n旧正文\n"
    sk2 = sk1.replace("旧正文", "新正文")
    w(os.path.join(repo, "skills", "general-flow", "SKILL.md"), sk1); w(os.path.join(repo, "templates", "deputy.md"), tpl)
    g("add", "-A"); g("commit", "-qm", "a"); g("tag", "v1.0.0")
    w(os.path.join(repo, "skills", "general-flow", "SKILL.md"), sk2)
    w(os.path.join(repo, "templates", "deputy.md"), tpl.replace("冲突时", "冲突时一律"))
    g("add", "-A"); g("commit", "-qm", "b"); g("tag", "v1.1.0")
    st = C.repo_state(repo)
    t.check("保留 tag 识别：停在 v1.1.0、干净、最新", st["tag"] == "v1.1.0" and st["clean"] and st["latest"] == "v1.1.0")
    w(os.path.join(wf, "s1", "SKILL.md"), sk1)
    rep = C.Report(); C.check_skills(rep, repo, st, wf)
    t.check("保留 skill 落后到旧 tag", any(f["类型"] == "落后" and "v1.0.0" in f["详情"] for f in rep.findings))
    w(os.path.join(wf, "s1", "SKILL.md"), sk2.replace("新正文", "乱改"))
    rep = C.Report(); C.check_skills(rep, repo, st, wf)
    t.check("保留 skill 本机被改过", any(f["类型"] == "本机被改过" for f in rep.findings))
    w(os.path.join(wf, "s1", "SKILL.md"), sk2)
    rep = C.Report(); C.check_skills(rep, repo, st, wf)
    t.check("保留 skill 与克隆一致", not rep.findings and rep.ok)
    w(os.path.join(wf, "s1", "SKILL.md"), sk2.replace("name: 通用流程", "name: general-flow"))
    rep = C.Report(); C.check_skills(rep, repo, st, wf)
    t.check("J2 别名：仓库叫通用流程、本机叫 general-flow 也不算缺失（中英文名互认）", not any(f["类型"] == "本机缺 skill" for f in rep.findings), str(rep.findings))
    sk3 = sk2.replace("name: 通用流程", "name: flow-general")
    w(os.path.join(repo, "skills", "general-flow", "SKILL.md"), sk3)
    g("add", "-A"); g("commit", "-qm", "c"); g("tag", "v1.2.0")
    st = C.repo_state(repo)
    w(os.path.join(wf, "s1", "SKILL.md"), sk2)
    rep = C.Report(); C.check_skills(rep, repo, st, wf)
    t.check("改英文名后：本机旧中文名那份认作落后（不是缺失）", any(f["类型"] == "落后" and "v1.1.0" in f["详情"] for f in rep.findings)
            and not any(f["类型"] == "本机缺 skill" for f in rep.findings), str(rep.findings))
    ei = L.Env(data_root=os.path.join(root, "inv-rename", "data"), agents_dir=os.path.join(root, "inv-rename", "agents"),
               deleted=os.path.join(root, "inv-rename", "deleted.json"), repo=repo)
    os.makedirs(ei.agents_dir)
    _, out, res, _ = C.inventory(ei, "a0000000-0000-0000-0000-000000000001", out=os.path.join(root, "inv-rename.json"), workflows_dir=wf)
    acts = {r["对象"]: r["建议动作"] for r in res["表"]}
    t.check("改英文名后 inventory：旧中文名那份建议「改英文名」并给出 skill-id、问删不删", acts.get("skill flow-general", "").startswith("改英文名")
            and "s1" in acts.get("skill flow-general", "") and "删除全局生效" in acts.get("skill flow-general", ""), out)
    w(os.path.join(wf, "flow-general", "SKILL.md"), sk3)
    rep = C.Report(); C.check_skills(rep, repo, st, wf)
    t.check("改英文名后：新装英文名、旧中文名还在 → 报两份", any("多份" in f["类型"] or "多份" in f["详情"] or "；" in f["详情"] for f in rep.findings), str(rep.findings))
    g("reset", "-q", "--hard", "v1.1.0"); g("tag", "-d", "v1.2.0")  # 临时仓库复原，后面的用例按 v1.0.0 / v1.1.0 写
    st = C.repo_state(repo)
    shutil.rmtree(wf)
    w(os.path.join(wf, "s1", "SKILL.md"), sk2)

    def bot(bid, desc):
        w(os.path.join(ag, bid, "profile.json"), json.dumps({"description": desc}, ensure_ascii=False))
    bot("b1", C.fill(tpl, "记账") + "说中文。")
    bot("b2", C.fill(tpl.replace("冲突时", "冲突时一律"), "记账"))
    bot("b3", "你是副官·记账，随便改的。\n【项目专有补充】\n")
    rows = [{"code": "B-1", "bot_id": "b1", "名称": "副官·记账", "所属项目": "记账", "所用模板": "deputy.md@v1.0.0", "状态": "在用"},
            {"code": "B-2", "bot_id": "b2", "名称": "副官·记账2", "所属项目": "记账", "所用模板": "deputy.md@v1.0.0", "状态": "在用"},
            {"code": "B-3", "bot_id": "b3", "名称": "副官·记账3", "所属项目": "记账", "所用模板": "deputy.md@v1.1.0", "状态": "在用"},
            {"code": "B-4", "bot_id": "gone", "名称": "副官·旧", "所属项目": "旧", "所用模板": "deputy.md@v1.0.0", "状态": "在用"}]
    rep = C.Report(); supp = C.check_bots(rep, repo, st, rows, ag, {})
    ks = {(f["对象"].split("（")[1].rstrip("）"), f["类型"]) for f in rep.findings}
    t.check("保留 bot 停在旧模板 → 落后（补充段不参与）", ("b1", "落后") in ks)
    t.check("保留 bot 等于当前模板 → 正常；名册版本与实际不符 → 报", ("b2", "落后") not in ks and ("b2", "名册所用模板与实际不符") in ks)
    t.check("保留 bot 模板部分被改 → 设定被改过", ("b3", "设定被改过") in ks)
    t.check("保留 名册有而平台没有", ("gone", "名册有而平台没有") in ks)
    bot("b6", "从模板库导入的设定")
    rep = C.Report(); C.check_bots(rep, repo, st, [dict(rows[0], bot_id="b6", 所用模板="https://example.com/tpl")], ag, {})
    t.check("所用模板是链接 → 不核对、不降级", not rep.findings and not rep.degraded, f"{rep.findings} {rep.degraded}")
    bot("b1", C.fill(tpl, "记账") + "说英文。")
    rep = C.Report(); C.check_bots(rep, repo, st, rows, ag, supp)
    t.check("保留 补充段和上次比有变化 → 报", any(f["类型"] == "补充段有变化" and "b1" in f["对象"] for f in rep.findings))
    g("checkout", "-q", "v1.0.0")
    rep = C.Report(); C.check_repo(rep, C.repo_state(repo))
    t.check("保留 克隆停在旧 tag → 落后", any(f["类型"] == "落后" and "v1.1.0" in f["详情"] for f in rep.findings))
    g("checkout", "-q", "v1.1.0")
    w(os.path.join(repo, "templates", "deputy.md"), tpl.replace("冲突时", "草稿里"))
    g("commit", "-qam", "draft")
    st = C.repo_state(repo)
    rep = C.Report(); C.check_repo(rep, st)
    t.check("草稿提交：标签 draft-<提交号>，判降级「不在任何 tag 上」", st["label"].startswith("draft-")
            and any("草稿提交" in d["原因"] for d in rep.degraded))
    bot("b5", C.fill(tpl.replace("冲突时", "草稿里"), "记账"))
    rep = C.Report(); C.check_bots(rep, repo, st, [dict(rows[0], bot_id="b5", 所用模板=f"deputy.md@{st['label']}")], ag, {})
    t.check("草稿提交：bot 设定等于草稿模板 → 正常", not rep.findings and rep.ok, str(rep.findings))
    w(os.path.join(repo, "x.txt"), "脏")
    rep = C.Report(); C.check_repo(rep, C.repo_state(repo))
    t.check("保留 克隆有本地改动 → 降级", any("本地改动" in d["原因"] for d in rep.degraded))


def _new(t, root):
    env, wf = build(os.path.join(root, "a"))
    code, out, res, _ = chk(env, wf, L.GOV, COS, gov=True)
    t.check("新1 完整环境：流程治理 --governance 全部正常，退出码 0", code == 0, out)
    code, out, res, _ = chk(env, wf)
    t.check("新1 完整环境：项目库正常，退出码 0", code == 0, out)
    t.check("新1 第一行格式：仓库版本、库、schema、表数、修改记录", out.startswith("检查脚本（仓库版本 v1.0.0，提交 ")
            and "库 记账（schema 2），11 张表" in out.splitlines()[0] and "修改记录到 #" in out, out.splitlines()[0])

    # 14、15 --log
    code, out, res, outp = C.run_check(env, "记账", DEP, "每日扫描", log=True, workflows_dir=wf)
    c = L.connect_ro(env.db("记账"))
    row = c.execute("SELECT code,stdout,result_json,触发,exit_code FROM check_log ORDER BY id DESC LIMIT 1").fetchone()
    c.close()
    t.check("新14 --log：check_log 的 stdout 与终端逐字相同", row and row[1] == out, out)
    t.check("新14 --log：result_json 与 --out 文件逐字相同", row[2] == open(outp, encoding="utf-8").read())
    t.check("新14 --log：第一行带 C 编号", f"检查日志 {row[0]}。" in out.splitlines()[0] and row[0] == "C-1")
    t.check("新15 默认 out 路径带项目名、时间、ID 前 8 位",
            outp.startswith(os.path.join(env.data_root, "记账", "runs")) and outp.endswith(f"-{DEP[:8]}/result.json"), outp)
    # 新17 参谋长停摆告警
    rows = L.roster(env)
    t.check("新17 工作日计数：周五→下周二 = 2，周五→下周三 = 3",
            C.working_days_between(datetime.date(2026, 10, 23), datetime.date(2026, 10, 27)) == 2
            and C.working_days_between(datetime.date(2026, 10, 23), datetime.date(2026, 10, 28)) == 3)
    today = datetime.date.today()
    rp = C.Report(); C.check_chief_alive(rp, env, rows, today)
    t.check("新17 参谋长刚建库、未超时 → 不报", not rp.findings and not rp.degraded, str(rp.findings))
    rp = C.Report(); C.check_chief_alive(rp, env, rows, today + datetime.timedelta(days=7))
    t.check("新17 参谋长 7 天没有定时检查 → 报「参谋长可能停了」",
            any(f["类型"] == "参谋长可能停了" and "参谋长可能停了" in f["详情"] for f in rp.findings), str(rp.findings))
    C.run_check(env, L.GOV, COS, "工作日巡检", governance=True, log=True, workflows_dir=wf)
    C.run_check(env, "记账", DEP, "手动", log=True, workflows_dir=wf)
    rp = C.Report(); C.check_chief_alive(rp, env, rows, today + datetime.timedelta(days=1))
    t.check("新17 有参谋长的工作日巡检日志 → 按它算、不报；副官自己的检查日志不算数", not rp.findings
            and any("最近一次是 C-" in g["详情"] for g in rp.ok), str(rp.ok[-1:]))
    code, out, res, _ = chk(env, wf)
    t.check("新17 项目检查里带这一项（正常时进正常项）", any(g["表"] == "check_log" and g["对象"] == "流程治理" for g in res["正常项"]), out)

    code, out, res, _ = C.run_check(env, "记账", COS, "手动", log=True, workflows_dir=wf, out=os.path.join(root, "x.json"))
    t.check("新14 --log 写失败（参谋长写副官库）→ 退出码 2，最后一行说明", code == 2 and "检查日志写入失败" in out.splitlines()[-1]
            and "参谋长不写副官的库" in out, out)

    # 2 拆触发器 / 3 偷插枚举
    c = raw(env.db("记账"))
    c.execute("DROP TRIGGER F_bd")
    c.execute("BEGIN"); c.execute("UPDATE _ctx SET actor=?,reason='x',mode='migrate' WHERE id=1", (DEP,))
    c.execute("INSERT INTO enum VALUES('F','状态','偷加的',9,0)")
    c.execute("UPDATE _ctx SET actor=NULL,reason=NULL,mode=NULL WHERE id=1"); c.execute("COMMIT")
    c.close()
    code, out, res, _ = chk(env, wf)
    names = {f["对象"] for f in res["发现"] if f["类型"] == "规则被改动"}
    t.check("新2 DROP TRIGGER：报「规则被改动」", "trigger F_bd" in names, out)
    t.check("新3 偷插枚举：报「规则被改动」", "enum 行" in names, out)

    env, wf = build(os.path.join(root, "b"))
    # 7 写入者不在名册；9 个人信息绕过写入；8b 备份落后
    c = raw(env.db("记账"))
    c.execute("BEGIN"); c.execute("UPDATE _ctx SET actor=?,reason='绕过',mode='write' WHERE id=1", (FAKE,))
    c.execute("INSERT INTO F(seq,内容,类别,状态,created_by) VALUES(1,'电话 13800138000','其他','待查证',?)", (FAKE,))
    c.execute("UPDATE _ctx SET actor=NULL,reason=NULL,mode=NULL WHERE id=1"); c.execute("COMMIT")
    c.close()
    code, out, res, _ = chk(env, wf)
    t.check("新7 change_log 里有不在名册的写入者：报", any(f["类型"] == "写入者不在名册" and f["对象"] == FAKE for f in res["发现"]), out)
    t.check("新9 个人信息绕过写入：报位置，不打印原文", any(f["类型"] == "疑似个人信息原文" and f["对象"] == "F-1.内容" for f in res["发现"])
            and "13800138000" not in out and "13800138000" not in json.dumps(res, ensure_ascii=False), out)
    t.check("新8 备份成功但落后于修改记录：报", any(f["类型"] == "备份未推成功" and "只覆盖到" in f["详情"] for f in res["发现"]), out)
    # 8a 最后一条失败 + 本地有没推出去的提交
    bare = os.path.join(os.path.dirname(env.data_root), "bare.git")
    for dp, dn, fn in os.walk(bare):
        for x in dn + fn:
            os.chmod(os.path.join(dp, x), 0o500 if os.path.isdir(os.path.join(dp, x)) else 0o400)
    run_cli(env, "add", "S", "--project", "记账", "--actor", DEP, "--reason", "x", "--set", "节=1", "结论=a", "状态=生效")
    for dp, dn, fn in os.walk(bare):
        for x in dn + fn:
            os.chmod(os.path.join(dp, x), 0o700 if os.path.isdir(os.path.join(dp, x)) else 0o600)
    code, out, res, _ = chk(env, wf)
    det = [f["详情"] for f in res["发现"] if f["类型"] == "备份未推成功"]
    t.check("新8 backup_log 最后一条失败：报", any("只覆盖到" not in d and "没推出去" not in d for d in det), str(det))
    t.check("新8 备份仓库有没推出去的提交：报", any("没推出去的提交" in d for d in det), str(det))

    # 6 行数减少（用旧快照模拟）
    env, wf = build(os.path.join(root, "c"))
    snap = L.snapshot(env, "记账", "旧")[0]
    run_cli(env, "add", "F", "--project", "记账", "--actor", DEP, "--reason", "x", "--set", "内容=a", "类别=其他", "状态=待查证")
    prevp = os.path.join(root, "prev.json")
    chk(env, wf, out=prevp)
    shutil.copy(snap, env.db("记账"))
    code, out, res, _ = chk(env, wf, prev_path=prevp)
    t.check("新6 行数比上次少：报「行数减少」", "行数减少" in kinds(res), out)
    # 5 schema 版本
    def set_v(v):
        c = raw(env.db("记账"))
        c.execute("BEGIN"); c.execute("UPDATE _ctx SET actor=?,reason='x',mode='migrate' WHERE id=1", (DEP,))
        c.execute("UPDATE meta SET value=? WHERE key='schema_version'", (str(v),))
        c.execute("UPDATE _ctx SET actor=NULL,reason=NULL,mode=NULL WHERE id=1"); c.execute("COMMIT"); c.close()
    set_v(0)
    code, out, res, _ = chk(env, wf)
    t.check("新5 库 schema 低：报「需迁移」", "需迁移" in kinds(res), out)
    set_v(9)
    code, out, res, _ = chk(env, wf)
    t.check("新5 库 schema 高：降级「克隆比库旧」", code == 2 and any("克隆比库旧" in d["原因"] for d in res["降级"]), out)
    # 4 库损坏
    data = open(env.db("记账"), "rb").read()
    open(env.db("记账"), "wb").write(data[:len(data) // 3])
    code, out, res, _ = chk(env, wf)
    t.check("新4 库文件损坏（截断）：降级", code == 2 and any("库打不开或完整性" in d["原因"] for d in res["降级"]), out)
    os.remove(env.db("记账"))
    code, out, res, _ = chk(env, wf, L.GOV, COS, gov=True)
    t.check("名册库路径：副官的库文件不在 → 报「名册登记的库不存在」", "名册登记的库不存在" in kinds(res), out)

    # 10–13 名册对平台
    env, wf = build(os.path.join(root, "d"))
    make_bot(env, ORPHAN, "专职·流程QA", "旧的 QA")
    code, out, res, _ = chk(env, wf, L.GOV, COS, gov=True)
    t.check("新10 平台有「专职·流程QA」不在名册：报「平台有而名册没有」",
            any(f["类型"] == "平台有而名册没有" and ORPHAN in f["对象"] for f in res["发现"]), out)
    json.dump({"version": 1, "agents": {ORPHAN: {"upstream": "done"}}}, open(env.deleted, "w"))
    code, out, res, _ = chk(env, wf, L.GOV, COS, gov=True)
    t.check("新10 ID 在删除记录里：不报", not any(ORPHAN in f["对象"] for f in res["发现"]), out)
    make_bot(env, "11ae0000-0000-0000-0000-000000000008", "随便改的名字", open(os.path.join(env.repo, "templates", "idea-critic.md"), encoding="utf-8").read())
    code, out, res, _ = chk(env, wf, L.GOV, COS, gov=True)
    t.check("新11 设定等于模板但名字改过：也算「平台有而名册没有」",
            any(f["类型"] == "平台有而名册没有" and "idea-critic.md@v1.0.0" in f["详情"] for f in res["发现"]), out)
    p = os.path.join(env.agents_dir, QA, "profile.json")
    pr = json.load(open(p, encoding="utf-8")); pr["name"] = "专职·质检"; json.dump(pr, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    code, out, res, _ = chk(env, wf, L.GOV, COS, gov=True)
    t.check("新12 名册名称和平台名字不同：报「名称不一致」", "名称不一致" in kinds(res), out)
    make_bot(env, FAKE, "参谋长", "另一个参谋长")
    code, out, res, _ = chk(env, wf, L.GOV, FAKE, gov=True)
    t.check("新13 在用参谋长不是 --actor：报「名册里没有本参谋长在用行」", "名册里没有本参谋长在用行" in kinds(res), out)

    # 17 meta 流程版本和克隆不一致
    subprocess.run(["git", "-C", env.repo, "tag", "v1.0.1"], check=True)
    code, out, res, _ = chk(env, wf)
    t.check("新17 meta 流程版本和克隆 tag 不一致：报", any(f["类型"] == "登记与实际不符" and f["对象"] == "流程版本" for f in res["发现"]), out)

    # 16 inventory 四种情况
    e0 = L.Env(data_root=os.path.join(root, "empty", "data"), agents_dir=os.path.join(root, "empty", "agents"),
               deleted=os.path.join(root, "empty", "deleted.json"), repo=env.repo)
    os.makedirs(e0.agents_dir)
    make_bot(e0, COS, "参谋长", "x")
    code, out, res, _ = C.inventory(e0, COS, out=os.path.join(root, "inv0.json"), workflows_dir=os.path.join(root, "empty", "wf"))
    acts = {r["对象"]: r["建议动作"] for r in res["表"]}
    t.check("新16 inventory 空环境：数据根新建、skill 补建、库新建", acts.get("数据根目录") == "新建" and acts.get("流程治理库") == "新建"
            and sum(1 for k, v in acts.items() if k.startswith("skill ") and v == "补建") == 4, out)
    t.check("新16 inventory 自己（--actor）不当成未登记 bot 让用户收编", "平台 bot 参谋长" not in acts
            and acts.get("平台 bot 参谋长（自己）", "").startswith("不收编"), out)
    env2, wf2 = build(os.path.join(root, "e"))
    code, out, res, _ = C.inventory(env2, COS, out=os.path.join(root, "inv1.json"), workflows_dir=wf2)
    acts = {r["对象"]: r["建议动作"] for r in res["表"]}
    t.check("新16 inventory 完整环境：skill 全复用、不执行创世", sum(1 for k, v in acts.items() if k.startswith("skill ") and v == "复用") == 4
            and acts.get("流程治理库", "").startswith("不执行创世"), out)
    make_bot(env2, ORPHAN, "专职·想法挑刺", "旧的")
    code, out, res, _ = C.inventory(env2, COS, out=os.path.join(root, "inv2.json"), workflows_dir=wf2)
    orow = [r for r in res["表"] if r["对象"] == "平台 bot 专职·想法挑刺"]
    t.check("新16 inventory 孤儿 bot：报「未登记，可能是已删 bot 残留」，由用户定收编或忽略，不默认、不新建同名",
            len(orow) == 1 and "可能是已删 bot 残留" in orow[0]["现状"] and "由用户定" in orow[0]["建议动作"]
            and "默认建议" not in out and "不默认" in orow[0]["建议动作"], out)
    t.check("新16 inventory 孤儿 bot 不再单列「专职设定…复用」行", not any(r["对象"].startswith("专职设定 专职·想法挑刺") for r in res["表"]), out)
    newer = subprocess.run(["git", "-C", env2.repo, "commit-tree", "HEAD^{tree}", "-p", "HEAD", "-m", "newer"],
                           capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(["git", "-C", env2.repo, "tag", "v9.0.0", newer], check=True)
    code, out, res, _ = C.inventory(env2, COS, out=os.path.join(root, "inv2b.json"), workflows_dir=wf2)
    crow = [r for r in res["表"] if r["对象"] == "本机克隆"]
    t.check("新16 inventory 克隆落后于已知最新 tag：停下问用户，不自己切", len(crow) == 1 and crow[0]["建议动作"].startswith("停，问用户")
            and "v9.0.0" in crow[0]["建议动作"] and "克隆落后" in crow[0]["原因"], out)
    subprocess.run(["git", "-C", env2.repo, "tag", "-d", "v9.0.0"], check=True, capture_output=True)
    shutil.move(env2.db(L.GOV), os.path.join(root, "gov-moved.db"))
    code, out, res, _ = C.inventory(env2, COS, out=os.path.join(root, "inv3.json"), workflows_dir=wf2)
    t.check("新16 inventory 有备份没有库：建议「从备份恢复 / 新建」", any(r["对象"] == "流程治理库" and "恢复" in r["建议动作"] for r in res["表"])
            and res["备份"]["有流程治理备份"], out)
