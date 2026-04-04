import argparse
import json
from pathlib import Path
from time import sleep

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
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


def save_cookies(driver, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cookies = driver.get_cookies()
    output_path.write_text(json.dumps(cookies, indent=2), encoding="utf-8")
    return len(cookies)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Open browser for manual X/Twitter login and save session cookies.",
    )
    parser.add_argument(
        "--output",
        default="auth/session_cookies.json",
        help="Cookie output file path (default: auth/session_cookies.json)",
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
        help="Run browser in headless mode (not recommended for manual login)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    cookie_file = Path(args.output)

    try:
        driver = build_driver(args.browser, args.headless)
    except WebDriverException as exc:
        print(f"Failed to start browser: {exc}")
        raise SystemExit(1)

    try:
        driver.maximize_window()
        driver.get("https://x.com/i/flow/login")

        print("Browser opened at X login page.")
        print("1) Complete login manually in the browser.")
        print("2) After you can see your home feed, come back here and press Enter.")
        input("Press Enter to save cookies... ")

        # Give the browser one moment to settle after navigation.
        sleep(1)
        count = save_cookies(driver, cookie_file)
        print(f"Saved {count} cookies to: {cookie_file}")
        print("Manual auth bootstrap complete.")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
