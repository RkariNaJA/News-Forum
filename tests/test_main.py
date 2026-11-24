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


class FakeNotifier:
    started = []

    def start(self):
        FakeNotifier.started.append(1)


def test_second_launch_exits_without_starting_server(monkeypatch):
    started, opened = [], []
    FakeNotifier.started = []
    monkeypatch.setattr(entry, "already_running", lambda h, p: True)
    monkeypatch.setattr(entry.uvicorn, "run", lambda *a, **k: started.append(1))
    monkeypatch.setattr(entry.webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr(entry, "PriceNotifier", FakeNotifier)
    entry.main(["--no-browser"])
    assert started == [] and opened == [] and FakeNotifier.started == []
    entry.main([])  # a manual launch just opens the running page
    assert started == [] and opened == ["http://127.0.0.1:8770/"] and FakeNotifier.started == []


def test_notifier_starts_with_the_server(monkeypatch):
    started = []
    FakeNotifier.started = []
    monkeypatch.setattr(entry, "already_running", lambda h, p: False)
    monkeypatch.setattr(entry, "create_app", lambda *a: "app")
    monkeypatch.setattr(entry.uvicorn, "run", lambda app, **k: started.append(app))
    monkeypatch.setattr(entry, "PriceNotifier", FakeNotifier)
    entry.main(["--no-browser"])
    assert started == ["app"] and FakeNotifier.started == [1]


def test_send_prices_flag_sends_once_and_exits(monkeypatch, capsys):
    started, sent = [], []
    FakeNotifier.started = []
    monkeypatch.setattr(entry, "already_running", lambda h, p: True)   # works while the app runs
    monkeypatch.setattr(entry.uvicorn, "run", lambda *a, **k: started.append(1))
    monkeypatch.setattr(entry, "PriceNotifier", FakeNotifier)
    monkeypatch.setattr(entry, "send_prices", lambda: sent.append(1) or "Sent")
    entry.main(["--send-prices"])
    assert sent == [1] and started == [] and FakeNotifier.started == []
    assert "Telegram prices: Sent" in capsys.readouterr().out


def test_windowless_output_goes_to_log_file(monkeypatch, tmp_path):
    log = tmp_path / "news-forum.log"
    monkeypatch.setattr(entry, "LOG_PATH", log)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    entry.use_log_file_if_windowless()
    print("hello log")
    sys.stdout.close()
    assert log.read_text(encoding="utf-8") == "hello log\n"
