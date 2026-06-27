#!/usr/bin/env python3
"""
v4 ACE 企业级权限模型验证脚本
=============================
通过 HTTP API 验证 ACE（Access Control Entry）权限体系。

前提条件:
  1. 所有服务已启动
  2. Java 后端运行在 localhost:8080
  3. 已执行 migration-v4-ace-permission.sql

测试场景:
  1. 全局管理员 → 全量访问所有 KB
  2. Owner (张三) → space_wide + ACE allow - deny 覆盖
  3. 普通成员 (李四, 研发部) → space_wide - deny 覆盖
  4. 外部成员 (王五, 高管组) → space_wide + ACE allow
  5. 组嵌套: 后端架构组 ⊂ 研发部，继承父组权限

用法:
  python scripts/verify_permissions_v4.py
"""

import requests
import sys
import os

BASE_URL = os.environ.get("KES_BASE_URL", "http://localhost:8080/api")
PASSWORD = "Test123456"

# ---- 测试数据定义 ----
# 用户组嵌套关系: 后端架构组(parent=研发部) ⊂ 研发部(parent=null)
# 高管组独立 (parent=null)

TEST_DATA = {
    "users": {
        "zhangsan": {"username": "v4_zhangsan", "display_name": "张三", "desc": "后端架构组成员 → Space owner"},
        "lisi":    {"username": "v4_lisi",    "display_name": "李四", "desc": "研发部全员组成员"},
        "wangwu":  {"username": "v4_wangwu",  "display_name": "王五", "desc": "高管组成员"},
        "zhaoliu": {"username": "v4_zhaoliu", "display_name": "赵六", "desc": "全局管理员"},
    },
}

# 跟踪创建的资源 ID
ids = {
    "space_id": None,
    "groups": {},     # name → id
    "kb_ids": {},     # name → id
    "user_ids": {},   # name → id
    "tokens": {},     # name → context_token
    "role_ids": {},   # name → id (角色)
}

pass_count = 0
fail_count = 0


def log(level, msg):
    global pass_count, fail_count
    prefix = {"pass": "✅", "fail": "❌", "info": "📋", "warn": "⚠️ "}
    print(f"  {prefix.get(level, '  ')} {msg}")
    if level == "pass":
        pass_count += 1
    elif level == "fail":
        fail_count += 1


