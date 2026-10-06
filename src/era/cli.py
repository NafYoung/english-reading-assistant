from __future__ import annotations

from pathlib import Path

import typer
import uvicorn

from era.config import load_config

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Reading Coach Agent")


@app.command("setup-dict")
def setup_dict(
    zip_path: Path | None = typer.Option(
        None, "--zip", help="已下载的 ecdict-sqlite-28.zip（跳过网络）"
    ),
) -> None:
    """下载 ECDICT 并构建本地精简词典。"""
    from era.dictionary.setup import setup_dictionary

    n = setup_dictionary(source_zip=zip_path)
    typer.echo(f"完成：{n} 条")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="只监听本机"),
    port: int = typer.Option(8000),
    mock: bool = typer.Option(False, help="使用内置模拟 LLM（无需 API Key）"),
) -> None:
    """启动本地 Web 界面。"""
    import os

    if mock:
        os.environ["ERA_MOCK_LLM"] = "1"
    load_config()
    uvicorn.run("era.web.app:app", host=host, port=port, reload=False)


@app.command("import-text")
def import_text() -> None:
    """语料导入请使用网页 /import。此命令在后续版本提供。"""
    typer.echo("请打开 http://127.0.0.1:8000/import")


@app.command()
def eval(  # noqa: A001
    task: str = typer.Argument("e1", help="e1|e2|e3|e4|e5|e6"),
) -> None:
    """运行评测任务（第 4 周）。"""
    try:
        from era.evals.runners import run_eval
    except ImportError:
        typer.echo("评测运行器尚未就绪。")
        raise typer.Exit(1) from None
    path = run_eval(task)
    typer.echo(f"报告：{path}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
