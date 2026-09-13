import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from applypilot.core.exceptions import BrowserDriverError
from applypilot.browser.base import (
    ElementRect,
    InteractionPolicy,
    BrowserElement,
    BrowserPage,
    BrowserBackend,
)
from applypilot.browser.playwright_backend import (
    PlaywrightElement,
    PlaywrightPage,
    PlaywrightBackend,
)


class DummyElement:
    async def get_attribute(self, name: str):
        return "test"

    async def get_text(self):
        return "Hello"

    async def inspect_field(self):
        return {"observed_value": "Hello", "is_valid": True}

    async def is_checked(self):
        return False

    async def click(self):
        pass

    async def type_text(self, text: str):
        pass

    async def clear_text(self):
        pass

    async def select_option(self, value: str):
        pass

    async def set_files(self, file_paths: list[str]):
        pass

    async def get_bounding_rect(self):
        return ElementRect(x=0.0, y=0.0, width=10.0, height=10.0)

    async def scroll_into_view(self):
        pass


class DummyPage:
    async def url(self) -> str:
        return "https://example.com"

    async def title(self) -> str:
        return "Example"

    async def find(self, selector: str):
        return DummyElement()

    async def find_all(self, selector: str):
        return [DummyElement()]

    async def wait_for(self, selector: str, timeout_ms: int = 5000):
        return DummyElement()

    async def execute_unsafe_script(self, reason: str, script: str, arg=None):
        if not reason or not reason.strip():
            raise BrowserDriverError("reason cannot be empty")
        return 42


class DummyBackend:
    async def open_page(self, url: str):
        return DummyPage()

    async def current_page(self):
        return DummyPage()

    async def wait_for_user(self, reason: str):
        pass

    async def close(self):
        pass


def test_element_rect_model():
    rect = ElementRect(x=10.5, y=20.0, width=100.0, height=50.0)
    assert rect.x == 10.5
    assert rect.y == 20.0
    assert rect.width == 100.0
    assert rect.height == 50.0
    assert rect.model_dump() == {
        "x": 10.5,
        "y": 20.0,
        "width": 100.0,
        "height": 50.0,
    }


def test_interaction_policy_defaults():
    policy = InteractionPolicy()
    assert policy.min_action_interval_ms == 150
    assert policy.action_timeout_ms == 10000
    assert policy.max_retries == 3

    custom = InteractionPolicy(min_action_interval_ms=50, action_timeout_ms=5000, max_retries=1)
    assert custom.min_action_interval_ms == 50
    assert custom.action_timeout_ms == 5000
    assert custom.max_retries == 1


def test_protocol_adherence_with_dummy():
    dummy_elem = DummyElement()
    assert isinstance(dummy_elem, BrowserElement)

    dummy_page = DummyPage()
    assert isinstance(dummy_page, BrowserPage)

    dummy_backend = DummyBackend()
    assert isinstance(dummy_backend, BrowserBackend)


@pytest.mark.asyncio
async def test_playwright_element_implements_protocol():
    mock_locator = AsyncMock()
    elem = PlaywrightElement(mock_locator)
    assert isinstance(elem, BrowserElement)


@pytest.mark.asyncio
async def test_playwright_element_methods():
    mock_locator = AsyncMock()
    mock_locator.get_attribute.return_value = "submit-btn"
    mock_locator.inner_text.return_value = "Submit"
    mock_locator.bounding_box.return_value = {"x": 12.0, "y": 34.0, "width": 80.0, "height": 30.0}

    policy = InteractionPolicy(min_action_interval_ms=0)
    elem = PlaywrightElement(mock_locator, policy=policy)

    # get_attribute
    attr = await elem.get_attribute("id")
    assert attr == "submit-btn"
    mock_locator.get_attribute.assert_awaited_once_with("id", timeout=10000)

    # get_text
    text = await elem.get_text()
    assert text == "Submit"

    # click
    await elem.click()
    mock_locator.click.assert_awaited_once_with(timeout=10000)

    # type_text
    await elem.type_text("Hello World")
    mock_locator.fill.assert_awaited_once_with("Hello World", timeout=10000)

    # clear_text
    await elem.clear_text()
    mock_locator.clear.assert_awaited_once_with(timeout=10000)

    # select_option
    await elem.select_option("opt1")
    mock_locator.select_option.assert_awaited_once_with(value="opt1", timeout=10000)

    # set_files
    await elem.set_files(["/path/to/resume.pdf"])
    mock_locator.set_input_files.assert_awaited_once_with(["/path/to/resume.pdf"], timeout=10000)

    # get_bounding_rect
    rect = await elem.get_bounding_rect()
    assert isinstance(rect, ElementRect)
    assert rect.x == 12.0
    assert rect.y == 34.0
    assert rect.width == 80.0
    assert rect.height == 30.0

    # scroll_into_view
    await elem.scroll_into_view()
    mock_locator.scroll_into_view_if_needed.assert_awaited_once_with(timeout=10000)


