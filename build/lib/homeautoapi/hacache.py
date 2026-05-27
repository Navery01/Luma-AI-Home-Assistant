import asyncio


class HACache:
    def __init__(self):
        self.devices = {}
        self.entities = {}
        self.areas = {}
        self.states = {}
        self._ready = asyncio.Event()