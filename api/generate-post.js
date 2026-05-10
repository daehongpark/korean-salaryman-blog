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

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) return res.status(500).json({ error: 'GEMINI_API_KEY not configured' });

  const { keyword, category, context } = req.body || {};
  if (!keyword || !category) {
    return res.status(400).json({ error: 'keyword and category required' });
  }

  try {
    const template = await loadTemplate();
    const today = new Date().toISOString().slice(0, 10);
    const categoryIntent = template.category_intents[category] || template.category_intents.trending;
    const formatDirective = template.format_directives[categoryIntent.primary_format] || template.format_directives.guide;

    const contextBlock = context ? `\n[박대홍님이 추가로 지시한 글의 방향]\n${context}\n` : '';

    const prompt = [
      template.persona,
      ``,
      `[블로그 정보]`,
      `- 카테고리: ${category}`,
      `- 타겟 키워드: ${keyword}`,
      `- 작성 기준일: ${today}`,
      `- 대상 독자: ${categoryIntent.audience}`,
      contextBlock,
      formatDirective,
      ``,
      template.tone_guide,
      ``,
      template.tone_examples,
      ``,
      `[글 분량] 본문 ${template.common_rules.content_length}자 (공백 제외)`,
      ``,
      `[출력 형식 - 반드시 아래 JSON만 출력 (코드블록/설명/인사말 금지)]`,
      JSON.stringify({
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
      }, null, 2)
    ].join('\n');

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
