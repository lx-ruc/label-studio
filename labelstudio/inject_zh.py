#!/usr/bin/env python3
"""把 ls-zh.user.js 注入到 Label Studio 的 Django 模板里（本地用）。

本地没有 nginx，做不到 sub_filter 注入，所以直接内联进模板。
服务器那边走 nginx 注入，不需要跑这个脚本。

用法：
    python3 labelstudio/inject_zh.py            # 注入（幂等：先还原备份再注入）
    python3 labelstudio/inject_zh.py --restore  # 还原成原始模板

注意：
  1. 改完模板必须重启 Label Studio，Django 的 cached template loader 不会热加载。
  2. 升级 label-studio 后模板会被覆盖，重新跑一次本脚本即可。
"""
import argparse
import shutil
import sys
from pathlib import Path

# 模板继承关系（踩过坑，别改错）：
#   项目页 / 标注页  -> templates/base.html
#   登录页 / 注册页  -> templates/simple.html
#      （user_base.html 只是 {% extends 'simple.html' %} 的片段，自身没有 </body>）
REL_TARGETS = [
    "templates/base.html",
    "templates/simple.html",
]

MARKER = "ls-zh.user.js 内联版"


def find_label_studio_root() -> Path:
    """定位当前 Python 环境里的 label_studio 包目录。"""
    try:
        import label_studio  # noqa: F401
    except ImportError:
        print("当前环境没装 label-studio。请用装了它的那个 python 运行本脚本：")
        print("  ~/.workbuddy/binaries/python/envs/labelstudio/bin/python labelstudio/inject_zh.py")
        sys.exit(1)
    return Path(label_studio.__file__).parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--restore", action="store_true", help="还原成注入前的原始模板")
    ap.add_argument("--root", help="手动指定 label_studio 包目录")
    args = ap.parse_args()

    root = Path(args.root) if args.root else find_label_studio_root()
    src = Path(__file__).with_name("ls-zh.user.js")
    if not src.exists():
        print("找不到 ls-zh.user.js:", src)
        sys.exit(1)

    print("label_studio 目录:", root)
    print("脚本:", src, f"({src.stat().st_size} 字节)\n")

    for rel in REL_TARGETS:
        tpl = root / rel
        bak = tpl.with_suffix(tpl.suffix + ".bak_before_zh")

        if args.restore:
            if bak.exists():
                shutil.copy2(bak, tpl)
                print(f"[还原] {rel}")
            else:
                print(f"[跳过] {rel}（没有备份）")
            continue

        if not tpl.exists():
            print(f"[跳过] {rel}（不存在）")
            continue

        # 幂等：先从备份还原，再注入最新版
        if bak.exists():
            shutil.copy2(bak, tpl)
        else:
            shutil.copy2(tpl, bak)

        js = src.read_text(encoding="utf-8")
        if "</script" in js.lower():
            print("[错误] 脚本里含 </script，内联会破坏 HTML —— 已中止")
            sys.exit(1)

        html = tpl.read_text(encoding="utf-8")
        idx = html.rfind("</body>")
        if idx == -1:
            print(f"[跳过] {rel}（没有 </body>）")
            continue

        block = f"\n<!-- 中文界面（{MARKER}） -->\n<script>\n{js}\n</script>\n"
        tpl.write_text(html[:idx] + block + html[idx:], encoding="utf-8")
        print(f"[注入] {rel}  （备份 {bak.name}）")

    if not args.restore:
        print("\n注入完成 —— 记得重启 Label Studio，否则模板缓存不会刷新。")


if __name__ == "__main__":
    main()
