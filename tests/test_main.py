import socket
import sys

import news.__main__ as entry


def test_already_running_detects_a_listener():
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen()
        port = srv.getsockname()[1]
        assert entry.already_running("127.0.0.1", port) is True
    assert entry.already_running("127.0.0.1", port) is False


def test_second_launch_exits_without_starting_server(monkeypatch):
    started, opened = [], []
    monkeypatch.setattr(entry, "already_running", lambda h, p: True)
    monkeypatch.setattr(entry.uvicorn, "run", lambda *a, **k: started.append(1))
    monkeypatch.setattr(entry.webbrowser, "open", lambda url: opened.append(url))
    entry.main(["--no-browser"])
    assert started == [] and opened == []
    entry.main([])  # a manual launch just opens the running page
    assert started == [] and opened == ["http://127.0.0.1:8770/"]


def test_windowless_output_goes_to_log_file(monkeypatch, tmp_path):
    log = tmp_path / "news-forum.log"
    monkeypatch.setattr(entry, "LOG_PATH", log)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    entry.use_log_file_if_windowless()
    print("hello log")
    sys.stdout.close()
    assert log.read_text(encoding="utf-8") == "hello log\n"
