"""Build the public catalog from the numbered PNG files that actually exist."""
import hashlib
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = 500


def build():
    planned = {}
    for name in ['catalog-root.json', 'catalog-a.json', 'catalog-b.json', 'catalog-c.json']:
        source = ROOT / name
        if not source.exists():
            continue
        for item in json.loads(source.read_text()):
            number = int(item['id'])
            assert 1 <= number <= TARGET, number
            assert number not in planned, f'Duplicate ID {number}'
            planned[number] = item
    if not planned:
        for item in json.loads((ROOT / 'plan.json').read_text())['items']:
            planned[int(item['id'])] = item
    complete = []
    seen_ids = set()
    seen_hashes = set()
    reviewed_file = ROOT / 'reviewed.json'
    approved = None
    if reviewed_file.exists():
        reviewed = json.loads(reviewed_file.read_text())
        approved = set(reviewed['ids'])
        for name in ['progress-a.json', 'progress-b.json', 'progress-c.json']:
            progress_file = ROOT / name
            if progress_file.exists():
                progress = json.loads(progress_file.read_text())
                approved.update(progress.get('visual_review_passed_ids', []))
        reviewed['ids'] = sorted(approved)
        reviewed_file.write_text(json.dumps(reviewed, ensure_ascii=False, indent=2) + '\n')
    for file in sorted((ROOT / 'stickers').glob('*.png')):
        match = re.fullmatch(r'(\d{3})-(.+)\.png', file.name)
        assert match, f'Unexpected filename: {file.name}'
        number = int(match[1])
        if approved is not None and number not in approved:
            continue
        assert number not in seen_ids, f'Duplicate image number {number}'
        assert number in planned, f'Image missing catalog entry: {file.name}'
        item = planned[number]
        assert match[2] == item['caption'], f'Caption mismatch: {file.name}'
        data = file.read_bytes()
        assert data.startswith(b'\x89PNG\r\n\x1a\n'), file
        digest = hashlib.sha256(data).hexdigest()
        assert digest not in seen_hashes, f'Duplicate PNG: {file.name}'
        seen_ids.add(number)
        seen_hashes.add(digest)
        complete.append({
            'id': number, 'caption': item['caption'],
            'series': item['series'], 'path': file.relative_to(ROOT).as_posix(),
            'scene': item.get('scene', item.get('visual', '')),
            'sha256': digest, 'bytes': len(data),
            'text_type': '粉丝二创文案，非全部主播逐字语录',
        })
    result = {'target': TARGET, 'completed': len(complete), 'items': complete}
    (ROOT / 'catalog.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    cards = []
    for item in complete:
        caption = html.escape(item['caption'])
        series = html.escape(item['series'])
        path = html.escape(item['path'], quote=True)
        cards.append(f'<a class="card" href="{path}" download data-search="{caption} {series}"><img loading="lazy" src="{path}" alt="{caption}"><span>{item["id"]:03d} · {caption}</span><small>{series}</small></a>')
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>小小桃纸哟 · 表情包</title><style>*{box-sizing:border-box}body{margin:0;background:#fff5eb;color:#5a3128;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{max-width:1500px;margin:auto;padding:30px}h1{font-size:30px;margin:0 0 8px}.sub,small{color:#916b5d}input{width:100%;padding:13px 16px;margin:20px 0;border:1px solid #e4bca7;border-radius:14px;background:#fffcf8;font:inherit;color:inherit}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px}.card{display:block;padding:10px;border-radius:20px;background:#fffcf8;border:1px solid #f1dfd1;text-align:center;color:inherit;text-decoration:none}.card img{display:block;width:100%;aspect-ratio:1;object-fit:contain}.card span,.card small{display:block;margin:6px 0}.card[hidden]{display:none}footer{margin-top:24px;color:#916b5d;font-size:13px}</style><main><h1>小小桃纸哟 · 表情包</h1><div class="sub">已完成 COMPLETE / 500 张 · 点击图片下载透明 PNG</div><input id="search" aria-label="搜索文案或主题" placeholder="搜索文案或主题，例如：钓鱼、晚安、黑桃"><div class="grid">CARDS</div><footer>粉丝二创，非主播官方出品。文案为公开内容启发的创作，不全部作为主播原话。<a href="docs/research.md">调研与来源</a> · <a href="catalog.json">图片索引</a></footer></main><script>const cards=[...document.querySelectorAll('.card')];document.querySelector('#search').addEventListener('input',e=>{const q=e.target.value.trim().toLowerCase();cards.forEach(c=>c.hidden=!c.dataset.search.toLowerCase().includes(q));});</script></html>'''
    (ROOT / 'index.html').write_text(page.replace('COMPLETE', str(len(complete))).replace('CARDS', ''.join(cards)))
    preview = '\n'.join(f'| {i["id"]:03d} {i["caption"]} | ![{i["caption"]}]({i["path"]}) |' for i in complete[:10])
    state = '已完成' if len(complete) == TARGET else '制作中'
    quota_note = ''
    status_file = ROOT / 'status.json'
    if status_file.exists():
        status = json.loads(status_file.read_text())
        missing = sorted(set(range(1, TARGET + 1)) - seen_ids)
        ranges = []
        for number in missing:
            if ranges and number == ranges[-1]['to'] + 1:
                ranges[-1]['to'] = number
                ranges[-1]['count'] += 1
            else:
                ranges.append({'from': number, 'to': number, 'count': 1})
        status.update(completed=len(complete), remaining=len(missing),
                      missing_ids=missing, resume_ranges=ranges)
        if not missing:
            status['state'] = 'complete'
            status['reason'] = '500张图片已生成，已通过本地目录与完整性检查。'
        status_file.write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n')
        if missing and status.get('state') == 'waiting_for_image_quota':
            state = '等待出图额度恢复'
            quota_note = '\n内置图像生成额度已用完，预计 2026-10-29 19:34（上海时间）重置。剩余图片尚未生成。[续做记录](docs/resume.md) · [制作状态](status.json)\n'
    readme = f'''# 小小桃纸哟表情包

围绕 [小小桃纸哟（UID 6867955）](https://space.bilibili.com/6867955) 公开内容创作的 Q 版透明表情包。

**{state}：{len(complete)} / {TARGET} 张。** 每张独立绘制，统一橘发蓝眼、白领粉衣小熊形象。图片以实际落盘文件计数。
{quota_note}

- [全部图片](stickers/)：三位编号 + 中文文案，透明 PNG。
- [完整索引](catalog.json)：文案、主题、路径、SHA-256 校验值。
- [500 张制作目录](plan.json)：计划中的完整文案和主题；图片是否已完成以完整索引为准。
- [预览画廊](index.html)：下载仓库后，用浏览器打开，可按文案和主题筛选。
- [调研与创作说明](docs/research.md)：公开来源及文案边界。

## 首批预览

| 文案 | 图片 |
|---|---|
{preview}

## 说明

这是粉丝二创项目，非主播官方出品。文案包含有出处的历史梗及主题原创短句，不全部作为主播逐字原话。角色、头像及主播相关权益归相应权利人；本仓库不宣称获得主播背书或授予相关第三方权益。

制作：2026-10-28。使用内置 ImageGen 逐张生成。
'''
    (ROOT / 'README.md').write_text(readme)
    print(json.dumps({'planned': len(planned), 'completed': len(complete), 'target': TARGET}))


if __name__ == '__main__':
    build()
