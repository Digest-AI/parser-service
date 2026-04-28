from playwright.sync_api import sync_playwright

def get_html(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded")
        content = page.content()
        browser.close()
        return content

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(get_html(sys.argv[1]))
