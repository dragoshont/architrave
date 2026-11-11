#!/usr/bin/env python3
"""Real Chromium dashboard checks. Requires optional Playwright; never writes lifecycle state."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", required=True, help="already-generated real board HTML")
    parser.add_argument("--output", required=True, help="session-owned screenshots directory")
    args = parser.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Browser qualification needs Playwright and its Chromium runtime.", file=sys.stderr)
        return 2
    path = Path(args.board).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for name, width in (("desktop", 1440), ("narrow", 320)):
                context = browser.new_context(viewport={"width": width, "height": 1000}, reduced_motion="reduce")
                page = context.new_page()
                errors, remote = [], []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                page.on("request", lambda request: remote.append(request.url) if not request.url.startswith("file:") else None)
                page.goto(path.as_uri(), wait_until="load")
                page.wait_for_function("document.documentElement.classList.contains('enhanced')")
                page.screenshot(path=str(output / f"dashboard-{name}.png"), full_page=True)
                assert page.get_by_role("main").count() == 1
                assert page.locator("html").get_attribute("data-theme") == "dark"
                total = page.locator(".metric").all_inner_texts()[:3]
                links = page.locator(".task-square")
                assert links.count() > 0, "test requires actual task data"
                target = links.last.get_attribute("data-task")
                links.last.click()
                assert page.locator(f"[data-inspector='{target}']").is_visible()
                assert page.locator(f"[data-inspector='{target}'] h3").evaluate("node => node === document.activeElement")
                page.get_by_label("Find a task").fill(target)
                assert page.locator(".task-square:visible").count() == 1
                assert page.locator(".metric").all_inner_texts()[:3] == total, "filter changed primary denominators"
                page.get_by_role("button", name="List view", exact=True).click()
                assert page.locator(".task-list-row:visible").count() == 1
                page.get_by_role("button", name="Map view", exact=True).click()
                page.get_by_role("button", name="Light theme", exact=True).click()
                assert page.locator("html").get_attribute("data-theme") == "light"
                page.get_by_role("button", name="Dark theme", exact=True).click()
                pause = page.get_by_role("button", name="Pause updates", exact=True)
                if pause.is_visible():
                    pause.click()
                    assert page.get_by_role("button", name="Resume updates", exact=True).is_visible()
                    assert "ownership" in page.locator("#client-status").inner_text()
                page.reload(wait_until="load")
                page.wait_for_function("document.documentElement.classList.contains('enhanced')")
                assert page.get_by_label("Find a task").input_value() == target
                assert page.locator(f"[data-inspector='{target}']").is_visible()
                page.get_by_label("Find a task").fill("")
                page.get_by_label("Show tasks", exact=True).select_option("all")
                assert page.locator(".metric").all_inner_texts()[:3] == total
                page.locator(".task-square").first.focus()
                assert page.evaluate("document.activeElement.matches('.task-square')")
                page.keyboard.press("Enter")
                assert page.evaluate("document.activeElement.matches('.inspector h3')")
                page.locator("h1").scroll_into_view_if_needed()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "horizontal overflow"
                page.screenshot(path=str(output / f"dashboard-{name}.png"), full_page=True)
                assert not errors, errors
                assert not remote, remote
                print(f"PASS {name}: real YAML-derived board, CSP, task selection, filters, stable counts, theme, retained state, keyboard and overflow")
                context.close()
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
