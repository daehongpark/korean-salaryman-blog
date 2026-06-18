// api/subscribe.js
// 우리 폼 → 우리 서버 → Substack 정확한 형식으로 전달.
// 브라우저 직접 호출은 no-cors/origin검증에 막히므로 Vercel 함수가 대리 호출한다.
// Substack 요구: form-urlencoded + 브라우저 User-Agent/Origin/Referer + ?nojs=true.

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });
  const { email, publication } = req.body || {};
  if (!email || !email.includes('@')) return res.status(400).json({ error: 'invalid email' });

  // publication: 'en'이면 영어 본진(koreansalarymanen), 그 외 기본은 본진(koreansalaryman)
  const pub = publication === 'en' ? 'koreansalarymanen' : 'koreansalaryman';

  try {
    const r = await fetch(`https://${pub}.substack.com/api/v1/free?nojs=true`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
        'Origin': `https://${pub}.substack.com`,
        'Referer': `https://${pub}.substack.com/`,
      },
      body: new URLSearchParams({ email, source: 'subscribe_page' }).toString(),
    });
    const text = await r.text();

    // 검증/디버깅용: Vercel 함수 로그에서 실제 Substack 응답 확인 가능
    console.log(`[subscribe] pub=${pub} email=${email} status=${r.status} body=${text.slice(0, 300)}`);

    // Substack은 성공 시 200 + JSON. 봇차단/실패면 비정상 응답(403 등)
    if (r.ok) {
      return res.status(200).json({ ok: true, status: r.status, body: text.slice(0, 200) });
    }
    return res.status(502).json({ ok: false, status: r.status, body: text.slice(0, 200) });
  } catch (e) {
    console.log(`[subscribe] error pub=${pub} email=${email} err=${String(e).slice(0, 300)}`);
    return res.status(500).json({ ok: false, error: String(e).slice(0, 200) });
  }
}
