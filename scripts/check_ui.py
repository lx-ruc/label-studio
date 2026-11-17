#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证「人打开浏览器能不能正常用」——登录、打开标注页、页面渲染。

这个文件不是直接 `python` 跑的，要通过 Label Studio 自带的 Django shell 执行：

    echo "exec(open('scripts/check_ui.py').read())" | \\
      label-studio shell --database <项目根>/.tmp/lsdata/ls.sqlite3

为什么不在 e2e_test.py 里用 requests 做：
  Label Studio 的登录必须走 Django 表单 + CSRF cookie，
  从外部用 requests 模拟会撞到 CSRF/Host 检查，拿到 403 或 404，
  那是脚本的问题不是服务的问题。在服务端内部用 test client 才测得准。

注意：必须在启动服务时所用的那个数据库上跑，否则查到的项目/任务对不上。
"""

from django.test import Client  # noqa: E402

EMAIL = "annotator@example.com"
PASSWORD = "ich2026"
PROJECT = 2

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  [{'OK' if ok else 'FAIL'}]  {name}" + (f"  {detail}" if detail else ""))


print("=" * 66)
print("UI 层验证（Django test client，服务端内部模拟浏览器）")
print("=" * 66)

c = Client(enforce_csrf_checks=True)

# 先 GET 登录页拿 csrftoken —— 少了这一步 POST 必被 CSRF 拒（403）
r = c.get("/user/login/")
check("登录页可打开", r.status_code == 200, f"HTTP {r.status_code}")

csrf = c.cookies["csrftoken"].value
r = c.post("/user/login/", {
    "email": EMAIL,
    "password": PASSWORD,
    "csrfmiddlewaretoken": csrf,
})
check("表单登录成功", r.status_code == 302,
      f"HTTP {r.status_code} -> {dict(r.items()).get('Location', '')}")

if r.status_code != 302:
    print("\n登录失败，后续跳过")
    print(r.content.decode("utf-8", "ignore")[:400])
else:
    print()
    for label, path in [
        ("首页", "/"),
        ("项目列表页", "/projects/"),
        ("数据管理页", f"/projects/{PROJECT}/data"),
        ("标注页", f"/projects/{PROJECT}/data?tab=1"),
        ("当前用户 API", "/api/current-user/whoami"),
    ]:
        rr = c.get(path)
        check(f"{label}可打开", rr.status_code == 200,
              f"HTTP {rr.status_code}  {path}")

    rr = c.get("/api/current-user/whoami")
    if rr.status_code == 200:
        check("会话身份正确", rr.json().get("email") == EMAIL, rr.json().get("email"))

print("\n" + "=" * 66)
ok_n = sum(1 for x in results if x)
print(f"通过 {ok_n}/{len(results)}")
print("浏览器层面可用 —— 用 README 里的账号登录即可开始标注。"
      if ok_n == len(results) else "有失败项，见上面的 [FAIL]。")
