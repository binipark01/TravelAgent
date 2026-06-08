import { existsSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'

// 구글 지도 식당 검색 화면을 렌더링해 결과 카드에서 이름·평점·카테고리를 뽑는다.
// 사용법: node google_places_extract.mjs <url> <timeoutSec> <limit>
//   -> stdout: {"places": [{"name","rating","reviews","category"}], "final_url": "..."}

const url = process.argv[2]
const timeoutMs = Number(process.argv[3] ?? '35') * 1000
const limit = Number(process.argv[4] ?? '10')

if (!url) {
  console.error('source URL is required')
  process.exit(2)
}

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..')
const { chromium } = await import(
  pathToFileURL(path.join(repoRoot, 'frontend/node_modules/playwright-core/index.mjs')).href
)

const chromeCandidates = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean)
const executablePath = chromeCandidates.find((c) => existsSync(c))
if (!executablePath) {
  console.error('Chrome or Edge executable was not found')
  process.exit(2)
}

const browser = await chromium.launch({
  executablePath,
  headless: process.env.NAVER_HOTEL_HEADLESS !== 'false',
  args: [
    '--no-sandbox',
    '--disable-dev-shm-usage',
    '--disable-gpu',
    '--disable-extensions',
    '--disable-background-networking',
    '--blink-settings=imagesEnabled=false',
    '--disable-blink-features=AutomationControlled',
  ],
})
const BLOCKED = new Set(['image', 'media', 'font'])

try {
  const page = await browser.newPage({
    locale: 'ko-KR',
    viewport: { width: 1366, height: 900 },
    userAgent:
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
  })
  await page.route('**/*', (r) => (BLOCKED.has(r.request().resourceType()) ? r.abort() : r.continue()))
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: timeoutMs })
  try {
    await page.waitForFunction(() => document.querySelector('a[href*="/maps/place/"]') != null, undefined, {
      timeout: Math.max(8000, timeoutMs - 8000),
    })
  } catch {}
  await page.waitForTimeout(3500)

  const places = await page.evaluate((max) => {
    const out = []
    const seen = new Set()
    for (const card of document.querySelectorAll('[role="article"]')) {
      const link = card.querySelector('a[href*="/maps/place/"]')
      const name = (link?.getAttribute('aria-label') || '').trim()
      if (!name || seen.has(name)) continue
      seen.add(name)
      const t = (card.innerText || '').replace(/\s+/g, ' ')
      const rm = t.match(/(\d\.\d)\s*(?:\(([\d,]+)\))?/)
      const rating = rm ? parseFloat(rm[1]) : null
      const reviews = rm && rm[2] ? parseInt(rm[2].replace(/,/g, ''), 10) : null
      let category = null
      if (rm) {
        const after = t.slice(t.indexOf(rm[0]) + rm[0].length)
        const cm = after.match(/^\s*([^·]+?)\s*·/)
        if (cm) category = cm[1].trim()
      }
      out.push({ name, rating, reviews, category })
      if (out.length >= max) break
    }
    return out
  }, limit)

  process.stdout.write(JSON.stringify({ places, final_url: page.url() }))
} finally {
  await browser.close()
}
