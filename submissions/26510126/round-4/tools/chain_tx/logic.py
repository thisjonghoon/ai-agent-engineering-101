import httpx

def run(args, kit):
    c=httpx.get(kit.market+'/api/chain',timeout=10).json()
    method='eth_getTransactionReceipt' if args.get('receipt') else 'eth_getTransactionByHash'
    r=httpx.post(c['rpc'],json={'jsonrpc':'2.0','id':1,'method':method,'params':[args['tx_hash']]},timeout=15)
    return {'chain':c,'rpc':r.json()}
