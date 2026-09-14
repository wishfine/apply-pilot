import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional, Any, Callable
from playwright.async_api import async_playwright

from applypilot.core.config import get_browser_dir
from applypilot.core.exceptions import BrowserDriverError
from applypilot.browser.base import (
    ElementRect,
    InteractionPolicy,
    BrowserElement,
    BrowserPage,
    BrowserBackend,
)

logger = logging.getLogger(__name__)


class ActionRateLimiter:
    """底层动作间隔限流器，接管动作间隔，杜绝业务散落私有 jitter"""

    def __init__(self, min_interval_ms: int = 150):
        self.min_interval_ms = min_interval_ms
        self._last_action_time: float = 0.0
        self._lock = asyncio.Lock()

    async def throttle(self) -> None:
        if self.min_interval_ms <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            elapsed_ms = (now - self._last_action_time) * 1000.0
            if elapsed_ms < self.min_interval_ms:
                await asyncio.sleep((self.min_interval_ms - elapsed_ms) / 1000.0)
            self._last_action_time = time.monotonic()


class PlaywrightElement:
    """BrowserElement 协议的 Playwright Locator 适配器包装"""

    def __init__(
        self,
        locator: Any,
        policy: Optional[InteractionPolicy] = None,
        rate_limiter: Optional[ActionRateLimiter] = None,
    ):
        self._locator = locator
        self._policy = policy or InteractionPolicy()
        self._rate_limiter = rate_limiter or ActionRateLimiter(self._policy.min_action_interval_ms)

    async def _throttle(self) -> None:
        await self._rate_limiter.throttle()

    async def get_attribute(self, name: str) -> Optional[str]:
        try:
            return await self._locator.get_attribute(name, timeout=self._policy.action_timeout_ms)
        except BrowserDriverError:
            raise
        except Exception as e:
            raise BrowserDriverError(f"get_attribute('{name}') failed: {e}") from e

    async def get_text(self) -> str:
        try:
            if hasattr(self._locator, "inner_text"):
                try:
                    val = await self._locator.inner_text(timeout=min(2000, self._policy.action_timeout_ms))
                    return val if val is not None else ""
                except Exception:
                    pass
            if hasattr(self._locator, "text_content"):
                val = await self._locator.text_content(timeout=self._policy.action_timeout_ms)
                return val if val is not None else ""
            return ""
        except BrowserDriverError:
            raise
        except Exception as e:
            raise BrowserDriverError(f"get_text failed: {e}") from e

    async def is_checked(self) -> bool:
        try:
            return await self._locator.is_checked(timeout=self._policy.action_timeout_ms)
        except Exception as e:
            raise BrowserDriverError(f"is_checked failed: {e}") from e

    async def inspect_field(self) -> dict[str, Any]:
        """Read live form state, associated labels and requirement containers together."""
        try:
            return await self._locator.evaluate("""el => {
                const attrs = Object.fromEntries(Array.from(el.attributes, a => [a.name, a.value]));
                const container = el.closest('.ant-form-item, .el-form-item, .form-item, .form-group');
                const visible = node => !!node.getClientRects().length && getComputedStyle(node).visibility !== 'hidden';
                const active = !el.matches(':disabled') && (visible(el) || (el.type === 'file'
                    && (Array.from(el.labels || []).some(visible) || (container && visible(container)))));
                const labelText = Array.from(el.labels || [], l => l.textContent.trim()).join(' ');
                const labelledBy = (el.getAttribute('aria-labelledby') || '').split(/\\s+/)
                    .map(id => document.getElementById(id)?.textContent?.trim() || '').join(' ').trim();
                let label = el.getAttribute('aria-label') || labelledBy || labelText
                    || container?.querySelector('label')?.textContent?.trim()
                    || el.title || el.getAttribute('placeholder') || el.name || el.id || '';
                let observed = el.value ?? '';
                if (el.tagName.toLowerCase() === 'select') {
                    observed = el.selectedOptions?.[0]?.textContent?.trim() || el.value || '';
                }
                let required = el.required || el.getAttribute('aria-required') === 'true';
                let optionLabel = '';
                if (el.type === 'radio') {
                    const group = el.name ? Array.from(el.getRootNode().querySelectorAll('input[type=radio]'))
                        .filter(x => x.name === el.name && x.form === el.form) : [el];
                    const selected = group.find(x => x.checked);
                    observed = selected
                        ? (Array.from(selected.labels || [], l => l.textContent.trim()).join(' ') || selected.value)
                        : null;
                    optionLabel = labelText;
                    required = required || group.some(x => x.required);
                    label = el.closest('fieldset')?.querySelector('legend')?.textContent?.trim()
                        || el.getAttribute('aria-label') || labelledBy || el.name || label;
                } else if (el.type === 'checkbox') {
                    observed = el.checked ? (el.value || true) : null;
                } else if (el.type === 'file') {
                    observed = el.files.length ? Array.from(el.files, f => f.name).join(', ') : null;
                }
                if (required) attrs.required = '';
                let sectionTitle = '';
                for (let group = el.parentElement; group && !sectionTitle; group = group.parentElement) {
                    sectionTitle = group.querySelector(':scope > legend, :scope > h2, :scope > h3, :scope > h4')?.textContent?.trim()
                        || group.getAttribute('aria-label') || '';
                }
                const options = el.tagName.toLowerCase() === 'select'
                    ? Array.from(el.options).map(option => ({
                        value: (option.value || '').trim(),
                        text: (option.textContent || option.text || '').trim(),
                        label: (option.label || '').trim(),
                    }))
                    : null;
                const widget = el.getAttribute('data-widget') || el.getAttribute('data-component')
                    || (typeof el.className === 'string' ? el.className : '');
                return {section_title: sectionTitle, tag: el.tagName.toLowerCase(), type: el.type || '', label,
                    field_sig: el.id || el.name || label, element_attrs: attrs,
                    outer_html: (container || el).outerHTML, observed_value: observed,
                    option_label: optionLabel, options, widget, is_active: !!active,
                    is_valid: el.validity ? el.validity.valid : true};
            }""", timeout=self._policy.action_timeout_ms)
        except Exception as e:
            raise BrowserDriverError(f"inspect_field failed: {e}") from e

    async def click(self) -> None:
        try:
            await self._throttle()
            await self._locator.click(timeout=self._policy.action_timeout_ms)
        except BrowserDriverError:
            raise
        except Exception as e:
            raise BrowserDriverError(f"click failed: {e}") from e

    async def type_text(self, text: str) -> None:
        try:
            await self._throttle()
            if hasattr(self._locator, "fill"):
                await self._locator.fill(text, timeout=self._policy.action_timeout_ms)
            elif hasattr(self._locator, "press_sequentially"):
                await self._locator.press_sequentially(text, timeout=self._policy.action_timeout_ms)
            elif hasattr(self._locator, "type"):
                await self._locator.type(text, timeout=self._policy.action_timeout_ms)
            else:
                raise BrowserDriverError("Locator does not support fill/type")
        except BrowserDriverError:
            raise
        except Exception as e:
            raise BrowserDriverError(f"type_text failed: {e}") from e

    async def clear_text(self) -> None:
        try:
            await self._throttle()
            if hasattr(self._locator, "clear"):
                await self._locator.clear(timeout=self._policy.action_timeout_ms)
            elif hasattr(self._locator, "fill"):
                await self._locator.fill("", timeout=self._policy.action_timeout_ms)
            else:
                raise BrowserDriverError("Locator does not support clear/fill")
        except BrowserDriverError:
            raise
        except Exception as e:
            raise BrowserDriverError(f"clear_text failed: {e}") from e

    async def select_option(self, value: str, *, label: Optional[str] = None) -> None:
        try:
            await self._throttle()
            if label is not None:
                await self._locator.select_option(label=label, timeout=self._policy.action_timeout_ms)
                return
            try:
                await self._locator.select_option(value=value, timeout=self._policy.action_timeout_ms)
            except Exception:
                await self._locator.select_option(label=value, timeout=self._policy.action_timeout_ms)
        except BrowserDriverError:
            raise
        except Exception as e:
            raise BrowserDriverError(f"select_option('{value}') failed: {e}") from e

    async def set_files(self, file_paths: list[str]) -> None:
        try:
            await self._throttle()
            if hasattr(self._locator, "set_input_files"):
                await self._locator.set_input_files(file_paths, timeout=self._policy.action_timeout_ms)
            elif hasattr(self._locator, "set_files"):
                await self._locator.set_files(file_paths)
            else:
                raise BrowserDriverError("Locator does not support set_input_files")
        except BrowserDriverError:
            raise
        except Exception as e:
            raise BrowserDriverError(f"set_files failed: {e}") from e

    async def get_bounding_rect(self) -> ElementRect:
        try:
            box = await self._locator.bounding_box(timeout=self._policy.action_timeout_ms)
            if box is None and hasattr(self._locator, "scroll_into_view_if_needed"):
                try:
                    await self._locator.scroll_into_view_if_needed(timeout=2000)
                    box = await self._locator.bounding_box(timeout=2000)
                except Exception:
                    pass
            if box is None:
                raise BrowserDriverError("Element has no bounding box (it may be invisible or detached)")
            if isinstance(box, ElementRect):
                return box
            return ElementRect(
                x=float(box["x"]),
                y=float(box["y"]),
                width=float(box["width"]),
                height=float(box["height"]),
            )
        except BrowserDriverError:
            raise
        except Exception as e:
            raise BrowserDriverError(f"get_bounding_rect failed: {e}") from e

    async def scroll_into_view(self) -> None:
        try:
            await self._throttle()
            if hasattr(self._locator, "scroll_into_view_if_needed"):
                await self._locator.scroll_into_view_if_needed(timeout=self._policy.action_timeout_ms)
            elif hasattr(self._locator, "scroll_into_view"):
                await self._locator.scroll_into_view()
        except BrowserDriverError:
            raise
        except Exception as e:
            raise BrowserDriverError(f"scroll_into_view failed: {e}") from e

    async def evaluate(self, expression: str, arg: Any = None) -> Any:
        try:
            await self._throttle()
            return await self._locator.evaluate(expression, arg, timeout=self._policy.action_timeout_ms)
        except BrowserDriverError:
            raise
        except Exception as e:
            raise BrowserDriverError(f"evaluate failed: {e}") from e


