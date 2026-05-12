import { promises as fs } from 'fs';
import path from 'path';

let _template = null;
async function loadTemplate() {
  if (_template) return _template;
  const templatePath = path.join(process.cwd(), 'prompt_template.json');
  const content = await fs.readFile(templatePath, 'utf-8');
  _template = JSON.parse(content);
  return _template;
}

function buildPrompt(template, params) {
  const { keyword, category, context, mode, original_text } = params;
  const today = new Date().toISOString().slice(0, 10);
  const categoryIntent = template.category_intents[category] || template.category_intents.trending;
  const formatDirective = template.format_directives[categoryIntent.primary_format] || template.format_directives.guide;

  const contextBlock = context ? `\n[박대홍님이 추가로 지시한 글의 방향]\n${context}\n` : '';

  // 네이버 변형 모드: 원문을 박대홍 톤으로 재구성 (단일 진실 소스 prompt_template.json 재사용)
  const transformBlock = (mode === 'naver_transform' && original_text)
    ? `
[모드: 네이버 블로그 글 변형]
박대홍이 네이버 블로그에 올렸던 원문을 이 사이트(직장인 수익일기)용으로 변형합니다.

[원문]
"""
${original_text}
"""

[변형 규칙 — 매우 중요]
- 원문의 핵심 정보/주장/경험은 보존하되, 표현·문장 구조는 바꿀 것 (Google 중복 콘텐츠 회피)
- 분량은 원문의 1.3~1.5배로 늘리고, 박대홍 본인 경험/맥락을 더 풀어쓸 것
- 위·아래 톤가이드·페르소나·가독성 도구 100% 적용. 원문에 이모지/광고체 표현이 있어도 절대 따라가지 말 것
- AEO/GEO 필드(tldr / target_audience / comparison_table / steps / chart / faq / references / summary / tags) 모두 출력
- 마크다운 헤더는 ## 사용 (HTML 변환은 finalize 단계에서 처리)
`
    : '';

  const outputSchema = {
    title: "제목 (28~38자)",
    category: category,
    keyword: keyword,
    tldr: ["3줄 요약 첫번째", "두번째", "세번째"],
    target_audience: "이 글은 ___을 위한 글입니다",
    content: "도입부 + ## H2 4~5개 본문",
    summary: "2문장 핵심 요약 (각 70자 이내)",
    tags: [keyword, category, "직장인"],
    faq: [
      { q: "질문1", a: "답변1" },
      { q: "질문2", a: "답변2" },
      { q: "질문3", a: "답변3" },
      { q: "질문4", a: "답변4" },
      { q: "질문5", a: "답변5" }
    ],
    references: [{ label: "공식 사이트", url: "https://..." }],
    chart: {
      type: "(line/bar/doughnut/radar 중 하나, 없으면 빈 문자열)",
      title: "차트 제목",
      labels: ["X축1", "X축2"],
      datasets: [{ label: "시리즈명", data: [10, 20] }]
    }
  };

  return [
    template.persona,
    ``,
    `[블로그 정보]`,
    `- 카테고리: ${category}`,
    `- 타겟 키워드: ${keyword}`,
    `- 작성 기준일: ${today}`,
    `- 대상 독자: ${categoryIntent.audience}`,
    contextBlock,
    transformBlock,
    formatDirective,
    ``,
    template.tone_guide,
    ``,
    template.tone_examples,
    ``,
    `[글 분량] 본문 ${template.common_rules.content_length}자 (공백 제외)`,
    ``,
    `[출력 형식 - 반드시 아래 JSON만 출력 (코드블록/설명/인사말 금지)]`,
    JSON.stringify(outputSchema, null, 2)
  ].join('\n');
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) return res.status(500).json({ error: 'GEMINI_API_KEY not configured' });

  const { keyword, category, context, mode, original_text } = req.body || {};

  if (mode === 'naver_transform') {
    if (!original_text || !category) {
      return res.status(400).json({ error: 'original_text and category required for naver_transform' });
    }
  } else {
    if (!keyword || !category) {
      return res.status(400).json({ error: 'keyword and category required' });
    }
  }

  try {
    const template = await loadTemplate();
    // naver_transform 모드에서 keyword 미지정시 category로 폴백 (스키마 일관성 유지)
    const effectiveKeyword = keyword || category;
    const prompt = buildPrompt(template, {
      keyword: effectiveKeyword,
      category,
      context,
      mode,
      original_text
    });

    const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${apiKey}`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: { temperature: 0.95, topP: 0.92, maxOutputTokens: 8192 }
      })
    });

    if (!response.ok) {
      const errText = await response.text();
      return res.status(response.status).json({ error: 'Gemini API error', detail: errText });
    }

    const data = await response.json();
    const text = data.candidates?.[0]?.content?.parts?.[0]?.text || '';
    return res.status(200).json({ text, raw: data });
  } catch (e) {
    return res.status(500).json({ error: 'Server error', detail: e.message });
  }
}
