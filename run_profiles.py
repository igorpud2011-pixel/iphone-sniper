"""Run isolated local and nationwide scans without sharing mutable bot state."""
import os,subprocess,sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode

def national_env(original):
 env=dict(original);parts=urlsplit(env['SETTINGS_URL'])
 query=dict(parse_qsl(parts.query));query['profile']='polska'
 env['SETTINGS_URL']=urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(query),''))
 env['ALERT_PROFILE']='polska'
 env['DISCORD_WEBHOOK_URL']=urlunsplit((parts.scheme,parts.netloc,'/relay/polska','',''))
 for name in ('DISCORD_DEALS_WEBHOOK_URL','TELEGRAM_BOT_TOKEN','TELEGRAM_CHAT_ID'):env.pop(name,None)
 return env

def main():
 script=str(Path(__file__).with_name('bot.py'))
 local=os.environ.copy()
 profiles=[local]
 if local.get('SETTINGS_URL'):
  profiles.append(national_env(local))
  local['DAMAGED_ROUTED_NATIONALLY']='1'
 with ThreadPoolExecutor(max_workers=2) as pool:
  futures=[pool.submit(subprocess.run,[sys.executable,script],env=env) for env in profiles]
  codes=[future.result().returncode for future in futures]
 return max(codes)
if __name__=='__main__':sys.exit(main())