@pytest.mark.asyncio
async def test_playwright_element_bounding_box_none_raises_driver_error():
    mock_locator = AsyncMock()
    mock_locator.bounding_box.return_value = None

    elem = PlaywrightElement(mock_locator, policy=InteractionPolicy(min_action_interval_ms=0))
    with pytest.raises(BrowserDriverError):
        await elem.get_bounding_rect()


@pytest.mark.asyncio
async def test_playwright_element_error_wrapping():
    mock_locator = AsyncMock()
    mock_locator.click.side_effect = RuntimeError("Element not clickable")

    elem = PlaywrightElement(mock_locator, policy=InteractionPolicy(min_action_interval_ms=0))
    with pytest.raises(BrowserDriverError, match="click failed"):
        await elem.click()


@pytest.mark.asyncio
async def test_playwright_page_implements_protocol():
    mock_page = AsyncMock()
    mock_page.url = "https://campus.example.com"
    page = PlaywrightPage(mock_page)
    assert isinstance(page, BrowserPage)


@pytest.mark.asyncio
async def test_playwright_page_find_and_find_all():
    mock_page = AsyncMock()
    mock_locator = AsyncMock()
    mock_locator.count.return_value = 2
    sub_loc1 = AsyncMock()
    sub_loc2 = AsyncMock()
    mock_locator.nth.side_effect = [sub_loc1, sub_loc2]
    mock_locator.first = sub_loc1
    mock_page.locator.return_value = mock_locator

    page = PlaywrightPage(mock_page, policy=InteractionPolicy(min_action_interval_ms=0))

    # find returns first element
    elem = await page.find(".item")
    assert elem is not None
    assert isinstance(elem, BrowserElement)

    # find_all returns list
    mock_locator.count.return_value = 2
    mock_locator.all.return_value = [sub_loc1, sub_loc2]
    elements = await page.find_all(".item")
    assert len(elements) == 2
    assert all(isinstance(e, BrowserElement) for e in elements)

    # find returns None if count is 0
    mock_empty_loc = AsyncMock()
    mock_empty_loc.count.return_value = 0
    mock_page.locator.return_value = mock_empty_loc
    assert await page.find(".nonexistent") is None


@pytest.mark.asyncio
async def test_playwright_page_wait_for():
    mock_page = AsyncMock()
    mock_locator = AsyncMock()
    mock_page.locator.return_value = mock_locator
    mock_locator.first = mock_locator

    page = PlaywrightPage(mock_page, policy=InteractionPolicy(min_action_interval_ms=0))
    elem = await page.wait_for("#login", timeout_ms=3000)
    assert isinstance(elem, BrowserElement)
    mock_locator.wait_for.assert_awaited_once_with(timeout=3000)


@pytest.mark.asyncio
async def test_playwright_page_execute_unsafe_script_requires_reason():
    mock_page = AsyncMock()
    mock_page.evaluate.return_value = "probe_result"
    page = PlaywrightPage(mock_page)

    # Empty reason must raise ValueError or BrowserDriverError
    with pytest.raises((ValueError, BrowserDriverError)):
        await page.execute_unsafe_script("", "window.__status__")

    # Whitespace-only reason must raise ValueError or BrowserDriverError
    with pytest.raises((ValueError, BrowserDriverError)):
        await page.execute_unsafe_script("   ", "window.__status__")

    # Valid reason should execute successfully
    res = await page.execute_unsafe_script("Probe runtime platform signature", "window.__status__")
    assert res == "probe_result"
    mock_page.evaluate.assert_awaited_once_with("window.__status__")


@pytest.mark.asyncio
async def test_playwright_page_execute_unsafe_script_error_wrapping():
    mock_page = AsyncMock()
    mock_page.evaluate.side_effect = RuntimeError("JS execution crashed")
    page = PlaywrightPage(mock_page)

    with pytest.raises(BrowserDriverError, match="execute_unsafe_script failed"):
        await page.execute_unsafe_script("Valid reason", "throw new Error()")


@pytest.mark.asyncio
async def test_playwright_backend_implements_protocol():
    backend = PlaywrightBackend()
    assert isinstance(backend, BrowserBackend)


