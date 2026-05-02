from __future__ import annotations
import os
import threading
from typing import TYPE_CHECKING, Callable

from rtl.parser import VerilogPluginParser, RTLProfile

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

if TYPE_CHECKING:
    from sim.pipeline import PipelineEngine


class VerilogPluginLoader:
    def __init__(
        self,
        plugins_dir: str,
        pipeline: "PipelineEngine | None" = None,
        on_reload: Callable[[RTLProfile], None] | None = None,
    ):
        self._dir = plugins_dir
        self._pipeline = pipeline
        self._on_reload = on_reload
        self._parser = VerilogPluginParser()
        self._lock = threading.Lock()
        self._loaded: dict[str, RTLProfile] = {}
        self._observer = None

    def load_all(self) -> list[RTLProfile]:
        profiles = []
        if not os.path.isdir(self._dir):
            return profiles
        for fname in sorted(os.listdir(self._dir)):
            if fname.endswith(".v"):
                path = os.path.join(self._dir, fname)
                profile = self._load_file(path)
                if profile:
                    profiles.append(profile)
        return profiles

    def start_watching(self):
        if not WATCHDOG_AVAILABLE:
            return

        handler = _VerilogEventHandler(self._on_file_event)
        self._observer = Observer()
        self._observer.schedule(handler, self._dir, recursive=False)
        self._observer.start()

    def stop_watching(self):
        if self._observer:
            self._observer.stop()
            self._observer.join()

    def _load_file(self, path: str) -> RTLProfile | None:
        try:
            profile = self._parser.parse(path)
            with self._lock:
                self._loaded[path] = profile
            self._apply_to_pipeline(profile)
            if self._on_reload:
                self._on_reload(profile)
            return profile
        except Exception as e:
            print(f"[RTL loader] Failed to load {path}: {e}")
            return None

    def _apply_to_pipeline(self, profile: RTLProfile):
        if self._pipeline is None:
            return

        from sim.stage import RTLPluginStage
        stage = RTLPluginStage(profile)
        try:
            self._pipeline.replace_stage(profile.stage_name, stage)
        except KeyError:
            # Stage doesn't exist yet — append after last stage
            stages = self._pipeline.get_stages()
            if stages:
                try:
                    self._pipeline.insert_stage_after(stages[-1].metrics.name, stage)
                except KeyError:
                    self._pipeline.register_stage(stage)
            else:
                self._pipeline.register_stage(stage)

    def _on_file_event(self, path: str):
        if path.endswith(".v"):
            self._load_file(path)

    @property
    def loaded(self) -> dict[str, RTLProfile]:
        with self._lock:
            return dict(self._loaded)


if WATCHDOG_AVAILABLE:
    class _VerilogEventHandler(FileSystemEventHandler):
        def __init__(self, callback: Callable[[str], None]):
            self._callback = callback

        def on_created(self, event):
            if not event.is_directory:
                self._callback(event.src_path)

        def on_modified(self, event):
            if not event.is_directory:
                self._callback(event.src_path)
