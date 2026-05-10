// api/scheduled-publish.js
// 매 30분 GitHub Actions가 호출. manifest를 스캔해서 scheduled_at <= now 인
// status='scheduled' 글을 status='published'로 전환. 글 파일 + manifest 함께 갱신.

const REPO = 'daehongpark/korean-salaryman-blog';
const BRANCH = 'main';
const GH_API = 'https://api.github.com';

function ghHeaders(token) {
  return {
    Authorization: `token ${token}`,
    Accept: 'application/vnd.github.v3+json',
    'Content-Type': 'application/json',
  };
}

async function ghGet(path, token) {
  const res = await fetch(`${GH_API}/repos/${REPO}/contents/${path}?ref=${BRANCH}`, {
    headers: ghHeaders(token),
  });
  if (!res.ok) throw new Error(`ghGet ${path}: ${res.status} ${await res.text()}`);
  return res.json();
}

async function ghPut(path, contentB64, sha, message, token) {
  const res = await fetch(`${GH_API}/repos/${REPO}/contents/${path}`, {
    method: 'PUT',
    headers: ghHeaders(token),
    body: JSON.stringify({ message, content: contentB64, sha, branch: BRANCH }),
  });
  if (!res.ok) throw new Error(`ghPut ${path}: ${res.status} ${await res.text()}`);
  return res.json();
}

export default async function handler(req, res) {
  if (req.method !== 'POST' && req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  // 인증: SCHEDULED_PUBLISH_SECRET 헤더 일치 (설정된 경우만)
  const expectedSecret = process.env.SCHEDULED_PUBLISH_SECRET;
  if (expectedSecret) {
    const got = req.headers['x-publish-secret'];
    if (got !== expectedSecret) {
      return res.status(401).json({ error: 'Unauthorized' });
    }
  }

  const token = process.env.GH_PAT;
  if (!token) return res.status(500).json({ error: 'GH_PAT not configured' });

  try {
    // 1. manifest 로드
    const manifestFile = await ghGet('posts/manifest.json', token);
    const manifestRaw = Buffer.from(manifestFile.content, 'base64').toString('utf-8');
    const manifest = JSON.parse(manifestRaw);

    const nowIso = new Date().toISOString();
    const dueEntries = manifest.filter(p =>
      p && p.status === 'scheduled' &&
      p.scheduled_at &&
      p.scheduled_at <= nowIso
    );

    if (dueEntries.length === 0) {
      return res.status(200).json({ message: 'No scheduled posts due', count: 0, now: nowIso });
    }

    let publishedCount = 0;
    const errors = [];
    const publishedFilenames = new Set();

    // 2. 각 글 파일을 published로 갱신
    for (const entry of dueEntries) {
      try {
        const fileData = await ghGet(`posts/${entry.filename}`, token);
        const postRaw = Buffer.from(fileData.content, 'base64').toString('utf-8');
        const post = JSON.parse(postRaw);

        post.status = 'published';
        post.published_at = nowIso;
        // scheduled_at은 히스토리로 유지

        const newContentB64 = Buffer.from(JSON.stringify(post, null, 2), 'utf-8').toString('base64');
        await ghPut(
          `posts/${entry.filename}`,
          newContentB64,
          fileData.sha,
          `auto-publish (scheduled): ${entry.filename}`,
          token
        );
        publishedFilenames.add(entry.filename);
        publishedCount++;
      } catch (e) {
        errors.push({ filename: entry.filename, error: e.message });
      }
    }

    // 3. manifest 일괄 갱신 (개별 syncManifest 대신 한 번에)
    if (publishedCount > 0) {
      // manifest를 새로 로드 (위에서 글 파일 변경했으니 sha 충돌 방지)
      const freshManifestFile = await ghGet('posts/manifest.json', token);
      const freshManifestRaw = Buffer.from(freshManifestFile.content, 'base64').toString('utf-8');
      const freshManifest = JSON.parse(freshManifestRaw);

      const updatedManifest = freshManifest.map(p => {
        if (publishedFilenames.has(p.filename) && p.status === 'scheduled') {
          return { ...p, status: 'published', published_at: nowIso };
        }
        return p;
      });

      const manifestNewB64 = Buffer.from(
        JSON.stringify(updatedManifest, null, 2),
        'utf-8'
      ).toString('base64');
      await ghPut(
        'posts/manifest.json',
        manifestNewB64,
        freshManifestFile.sha,
        `manifest: scheduled publish ${publishedCount} posts`,
        token
      );
    }

    return res.status(200).json({
      message: `Published ${publishedCount} scheduled posts`,
      count: publishedCount,
      published: Array.from(publishedFilenames),
      errors,
      now: nowIso,
    });
  } catch (e) {
    return res.status(500).json({ error: 'Server error', detail: e.message });
  }
}
