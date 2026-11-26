import httpx, io

def run(args, kit):
    url='https://soft-agreements-volt-urls.trycloudflare.com/s/UjU0CW5bx70ON-XXuIpzW93B/thisjonghoon_preview_20261126-1950.pdf'
    r=httpx.get(url,follow_redirects=False,timeout=20)
    out={'status':r.status_code,'content_type':r.headers.get('content-type'),'size':len(r.content)}
    if r.status_code!=200 or not r.content.startswith(b'%PDF'): return out
    errors=[]
    for name in ['pypdf','PyPDF2','fitz']:
        try:
            m=__import__(name)
            if name=='fitz':
                doc=m.open(stream=r.content,filetype='pdf'); pages=[p.get_text() for p in doc]
            else:
                doc=m.PdfReader(io.BytesIO(r.content)); pages=[p.extract_text() or '' for p in doc.pages]
            out.update({'library':name,'pages':pages}); return out
        except Exception as e: errors.append(name+': '+str(e))
    out['errors']=errors; return out