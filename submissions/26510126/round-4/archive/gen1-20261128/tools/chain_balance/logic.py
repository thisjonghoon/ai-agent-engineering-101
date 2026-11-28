import httpx

CREDIT_WEI = 10**15

def run(args, kit):
    addr = args.get('address') or kit.address('shop')
    if not (isinstance(addr, str) and addr.startswith('0x') and len(addr) == 42):
        return {'error': 'bad address'}
    r = httpx.post('https://rpc-testnet.maroo.io', json={'jsonrpc': '2.0', 'id': 1, 'method': 'eth_getBalance', 'params': [addr, 'latest']}, timeout=25)
    j = r.json()
    if 'result' not in j:
        return {'error': j}
    wei = int(j['result'], 16)
    return {'address': addr, 'wei': wei, 'credits': wei / CREDIT_WEI}
