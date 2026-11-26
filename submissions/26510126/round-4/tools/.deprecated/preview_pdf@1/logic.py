import httpx, subprocess, tempfile, os

def run(args, kit):
    url='https://soft-agreements-volt-urls.trycloudflare.com/s/UjU0CW5bx70ON-XXuIpzW93B/thisjonghoon_preview_20261126-1950.pdf'
    r=httpx.get(url,follow_redirects=False,timeout=20)
    out={'status':r.status_code,'content_type':r.headers.get('content-type'),'size':len(r.content)}
    if r.status_code!=200 or not r.content.startswith(b'%PDF'):
        out['body_preview']=r.text[:1000]; return out
    try:
        p=subprocess.run(['pdftotext','-layout','-','-'],input=r.content,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
        out['text']=p.stdout.decode('utf-8','replace')[:25000]; out['error']=p.stderr.decode('utf-8','replace')[:1000]; out['returncode']=p.returncode
    except Exception as e: out['error']=str(e)
    return out