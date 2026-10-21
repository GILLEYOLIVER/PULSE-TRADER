"""Background work with callbacks exclusively on the Tk/main thread."""
from __future__ import annotations

from queue import Queue, Empty
from threading import Thread


class BackgroundJobs:
    def __init__(self, root, on_error):
        self.root, self.on_error = root, on_error
        self.busy = False
        self.closed = False
        self.queue = Queue()
        self.timer = None

    def start(self, work, done, failed=None):
        if self.closed:
            raise ValueError('Aplicativo em encerramento')
        if self.busy:
            raise ValueError('Aguarde a tarefa em andamento antes de iniciar outra')
        self.busy = True
        def execute():
            try:
                self.queue.put((True, work()))
            except Exception as error:
                self.queue.put((False, error))
        Thread(target=execute, daemon=True, name='pulse-background').start()
        self.timer = self.root.after(50, lambda: self._poll(done,failed))

    def _poll(self, done, failed=None):
        self.timer = None
        if self.closed:
            return
        try:
            ok, value = self.queue.get_nowait()
        except Empty:
            self.timer = self.root.after(50, lambda: self._poll(done,failed))
            return
        self.busy = False
        try:
            if ok:
                done(value)
            else:
                (failed or self.on_error)(value)
        except Exception as error:
            (failed or self.on_error)(error)

    def close(self):
        self.closed = True
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
