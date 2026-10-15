"""Create local secrets once; never print or overwrite them."""
from pathlib import Path
import secrets

root=Path(__file__).parent
env=root/'.env'
if env.exists():
    raise SystemExit('studio/.env already exists; kept unchanged.')
(root/'data'/'library').mkdir(parents=True,exist_ok=True)
env.write_text('STUDIO_BIND=127.0.0.1\nSTUDIO_PORT=43120\nSTUDIO_LIBRARY=./data/library\n'+
               '\n'.join(key+'='+secrets.token_urlsafe(32) for key in
                          ('LRR_API_KEY','STUDIO_PASSWORD','STUDIO_PC_WORKER_TOKEN','STUDIO_NAS_WORKER_TOKEN'))+'\n',encoding='utf-8')
try:env.chmod(0o600)
except OSError:pass
print('Created studio/.env. Login name: admin. Password is stored only in that local file.')
