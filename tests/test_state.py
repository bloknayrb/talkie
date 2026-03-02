"""Tests for the state machine."""

import threading

import pytest

from talkie_modules.state import AppState, StateMachine


class TestStateMachine:
    def test_initial_state_is_idle(self) -> None:
        sm = StateMachine()
        assert sm.state == AppState.IDLE

    def test_valid_transitions(self) -> None:
        sm = StateMachine()
        assert sm.transition(AppState.IDLE, AppState.RECORDING)
        assert sm.state == AppState.RECORDING

        assert sm.transition(AppState.RECORDING, AppState.PROCESSING)
        assert sm.state == AppState.PROCESSING

        assert sm.transition(AppState.PROCESSING, AppState.IDLE)
        assert sm.state == AppState.IDLE

    def test_invalid_transition_rejected(self) -> None:
        sm = StateMachine()
        # Can't go from IDLE directly to PROCESSING
        assert not sm.transition(AppState.IDLE, AppState.PROCESSING)
        assert sm.state == AppState.IDLE

    def test_cas_rejects_wrong_from_state(self) -> None:
        sm = StateMachine()
        # Current state is IDLE, but we say it's RECORDING
        assert not sm.transition(AppState.RECORDING, AppState.PROCESSING)
        assert sm.state == AppState.IDLE

    def test_double_press_rejected(self) -> None:
        sm = StateMachine()
        assert sm.transition(AppState.IDLE, AppState.RECORDING)
        # Second press should fail (already RECORDING, not IDLE)
        assert not sm.transition(AppState.IDLE, AppState.RECORDING)
        assert sm.state == AppState.RECORDING

    def test_error_transition(self) -> None:
        sm = StateMachine()
        sm.transition(AppState.IDLE, AppState.RECORDING)
        assert sm.transition(AppState.RECORDING, AppState.ERROR)
        assert sm.state == AppState.ERROR
        # Can recover from ERROR to IDLE
        assert sm.transition(AppState.ERROR, AppState.IDLE)
        assert sm.state == AppState.IDLE

    def test_force(self) -> None:
        sm = StateMachine()
        sm.transition(AppState.IDLE, AppState.RECORDING)
        sm.force(AppState.IDLE)
        assert sm.state == AppState.IDLE

    def test_callback_fires(self) -> None:
        sm = StateMachine()
        states: list[AppState] = []
        sm.on_change(lambda s: states.append(s))

        sm.transition(AppState.IDLE, AppState.RECORDING)
        assert states == [AppState.RECORDING]

    def test_thread_safety(self) -> None:
        """Concurrent transitions should not corrupt state."""
        sm = StateMachine()
        results: list[bool] = []

        def try_transition() -> None:
            result = sm.transition(AppState.IDLE, AppState.RECORDING)
            results.append(result)

        threads = [threading.Thread(target=try_transition) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Exactly one thread should succeed
        assert results.count(True) == 1
        assert sm.state == AppState.RECORDING
