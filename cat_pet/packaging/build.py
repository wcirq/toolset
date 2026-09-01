#!/usr/bin/env python3
"""
构建脚本 - 生成图标 + 打包 EXE
用法: 在项目目录运行 python packaging/build.py
"""
import os
import sys
import subprocess

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
    print("\n[1/3] 生成图标...")
    ret = subprocess.call([python, os.path.join("tools", "make_icon.py"),
                           os.path.join("assets", "cat.ico")])
    if ret != 0:
        print("图标生成失败, 将使用默认图标构建")

    # 2. 构建 EXE (onedir 模式: ONNX Runtime, 比 onefile 启动快)
    workdir = "build"  # 固定工作目录 (二次构建可复用缓存, 加快速度)
    print("\n[2/4] 构建 EXE (onedir, ONNX YOLO), 工作目录: %s" % workdir)

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

    cmd = [
        python, "-m", "PyInstaller",
        "--noconsole",
        "-y",
        "--workpath", workdir,  # 每次全新工作目录, 避免删除旧文件被沙箱拦截
        "--name", "CoolCat",
    ]
    icon_path = os.path.join("assets", "cat.ico")
    if os.path.exists(icon_path):
        cmd += ["--icon", icon_path]
    cmd.append("main.py")

    ret = subprocess.call(cmd)
    if ret != 0:
        print("构建失败!")
        sys.exit(1)

    # 3. 复制 YOLO 权重和默认配置到输出目录
    print("\n[3/4] 复制 YOLO 权重和配置...")
    import shutil
    out_dir = os.path.join("dist", "CoolCat")
    resources = [
        (os.path.join("assets", "models", "yolo26n.onnx"),
         os.path.join("assets", "models", "yolo26n.onnx")),
        (os.path.join("assets", "models", "yolo26n-pose.onnx"),
         os.path.join("assets", "models", "yolo26n-pose.onnx")),
        (os.path.join("config", "config.json"), "config.json"),
    ]
    for source, target in resources:
        if os.path.exists(source):
            target_path = os.path.join(out_dir, target)
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            shutil.copy2(source, target_path)
            print(f"已复制: {source}")

    # 4. 完成
    exe_path = os.path.join("dist", "CoolCat", "CoolCat.exe")
    print("\n[4/4] 构建完成!")
    if os.path.exists(exe_path):
        print("EXE 文件: " + os.path.abspath(exe_path))


if __name__ == "__main__":
    main()
