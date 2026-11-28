from datetime import datetime, timezone, timedelta
def run(args, kit):
 return {'kst': datetime.fromtimestamp(args['timestamp'], timezone(timedelta(hours=9))).isoformat()}
