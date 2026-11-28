import httpx,json

def run(args,kit):
 c=httpx.get(kit.market+'/entities/forum/.well-known/agent-card.json',timeout=10)
 card=c.json(); skills=card.get('skills',[])
 return {'card':card,'skills':skills}
