import argparse
import json
from pathlib import Path
from time import sleep

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions


def build_driver(browser: str, headless: bool):
    if browser == "chrome":
        options = ChromeOptions()
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        if headless:
            options.add_argument("--headless=new")
        driver = webdriver.Chrome(options=options)
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return driver

    options = FirefoxOptions()
    options.add_argument("--disable-notifications")
    if headless:
        options.add_argument("--headless")
    return webdriver.Firefox(options=options)


def load_cookies(driver, cookie_path: Path):
    if not cookie_path.exists():
        raise FileNotFoundError(f"Cookie file not found: {cookie_path}")

    raw = json.loads(cookie_path.read_text(encoding="utf-8"))
    loaded = 0

    for cookie in raw:
        normalized = dict(cookie)
        normalized.pop("sameSite", None)

        expiry = normalized.get("expiry")
        if isinstance(expiry, float):
            normalized["expiry"] = int(expiry)

        try:
            driver.add_cookie(normalized)
            loaded += 1
        except WebDriverException:
            continue

    return loaded


def is_logged_in(driver):
    url = driver.current_url.lower()
    if "flow/login" in url:
        return False

    xpaths = [
        "//a[@data-testid='AppTabBar_Home_Link']",
        "//article[@data-testid='tweet']",
        "//div[@data-testid='SideNav_AccountSwitcher_Button']",
    ]

    for xpath in xpaths:
        try:
            driver.find_element("xpath", xpath)
            return True
        except NoSuchElementException:
            continue

    return False


def parse_args():
    parser = argparse.ArgumentParser(
        description="Test whether saved X/Twitter cookies still authenticate successfully.",
    )
    parser.add_argument(
        "--cookies",
        default="auth/session_cookies.json",
        help="Cookie file path (default: auth/session_cookies.json)",
    )
    parser.add_argument(
        "--browser",
        choices=["firefox", "chrome"],
        default="chrome",
        help="Browser to use (default: chrome)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser headless",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=3,
        help="Number of tweet snippets to print if available (default: 3)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    cookie_file = Path(args.cookies)

    try:
        driver = build_driver(args.browser, args.headless)
    except WebDriverException as exc:
        print(f"Failed to start browser: {exc}")
        raise SystemExit(1)

    try:
        driver.maximize_window()
        driver.get("https://x.com")

        loaded_count = load_cookies(driver, cookie_file)
        driver.get("https://x.com/home")
        sleep(4)

        print(f"Loaded cookies: {loaded_count}")
        print(f"Current URL: {driver.current_url}")

        if not is_logged_in(driver):
            print("Auth test FAILED: session does not appear to be logged in.")
            raise SystemExit(2)

        cards = driver.find_elements("xpath", "//article[@data-testid='tweet']")
        print(f"Auth test OK. Visible tweet cards: {len(cards)}")

        sample_count = max(0, min(args.sample, len(cards)))
        for idx in range(sample_count):
            snippet = cards[idx].text.strip().replace("\n", " ")
            if len(snippet) > 180:
                snippet = snippet[:180] + "..."
            print(f"[{idx + 1}] {snippet}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
