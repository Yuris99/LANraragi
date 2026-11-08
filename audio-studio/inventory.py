"""Read-only media inventory. Reports candidates; never imports or merges works."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re

RJ = re.compile(r'(?<![A-Za-z0-9])RJ[0-9]{6,12}(?![0-9])', re.I)
SUPPORTED_AUDIO = {'.mp3', '.m4a', '.aac', '.ogg', '.opus', '.wav', '.flac'}
SUPPORTED_VIDEO = {'.mp4', '.webm'}
OTHER_MEDIA = {'.wma', '.aiff', '.aif', '.ape', '.m4b', '.m4v', '.mkv', '.avi', '.mov', '.wmv', '.flv'}


def codes(value):
    return sorted({match.upper() for match in RJ.findall(value)})


def category(suffix):
    if suffix in SUPPORTED_AUDIO:
        return 'audio'
    if suffix in SUPPORTED_VIDEO:
        return 'video'
    if suffix in OTHER_MEDIA:
        return 'other_media'
    if suffix in {'.srt', '.vtt', '.ass', '.ssa', '.smi', '.lrc'}:
        return 'subtitle'
    if suffix in {'.zip', '.rar', '.7z', '.tar', '.gz'}:
        return 'archive'
    if suffix in {'.txt', '.pdf', '.doc', '.docx', '.html', '.htm', '.json', '.url', '.xml', '.csv'}:
        return 'document_or_metadata'
    if suffix in {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'}:
        return 'image'
    return 'other'


def scan(root):
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Inventory root must be a directory')
    files, errors, skipped_links = [], [], []
    directories = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            children = sorted(directory.iterdir(), key=lambda p: p.name.casefold())
        except OSError as exc:
            errors.append({'path': str(directory.relative_to(root)), 'error': str(exc)})
            continue
        for child in children:
            relative = child.relative_to(root)
            try:
                if child.is_symlink() or (hasattr(child, 'is_junction') and child.is_junction()):
                    skipped_links.append(str(relative))
                    continue
                if child.is_dir():
                    directories += 1
                    pending.append(child)
                    continue
                stat = child.stat()
                own_codes = codes(child.name)
                parent_codes = codes(str(relative.parent))
                candidates = sorted(set(own_codes + parent_codes))
                files.append({'path': str(relative), 'top': relative.parts[0],
                              'bytes': stat.st_size, 'extension': child.suffix.lower(),
                              'category': category(child.suffix.lower()),
                              'filename_codes': own_codes, 'folder_codes': parent_codes,
                              'candidate_codes': candidates,
                              'review': 'missing_code' if not candidates else
                                        'multiple_codes' if len(candidates) > 1 else 'candidate'})
            except OSError as exc:
                errors.append({'path': str(relative), 'error': str(exc)})
    return {'root': str(root), 'scanned_at': datetime.now(timezone.utc).isoformat(),
            'method': 'Names and sizes only; no file contents, archive extraction, hashes, import or merging.',
            'directories': directories, 'files': files, 'errors': errors, 'skipped_links': skipped_links,
            'summary': {'files': len(files), 'bytes': sum(f['bytes'] for f in files),
                        'extensions': dict(Counter(f['extension'] or '(none)' for f in files)),
                        'categories': dict(Counter(f['category'] for f in files)),
                        'review': dict(Counter(f['review'] for f in files)),
                        'unique_candidate_codes': len({c for f in files for c in f['candidate_codes']})}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve(strict=True)
    output = Path(args.output).resolve()
    if output == root or root in output.parents:
        parser.error('Output must be outside the inventory root')
    if output.exists():
        parser.error('Output already exists; choose a new report path')
    report = scan(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'summary': report['summary'], 'errors': len(report['errors']),
                      'skipped_links': len(report['skipped_links']), 'report': str(output)}, ensure_ascii=False))
    if report['errors']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
