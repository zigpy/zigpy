import asyncio
from typing import Callable, Generic, TypeVar

K = TypeVar('K')
V = TypeVar('V')
class MessageConcentrator(Generic[K, V]):
    def __init__(self, callback_s: float = 0.10, refract_s: float = 3) -> None:
        # callback_s is set to 0.10 as per A.3.6.3.1 gppTunnelingDelay
        # refract_s is a more practical hold on incoming broadcast packets
        super().__init__()
        self._callback_s = callback_s
        self._refract_s = refract_s
        self._message_lists: dict[K, tuple[asyncio.Task, list[V]]] = {}
        self._refract_protect: set[K] = set()
    
    def push(self, key: K, value: V, callback: Callable[[K,list[V]], None], reset_timer: bool = False) -> bool:
        if key in self._refract_protect:
            return False

        if not key in self._message_lists:
            self._message_lists[key] = (
                asyncio.create_task(self._callback_trampoline(key, callback)), 
                [value]
            )
        else:
            task, values = self._message_lists[key]
            values.append(value)
            if reset_timer:
                task.cancel()
                self._message_lists[key] = (
                    asyncio.create_task(self._callback_trampoline(key, callback)), 
                    values
                )

        return True

    async def _callback_trampoline(self, key: K, callback: Callable[[K,list[V]], None]):
        await asyncio.sleep(self._callback_s)
        task, values = self._message_lists.pop(key)
        try:
            callback(key, values)
            # no matter what honor refract
        finally:
            if self._refract_s > 0:
                self._refract_protect.add(key)
                await asyncio.sleep(self._refract_s)
                self._refract_protect.remove(key)
