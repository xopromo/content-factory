#!/usr/bin/env python3
"""
Threads Comment Agent using Selenium for real browser automation
This bypasses Instagram bot detection by using actual Chrome browser
"""
import time
import json
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager


class ThreadsSeleniumAgent:
    """Threads agent using Selenium for real browser automation"""

    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.driver = None
        self.wait = None

    def _load_config(self) -> dict:
        """Load configuration from JSON file"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"❌ Config file not found: {self.config_path}")
            raise

    def _init_driver(self, headless: bool = False):
        """Initialize Chrome WebDriver with proper options"""
        print("🚀 Initializing Chrome WebDriver...")

        chrome_options = Options()

        # User-Agent to appear as real browser
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

        # Security and performance options
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        if headless:
            chrome_options.add_argument("--headless=new")

        # Initialize driver
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )

        # Set explicit wait
        self.wait = WebDriverWait(self.driver, 15)

        print("✅ Chrome WebDriver initialized")

    def _check_already_logged_in(self) -> bool:
        """Check if already logged in by looking for profile elements"""
        try:
            # Try to find profile icon or home feed
            self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(@href, '/')]"))
            )
            print("✅ Already logged in to Threads")
            return True
        except:
            return False

    def login(self):
        """Log in to Threads"""
        print("\n🔐 Logging in...")
        username = self.config["account"]["username"]
        password = self.config["account"]["password"]

        # Navigate to Threads
        self.driver.get("https://www.threads.net/")
        print("📍 Navigated to https://www.threads.net/")

        # Wait for page to load
        time.sleep(3)

        # Check if already logged in
        if self._check_already_logged_in():
            return True

        print("🔍 Looking for login form...")

        # Wait for login elements to appear
        # Instagram/Threads redirects to login page
        try:
            # Method 1: Try username field directly
            print("  Waiting for username input...")
            username_input = self.wait.until(
                EC.presence_of_element_located((By.NAME, "username"))
            )
            print("  ✅ Found username input")
        except:
            try:
                # Method 2: Try finding by type attribute
                print("  Username not found by name, trying by type...")
                username_input = self.wait.until(
                    EC.presence_of_element_located((By.XPATH, "//input[@type='text'][1]"))
                )
                print("  ✅ Found text input")
            except:
                # Method 3: Look for any input and take first one
                print("  Trying to find any input field...")
                inputs = self.driver.find_elements(By.TAG_NAME, "input")
                if not inputs:
                    print("❌ No input fields found on page")
                    print("📸 Page title:", self.driver.title)
                    print("📸 Current URL:", self.driver.current_url)

                    # Save page source for debugging
                    with open("debug_page.html", "w", encoding="utf-8") as f:
                        f.write(self.driver.page_source)
                    print("💾 Saved page source to debug_page.html")
                    return False

                username_input = inputs[0]
                print(f"  ✅ Found input field ({len(inputs)} inputs total)")

        # Enter username
        username_input.clear()
        username_input.send_keys(username)
        print(f"  ✅ Entered username: {username}")
        time.sleep(1)

        # Find and fill password field
        try:
            password_input = self.wait.until(
                EC.presence_of_element_located((By.NAME, "password"))
            )
            print("  ✅ Found password input")
        except:
            try:
                # Try finding password field by type
                password_input = self.wait.until(
                    EC.presence_of_element_located((By.XPATH, "//input[@type='password']"))
                )
                print("  ✅ Found password input (by type)")
            except:
                print("❌ Password input not found")
                return False

        # Enter password
        password_input.clear()
        password_input.send_keys(password)
        print(f"  ✅ Entered password")
        time.sleep(1)

        # Find and click login button
        try:
            login_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Log in') or contains(text(), 'login')]"))
            )
            print("  ✅ Found login button")
            login_button.click()
            print("  🔄 Clicked login button")
        except:
            try:
                # Try finding submit button
                login_button = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//button[@type='submit']"))
                )
                print("  ✅ Found submit button")
                login_button.click()
                print("  🔄 Clicked submit button")
            except:
                print("❌ Login button not found")
                return False

        # Wait for page to load after login
        time.sleep(5)

        # Check if login was successful
        try:
            self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(@href, 'create')]"))
            )
            print("✅ Login successful!")
            return True
        except:
            print("⚠️  Login may have failed - page didn't load expected elements")
            print("📸 Current URL:", self.driver.current_url)
            return False

    def search_hashtag(self, hashtag: str):
        """Search for posts with a specific hashtag"""
        print(f"\n🔍 Searching for {hashtag}...")

        # Wait for page to be ready
        time.sleep(2)

        # Find search input
        try:
            # Try search by placeholder
            search_input = self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Search']"))
            )
            print("  ✅ Found search input (by placeholder)")
        except:
            try:
                # Try finding search input by type
                search_input = self.wait.until(
                    EC.presence_of_element_located((By.XPATH, "//input[@type='text']"))
                )
                print("  ✅ Found search input (by type)")
            except:
                try:
                    # Look for any input field
                    inputs = self.driver.find_elements(By.TAG_NAME, "input")
                    if inputs:
                        search_input = inputs[0]
                        print(f"  ✅ Found input field ({len(inputs)} available)")
                    else:
                        print("❌ No search input found")
                        return False
                except:
                    print("❌ Search input not found")
                    return False

        # Enter hashtag
        search_input.clear()
        search_input.send_keys(hashtag)
        print(f"  ✅ Entered search term: {hashtag}")
        time.sleep(2)

        # Press Enter to search
        search_input.submit()
        print("  🔄 Submitted search")

        # Wait for search results
        time.sleep(5)

        print(f"✅ Search completed for {hashtag}")

    def find_and_comment_first_post(self, comment_text: str = "Отличный пост! 👍"):
        """Find first post and post a comment"""
        print(f"\n💬 Looking for first post to comment...")

        try:
            # Wait for post elements
            posts = self.wait.until(
                EC.presence_of_all_elements_located((By.XPATH, "//article"))
            )
            print(f"  ✅ Found {len(posts)} posts")

            if not posts:
                print("❌ No posts found")
                return False

            # Get first post
            first_post = posts[0]
            print("  📌 Got first post element")

            # Find reply button in the post
            try:
                reply_button = first_post.find_element(By.XPATH, ".//button[contains(@aria-label, 'Reply')]")
                print("  ✅ Found reply button")
            except:
                try:
                    # Try finding comment button
                    reply_button = first_post.find_element(By.XPATH, ".//button[contains(text(), 'Reply')]")
                    print("  ✅ Found reply button (by text)")
                except:
                    # Try any button that looks like reply
                    buttons = first_post.find_elements(By.TAG_NAME, "button")
                    if len(buttons) < 3:
                        print(f"❌ Not enough buttons found ({len(buttons)})")
                        return False
                    reply_button = buttons[2]  # Reply is usually 3rd button
                    print(f"  ✅ Using button at index 2 ({len(buttons)} buttons total)")

            # Click reply button
            self.driver.execute_script("arguments[0].scrollIntoView();", first_post)
            reply_button.click()
            print("  🔄 Clicked reply button")
            time.sleep(2)

            # Find comment text area
            try:
                comment_area = self.wait.until(
                    EC.presence_of_element_located((By.XPATH, "//textarea"))
                )
                print("  ✅ Found comment textarea")
            except:
                try:
                    # Try finding contenteditable div
                    comment_area = self.wait.until(
                        EC.presence_of_element_located((By.XPATH, "//*[@contenteditable='true']"))
                    )
                    print("  ✅ Found editable text area")
                except:
                    print("❌ Comment area not found")
                    return False

            # Type comment
            comment_area.click()
            comment_area.clear()
            comment_area.send_keys(comment_text)
            print(f"  ✅ Typed comment: {comment_text}")
            time.sleep(1)

            # Find and click post button
            try:
                post_button = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Reply') or contains(text(), 'Post')]"))
                )
                print("  ✅ Found post button")
            except:
                post_buttons = self.driver.find_elements(By.TAG_NAME, "button")
                if not post_buttons:
                    print("❌ No post button found")
                    return False
                post_button = post_buttons[-1]  # Usually last button
                print(f"  ✅ Using last button as post button")

            # Click post button
            post_button.click()
            print("  🔄 Clicked post button")
            time.sleep(3)

            print("✅ Comment posted successfully!")
            return True

        except Exception as e:
            print(f"❌ Error commenting on post: {e}")
            return False

    def run(self, headless: bool = False):
        """Run the full agent"""
        print("=" * 60)
        print("🤖 THREADS SELENIUM AGENT")
        print("=" * 60)

        try:
            # Initialize driver
            self._init_driver(headless=headless)

            # Login
            if not self.login():
                print("❌ Login failed")
                return False

            # Search for hashtag
            hashtags = self.config.get("search", {}).get("hashtags", ["#AI"])
            for hashtag in hashtags[:1]:  # First hashtag only
                self.search_hashtag(hashtag)

                # Comment on first post
                if self.find_and_comment_first_post():
                    print("\n✅ Agent completed successfully!")
                    return True

            print("\n⚠️  No comments posted")
            return False

        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return False

        finally:
            if self.driver:
                time.sleep(2)
                self.driver.quit()
                print("\n🏁 Browser closed")


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Threads Selenium Agent")
    parser.add_argument("--config", default="config.json", help="Config file path")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")

    args = parser.parse_args()

    agent = ThreadsSeleniumAgent(args.config)
    success = agent.run(headless=args.headless)

    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
