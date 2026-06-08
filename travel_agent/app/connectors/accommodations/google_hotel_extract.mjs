import { existsSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'

// 구글 호텔 검색 화면을 렌더링해 호텔 카드(aria-label)에서 이름·가격·평점을 구조적으로 뽑는다.
// 사용법: node google_hotel_extract.mjs <url> <timeoutSec> <limit>
//   -> stdout: {"hotels": [{"name","amount","rating"}], "final_url": "..."}

const url = process.argv[2]
const timeoutMs = Number(process.argv[3] ?? '35') * 1000
const limit = Number(process.argv[4] ?? '12')

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
    await page.waitForFunction(() => /₩[\d,]{4,}/.test(document.body?.innerText ?? ''), undefined, {
      timeout: Math.max(8000, timeoutMs - 8000),
    })
  } catch {}
  await page.waitForTimeout(3000)

  const hotels = await page.evaluate((max) => {
    const out = []
    const seen = new Set()
    const re = /^최저가\s*₩([\d,]+),\s*(.+)$/
    const parseReviews = (s) => {
      const m = s.match(/\(([\d.]+)\s*(천|만)?\)/)
      if (!m) return null
      let n = parseFloat(m[1])
      if (m[2] === '천') n *= 1000
      if (m[2] === '만') n *= 10000
      return Math.round(n)
    }
    for (const el of document.querySelectorAll('[aria-label]')) {
      const label = (el.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim()
      const m = re.exec(label)
      if (!m) continue
      const name = m[2].split(/\s(?:파격|일반적인|할인|특가)/)[0].trim()
      if (!name || seen.has(name)) continue
      seen.add(name)
      // 카드 컨테이너 텍스트에서 평점·리뷰수·성급·편의시설을 함께 뽑는다.
      let node = el
      let txt = ''
      for (let i = 0; i < 7 && node; i++) {
        node = node.parentElement
        if (node && /성급|\(\d/.test(node.innerText || '')) {
          txt = (node.innerText || '').replace(/\s+/g, ' ')
          break
        }
      }
      const ratingM = txt.match(/(\d\.\d)\s*(?:\/\s*5|\()/)
      const starM = txt.match(/(\d)\s*성급/)
      let amenities = []
      const am = txt.match(/편의시설:\s*([^]+?)(?:,?\s*\d\s*성급|$)/)
      if (am) {
        amenities = am[1]
          .split(',')
          .map((s) => s.trim())
          .filter((s) => s && !/성급/.test(s))
          .slice(0, 6)
      }
      out.push({
        name,
        amount: parseInt(m[1].replace(/,/g, ''), 10),
        rating: ratingM ? parseFloat(ratingM[1]) : null,
        reviews: parseReviews(txt),
        star: starM ? parseInt(starM[1], 10) : null,
        amenities,
      })
      if (out.length >= max) break
    }
    return out
  }, limit)

  process.stdout.write(JSON.stringify({ hotels, final_url: page.url() }))
} finally {
  await browser.close()
}
