"""GUI 冒烟测试：创建主窗口、渲染控件，然后自动关闭。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    from yunx.ui.main_window import MainWindow

    app = MainWindow()
    app.update_idletasks()
    app.update()

    # 模拟一次链接识别
    app.link_var.set("https://pan.quark.cn/s/abc123def 提取码: 1234")
    app._on_link_changed()
    assert app.platform_label.cget("text") == "夸克网盘", app.platform_label.cget("text")

    # 用一个假文件渲染列表
    from yunx.models import PanFile

    app.files = [
        PanFile(fid="1", name="电影", is_dir=True),
        PanFile(fid="2", name="demo.mkv", size=1234567890),
    ]
    app._render_files()
    rows = app.tree.get_children()
    assert len(rows) == 2, rows

    # 校验下载卡片能正常创建并刷新
    from yunx.downloader import Download
    from yunx.models import DownloadLink

    link = DownloadLink(url="http://127.0.0.1:1/x.bin", filename="x.bin", size=100)
    task = Download("t-gui", link, os.path.expanduser("~"), threads=4)
    app._enqueue(link, os.path.expanduser("~"), 4, None) if False else None
    from yunx.ui.widgets import TaskCard

    card = TaskCard(
        app.dl_scroll.body,
        task,
        on_pause=lambda t: None,
        on_resume=lambda t: None,
        on_cancel=lambda t: None,
        on_remove=lambda t: None,
    )
    card.pack(fill="x")
    app.tasks[task.id] = task
    app.cards[task.id] = card
    app._tick_forced = True
    card.refresh()
    app.update_idletasks()

    app._on_close()
    print("GUI SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
