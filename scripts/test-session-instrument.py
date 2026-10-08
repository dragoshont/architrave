"""Optional real-browser UI contract. Host data is synthetic, never native proof."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".github" / "extensions" / "architrave-ribbon" / "extension.mjs"


def fixture():
    return {
        "activity": "working", "selectedModel": "Fixture selected model",
        "selectedEffort": "high", "observedModel": "Fixture observed model",
        "observedEffort": "medium", "contextTier": "default",
        "observedAt": "2026-10-08T21:00:00Z", "autoOpen": True,
        "diagnostic": None, "subagentsDiagnostic": None, "subagentsStatus": "observed",
        "activeTools": ["read", "test"],
        "usage": {"currentTokens": 16384, "tokenLimit": 65536, "capturedAt": "2026-10-08T21:00:00Z"},
        "subagents": [{
            "id": "fixture-implementation", "name": "Session instrument", "role": "UI implementer",
            "assignedSlice": "Telemetry rail and session activity", "status": "running",
            "requestedModel": None, "resolvedModel": "Fixture resolved model",
            "observedModel": "Fixture child model", "configuredEffort": "high",
            "observedEffort": "medium", "currentActivity": "test", "contextTier": None,
            "usage": None,
        }, {
            "id": "fixture-review", "name": "Source review", "role": "Reviewer",
            "assignedSlice": "Lifecycle and unknown-state behavior", "status": "idle",
            "requestedModel": None, "resolvedModel": None, "observedModel": None,
            "configuredEffort": None, "observedEffort": None, "currentActivity": None,
            "contextTier": None, "usage": None,
        }],
    }


def contrast(foreground, background):
    def luminance(rgb):
        scaled = [n / 255 for n in rgb]
        linear = [n / 12.92 if n <= .04045 else ((n + .055) / 1.055) ** 2.4 for n in scaled]
        return sum(n * weight for n, weight in zip(linear, (.2126, .7152, .0722)))
    a, b = sorted((luminance(foreground), luminance(background)))
    return (b + .05) / (a + .05)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("output", type=Path)
    parser.add_argument("--browser", help="Existing Chromium/Edge executable; defaults to Playwright Chromium")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    receipts = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, **({"executable_path": args.browser} if args.browser else {}))
        try:
            for name, width, dark in [("desktop-light", 1280, False), ("narrow-dark", 360, True)]:
                page = browser.new_page(viewport={"width": width, "height": 900}, reduced_motion="reduce",
                                        color_scheme="dark" if dark else "light")
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                data = fixture()
                requests = []

                def snapshot(route):
                    route.fulfill(json=data)

                def preference(route):
                    requests.append(route.request.post_data_json)
                    data["autoOpen"] = route.request.post_data_json["enabled"]
                    route.fulfill(json={})

                page.route("**/snapshot", snapshot)
                page.route("**/preferences", preference)
                page.route("**/dismiss", lambda route: route.fulfill(json={}))
                # No event source in this fixture. Explicit refresh exercises the same renderer.
                page.add_init_script("window.EventSource=class { close(){} };")
                page.goto(args.url, wait_until="domcontentloaded")
                page.wait_for_function("() => document.querySelector('#selected').textContent==='Fixture selected model'")
                assert page.title() == "Architrave / Session instrument"
                assert page.locator("#usage span").all_text_contents() == ["16,384", "/ 65,536"]
                assert page.locator("#meter").get_attribute("max") == "65536"
                assert page.locator("#child-count").inner_text() == "2 subagents"
                assert page.locator(".lane[open]").count() == 0
                assert "Assigned: Telemetry rail" in page.locator(".lane").first.inner_text()
                assert "Observed model: Fixture child model" in page.locator(".lane").first.inner_text()
                assert "session subagents only" in page.locator(".boundary").inner_text()
                assert page.locator("[role=progressbar]").count() == 0
                assert page.locator("#track").get_attribute("aria-hidden") == "true"
                assert page.locator(".route").count() == 0  # No illustrative phases.
                page.screenshot(path=str(args.output / f"{name}.png"), full_page=True)
                await_motion = """() => getComputedStyle(document.querySelector('#track span')).animationName"""
                page.emulate_media(reduced_motion="no-preference")
                assert page.evaluate(await_motion) == "travel"
                page.emulate_media(reduced_motion="reduce")
                assert page.evaluate(await_motion) == "none"
                # The documented host theme contract must override the OS preference.
                page.evaluate("""() => {
                    document.documentElement.dataset.colorMode='light';
                    document.documentElement.style.setProperty('--background-color-default','#fafafa');
                    document.documentElement.style.setProperty('--text-color-default','#24292f');
                }""")
                assert page.locator("body").evaluate("(n)=>getComputedStyle(n).backgroundColor") == "rgb(250, 250, 250)"
                assert page.locator("body").evaluate("(n)=>getComputedStyle(n).color") == "rgb(36, 41, 47)"
                page.evaluate("""() => {
                    delete document.documentElement.dataset.colorMode;
                    document.documentElement.style.removeProperty('--background-color-default');
                    document.documentElement.style.removeProperty('--text-color-default');
                }""")

                summary = page.locator(".lane summary").first
                summary.focus()
                page.keyboard.press("Enter")
                assert page.locator(".lane").first.get_attribute("open") is not None
                data["subagents"][0]["currentActivity"] = "read"
                page.evaluate("refresh()")
                page.wait_for_function("() => document.querySelector('.lane .facts').textContent.includes('read')")
                assert summary.evaluate("(node)=>document.activeElement===node")
                assert page.locator(".lane").first.get_attribute("open") is not None
                assert page.locator(".lane").first.locator(".facts").inner_text().count("Fixture child model") == 1

                state_labels = {
                    "ready": "Ready", "working": "Working", "waiting": "Waiting for input",
                    "blocked": "Waiting for permission", "error": "Error reported", "idle": "Idle",
                    "stopped": "Stopped", "unavailable": "Activity unavailable",
                }
                for state, label in state_labels.items():
                    data["activity"] = state
                    data["activeTools"] = []
                    page.evaluate("refresh()")
                    page.wait_for_function("(label)=>document.querySelector('#activity').textContent===label", arg=label)
                    assert page.locator("#track").get_attribute("data-state") == state
                    assert "%" not in page.locator(".activity-note").inner_text()
                    assert page.locator("#track span").evaluate("(n)=>getComputedStyle(n).animationName") == "none"
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                data["usage"] = {"currentTokens": 302206, "tokenLimit": 922000, "capturedAt": "2026-10-08T21:00:00Z"}
                data["selectedModel"] = "long-provider-qualified-model-identifier-" * 3
                page.evaluate("refresh()")
                assert page.locator("#usage span").all_text_contents() == ["302,206", "/ 922,000"]
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

                data["subagents"][0].update(
                    name="Long host-provided name " * 8,
                    role="fixture-role-with-an-unbroken-name-" * 3,
                    assignedSlice="Long explicit assigned slice with unbroken-host-identifier-" * 4,
                    observedModel="model-with-long-provider-qualified-identity-" * 2,
                    status="completed",
                )
                data["activity"] = "working"
                page.evaluate("refresh()")
                page.wait_for_function("() => document.querySelector('.status-label').textContent==='Completed'")
                assert "Verified" not in page.locator(".lane").first.inner_text()
                overflow = page.evaluate("document.documentElement.scrollWidth > innerWidth")
                assert not overflow
                data["subagents"] = []
                data["subagentsStatus"] = "unavailable"
                data["selectedModel"] = data["selectedEffort"] = None
                data["observedModel"] = data["observedEffort"] = data["usage"] = None
                data["activity"] = "unavailable"
                page.evaluate("refresh()")
                page.wait_for_function("() => document.querySelector('#selected').textContent==='Unavailable'")
                assert page.locator("#meter").is_hidden()
                assert page.locator("#usage").inner_text() == "Unavailable"
                assert page.locator("#child-count").inner_text() == "Unavailable"
                assert page.locator("#children-empty").is_visible()
                assert page.locator(".lane").count() == 0
                page.screenshot(path=str(args.output / f"{name}-unknown.png"), full_page=True)

                page.locator("#source-details > summary").focus()
                page.keyboard.press("Enter")
                assert page.locator("#observed").inner_text() == "Not observed"
                page.locator("#enabled").uncheck()
                page.wait_for_function("() => !document.querySelector('#enabled').disabled")
                assert requests == [{"enabled": False}]
                assert not page.locator("#enabled").is_checked()
                page.evaluate("disconnect('Synthetic connection loss')")
                assert page.locator("#activity").inner_text() == "Disconnected"
                assert "last observed" in page.locator("#goal").inner_text()
                assert page.locator("#track").get_attribute("data-state") == "unavailable"
                page.evaluate("refresh()")
                page.wait_for_function("() => document.body.dataset.disconnected==='false'")
                assert page.locator("#error").inner_text() == ""

                colors = page.evaluate("""() => {
                    function rgb(value){const c=document.createElement('canvas').getContext('2d');c.fillStyle=value;c.fillRect(0,0,1,1);return [...c.getImageData(0,0,1,1).data].slice(0,3)}
                    const pairs=[];
                    for(const selector of ['.telemetry dt','.goal','.boundary','.source>summary']){
                        const n=document.querySelector(selector),surface=n.closest('.workspace')||document.body;
                        pairs.push([selector,rgb(getComputedStyle(n).color),rgb(getComputedStyle(surface).backgroundColor)]);
                    }
                    return pairs;
                }""")
                ratios = {selector: round(contrast(fg, bg), 2) for selector, fg, bg in colors}
                assert all(value >= 4.5 for value in ratios.values()), ratios
                assert page.locator("#close").evaluate("(n)=>n.getBoundingClientRect().height") >= 44
                page.locator("#close").click()
                page.wait_for_function("() => document.querySelector('#activity').textContent==='Closed'")
                page.evaluate("refresh()")
                assert page.locator("#activity").inner_text() == "Closed"
                assert page.locator("#enabled").is_disabled()
                assert not errors, errors
                receipts.append({"layout": name, "width": width, "scriptErrors": errors, "contrast": ratios,
                                 "states": list(state_labels), "keyboardAndFocusPreserved": True,
                                 "unknownUsageHidden": True, "longContentNoOverflow": True,
                                 "syntheticPreferencesAndClose": True})
                page.close()
        finally:
            browser.close()
    report = {"kind": "synthetic-browser-contract", "nativeHostProof": False,
              "rendererSha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(), "layouts": receipts}
    (args.output / "visual-receipts.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
