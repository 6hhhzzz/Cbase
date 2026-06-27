#!/usr/bin/env python3
"""
v3 权限体系自动化验证脚本
========================
通过 HTTP API 验证 Space/KB RBAC 权限体系是否正常工作。

前提条件:
  1. 所有服务已启动 (./start.sh)
  2. Java 后端运行在 localhost:8080

测试场景:
  - admin_test: Space admin → 可访问全部 3 个 KB
  - member_test: Space member → 仅可访问 space_wide KB (不能访问 restricted)
  - finance_test: Space member + KB-B viewer → 可访问 space_wide + KB-B

用法:
  python scripts/verify_permissions_v3.py
"""

import requests
import json
import sys
import os

BASE_URL = os.environ.get("KES_BASE_URL", "http://localhost:8080/api")
PASSWORD = "Test123456"

# 测试用户定义
USERS = {
    "admin": {
        "username": "perf_admin",
        "display_name": "权限测试管理员",
        "expected_kbs": {"perf-kba", "perf-kbb"},  # 应该看到 KB-A 和 KB-B
    },
    "member": {
        "username": "perf_member",
        "display_name": "权限测试普通成员",
        "expected_kbs": {"perf-kba"},  # 只能看到 KB-A (space_wide)
    },
    "finance": {
        "username": "perf_finance",
        "display_name": "权限测试财务",
        "expected_kbs": {"perf-kba", "perf-kbb"},  # space_wide + restricted (viewer)
    },
}

# 跟踪创建的资源 ID，以便清理
created_ids = {
    "space_id": None,
    "kba_id": None,
    "kbb_id": None,
    "user_ids": {},
}

def log(level, msg):
    prefix = {"pass": "✅", "fail": "❌", "info": "📋", "warn": "⚠️ "}
    print(f"  {prefix.get(level, '  ')} {msg}")

def api(path, method="GET", token=None, json_data=None, params=None):
    """简化的 API 调用"""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{BASE_URL}{path}"
    if method == "GET":
        return requests.get(url, headers=headers, params=params, timeout=30)
    elif method == "POST":
        return requests.post(url, headers=headers, json=json_data, timeout=30)
    elif method == "DELETE":
        return requests.delete(url, headers=headers, params=params, timeout=30)
    elif method == "PUT":
        return requests.put(url, headers=headers, json=json_data, timeout=30)
    return None

def register_user(username, display_name):
    """注册用户并返回 user_id"""
    r = api("/auth/register", "POST", json_data={
        "username": username,
        "password": PASSWORD,
        "display_name": display_name,
    })
    if r.status_code == 200:
        data = r.json().get("data", {})
        return data.get("id") or data.get("user_id")
    # 如果已存在，尝试登录获取 ID
    r = api("/auth/login", "POST", json_data={"username": username, "password": PASSWORD})
    if r.status_code == 200:
        data = r.json().get("data", {})
        user = data.get("user", {})
        return user.get("id") or user.get("user_id")
    return None

def login(username):
    """登录，返回 (refresh_token, user_id)"""
    r = api("/auth/login", "POST", json_data={
        "username": username, "password": PASSWORD
    })
    if r.status_code != 200:
        log("fail", f"登录失败: {username} — {r.text}")
        return None, None
    data = r.json().get("data", {})
    token = data.get("refresh_token")
    user = data.get("user", {})
    spaces = user.get("spaces", [])
    return token, user.get("id"), spaces

def switch_space(refresh_token, space_id):
    """切换 Space，返回 context_token"""
    r = api("/auth/switch-space", "POST", token=refresh_token, json_data={
        "space_id": space_id
    })
    if r.status_code != 200:
        return None
    return r.json().get("data", {}).get("access_token")

def get_accessible_kbs(context_token):
    """获取可访问的 KB 列表"""
    r = api("/auth/accessible-kbs", "GET", token=context_token)
    if r.status_code != 200:
        return []
    return r.json().get("data", []) or []

