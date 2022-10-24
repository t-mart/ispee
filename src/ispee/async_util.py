from collections.abc import Callable, Coroutine
from typing import Any, TypeAlias

from anyio.abc import CancelScope

CancellableTask: TypeAlias = Callable[[CancelScope], Coroutine[Any, Any, Any]]