@pytest.mark.asyncio
async def test_playwright_backend_lifecycle(tmp_path: Path):
    backend = PlaywrightBackend(
        headless=True,
        user_data_dir=tmp_path / "browser_test",
        policy=InteractionPolicy(min_action_interval_ms=0),
    )
    assert backend.headless is True
    assert backend.user_data_dir == tmp_path / "browser_test"

    mock_playwright = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_page.url = "about:blank"
    mock_context.pages = [mock_page]
    mock_playwright.chromium.launch_persistent_context.return_value = mock_context

    with patch("applypilot.browser.playwright_backend.async_playwright") as mock_ap:
        mock_ap.return_value.start = AsyncMock(return_value=mock_playwright)

        # open_page
        opened_page = await backend.open_page("https://example.com/apply")
        assert isinstance(opened_page, BrowserPage)
        mock_page.goto.assert_awaited_once_with("https://example.com/apply", timeout=10000)

        # current_page
        curr_page = await backend.current_page()
        assert curr_page is opened_page

        # wait_for_user with custom hook
        hook_called = False

        async def custom_prompt(reason: str):
            nonlocal hook_called
            hook_called = True
            assert reason == "Captcha detected"

        backend.user_prompt_handler = custom_prompt
        await backend.wait_for_user("Captcha detected")
        assert hook_called is True

        # close
        await backend.close()
        mock_context.close.assert_awaited_once()
        mock_playwright.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_playwright_backend_context_manager(tmp_path: Path):
    mock_playwright = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_page.url = "about:blank"
    mock_context.pages = [mock_page]
    mock_playwright.chromium.launch_persistent_context.return_value = mock_context

    with patch("applypilot.browser.playwright_backend.async_playwright") as mock_ap:
        mock_ap.return_value.start = AsyncMock(return_value=mock_playwright)

        async with PlaywrightBackend(
            headless=True,
            user_data_dir=tmp_path / "ctx_test",
            policy=InteractionPolicy(min_action_interval_ms=0),
        ) as backend:
            page = await backend.current_page()
            assert isinstance(page, BrowserPage)

        mock_context.close.assert_awaited_once()
        mock_playwright.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_playwright_backend_creates_new_page_when_busy(tmp_path: Path):
    backend = PlaywrightBackend(
        headless=True,
        user_data_dir=tmp_path / "busy_test",
        policy=InteractionPolicy(min_action_interval_ms=0),
    )
    mock_playwright = AsyncMock()
    mock_context = AsyncMock()
    existing_page = AsyncMock()
    existing_page.url = "https://already-open.com"
    new_page = AsyncMock()
    new_page.url = "about:blank"
    mock_context.pages = [existing_page]
    mock_context.new_page.return_value = new_page
    mock_playwright.chromium.launch_persistent_context.return_value = mock_context

    with patch("applypilot.browser.playwright_backend.async_playwright") as mock_ap:
        mock_ap.return_value.start = AsyncMock(return_value=mock_playwright)

        opened = await backend.open_page("https://new-job.com")
        mock_context.new_page.assert_awaited_once()
        new_page.goto.assert_awaited_once_with("https://new-job.com", timeout=10000)
        assert isinstance(opened, BrowserPage)


@pytest.mark.asyncio
async def test_playwright_backend_launch_error_wrapped(tmp_path: Path):
    backend = PlaywrightBackend(
        headless=True,
        user_data_dir=tmp_path / "err_test",
    )
    with patch("applypilot.browser.playwright_backend.async_playwright") as mock_ap:
        mock_ap.return_value.start.side_effect = RuntimeError("Chromium binary not found")
        with pytest.raises(BrowserDriverError, match="Failed to launch browser context"):
            await backend.open_page("https://example.com")


@pytest.mark.asyncio
async def test_playwright_page_execute_unsafe_script_with_arg():
    mock_page = AsyncMock()
    mock_page.evaluate.return_value = "arg_result"
    page = PlaywrightPage(mock_page)

    res = await page.execute_unsafe_script("Test with arg", "el => el.value", {"key": "val"})
    assert res == "arg_result"
    mock_page.evaluate.assert_awaited_once_with("el => el.value", {"key": "val"})


@pytest.mark.asyncio
async def test_playwright_page_url_and_title_properties():
    mock_page = MagicMock()
    mock_page.url = "https://example.com/login"
    mock_page.title = AsyncMock(return_value="Login Page")

    page = PlaywrightPage(mock_page)
    assert await page.url() == "https://example.com/login"
    assert await page.title() == "Login Page"


@pytest.mark.asyncio
async def test_playwright_backend_default_wait_for_user_prints(capsys):
    backend = PlaywrightBackend()
    await backend.wait_for_user("Please solve captcha manually")
    captured = capsys.readouterr()
    assert "Please solve captcha manually" in captured.out


@pytest.mark.asyncio
async def test_action_rate_limiter_pacing():
    from applypilot.browser.playwright_backend import ActionRateLimiter
    import time

    limiter = ActionRateLimiter(min_interval_ms=50)
    t0 = time.monotonic()
    await limiter.throttle()
    await limiter.throttle()
    elapsed = (time.monotonic() - t0) * 1000.0
    assert elapsed >= 45.0  # throttled at least 50ms (with 5ms tolerance)

    zero_limiter = ActionRateLimiter(min_interval_ms=0)
    t0 = time.monotonic()
    await zero_limiter.throttle()
    await zero_limiter.throttle()
    elapsed_zero = (time.monotonic() - t0) * 1000.0
    assert elapsed_zero < 20.0


@pytest.mark.asyncio
async def test_playwright_backend_close_robustness(tmp_path: Path):
    backend = PlaywrightBackend(headless=True, user_data_dir=tmp_path / "close_test")
    mock_context = AsyncMock()
    mock_context.close.side_effect = RuntimeError("Browser crashed")
    mock_playwright = AsyncMock()
    backend._context = mock_context
    backend._playwright = mock_playwright

    with pytest.raises(BrowserDriverError, match="close failed"):
        await backend.close()

    # Verify playwright.stop() was still called despite context.close() failure
    mock_playwright.stop.assert_awaited_once()
    assert backend._context is None
    assert backend._playwright is None

