import os

def run(args, kit):
    notes_path='notes.md'
    rules_path='owner_rules.md'
    try:
        notes=open(notes_path,encoding='utf-8').read() if os.path.exists(notes_path) else ''
    except Exception:
        notes=''
    try:
        rules=open(rules_path,encoding='utf-8').read() if os.path.exists(rules_path) else ''
    except Exception:
        rules=''
    rules=rules.strip()
    suffix=('\n\n'+rules if rules else '')
    budget=max(0,3000-len(suffix))
    recent=notes[-budget:] if len(notes)>budget else notes
    if len(recent)==budget and '\n' in recent:
        recent=recent[recent.find('\n')+1:]
    out=(recent.rstrip()+suffix).strip()+'\n'
    out=out[:3000]
    open(notes_path,'w',encoding='utf-8').write(out)
    return {'ok':True,'chars':len(out),'rules_chars':len(rules),'rules_written':False}
