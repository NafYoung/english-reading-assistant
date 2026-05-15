from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile


APP_NAME = "英语阅读助手.app"
BACKGROUND_LAUNCHER_NAME = "run_background.command"
ICON_SOURCE_RELATIVE_PATH = Path("assets/app-icon.png")
ICON_BUNDLE_NAME = "applet.icns"
ICONSET_SIZES = (
    (16, "icon_16x16.png"),
    (32, "icon_16x16@2x.png"),
    (32, "icon_32x32.png"),
    (64, "icon_32x32@2x.png"),
    (128, "icon_128x128.png"),
    (256, "icon_128x128@2x.png"),
    (256, "icon_256x256.png"),
    (512, "icon_256x256@2x.png"),
    (512, "icon_512x512.png"),
    (1024, "icon_512x512@2x.png"),
)


class DesktopLauncherError(Exception):
    """Raised when the macOS desktop launcher cannot be created."""


def build_launcher_applescript(launcher_path: Path) -> str:
    escaped_path = str(launcher_path).replace("\\", "\\\\").replace('"', '\\"')
    return (
        "on run\n"
        f'    set launcherPath to "{escaped_path}"\n'
        "    do shell script quoted form of launcherPath\n"
        "end run\n"
    )


def _run_command(command: list[str], error_prefix: str) -> None:
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        error_message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise DesktopLauncherError(f"{error_prefix}：{error_message}") from exc


def find_icon_source(project_dir: Path) -> Path | None:
    icon_path = project_dir / ICON_SOURCE_RELATIVE_PATH
    return icon_path if icon_path.is_file() else None


def create_app_icon(icon_png_path: Path, target_icns_path: Path) -> None:
    sips_path = shutil.which("sips")
    iconutil_path = shutil.which("iconutil")
    if sips_path is None or iconutil_path is None:
        raise DesktopLauncherError("未找到 sips 或 iconutil，无法生成桌面图标。")

    with tempfile.TemporaryDirectory() as temp_dir:
        iconset_dir = Path(temp_dir) / "AppIcon.iconset"
        iconset_dir.mkdir()
        for size, file_name in ICONSET_SIZES:
            _run_command(
                [
                    sips_path,
                    "-z",
                    str(size),
                    str(size),
                    str(icon_png_path),
                    "--out",
                    str(iconset_dir / file_name),
                ],
                "生成图标尺寸失败",
            )

        _run_command(
            [
                iconutil_path,
                "-c",
                "icns",
                str(iconset_dir),
                "-o",
                str(target_icns_path),
            ],
            "生成 icns 图标失败",
        )


def install_custom_icon(app_bundle_path: Path, icon_png_path: Path) -> None:
    resources_dir = app_bundle_path / "Contents" / "Resources"
    resources_dir.mkdir(parents=True, exist_ok=True)
    create_app_icon(icon_png_path, resources_dir / ICON_BUNDLE_NAME)

    codesign_path = shutil.which("codesign")
    if codesign_path is not None:
        _run_command(
            [
                codesign_path,
                "--force",
                "--deep",
                "--sign",
                "-",
                str(app_bundle_path),
            ],
            "更新应用签名失败",
        )

    touch_path = shutil.which("touch")
    if touch_path is not None:
        _run_command([touch_path, str(app_bundle_path)], "刷新应用图标缓存失败")


def install_desktop_launcher(
    project_dir: Path,
    output_path: Path | None = None,
    overwrite_existing: bool = False,
) -> Path:
    launcher_path = project_dir / BACKGROUND_LAUNCHER_NAME
    if not launcher_path.is_file():
        raise DesktopLauncherError(f"未找到项目启动脚本：{launcher_path}")

    osacompile_path = shutil.which("osacompile")
    if osacompile_path is None:
        raise DesktopLauncherError("未找到 osacompile，无法创建 macOS 桌面启动器。")

    target_path = output_path or (Path.home() / "Desktop" / APP_NAME)
    if target_path.exists():
        if not overwrite_existing:
            raise DesktopLauncherError(f"桌面启动器已存在：{target_path}")
        if target_path.is_dir() and not target_path.is_symlink():
            shutil.rmtree(target_path)
        else:
            target_path.unlink()

    target_path.parent.mkdir(parents=True, exist_ok=True)
    script_content = build_launcher_applescript(launcher_path.resolve())

    temp_script_path: Path | None = None
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".applescript",
        encoding="utf-8",
        delete=False,
    ) as handle:
        handle.write(script_content)
        temp_script_path = Path(handle.name)

    try:
        _run_command(
            [osacompile_path, "-o", str(target_path), str(temp_script_path)],
            "生成桌面启动器失败",
        )
    finally:
        if temp_script_path is not None and temp_script_path.exists():
            temp_script_path.unlink()

    icon_source = find_icon_source(project_dir)
    if icon_source is not None:
        install_custom_icon(target_path, icon_source)

    return target_path
