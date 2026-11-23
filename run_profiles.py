"""Run isolated local and nationwide scans without sharing mutable bot state."""
import os,subprocess,sys,time
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

def run_local(script, env):
 command=[sys.executable,script]
 started=time.monotonic()
 result=subprocess.run(command,env=env).returncode
 delay=30-(time.monotonic()-started)
 # A slow or failed full scan gets its usual minute to recover. Never run
 # two local scans concurrently against the same saved state.
 if result in (0,1) and delay>0:
  time.sleep(delay)
  fast=subprocess.run(command,env={**env,"OLX_LOCAL_FAST_SCAN":"1"}).returncode
  if fast:
   print("Niepełne dodatkowe sprawdzenie Bielska-Białej. Pełny skan wróci w następnym cyklu.",flush=True)
 return result

def main():
 script=str(Path(__file__).with_name('bot.py'))
 local=os.environ.copy()
 local["ALERT_PROFILE"]="local"
 local.pop("OLX_LOCAL_FAST_SCAN",None)
 with ThreadPoolExecutor(max_workers=2) as pool:
  if local.get("SETTINGS_URL"):
   national=national_env(local)
   local["DAMAGED_ROUTED_NATIONALLY"]="1"
   whole_country=pool.submit(subprocess.run,[sys.executable,script],env=national)
  else:
   whole_country=None
  local_result=pool.submit(run_local,script,local).result()
  return max(local_result,whole_country.result().returncode) if whole_country else local_result

if __name__=='__main__':sys.exit(main())
