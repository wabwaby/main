// Realistic desktop Chrome headers. Bandai's CDN serves 403 for obvious
// scraper user-agents (curl/axios/python-requests), so every outbound
// request to gundam-gcg.com goes through these headers.
const BROWSER_HEADERS = {
    'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
        '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
    Accept:
        'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,' +
        'image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Cache-Control': 'no-cache',
    Pragma: 'no-cache',
    Referer: 'https://www.gundam-gcg.com/en/cards/',
};

const IMAGE_HEADERS = {
    ...BROWSER_HEADERS,
    Accept: 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
};

module.exports = { BROWSER_HEADERS, IMAGE_HEADERS };
