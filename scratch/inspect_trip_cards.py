from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
        viewport={"width": 1366, "height": 850},
    )
    page = context.new_page()
    url = "https://www.trip.com/flights/showfarefirst?dcity=fln&acity=gig&ddate=2026-12-25&triptype=ow&class=y&quantity=1&lowpricesource=searchform"
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(8000)
    
    # Evaluate in page to find flight cards and their selectors
    info = page.evaluate("""() => {
        const cards = [];
        // Look for elements containing price or airline
        const allElements = document.querySelectorAll('*');
        for (const el of allElements) {
            const txt = el.innerText || '';
            // If it contains GOL or LATAM and has price and is a card container
            if ((txt.includes('LATAM') || txt.includes('Gol') || txt.includes('Azul')) && 
                (txt.includes('US$') || txt.includes('R$')) && 
                el.children.length > 2 && el.children.length < 20 &&
                el.offsetWidth > 300 && el.offsetHeight > 80 && el.offsetHeight < 400) {
                cards.push({
                    tagName: el.tagName,
                    className: el.className,
                    textSnippet: txt.substring(0, 150).replace(/\\n/g, ' ')
                });
            }
        }
        return cards;
    }""")
    print("Found potential cards:", len(info))
    for c in info[:10]:
        print(f"Class: '{c['className']}' | Snippet: {c['textSnippet']}")
    browser.close()
