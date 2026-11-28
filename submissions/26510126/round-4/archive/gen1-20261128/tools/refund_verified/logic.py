def run(args, kit):
    try:
        from eth_utils import to_checksum_address
        to=to_checksum_address(args['to'])
    except Exception:
        to=args['to']
    credits=int(args['credits'])
    tx=kit.pay(to, credits*10**15, '0x', role='shop')
    return {'to':to,'credits':credits,'tx_hash':tx}
