from pathlib import Path

def edit(text, args):
    lines = text.splitlines()
    if args.get('remove_today'):
        keys = ('요거트는 01:03', '01:40 우유·사과', '요거트 01:03', '우유·사과 마감 할인')
        lines = [x for x in lines if not any(k in x for k in keys)]
    if args.get('remove_test_line'):
        lines = [x for x in lines if x.strip() != '새 교훈: 재고는 소량 시험 매입']
    out = '\n'.join(lines).rstrip()
    append = args.get('append')
    if append:
        out = (out + '\n' if out else '') + str(append).strip()
    return out

def run(args, kit):
    p = Path('owner_rules.md')
    text = p.read_text(encoding='utf-8') if p.exists() else ''
    out = edit(text, args)
    if getattr(kit, 'testing', False):
        return {'ok': True, 'text': out}
    p.write_text(out + ('\n' if out else ''), encoding='utf-8')
    return {'ok': True, 'path': str(p), 'lines': len(out.splitlines()) if out else 0}
