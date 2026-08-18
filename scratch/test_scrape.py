import urllib.request
import re
import ssl
import html as html_parser

def test_scrape():
    url = 'https://t.me/s/ProxyMTProto'
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            raw_html = r.read().decode('utf-8', errors='ignore')
            
        # Decode HTML entities (like &amp;)
        html = html_parser.unescape(raw_html)
        print('HTML Length:', len(html))
        
        # Look for regex patterns matching tg://proxy or t.me/proxy
        mtproto_pattern = r'(?:tg://proxy\?server=[^"\'\s&]+&port=\d+&secret=[^"\'\s&]+|https://t\.me/proxy\?server=[^"\'\s&]+&port=\d+&secret=[^"\'\s&]+)'
        socks_pattern = r'(?:tg://socks\?server=[^"\'\s&]+&port=\d+(?:&user=[^"\'\s&]+)?(?:&pass=[^"\'\s&]+)?|https://t\.me/socks\?server=[^"\'\s&]+&port=\d+(?:&user=[^"\'\s&]+)?(?:&pass=[^"\'\s&]+)?)'
        
        mtproto_matches = re.findall(mtproto_pattern, html, re.IGNORECASE)
        socks_matches = re.findall(socks_pattern, html, re.IGNORECASE)
        
        print('MTProto Matches count:', len(mtproto_matches))
        print('Socks Matches count:', len(socks_matches))
        
        if mtproto_matches:
            print('Sample MTProto match:', mtproto_matches[0])
        if socks_matches:
            print('Sample Socks match:', socks_matches[0])
            
    except Exception as e:
        print('Error:', e)

if __name__ == '__main__':
    test_scrape()
