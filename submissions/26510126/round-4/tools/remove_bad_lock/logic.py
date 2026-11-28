import json

def run(args,kit):
    path='checkout_locks.json'
    try:
        with open(path,encoding='utf-8') as f: locks=json.load(f)
    except Exception as e:
        return {'error':str(e)}
    if not isinstance(locks,dict): return {'error':'예약 파일 형식이 dict가 아닙니다.'}
    sku=str(args.get('sku','G36ca7485'))
    existed=sku in locks
    if existed:
        del locks[sku]
        with open(path,'w',encoding='utf-8') as f: json.dump(locks,f,ensure_ascii=False)
    return {'removed':sku if existed else None,'remaining':locks}
