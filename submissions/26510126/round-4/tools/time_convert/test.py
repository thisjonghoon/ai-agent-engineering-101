def test(run, kit):
 assert run({'timestamp': 0}, kit)['kst'].startswith('1970-01-01T09:00:00')
