"""A second session must not evict modules another session is still importing."""
from concurrent.futures import ThreadPoolExecutor
import importlib
import importlib.abc
import importlib.util
from pathlib import Path
import sys
from threading import Event
import streamlit as st
import src


def test_startup_preserves_an_import_in_progress(monkeypatch):
    entered, release = Event(), Event()
    module_name = 'src._startup_probe'

    class Loader(importlib.abc.Loader):
        def create_module(self, spec):
            return None

        def exec_module(self, module):
            entered.set()
            assert release.wait(10)
            module.ready = True

    class Finder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            if fullname == module_name:
                return importlib.util.spec_from_loader(fullname, Loader())

    finder = Finder()
    monkeypatch.setattr(st, 'set_page_config', lambda **kwargs: None)
    monkeypatch.setattr(src, '__code_signature__', 'previous-deployment', raising=False)
    app = Path(__file__).resolve().parents[1] / 'app.py'
    startup = app.read_text().split('from src import corte, ui')[0]
    sys.meta_path.insert(0, finder)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(importlib.import_module, module_name)
            try:
                assert entered.wait(10)
                in_progress = sys.modules[module_name]
                exec(compile(startup, str(app), 'exec'), {'__file__': str(app)})
                assert sys.modules.get(module_name) is in_progress
            finally:
                release.set()
            assert pending.result(timeout=10).ready
    finally:
        sys.meta_path.remove(finder)
        sys.modules.pop(module_name, None)
        if hasattr(src, '_startup_probe'):
            delattr(src, '_startup_probe')
