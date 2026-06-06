import sys
files = [
    'shared/cedarfix_shared/schemas.py',
    'services/routing_engine/app/router.py',
    'services/gateway/app/database.py',
    'services/gateway/app/orchestrator.py',
    'services/gateway/app/main.py',
    'services/review_service/app/store.py',
    'services/review_service/app/main.py',
]
ok = True
for f in files:
    try:
        with open(f, encoding='utf-8-sig') as fh:
            src = fh.read()
        compile(src, f, 'exec')
        print(f'OK  {f}')
    except SyntaxError as e:
        print(f'ERR {f}: line {e.lineno}: {e.msg}')
        ok = False
sys.exit(0 if ok else 1)
