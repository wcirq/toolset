#!/usr/bin/env python3
"""
构建脚本 - 生成图标 + 打包 EXE
用法: 在项目目录运行 python packaging/build.py
"""
import os
import sys
import subprocess
import shutil


def copy_resources(project_dir, output_dir):
    """复制 EXE 运行所需的模型，返回缺失资源列表。"""
    resources = [
        (os.path.join("assets", "models", "yolo26n.onnx"),
         os.path.join("assets", "models", "yolo26n.onnx")),
        (os.path.join("assets", "models", "yolo26n-pose.onnx"),
         os.path.join("assets", "models", "yolo26n-pose.onnx")),
    ]
    missing = []
    for relative_source, relative_target in resources:
        source = os.path.join(project_dir, relative_source)
        target = os.path.join(output_dir, relative_target)
        if not os.path.isfile(source):
            missing.append(relative_source)
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)
        print("已复制: %s -> %s" % (relative_source, relative_target))
    return missing


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = (os.path.dirname(script_dir)
                   if os.path.basename(script_dir) == "packaging" else script_dir)
    os.chdir(project_dir)
    python = sys.executable

    print("=" * 40)
    print("  酷炫小猫悬浮窗 - 构建脚本")
    print("=" * 40)

    # 1. 生成图标
    print("\n[1/4] 生成图标...")
    ret = subprocess.call([python, os.path.join("tools", "make_icon.py"),
                           os.path.join("assets", "cat.ico")])
    if ret != 0:
        print("图标生成失败, 将使用默认图标构建")

    # 2. 构建 EXE (onedir 模式: ONNX Runtime, 比 onefile 启动快)
    workdir = "build"  # 将 PyInstaller 中间产物固定在项目 build 目录
    print("\n[2/4] 使用 packaging/CoolCat.spec 构建 EXE, 工作目录: %s" % workdir)

    # 预清理旧 dist 输出目录; 删不掉(如 exe 正在运行占用文件)就提示用户手动删, 不强删
    out_dir = os.path.join("dist", "CoolCat")
    if os.path.exists(out_dir):
        print("预清理旧输出目录: %s" % out_dir)
        subprocess.call(["powershell", "-NoProfile", "-Command",
                         "Remove-Item -Recurse -Force -Confirm:$false '%s'"
                         % os.path.abspath(out_dir)])
        if os.path.exists(out_dir):
            print("\n[!] 无法删除旧输出目录: %s" % os.path.abspath(out_dir))
            print("    通常是 CoolCat.exe 还在运行占用了文件, 请先退出小猫,")
            print("    然后手动删除该目录后重新运行 build.py")
            sys.exit(1)

    spec_path = os.path.join("packaging", "CoolCat.spec")
    if not os.path.isfile(spec_path):
        print("构建配置不存在: %s" % os.path.abspath(spec_path))
        sys.exit(1)
    cmd = [
        python, "-m", "PyInstaller",
        "--clean",
        "-y",
        "--workpath", workdir,
        spec_path,
    ]

    ret = subprocess.call(cmd)
    if ret != 0:
        print("构建失败!")
        sys.exit(1)

    # 3. 复制 YOLO 权重到输出目录；配置由程序首次保存设置时创建
    print("\n[3/4] 复制 YOLO 权重...")
    out_dir = os.path.join("dist", "CoolCat")
    missing = copy_resources(project_dir, os.path.abspath(out_dir))
    if missing:
        print("\n构建产物不完整，缺少以下运行时资源:")
        for path in missing:
            print("  - " + path)
        sys.exit(1)

    # 4. 完成
    exe_path = os.path.join("dist", "CoolCat", "CoolCat.exe")
    print("\n[4/4] 构建完成!")
    if not os.path.isfile(exe_path):
        print("未找到预期的 EXE 文件: " + os.path.abspath(exe_path))
        sys.exit(1)
    print("EXE 文件: " + os.path.abspath(exe_path))


if __name__ == "__main__":
    main()
