"""Read-only Korean labels and concise explanations; stored tags stay original."""
from functools import lru_cache
from tag_dictionary_data import LABELS as UPSTREAM_LABELS

NAMESPACES = {
    'artist': ['작가', '작품의 작가 이름입니다.'],
    'group': ['그룹', '작품을 제작한 그룹·서클 이름입니다.'],
    'parody': ['원작', '작품의 바탕이 된 원작·시리즈입니다.'],
    'character': ['캐릭터', '작품에 등장하는 캐릭터 이름입니다.'],
    'female': ['여성', '여성 인물에 적용되는 태그 분류입니다.'],
    'male': ['남성', '남성 인물에 적용되는 태그 분류입니다.'],
    'mixed': ['혼합', '여러 인물·성별에 걸쳐 적용되는 태그 분류입니다.'],
    'other': ['기타', '작품 전체의 소재·형식 등에 적용되는 태그 분류입니다.'],
    'language': ['언어', '작품에 사용된 언어·번역 상태입니다.'],
    'tag': ['일반', '작품의 소재·형식을 나타내는 일반 태그입니다.'],
    'cosplayer': ['코스플레이어', '코스프레를 한 사람의 이름입니다.'],
    'reclass': ['작품 종류', '원본 사이트의 작품 종류 분류입니다.'],
    'user': ['내 태그', '사용자가 붙인 태그입니다.'],
}
LABELS = {**UPSTREAM_LABELS, **{
    'language:korean': '한국어', 'language:japanese': '일본어',
    'language:english': '영어', 'language:chinese': '중국어',
    'language:spanish': '스페인어', 'language:french': '프랑스어',
    'language:german': '독일어', 'language:russian': '러시아어',
    'language:translated': '번역본', 'language:rewrite': '대사 개작',
    'language:textless': '글 없음', 'language:speechless': '대사 없음',
    'translated': '번역본', 'full color': '풀컬러', 'black and white': '흑백',
    'glasses': '안경', 'ponytail': '포니테일', 'artbook': '아트북',
    'ai generated': 'AI 생성', 'ai assisted': 'AI 보조',
    'short hair': '짧은 머리', 'long hair': '긴 머리', 'twintails': '트윈테일',
    'black hair': '검은 머리', 'blonde hair': '금발', 'white hair': '흰 머리',
    'red hair': '붉은 머리', 'blue hair': '파란 머리', 'hair ribbon': '머리 리본',
    'ribbon': '리본', 'hat': '모자', 'earrings': '귀걸이', 'eyepatch': '안대',
    'mask': '가면·마스크', 'boots': '부츠', 'kimono': '기모노', 'maid': '메이드',
    'schoolgirl uniform': '여학생 교복', 'schoolboy uniform': '남학생 교복',
    'suit': '정장', 'apron': '앞치마', 'animal ears': '동물 귀', 'catgirl': '고양이 소녀',
    'fox girl': '여우 소녀', 'elf': '엘프', 'robot': '로봇', 'uncensored': '무검열',
    'mosaic censorship': '모자이크 검열', 'rough translation': '번역 품질 주의',
    'poor grammar': '문법 품질 주의', 'anthology': '앤솔러지', 'compilation': '합본',
    'webtoon': '웹툰', '4-koma': '4컷 만화', 'comic': '만화', 'non-h': '비성인',
    'first person perspective': '1인칭 시점',
    'parody:original': '오리지널', 'original': '오리지널',
}}
# Authored factual definitions. Names and unmapped terms never get invented lore.
DESCRIPTIONS = {
    'glasses': '인물이 안경을 착용합니다.',
    'ponytail': '머리카락을 뒤쪽에서 하나로 묶은 머리 모양입니다.',
    'twintails': '머리카락을 양쪽으로 나누어 묶은 머리 모양입니다.',
    'short hair': '짧은 머리 모양을 나타냅니다.',
    'long hair': '긴 머리 모양을 나타냅니다.',
    'black hair': '검은색 머리카락을 나타냅니다.',
    'blonde hair': '금발 머리카락을 나타냅니다.',
    'white hair': '흰색 머리카락을 나타냅니다.',
    'red hair': '붉은색 머리카락을 나타냅니다.',
    'blue hair': '파란색 머리카락을 나타냅니다.',
    'ribbon': '리본 장식을 착용합니다.',
    'hair ribbon': '머리에 리본 장식을 착용합니다.',
    'hat': '모자를 착용합니다.',
    'earrings': '귀걸이를 착용합니다.',
    'eyepatch': '한쪽 눈에 안대를 착용합니다.',
    'mask': '얼굴에 가면·마스크를 착용합니다.',
    'boots': '발목 위까지 올라오는 부츠를 착용합니다.',
    'kimono': '일본 전통 의상인 기모노를 착용합니다.',
    'maid': '메이드 역할·복장을 나타냅니다.',
    'schoolgirl uniform': '여학생 교복을 착용합니다. 나이를 확정하는 태그는 아닙니다.',
    'schoolboy uniform': '남학생 교복을 착용합니다. 나이를 확정하는 태그는 아닙니다.',
    'suit': '정장 차림을 나타냅니다.',
    'apron': '앞치마를 착용합니다.',
    'animal ears': '동물 형태의 귀가 있는 인물을 나타냅니다.',
    'catgirl': '고양이의 귀·꼬리 같은 특징을 가진 여성 캐릭터입니다.',
    'fox girl': '여우의 귀·꼬리 같은 특징을 가진 여성 캐릭터입니다.',
    'elf': '엘프라는 가상의 종족을 나타냅니다.',
    'robot': '로봇 캐릭터가 등장합니다.',
    'full color': '작품 전체가 컬러로 채색되어 있습니다.',
    'black and white': '흑백으로 표현된 작품입니다.',
    'uncensored': '원본 사이트에서 검열 표시가 없는 판본으로 분류한 태그입니다.',
    'mosaic censorship': '원본에 모자이크 처리가 있는 판본입니다.',
    'rough translation': '원본 사이트에서 번역 품질에 주의가 필요하다고 분류한 태그입니다.',
    'poor grammar': '원본 사이트에서 문법·문장 품질에 주의가 필요하다고 분류한 태그입니다.',
    'artbook': '삽화·설정화 등을 모은 화집 형식입니다.',
    'anthology': '여러 작가의 작품을 모은 선집 형식입니다.',
    'compilation': '여러 작품·회차를 하나로 묶은 합본입니다.',
    'webtoon': '웹에서 연재하는 만화 형식입니다.',
    '4-koma': '네 칸을 기본 단위로 구성한 만화 형식입니다.',
    'comic': '그림과 칸을 이용해 이야기를 전개하는 만화입니다.',
    'non-h': '원본 사이트의 비성인 작품 분류 태그입니다.',
    'ai generated': '생성형 AI로 제작된 이미지가 있는 작품입니다.',
    'ai assisted': '제작 과정에 생성형 AI를 보조 도구로 사용한 작품입니다.',
    'first person perspective': '인물의 시점에서 바라보는 구도입니다.',
    'parody:original': '기존 원작의 패러디가 아닌 오리지널 작품으로 분류합니다.',
    'original': '기존 원작의 패러디가 아닌 오리지널 작품으로 분류합니다.',
    'translated': '원래 언어에서 다른 언어로 번역한 판본입니다.',
    'language:translated': '원래 언어에서 다른 언어로 번역한 판본입니다.',
    'language:rewrite': '원래 대사를 다른 내용으로 바꾼 판본입니다.',
    'language:textless': '문자가 없는 판본입니다.',
    'language:speechless': '인물의 대사가 없는 판본입니다.',
}
GENERAL = {'', 'female', 'male', 'mixed', 'other', 'tag'}


@lru_cache(maxsize=16384)
def tag_words(tag):
    key = tag.casefold()
    namespace, _, value = key.partition(':')
    if not value:
        namespace, value = '', key
    translated = LABELS.get(key) or (LABELS.get(value, '') if namespace in GENERAL else '')
    return (tag + ' ' + translated).casefold()


def dictionary():
    return {'labels': LABELS, 'descriptions': DESCRIPTIONS, 'namespaces': NAMESPACES,
            'source': 'https://github.com/project-violet/tag-info/tree/51233c8df9fd5d2247a82865ebef29cad8664b26'}
