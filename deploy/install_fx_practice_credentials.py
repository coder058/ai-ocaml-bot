"""Run interactively on Dublin; never paste a practice token into chat.

Validates the token against the hardcoded OANDA practice origin before saving.
No trading request, credential regeneration or production host is available.
"""
import getpass,json,os,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research'))
from oanda_practice import ENV_PATH,get

def main():
    if os.geteuid()!=0:raise SystemExit('Run as root on Dublin.')
    if ENV_PATH.exists():raise SystemExit('Practice file already exists; preserve and review it before replacement.')
    account=input('OANDA v20 practice account ID: ').strip()
    token=getpass.getpass('Practice API token (hidden): ').strip()
    if not re.fullmatch(r'[0-9-]+',account) or not token or any(c in token for c in '\r\n\0'):
        raise SystemExit('Invalid credential format; nothing saved.')
    try:
        document=get('/v3/accounts/'+account+'/summary',token)
        if not isinstance(document.get('account'),dict):raise ValueError('summary missing')
    except Exception as error:
        raise SystemExit('Practice validation failed ('+type(error).__name__+'); nothing saved.')
    # SOURCE: root-only token storage, fsynced before atomic installation.
    temporary=ENV_PATH.with_suffix('.tmp');fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as output:
        output.write('OANDA_PRACTICE_ACCOUNT='+account+'\nOANDA_PRACTICE_TOKEN='+token+'\n')
        output.flush();os.fsync(output.fileno())
    os.replace(temporary,ENV_PATH)
    print(json.dumps({'practiceCredentialsValidated':True,'saved':True,'ordersSubmitted':False}))

if __name__=='__main__':main()
