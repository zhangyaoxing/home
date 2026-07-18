"""Tests for SceneCountdownScreen countdown and cancel/apply semantics.

Uses asyncio.run() directly rather than async test functions to avoid
requiring pytest-asyncio as a dev dependency.
"""

from __future__ import annotations

import asyncio

from textual.app import App
from textual.widgets import Static

from home_control_panel.lights import SceneCountdownScreen


class _HarnessApp(App):
    """Minimal app that mounts the screen under test."""

    def __init__(self, screen: SceneCountdownScreen):
        super().__init__()
        self._screen = screen

    def on_mount(self) -> None:
        self.push_screen(self._screen)


def _make_screen(delay: int = 5, name: str = "Cinema") -> SceneCountdownScreen:
    return SceneCountdownScreen(name, delay)


def test_initial_display_sets_widget_and_remaining():
    """On mount the time widget exists and remaining matches the delay."""

    async def scenario():
        app = _HarnessApp(_make_screen(delay=30))
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, SceneCountdownScreen)
            assert screen._remaining == 30
            # Time widget exists with correct ID
            time_widget = app.screen.query_one("#sc-time", Static)
            assert time_widget is not None
            app.exit()

    asyncio.run(scenario())


def test_escape_cancels():
    """Pressing Esc dismisses the modal screen (cancel path)."""

    async def scenario():
        app = _HarnessApp(_make_screen(delay=10))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            # After Esc, the modal is gone — active screen is the default
            assert not isinstance(app.screen, SceneCountdownScreen)
            app.exit()

    asyncio.run(scenario())


def test_finish_with_apply_calls_dismiss_true():
    """When _finish(apply=True) is called, dismiss receives True."""

    captured: list = []
    screen = _make_screen(delay=1, name="Evening")

    # Intercept dismiss to capture the result
    def capture_dismiss(result=None):
        captured.append(result)
        return None

    screen.dismiss = capture_dismiss  # type: ignore[method-assign]

    async def scenario():
        app = _HarnessApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            screen._finish(apply=True)
            await pilot.pause()
            app.exit()

    asyncio.run(scenario())
    assert captured == [True], f"expected [True], got {captured}"


def test_finish_with_cancel_calls_dismiss_false():
    """When _finish(apply=False) is called, dismiss receives False."""

    captured: list = []
    screen = _make_screen(delay=1, name="Evening")

    def capture_dismiss(result=None):
        captured.append(result)
        return None

    screen.dismiss = capture_dismiss  # type: ignore[method-assign]

    async def scenario():
        app = _HarnessApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            screen._finish(apply=False)
            await pilot.pause()
            app.exit()

    asyncio.run(scenario())
    assert captured == [False], f"expected [False], got {captured}"


def test_finish_is_idempotent():
    """Calling _finish twice does not call dismiss twice."""

    captured: list = []
    screen = _make_screen(delay=1)

    def capture_dismiss(result=None):
        captured.append(result)
        return None

    screen.dismiss = capture_dismiss  # type: ignore[method-assign]

    async def scenario():
        app = _HarnessApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            screen._finish(apply=True)
            screen._finish(apply=False)  # should be ignored
            screen._finish(apply=True)   # should be ignored
            await pilot.pause()
            app.exit()

    asyncio.run(scenario())
    assert captured == [True], f"expected single [True], got {captured}"


def test_tick_decrements_remaining():
    """Each _tick decrements _remaining by 1 without firing _finish early."""

    screen = _make_screen(delay=5)

    async def scenario():
        app = _HarnessApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert screen._remaining == 5
            screen._tick()
            assert screen._remaining == 4
            screen._tick()
            assert screen._remaining == 3
            app.exit()

    asyncio.run(scenario())


def test_tick_at_zero_triggers_apply():
    """When _tick drives remaining to 0, dismiss(True) fires."""

    captured: list = []
    screen = _make_screen(delay=2)

    def capture_dismiss(result=None):
        captured.append(result)
        return None

    screen.dismiss = capture_dismiss  # type: ignore[method-assign]

    async def scenario():
        app = _HarnessApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            screen._tick()  # 2 -> 1
            assert captured == []
            screen._tick()  # 1 -> 0, fires _finish(True)
            await pilot.pause()
            app.exit()

    asyncio.run(scenario())
    assert captured == [True], f"expected [True] after countdown, got {captured}"


def test_blink_toggles_color():
    """Each _blink_toggle flips _blink_on and redraws."""

    screen = _make_screen(delay=5)

    async def scenario():
        app = _HarnessApp(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert screen._blink_on is True
            screen._blink_toggle()
            assert screen._blink_on is False
            screen._blink_toggle()
            assert screen._blink_on is True
            app.exit()

    asyncio.run(scenario())
