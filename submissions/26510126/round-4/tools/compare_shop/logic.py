import httpx
def run(args,kit):
 r=httpx.get('https://blast-owns-betty-described.trycloudflare.com/.well-known/agent-card.json',timeout=20,follow_redirects=False)
 return {'status':r.status_code,'body':r.text[:25000]}
