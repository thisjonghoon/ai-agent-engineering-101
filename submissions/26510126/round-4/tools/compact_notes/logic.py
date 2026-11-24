from pathlib import Path

def run(args, kit):
    p=Path('notes.md')
    text=p.read_text() if p.exists() else ''
    limit=int(args.get('limit',3000))
    if len(text)<=limit:
        return {'written':False,'chars':len(text),'text':text}
    prefix='[압축됨: 최신 기록 우선]\n'
    body=text[-(limit-len(prefix)):]
    out=prefix+body
    p.write_text(out)
    return {'written':True,'chars':len(out),'text':out}