class PlaywrightPage:
    """BrowserPage 协议的 Playwright Page 适配器包装"""

    def __init__(
        self,
        page: Any,
        policy: Optional[InteractionPolicy] = None,
        rate_limiter: Optional[ActionRateLimiter] = None,
    ):
        self._page = page
        self._policy = policy or InteractionPolicy()
        self._rate_limiter = rate_limiter or ActionRateLimiter(self._policy.min_action_interval_ms)

    async def url(self) -> str:
        try:
            u = self._page.url
            if callable(u):
                res = u()
                if asyncio.iscoroutine(res):
                    return await res
                return str(res)
            return str(u)
        except BrowserDriverError:
            raise
        except Exception as e:
            raise BrowserDriverError(f"url failed: {e}") from e

    async def title(self) -> str:
        try:
            t = self._page.title
            if callable(t):
                res = t()
                if asyncio.iscoroutine(res):
                    return await res
                return str(res)
            return str(t)
        except BrowserDriverError:
            raise
        except Exception as e:
            raise BrowserDriverError(f"title failed: {e}") from e

    async def _resolve_locator(self, selector: str) -> Any:
        loc = self._page.locator(selector)
        if asyncio.iscoroutine(loc):
            loc = await loc
        return loc

    def _child_frames(self) -> list[Any]:
        """Return live child frames without making frame access a hard dependency."""
        try:
            frames = list(getattr(self._page, "frames", []) or [])
        except Exception:
            return []
        children: list[Any] = []
        for frame in frames:
            try:
                if getattr(frame, "parent_frame", None) is not None:
                    children.append(frame)
            except Exception:
                continue
        return children

    async def _locator_elements(self, owner: Any, selector: str) -> list[Any]:
        """Resolve all matching locators in a page or child frame."""
        loc = owner.locator(selector)
        if asyncio.iscoroutine(loc):
            loc = await loc
        if hasattr(loc, "all"):
            locs = loc.all()
            if asyncio.iscoroutine(locs):
                locs = await locs
            if isinstance(locs, (list, tuple)):
                return list(locs)
        if hasattr(loc, "count"):
            cnt = loc.count()
            if asyncio.iscoroutine(cnt):
                cnt = await cnt
            if int(cnt) == 0:
                return []
            resolved = []
            for i in range(int(cnt)):
                item = loc.nth(i)
                if asyncio.iscoroutine(item):
                    item = await item
                resolved.append(item)
            return resolved
        if hasattr(loc, "all"):
            locs = loc.all()
            if asyncio.iscoroutine(locs):
                locs = await locs
            return list(locs)
        return []

    async def find(self, selector: str) -> Optional[BrowserElement]:
        try:
            locs = await self._locator_elements(self._page, selector)
            for frame in self._child_frames():
                try:
                    locs.extend(await self._locator_elements(frame, selector))
                except Exception:
                    # Cross-origin or already detached frames can be skipped.
                    continue
            if not locs:
                return None
            return PlaywrightElement(locs[0], policy=self._policy, rate_limiter=self._rate_limiter)
        except BrowserDriverError:
            raise
        except Exception as e:
            raise BrowserDriverError(f"find('{selector}') failed: {e}") from e

    async def find_all(self, selector: str) -> list[BrowserElement]:
        try:
            locs = await self._locator_elements(self._page, selector)
            for frame in self._child_frames():
                try:
                    locs.extend(await self._locator_elements(frame, selector))
                except Exception:
                    continue
            return [
                PlaywrightElement(l, policy=self._policy, rate_limiter=self._rate_limiter)
                for l in locs
            ]
        except BrowserDriverError:
            raise
        except Exception as e:
            raise BrowserDriverError(f"find_all('{selector}') failed: {e}") from e

    async def wait_for(self, selector: str, timeout_ms: int = 5000) -> BrowserElement:
        try:
            loc = await self._resolve_locator(selector)
            first_loc = loc.first if hasattr(loc, "first") else loc
            if hasattr(first_loc, "wait_for"):
                res = first_loc.wait_for(timeout=timeout_ms)
                if asyncio.iscoroutine(res):
                    await res
            elif hasattr(self._page, "wait_for_selector"):
                res = self._page.wait_for_selector(selector, timeout=timeout_ms)
                if asyncio.iscoroutine(res):
                    await res
            return PlaywrightElement(first_loc, policy=self._policy, rate_limiter=self._rate_limiter)
        except BrowserDriverError:
            raise
        except Exception as e:
            raise BrowserDriverError(f"wait_for('{selector}') failed: {e}") from e

    async def execute_unsafe_script(self, reason: str, script: str, arg: Any = None) -> Any:
        if not reason or not reason.strip():
            raise BrowserDriverError("execute_unsafe_script requires a non-empty reason for audit trail")
        logger.warning(
            "AUDIT [execute_unsafe_script]: reason='%s', script='%s'",
            reason.strip(),
            script[:120],
        )
        async def evaluate(owner: Any) -> Any:
            if arg is not None:
                return await owner.evaluate(script, arg)
            return await owner.evaluate(script)

        try:
            main_result = await evaluate(self._page)
            if isinstance(main_result, bool) and main_result is True:
                return True
            if not isinstance(main_result, (bool, dict)) and main_result is not None:
                return main_result
            frame_results: list[Any] = []
            for frame in self._child_frames():
                try:
                    frame_result = await evaluate(frame)
                    frame_results.append(frame_result)
                except Exception:
                    continue

            # Boolean probes are used for platform/login/final-stage detection.
            # A true result in any child frame is sufficient.
            if isinstance(main_result, bool):
                return any(result is True for result in frame_results)
            # Stage marker scripts return dictionaries.  Prefer the richest
            # context so an iframe-hosted form is not mistaken for an empty page.
            if isinstance(main_result, dict):
                dict_results = [result for result in frame_results if isinstance(result, dict)]
                if dict_results:
                    return max([main_result, *dict_results], key=lambda result: len(json.dumps(result, default=str)))
            return main_result
        except BrowserDriverError:
            raise
        except Exception as e:
            raise BrowserDriverError(f"execute_unsafe_script failed: {e}") from e


