# 临时脚本：构建通用总词库(20000+) + 5 学段筛选规则
import json, csv, urllib.request, re, os
from collections import defaultdict

# 5 学段（筛选规则）+ 额外通用词表（扩充总词库，不带学段标签）
STAGE_RAW = {
    "中考": "https://raw.githubusercontent.com/genkin-he/english-vocabulary/master/json_simple/1-%E5%88%9D%E4%B8%AD-%E9%A1%BA%E5%BA%8F.json",
    "高考": "https://raw.githubusercontent.com/genkin-he/english-vocabulary/master/json_simple/2-%E9%AB%98%E4%B8%AD-%E9%A1%BA%E5%BA%8F.json",
}
EXTRA_RAW = {
    "托福": "https://raw.githubusercontent.com/genkin-he/english-vocabulary/master/json_simple/6-%E6%89%98%E7%A6%8F-%E9%A1%BA%E5%BA%8F.json",
    "SAT": "https://raw.githubusercontent.com/genkin-he/english-vocabulary/master/json_simple/7-SAT-%E9%A1%BA%E5%BA%8F.json",
}

def clean(s):
    s = s.strip().replace('， ', '，').replace('； ', '；')
    return re.sub(r'\s+', ' ', s)

def parse_json(fn):
    data = json.load(open(fn, encoding='utf-8'))
    groups = {}
    for it in data:
        w = (it.get('word') or '').strip()
        if not w or not re.fullmatch(r"[A-Za-z][A-Za-z'’\- ]*", w):
            continue
        parts = []
        for t in it.get('translations', []):
            tt = clean(t.get('translation') or '')
            ty = (t.get('type') or '').strip()
            ty = ty if (ty and re.fullmatch(r'[A-Za-z]{1,6}\.?', ty)) else ''
            if tt:
                parts.append(f'{ty}. {tt}' if ty else tt)
        trans = '；'.join(parts)
        if w not in groups or len(trans) > len(groups[w]):
            groups[w] = trans
    return groups

def read_csv(fn):
    d = {}
    with open(fn, encoding='utf-8-sig') as f:
        for row in csv.reader(f):
            if len(row) >= 2 and row[0].strip() and row[1].strip():
                d[row[0].strip()] = row[1].strip()
    return d

import time
os.makedirs('data/builtin', exist_ok=True)
for stage, url in {**STAGE_RAW, **EXTRA_RAW}.items():
    fn = f'data/builtin/_raw_{stage}.json'
    if os.path.exists(fn) and os.path.getsize(fn) > 1000:
        continue
    print('downloading', stage, flush=True)
    last_err = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            data = urllib.request.urlopen(req, timeout=120).read()
            open(fn, 'wb').write(data)
            print('  ok', stage, len(data), flush=True)
            last_err = None
            break
        except Exception as ex:
            last_err = ex
            print('  retry', stage, attempt, ex, flush=True)
            time.sleep(2 * (attempt + 1))
    if last_err:
        raise last_err

# 5 学段（来自 json 下载 + 已有 csv）
stage_words = {
    "中考": parse_json('data/builtin/_raw_中考.json'),
    "高考": parse_json('data/builtin/_raw_高考.json'),
    "四级": read_csv('data/builtin/level4.csv'),
    "六级": read_csv('data/builtin/level6.csv'),
    "考研": read_csv('data/builtin/kaoyan.csv'),
}
# 额外通用词（扩充总词库，不入 5 学段）
extra_words = {}
for stage in EXTRA_RAW:
    d = parse_json(f'data/builtin/_raw_{stage}.json')
    for w, t in d.items():
        if w not in extra_words or len(t) > len(extra_words[w]):
            extra_words[w] = t

for s, d in stage_words.items():
    print(s, len(d))
print('extra(托福+SAT) unique:', len(extra_words))

# 通用总词库 = 5 学段 ∪ 额外通用词
universe = {}
for d in list(stage_words.values()) + [extra_words]:
    for w, t in d.items():
        if w not in universe or len(t) > len(universe[w]):
            universe[w] = t

with open('data/universe.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    for word in sorted(universe):
        w.writerow([word, universe[word]])
print('universe words:', len(universe))

# 学段筛选（仅 5 学段）
stage_of_word = defaultdict(list)
for s, d in stage_words.items():
    for w in d:
        stage_of_word[w].append(s)

with open('data/stage_words.json', 'w', encoding='utf-8') as f:
    json.dump({w: stage_of_word[w] for w in universe if w in stage_of_word}, f, ensure_ascii=False)

print('DONE: universe.csv + stage_words.json')