def create_space(refresh_token, name):
    """创建 Space，返回 space_id"""
    r = api("/spaces", "POST", token=refresh_token, json_data={
        "name": name, "type_label": "test", "description": "权限验证测试空间"
    })
    if r.status_code != 200:
        return None
    return r.json().get("data", {}).get("space_id")

def create_kb(context_token, space_id, name, visibility):
    """创建 KB，返回 kb_id"""
    r = api(f"/spaces/{space_id}/kbs", "POST", token=context_token, json_data={
        "name": name, "visibility": visibility
    })
    if r.status_code != 200:
        return None
    return r.json().get("data", {}).get("kb_id")

def add_kb_member(context_token, kb_id, user_id, role):
    """添加 KB 成员"""
    r = api(f"/kbs/{kb_id}/members", "POST", token=context_token, json_data={
        "user_id": user_id, "role": role
    })
    return r.status_code == 200

def add_space_member(context_token, space_id, user_id, role):
    """添加 Space 成员"""
    r = api(f"/spaces/{space_id}/members", "POST", token=context_token, json_data={
        "user_id": user_id, "role": role
    })
    return r.status_code == 200


def main():
    print("=" * 60)
    print("v3 权限体系验证")
    print("=" * 60)
    results = []

    # ---- Phase 1: Setup ----
    print("\n[Phase 1] 准备测试环境")
    print("-" * 40)

    # 1a. 注册测试用户
    for key, u in USERS.items():
        uid = register_user(u["username"], u["display_name"])
        if uid:
            created_ids["user_ids"][key] = uid
            log("pass", f"用户就绪: {u['username']} ({uid[:8]}...)")
        else:
            log("fail", f"用户注册/登录失败: {u['username']}")
            results.append(("用户注册", key, False))
            continue

    # 1b. Admin 登录并创建 Space
    admin_refresh, admin_id, admin_spaces = login(USERS["admin"]["username"])
    if not admin_refresh:
        log("fail", "管理员登录失败，无法继续")
        sys.exit(1)

    space_id = None
    # 查找是否已有测试空间
    if admin_spaces:
        space_id = admin_spaces[0].get("space_id")
        if space_id:
            log("info", f"使用已有 Space: {space_id[:8]}...")

    if not space_id:
        space_id = create_space(admin_refresh, "权限测试空间")
        if not space_id:
            log("fail", "创建测试 Space 失败")
            sys.exit(1)
        log("pass", f"创建测试 Space: {space_id[:8]}...")
    created_ids["space_id"] = space_id

    # Admin 切换到 Space
    admin_ctx = switch_space(admin_refresh, space_id)
    if not admin_ctx:
        log("fail", "管理员切换 Space 失败")
        sys.exit(1)

    # 1c. 添加其他用户到 Space
    for key in ["member", "finance"]:
        uid = created_ids["user_ids"].get(key)
        if uid:
            if add_space_member(admin_ctx, space_id, uid, "member"):
                log("pass", f"添加 {USERS[key]['username']} 到 Space")
            else:
                log("warn", f"添加 {USERS[key]['username']} 失败（可能已存在）")

    # 1d. 创建 KB-A (space_wide) 和 KB-B (restricted)
    kb_a_id = create_kb(admin_ctx, space_id, "公开技术文档", "space_wide")
    kb_b_id = create_kb(admin_ctx, space_id, "私密财务文档", "restricted")

    if kb_a_id:
        created_ids["kba_id"] = kb_a_id
        log("pass", f"KB-A 创建 (space_wide): {kb_a_id[:8]}...")
    else:
        log("fail", "KB-A 创建失败")
        sys.exit(1)

    if kb_b_id:
        created_ids["kbb_id"] = kb_b_id
        log("pass", f"KB-B 创建 (restricted): {kb_b_id[:8]}...")
    else:
        log("fail", "KB-B 创建失败")
        sys.exit(1)

    # 1e. 将 finance 用户添加到 KB-B 为 viewer
    finance_uid = created_ids["user_ids"].get("finance")
    if finance_uid:
        if add_kb_member(admin_ctx, kb_b_id, finance_uid, "viewer"):
            log("pass", "添加 perf_finance 为 KB-B viewer")
        else:
            log("warn", "添加 KB-B 成员失败")

    # ---- Phase 2: 权限验证 ----
    print("\n[Phase 2] 权限验证")
    print("-" * 40)

    # 定义各用户的期望 KB 列表
    expected = {
        "admin": {"公开技术文档"},      # space_wide + restricted (is member)
        "member": {"公开技术文档"},      # space_wide only
        "finance": {"公开技术文档", "私密财务文档"},  # space_wide + KB-B viewer
    }

    for key, u in USERS.items():
        print(f"\n  测试: {u['username']} ({key})")
        rt, uid, spaces = login(u["username"])
        if not rt:
            results.append(("登录", key, False, "登录失败"))
            log("fail", "  登录失败")
            continue

        ctx = switch_space(rt, space_id)
        if not ctx:
            results.append(("切换Space", key, False, "切换失败"))
            log("fail", "  切换 Space 失败")
            continue

        kbs = get_accessible_kbs(ctx)
        kb_names = {kb.get("name", "") for kb in kbs}

        log("info", f"  accessible-kbs 返回: {kb_names}")

        expected_names = expected[key]
        has_all = expected_names.issubset(kb_names)
        has_extra = kb_names - expected_names

        if has_all and not has_extra:
            log("pass", f"  权限正确: 可访问 {kb_names}")
            results.append(("权限检查", key, True, str(kb_names)))
        elif has_all and has_extra:
            log("warn", f"  可访问 {kb_names}，多了 {has_extra}")
            results.append(("权限检查", key, "WARN", str(kb_names)))
        else:
            missing = expected_names - kb_names
            log("fail", f"  缺少: {missing}, 实际: {kb_names}")
            results.append(("权限检查", key, False, f"缺少{missing}"))

    # 验证: member 不应该看到 KB-B 的任何内容
    member_rt, _, _ = login(USERS["member"]["username"])
    if member_rt:
        member_ctx = switch_space(member_rt, space_id)
        if member_ctx:
            kbs = get_accessible_kbs(member_ctx)
            kb_names = {kb.get("name", "") for kb in kbs}
            has_restricted = "私密财务文档" in kb_names
            if has_restricted:
                log("fail", "  member 不应该能看到私密财务文档!")
                results.append(("隔离检查", "member", False, "看到了 restricted KB"))
            else:
                log("pass", "  隔离正确: member 看不到 restricted KB")
                results.append(("隔离检查", "member", True))

    # ---- Phase 3: 汇总报告 ----
    print("\n" + "=" * 60)
    print("[Phase 3] 测试报告")
    print("=" * 60)

    passed = sum(1 for r in results if r[2] == True)
    failed = sum(1 for r in results if r[2] == False)
    warnings = sum(1 for r in results if r[2] == "WARN")

    print(f"\n  总计: {len(results)} | 通过: {passed} | 失败: {failed} | 警告: {warnings}")

    if failed > 0:
        print("\n  失败项:")
        for r in results:
            if r[2] == False:
                print(f"    - [{r[0]}] {r[1]}: {r[3] if len(r) > 3 else '检查失败'}")

    if warnings > 0:
        print("\n  警告项:")
        for r in results:
            if r[2] == "WARN":
                print(f"    - [{r[0]}] {r[1]}: {r[3] if len(r) > 3 else ''}")

    print(f"\n  创建的资源:")
    for k, v in created_ids.items():
        if v:
            print(f"    {k}: {v}")

    print("\n" + ("=" * 60))
    if failed == 0:
        print("🎉 所有权限检查通过！v3 RBAC 工作正常。")
    else:
        print(f"⚠️  {failed} 项权限检查失败，请排查。")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
