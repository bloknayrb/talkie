"""Thread-safe state machine for Talkie pipeline."""

import threading
from enum import Enum, auto
from typing import Callable, Optional

from talkie_modules.logger import get_logger

logger = get_logger("state")


class AppState(Enum):
    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()
    ERROR = auto()


class StateMachine:
    """Thread-safe state machine with atomic compare-and-swap transitions."""

    # Valid transitions: from_state -> set of allowed to_states
    _TRANSITIONS: dict[AppState, set[AppState]] = {
        AppState.IDLE: {AppState.RECORDING},
        AppState.RECORDING: {AppState.PROCESSING, AppState.IDLE, AppState.ERROR},
        AppState.PROCESSING: {AppState.IDLE, AppState.ERROR},
        AppState.ERROR: {AppState.IDLE},
    }

    def __init__(self) -> None:
        self._state: AppState = AppState.IDLE
        self._lock: threading.Lock = threading.Lock()
        self._callbacks: list[Callable[[AppState], None]] = []

    @property
    def state(self) -> AppState:
        with self._lock:
            return self._state

    def transition(self, from_state: AppState, to_state: AppState) -> bool:
        """
        Atomic compare-and-swap: only transitions if current state matches from_state
        and the transition is valid. Returns True on success.
        """
        with self._lock:
            if self._state != from_state:
                logger.debug(
                    "Transition rejected: expected %s, was %s", from_state.name, self._state.name
                )
                return False

            allowed = self._TRANSITIONS.get(from_state, set())
            if to_state not in allowed:
                logger.warning(
                    "Invalid transition: %s -> %s", from_state.name, to_state.name
                )
                return False

            old = self._state
            self._state = to_state
            logger.info("State: %s -> %s", old.name, to_state.name)

        # Notify callbacks outside lock
        for cb in self._callbacks:
            try:
                cb(to_state)
            except Exception as e:
                logger.warning("State callback error: %s", e)

        return True

    def force(self, state: AppState) -> None:
        """Force state without validation — for error recovery only."""
        with self._lock:
            old = self._state
            self._state = state
            logger.warning("State forced: %s -> %s", old.name, state.name)

    def on_change(self, callback: callable) -> None:
        """Register a callback that fires on every state change."""
        self._callbacks.append(callback)