class PlaywrightBackend:
    """BrowserBackend 协议的 Playwright 驱动实现"""

    def __init__(
        self,
        headless: bool = False,
        user_data_dir: Optional[Path] = None,
        policy: Optional[InteractionPolicy] = None,
        user_prompt_handler: Optional[Callable[[str], Any]] = None,
    ):
        self.headless = headless
        self.user_data_dir = user_data_dir or get_browser_dir()
        self.policy = policy or InteractionPolicy()
        self.user_prompt_handler = user_prompt_handler
        self._playwright: Optional[Any] = None
        self._context: Optional[Any] = None
        self._current_page: Optional[PlaywrightPage] = None
        self._rate_limiter = ActionRateLimiter(min_interval_ms=self.policy.min_action_interval_ms)
        self._lock = asyncio.Lock()

    async def _ensure_context(self) -> Any:
        async with self._lock:
            is_closed = False
            if self._context is not None:
                try:
                    if hasattr(self._context, "is_closed"):
                        res = self._context.is_closed()
                        if asyncio.iscoroutine(res):
                            res = await res
                        if isinstance(res, bool):
                            is_closed = res
                except Exception:
                    is_closed = True

            if self._context is None or is_closed:
                try:
                    Path(self.user_data_dir).mkdir(parents=True, exist_ok=True)
                    if self._playwright is None:
                        self._playwright = await async_playwright().start()
                    self._context = await self._playwright.chromium.launch_persistent_context(
                        user_data_dir=str(self.user_data_dir),
                        headless=self.headless,
                    )
                except BrowserDriverError:
                    raise
                except Exception as e:
                    if self._playwright is not None and self._context is None:
                        try:
                            await self._playwright.stop()
                        except Exception:
                            pass
                        self._playwright = None
                    raise BrowserDriverError(f"Failed to launch browser context: {e}") from e
        return self._context

    async def open_page(self, url: str) -> BrowserPage:
        try:
            await self._ensure_context()
            page = None
            if self._context.pages:
                candidate = self._context.pages[0]
                try:
                    cand_url = candidate.url
                    if cand_url in ("about:blank", "") and len(self._context.pages) == 1:
                        page = candidate
                except Exception:
                    pass
            newly_opened = False
            if page is None:
                page = await self._context.new_page()
                newly_opened = True

            try:
                await page.goto(
                    url,
                    timeout=self.policy.navigation_timeout_ms,
                    wait_until="domcontentloaded",
                )
            except Exception:
                if newly_opened and hasattr(page, "close"):
                    try:
                        res = page.close()
                        if asyncio.iscoroutine(res):
                            await res
                    except Exception:
                        pass
                raise

            self._current_page = PlaywrightPage(page, policy=self.policy, rate_limiter=self._rate_limiter)
            return self._current_page
        except BrowserDriverError:
            raise
        except Exception as e:
            raise BrowserDriverError(f"open_page('{url}') failed: {e}") from e

    async def current_page(self) -> BrowserPage:
        try:
            await self._ensure_context()
            open_pages = []
            if hasattr(self._context, "pages") and self._context.pages:
                for p in self._context.pages:
                    p_closed = False
                    if hasattr(p, "is_closed"):
                        try:
                            res = p.is_closed()
                            if asyncio.iscoroutine(res):
                                res = await res
                            if isinstance(res, bool):
                                p_closed = res
                        except Exception:
                            p_closed = True
                    if not p_closed:
                        open_pages.append(p)

            if open_pages:
                # Browser contexts append popup/new-tab pages.  Always use the
                # newest live page so a login flow opened in a popup is resumed.
                page = open_pages[-1]
                if self._current_page is not None and getattr(self._current_page, "_page", None) is page:
                    return self._current_page
            else:
                if self._current_page is not None:
                    page_obj = getattr(self._current_page, "_page", None)
                    if page_obj is not None:
                        try:
                            closed = page_obj.is_closed()
                            if asyncio.iscoroutine(closed):
                                closed = await closed
                            if not closed:
                                return self._current_page
                        except Exception:
                            pass
                page = await self._context.new_page()

            self._current_page = PlaywrightPage(page, policy=self.policy, rate_limiter=self._rate_limiter)
            return self._current_page
        except BrowserDriverError:
            raise
        except Exception as e:
            raise BrowserDriverError(f"current_page failed: {e}") from e

    async def wait_for_user(self, reason: str) -> None:
        logger.info("AUDIT: Human intervention requested: %s", reason)
        if self.user_prompt_handler is not None:
            res = self.user_prompt_handler(reason)
            if asyncio.iscoroutine(res):
                await res
            return
        print(f"\n[ApplyPilot] Human action required: {reason}")

    async def close(self) -> None:
        errors: list[Exception] = []
        if self._context is not None:
            try:
                await self._context.close()
            except Exception as e:
                errors.append(e)
            finally:
                self._context = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as e:
                errors.append(e)
            finally:
                self._playwright = None
        self._current_page = None
        if errors:
            raise BrowserDriverError(f"close failed: {errors[0]}") from errors[0]

    async def __aenter__(self):
        await self._ensure_context()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
