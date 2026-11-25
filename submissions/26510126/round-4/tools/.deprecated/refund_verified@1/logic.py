def run(args, kit):
    to=args['to']; credits=int(args['credits'])
    tx=kit.pay(to, credits*10**15, '0x', role='shop')
    return {'to':to,'credits':credits,'tx_hash':tx}
