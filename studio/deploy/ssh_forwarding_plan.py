"""Generate/validate a scoped forwarding proposal; never installs or reloads sshd."""
import argparse
import ipaddress
from pathlib import Path
import re
import shutil
import subprocess

MARKER='# BEGIN Library Studio scoped tunnel'


def proposal(original,user,client):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,63}',user):raise ValueError('Use an exact verified SSH username')
    address=ipaddress.IPv4Address(client)
    if str(address)!=client:raise ValueError('Use an exact IPv4 address')
    if MARKER in original:raise ValueError('An existing Studio SSH proposal requires review; do not append again')
    return original.rstrip()+'\n\n'+MARKER+'\nMatch User '+user+' Address '+client+'\n    AllowTcpForwarding local\n    PermitOpen 127.0.0.1:43120\n# END Library Studio scoped tunnel\n'


def effective(config,user,client,sshd=None,server='127.0.0.1',port=22):
    binary=sshd or shutil.which('sshd')
    if not binary:raise ValueError('OpenSSH sshd is required to validate the proposal')
    result=subprocess.run([binary,'-T','-f',str(config),'-C','user='+user+',addr='+client+',host='+client+',laddr='+server+',lport='+str(port)],capture_output=True,text=True,check=True)
    return dict(line.split(' ',1) for line in result.stdout.splitlines())


def validate(original,candidate,user,client,sshd=None,server='127.0.0.1',port=22):
    target=effective(candidate,user,client,sshd,server,port)
    if target.get('allowtcpforwarding')!='local' or target.get('permitopen')!='127.0.0.1:43120' or target.get('disableforwarding')!='no':
        raise ValueError('Existing policy prevents the scoped rule; do not install/reload')
    address=ipaddress.IPv4Address(client)
    other=str(ipaddress.IPv4Address(int(address)^1))
    different_user='root' if user!='root' else 'nobody'
    for name,source in [(user,other),(different_user,client)]:
        if effective(original,name,source,sshd,server,port)!=effective(candidate,name,source,sshd,server,port):
            raise ValueError('Unrelated effective policy changed; do not install/reload')
    return {'forwarding':'local','destination':'127.0.0.1:43120','unrelated_contexts_unchanged':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user',required=True);parser.add_argument('--client',required=True)
    args=parser.parse_args()
    # Print only the reviewable fragment, never a server's configuration/keys.
    print(proposal('',args.user,args.client).strip())
