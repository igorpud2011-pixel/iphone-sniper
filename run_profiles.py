"""Run isolated local and nationwide scans without sharing mutable bot state."""
import os,subprocess,sys
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode

def national_env(original):
 env=dict(original);parts=urlsplit(env['SETTINGS_URL'])
 query=dict(parse_qsl(parts.query));query['profile']='polska'
 env['SETTINGS_URL']=urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(query),''))
 env['ALERT_PROFILE']='polska'
 env['DISCORD_WEBHOOK_URL']=urlunsplit((parts.scheme,parts.netloc,'/relay/polska','',''))
 for name in ('DISCORD_DAMAGED_WEBHOOK_URL','DISCORD_DEALS_WEBHOOK_URL','TELEGRAM_BOT_TOKEN','TELEGRAM_CHAT_ID'):env.pop(name,None)
 return env

def main():
 script=str(Path(__file__).with_name('bot.py'))
 codes=[subprocess.run([sys.executable,script],env=os.environ.copy()).returncode]
 if os.environ.get('SETTINGS_URL'):
  codes.append(subprocess.run([sys.executable,script],env=national_env(os.environ)).returncode)
 return max(codes)
if __name__=='__main__':sys.exit(main())
