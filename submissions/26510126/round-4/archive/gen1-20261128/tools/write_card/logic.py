import json

def run(args, kit):
    desc = str(args.get('description', ''))[:1500]
    skills = args.get('skills') or []
    out = []
    for s in skills[:10]:
        if isinstance(s, dict):
            out.append({'id': str(s.get('id', 'skill'))[:40], 'name': str(s.get('name', ''))[:80], 'description': str(s.get('description', ''))[:400], 'tags': ['shop']})
    card = {'name': kit.name, 'description': desc, 'version': '1.0.0', 'skills': out}
    with open('card.json', 'w', encoding='utf-8') as f:
        json.dump(card, f, ensure_ascii=False)
    return {'ok': True, 'path': 'card.json', 'bytes': len(json.dumps(card, ensure_ascii=False))}