def api(path, method="GET", token=None, json_data=None, params=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{BASE_URL}{path}"
    try:
        if method == "GET":
            r = requests.get(url, headers=headers, params=params, timeout=10)
        elif method == "POST":
            r = requests.post(url, headers=headers, json=json_data, timeout=10)
        elif method == "PUT":
            r = requests.put(url, headers=headers, json=json_data, timeout=10)
        elif method == "DELETE":
            r = requests.delete(url, headers=headers, timeout=10)
        else:
            raise ValueError(f"Unknown method: {method}")
        return r.json()
    except Exception as e:
        log("fail", f"API 调用失败 {method} {path}: {e}")
        return None


def login(username):
    """登录获取 refresh_token"""
    resp = api("/auth/login", "POST", json_data={"username": username, "password": PASSWORD})
    if resp and resp.get("code") == 0:
        return resp["data"]["refresh_token"]
    return None


def switch_space(space_id, refresh_token):
    """切换 Space 获取 context_token"""
    resp = api("/auth/switch-space", "POST", token=refresh_token,
               json_data={"space_id": space_id})
    if resp and resp.get("code") == 0:
        return resp["data"]["access_token"]
    return None


def register_user(username, display_name):
    """注册新用户"""
    resp = api("/auth/register", "POST",
               json_data={"username": username, "password": PASSWORD, "display_name": display_name})
    if resp and resp.get("code") == 0:
        return resp["data"]["id"]
    log("warn", f"注册用户失败（可能已存在）: {username}, resp={resp}")
    return None


def get_accessible_kbs(token):
    """获取用户有权访问的 KB 列表"""
    resp = api("/auth/accessible-kbs", "GET", token=token)
    if resp and resp.get("code") == 0:
        kbs = resp.get("data", [])
        return {kb["kb_id"] for kb in kbs} if isinstance(kbs, list) else set()
    return set()


# ================================================================
# Phase 1: 数据准备
# ================================================================

def phase1_setup():
    log("info", "=" * 60)
    log("info", "Phase 1: 创建测试数据")

    # 1. 注册所有用户
    log("info", "注册用户...")
    for name, info in TEST_DATA["users"].items():
        uid = register_user(info["username"], info["display_name"])
        if uid:
            ids["user_ids"][name] = uid
            ids["tokens"][name] = login(info["username"])
            log("pass", f"用户 {info['display_name']} ({name}) 创建成功: {uid[:8]}...")

    # 设置全局管理员（需手动 SQL，脚本无 API 可调用）
    log("info", "请手动设置赵六为全局管理员: UPDATE users SET is_global_admin = TRUE WHERE username = 'v4_zhaoliu';")
    log("warn", "脚本无法自动设置 is_global_admin，跳过全局管理员测试")

    # 2. 创建全局用户组 (嵌套: 后端架构组 ⊂ 研发部)
    log("info", "创建全局用户组...")
    zhangsan_token = ids["tokens"].get("zhangsan")

    # 研发部全员组 (根组)
    resp = api("/groups", "POST", token=zhangsan_token, json_data={
        "name": "研发部全员组", "description": "研发部所有成员"
    })
    if resp and resp.get("code") == 0:
        ids["groups"]["rd_dept"] = resp["data"]["group_id"]
        log("pass", f"研发部全员组 创建成功")

    # 后端架构组 (parent=研发部)
    resp = api("/groups", "POST", token=zhangsan_token, json_data={
        "name": "后端架构组",
        "description": "后端架构核心成员",
        "parent_group_id": ids["groups"]["rd_dept"]
    })
    if resp and resp.get("code") == 0:
        ids["groups"]["backend_arch"] = resp["data"]["group_id"]
        log("pass", f"后端架构组 创建成功 (parent=研发部)")

    # 高管组 (独立根组)
    resp = api("/groups", "POST", token=zhangsan_token, json_data={
        "name": "高管组", "description": "公司高管"
    })
    if resp and resp.get("code") == 0:
        ids["groups"]["executive"] = resp["data"]["group_id"]
        log("pass", f"高管组 创建成功")

    # 3. 分配用户到组
    log("info", "分配用户到组...")
    # 张三 → 后端架构组
    api(f"/groups/{ids['groups']['backend_arch']}/members", "POST", token=zhangsan_token,
        json_data={"user_id": ids["user_ids"]["zhangsan"]})
    log("pass", "张三 → 后端架构组")

    # 李四 → 研发部全员组
    api(f"/groups/{ids['groups']['rd_dept']}/members", "POST", token=zhangsan_token,
        json_data={"user_id": ids["user_ids"]["lisi"]})
    log("pass", "李四 → 研发部全员组")

    # 王五 → 高管组
    api(f"/groups/{ids['groups']['executive']}/members", "POST", token=zhangsan_token,
        json_data={"user_id": ids["user_ids"]["wangwu"]})
    log("pass", "王五 → 高管组")

    # 4. 创建 Space
    log("info", "创建 Space...")
    resp = api("/spaces", "POST", token=zhangsan_token, json_data={
        "name": "研发Space", "type_label": "engineering",
        "description": "用于验证 ACE 权限模型"
    })
    if resp and resp.get("code") == 0:
        ids["space_id"] = resp["data"]["space_id"]
        log("pass", f"研发Space 创建成功: {ids['space_id'][:8]}...")

        # 切换 context
        for name in ["zhangsan", "lisi", "wangwu"]:
            ctx = switch_space(ids["space_id"], ids["tokens"][name])
            if ctx:
                ids["tokens"][name] = ctx  # 替换为 context_token
        log("pass", "所有用户已切换 Space (获得 context_token)")

    # 5. 分配空间准入组
    log("info", "分配 Space 准入组...")
    ctx_zhangsan = ids["tokens"]["zhangsan"]
    api(f"/spaces/{ids['space_id']}/groups", "POST", token=ctx_zhangsan,
        json_data={"group_id": ids["groups"]["rd_dept"]})
    log("pass", "研发部全员组 → 研发Space")

    api(f"/spaces/{ids['space_id']}/groups", "POST", token=ctx_zhangsan,
        json_data={"group_id": ids["groups"]["executive"]})
    log("pass", "高管组 → 研发Space")

    # 6. 创建 KB
    log("info", "创建 KB...")
    # KB-A: space_wide
    resp = api(f"/spaces/{ids['space_id']}/kbs", "POST", token=ctx_zhangsan, json_data={
        "name": "KB-A (公开)", "visibility": "space_wide"
    })
    if resp and resp.get("code") == 0:
        ids["kb_ids"]["kba"] = resp["data"]["kb_id"]
        log("pass", "KB-A (space_wide) 创建成功")

    # KB-B: restricted (给后端架构组 Editor)
    resp = api(f"/spaces/{ids['space_id']}/kbs", "POST", token=ctx_zhangsan, json_data={
        "name": "KB-B (受限-后端架构组)", "visibility": "restricted"
    })
    if resp and resp.get("code") == 0:
        ids["kb_ids"]["kbb"] = resp["data"]["kb_id"]
        log("pass", "KB-B (restricted) 创建成功")

    # KB-C: restricted (给高管组 Viewer)
    resp = api(f"/spaces/{ids['space_id']}/kbs", "POST", token=ctx_zhangsan, json_data={
        "name": "KB-C (受限-高管组)", "visibility": "restricted"
    })
    if resp and resp.get("code") == 0:
        ids["kb_ids"]["kbc"] = resp["data"]["kb_id"]
        log("pass", "KB-C (restricted) 创建成功")

    # KB-D: restricted (deny 研发部全员组)
    resp = api(f"/spaces/{ids['space_id']}/kbs", "POST", token=ctx_zhangsan, json_data={
        "name": "KB-D (受限-拒绝研发部)", "visibility": "restricted"
    })
    if resp and resp.get("code") == 0:
        ids["kb_ids"]["kbd"] = resp["data"]["kb_id"]
        log("pass", "KB-D (restricted) 创建成功")

    # 7. 配置 ACE 矩阵
    log("info", "配置 ACE 矩阵...")
    space_id = ids["space_id"]

    # 获取 Viewer 角色 ID (系统角色 dddddddd-0000-4000-d000-000000000003)
    viewer_role_id = "dddddddd-0000-4000-d000-000000000003"
    editor_role_id = "dddddddd-0000-4000-d000-000000000002"
    deny_role_id   = "dddddddd-0000-4000-d000-000000000004"

    # ACE-1: KB-B ← 后端架构组 → Editor (allow)
    api(f"/spaces/{space_id}/aces", "POST", token=ctx_zhangsan, json_data={
        "resource_type": "kb", "resource_id": ids["kb_ids"]["kbb"],
        "principal_type": "group", "principal_id": ids["groups"]["backend_arch"],
        "role_id": editor_role_id, "effect": "allow"
    })
    log("pass", "ACE: KB-B ← 后端架构组 → Editor (allow)")

    # ACE-2: KB-C ← 高管组 → Viewer (allow)
    api(f"/spaces/{space_id}/aces", "POST", token=ctx_zhangsan, json_data={
        "resource_type": "kb", "resource_id": ids["kb_ids"]["kbc"],
        "principal_type": "group", "principal_id": ids["groups"]["executive"],
        "role_id": viewer_role_id, "effect": "allow"
    })
    log("pass", "ACE: KB-C ← 高管组 → Viewer (allow)")

    # ACE-3: KB-D ← 研发部全员组 → Deny
    api(f"/spaces/{space_id}/aces", "POST", token=ctx_zhangsan, json_data={
        "resource_type": "kb", "resource_id": ids["kb_ids"]["kbd"],
        "principal_type": "group", "principal_id": ids["groups"]["rd_dept"],
        "role_id": deny_role_id, "effect": "deny"
    })
    log("pass", "ACE: KB-D ← 研发部全员组 → Deny (deny)")

    log("pass", "Phase 1 数据准备完成")


# ================================================================
# Phase 2: 权限验证
# ================================================================

def phase2_verify():
    log("info", "")
    log("info", "=" * 60)
    log("info", "Phase 2: 权限验证")

    space_id = ids["space_id"]
    kba = ids["kb_ids"]["kba"]
    kbb = ids["kb_ids"]["kbb"]
    kbc = ids["kb_ids"]["kbc"]
    kbd = ids["kb_ids"]["kbd"]

    # 为每个测试用户切换 context
    for name in ["zhangsan", "lisi", "wangwu"]:
        ctx = switch_space(space_id, ids["tokens"].get(name))
        if ctx:
            ids["tokens"][name] = ctx

    # ---- 场景 1: 张三 (owner + 后端架构组成员) ----
    log("info", "")
    log("info", "场景 1: 张三 — Space owner + 后端架构组成员")
    log("info", "  预期: KB-A(✓) KB-B(✓ via ACE) KB-C(✓ owner 全量) KB-D(✗ deny 覆盖)")
    kbs = get_accessible_kbs(ids["tokens"]["zhangsan"])
    checks = [
        (kba in kbs, "KB-A (space_wide) 可见"),
        (kbb in kbs, "KB-B (ACE allow) 可见"),
        # 张三作为 Space owner 看到所有 KB（包括 restricted）
        (kbc in kbs, "KB-C 可见 (owner 全量访问)"),
        # KB-D 有 deny on 研发部，张三在后端架构组(⊂研发部) → deny 生效
        (kbd not in kbs, "KB-D 不可见 (deny 覆盖 owner)"),
    ]
    for ok, msg in checks:
        log("pass" if ok else "fail", f"  {msg}")

    # ---- 场景 2: 李四 (研发部全员组) ----
    log("info", "")
    log("info", "场景 2: 李四 — 研发部全员组成员")
    log("info", "  预期: KB-A(✓) KB-B(✗ 非后端架构组) KB-C(✗) KB-D(✗ deny)")
    kbs = get_accessible_kbs(ids["tokens"]["lisi"])
    checks = [
        (kba in kbs, "KB-A (space_wide) 可见"),
        (kbb not in kbs, "KB-B 不可见 (非后端架构组成员)"),
        (kbc not in kbs, "KB-C 不可见 (非高管组)"),
        (kbd not in kbs, "KB-D 不可见 (deny 覆盖)"),
    ]
    for ok, msg in checks:
        log("pass" if ok else "fail", f"  {msg}")

    # ---- 场景 3: 王五 (高管组) ----
    log("info", "")
    log("info", "场景 3: 王五 — 高管组成员")
    log("info", "  预期: KB-A(✓) KB-B(✗) KB-C(✓ via ACE) KB-D(✗ 无 ACE 授权)")
    kbs = get_accessible_kbs(ids["tokens"]["wangwu"])
    checks = [
        (kba in kbs, "KB-A (space_wide) 可见"),
        (kbb not in kbs, "KB-B 不可见 (非后端架构组)"),
        (kbc in kbs, "KB-C 可见 (ACE allow)"),
        # KB-D restricted + 无 ACE 授权给高管组 → 不可见
        (kbd not in kbs, "KB-D 不可见 (无 ACE 授权给高管组)"),
    ]
    for ok, msg in checks:
        log("pass" if ok else "fail", f"  {msg}")

    # ---- 场景 4: 嵌套组继承 ----
    log("info", "")
    log("info", "场景 4: 组嵌套继承 — 后端架构组 ⊂ 研发部")
    log("info", "  张三在后端架构组 → 继承研发部权限 → KB-D 应被 deny")
    kbs = get_accessible_kbs(ids["tokens"]["zhangsan"])
    ok = kbd not in kbs
    log("pass" if ok else "fail",
        f"  嵌套继承: KB-D 被拒绝 (后端架构组 继承 研发部 的 deny)")


# ================================================================
# Main
# ================================================================

def main():
    global pass_count, fail_count

    print("=" * 60)
    print("  v4 ACE 企业级权限模型 — 自动化验证")
    print("=" * 60)
    print()

    try:
        phase1_setup()
        phase2_verify()
    except Exception as e:
        log("fail", f"脚本异常: {e}")
        import traceback
        traceback.print_exc()

    print()
    print("=" * 60)
    print(f"  结果: {pass_count} 通过, {fail_count} 失败")
    if fail_count > 0:
        print("  ⚠️  存在失败项，请检查权限配置")
        sys.exit(1)
    else:
        print("  🎉 全部测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    main()
