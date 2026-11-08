"""Conservative translation checks; flags are suspicions, never proof of censorship."""
import re
import unicodedata

ISSUE_LABELS = {
    'empty': '번역 결과 없음',
    'refused': '모델의 번역 거절 의심',
    'truncated': '응답이 중간에 잘림',
    'untranslated': '원문이 번역되지 않음',
    'wrong_language': '한국어 번역 여부 확인 필요',
    'missing_number': '원문의 번호·숫자 누락 의심',
    'shortened': '과도한 축약·누락 의심',
    'term_omission': '검열·의미 완화 의심(핵심 용어 누락)',
    'redacted': '검열·삭제 표기 의심',
    'format': '줄 대응을 확인하지 못함',
    'request_failed': '로컬 번역 요청 실패',
    'source_changed': '편집 후 원문 정보가 바뀜',
    'user_flagged': '사용자가 검열·의미 완화를 의심함',
}
REFUSAL = re.compile(r'(?:죄송|미안).{0,45}(?:번역|도와|제공|지원)|(?:번역|제공|도와드릴)\s*(?:할\s*)?수\s*없|(?:cannot|can.t|unable to)\s+(?:assist|help|translate|provide)|翻訳できません|お手伝いできません', re.I | re.S)
TERMS = [
    ('耳かき', r'귀\s*(?:청소|파|를\s*파|를\s*청소)'),
    ('催眠', r'최면'), ('耳舐め', r'귀.*핥'),
    ('オナニー', r'자위'), ('射精', r'사정'), ('淫語', r'음담|음란|야한\s*말'),
]


def assess(original, translated, done_reason='stop'):
    source = unicodedata.normalize('NFKC', original).strip()
    target = unicodedata.normalize('NFKC', translated).strip()
    issues = []
    if not target:
        issues.append('empty')
    if REFUSAL.search(target):
        issues.append('refused')
    if done_reason == 'length':
        issues.append('truncated')
    if target and source == target and re.search(r'[\u3040-\u30ff\u3400-\u9fff]', source):
        issues.append('untranslated')
    if target and re.search(r'[\u3040-\u30ff\u3400-\u9fff]', source) and not re.search(r'[\uac00-\ud7a3]', target):
        issues.append('wrong_language')
    if target and any(number not in target for number in re.findall(r'\d+', source)):
        issues.append('missing_number')
    if len(source) >= 12 and len(target) < len(source) * .22:
        issues.append('shortened')
    if target and any(term in source and not re.search(pattern, target) for term, pattern in TERMS):
        issues.append('term_omission')
    if re.search(r'\[(?:검열|삭제|redacted|censored)\]|\*{3,}', target, re.I) and not re.search(r'\[(?:검열|삭제|redacted|censored)\]|\*{3,}', source, re.I):
        issues.append('redacted')
    return list(dict.fromkeys(issues))
