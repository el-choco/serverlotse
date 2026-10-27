"""Opt-in alerting/healing/maintenance. Defaults are disabled; state is durable."""
import datetime
import json
import re
import socket
import time
import admin_core as core
import advanced
import sensors

LAST_CHECK={}
HIGH_SINCE={}
FAILURES={}


def alert(key,text,cfg,now):
    last=advanced.state('alert:'+key) or 0
    if now-last<cfg['cooldown_minutes']*60:return
    # Failed deliveries also back off, never expose secret URLs in diagnostics.
    advanced.state('alert:'+key,now)
    try:advanced.notify('ServerLotse · '+socket.gethostname()+'\n'+text,cfg);advanced.log_event('notification',key)
    except ValueError as exc:advanced.log_event('notification',str(exc),'error')


def intentional_stop(target,info,now):
    if advanced.state('suppressed:'+target):return True
    if info.get('ExitCode',0) in {0,137,143} and not info.get('OOMKilled'):return True
    try:
        stamp=re.sub(r'(\.\d{6})\d+',r'\1',info.get('FinishedAt','').replace('Z','+00:00'))
        finished=datetime.datetime.fromisoformat(stamp).timestamp()
        events=core.command(['docker','events','--since',str(int(now-86400)),'--until',str(int(now)),
                             '--filter','type=container','--filter','container='+target,'--filter','event=stop','--format','{{.Time}}'],timeout=15)
        if any(float(line)>=finished-3 for line in events.splitlines() if line.strip()):
            advanced.state('suppressed:'+target,True);return True
    except (ValueError,TypeError,OverflowError):
        # If intent cannot be determined, do not restart this target blindly.
        return True
    return False


def heal(cfg,now):
    if core.MUTEX.locked() or core.POWER_UNTIL>now:return
    for kind,key in [('container','heal_containers'),('service','heal_services')]:
        for target in cfg[key]:
            if advanced.state('suppressed:'+target):continue
            attempts=[stamp for stamp in (advanced.state('attempts:'+target) or []) if now-stamp<3600]
            if len(attempts)>=3 or (attempts and now-attempts[-1]<300):continue
            try:
                if kind=='container':
                    info=json.loads(core.command(['docker','inspect','--type','container',target]))[0]['State']
                    if info.get('Paused'):failed=False
                    elif info.get('Status')=='exited':failed=info.get('ExitCode',0)!=0 and not intentional_stop(target,info,now)
                    else:failed=bool(info.get('Running') and info.get('Health',{}).get('Status')=='unhealthy')
                else:failed=core.command(['systemctl','show','--property=ActiveState','--value',target]).strip()=='failed'
                FAILURES[target]=FAILURES.get(target,0)+1 if failed else 0
                if FAILURES[target]>=2:
                    plan=core.validate({'operation':kind,'verb':'restart',('container' if kind=='container' else 'name'):target})
                    core.enqueue(plan)
                    advanced.state('attempts:'+target,attempts+[now]);FAILURES[target]=0
                    advanced.log_event('auto_heal','Neustart angefordert: '+target)
                    return
            except (ValueError,KeyError,IndexError,TypeError) as exc:
                if now-LAST_CHECK.get('error:'+target,0)>900:
                    LAST_CHECK['error:'+target]=now;advanced.log_event('auto_heal','Ziel nicht prüfbar: '+target+' · '+type(exc).__name__,'error')


def tick(now=None):
    now=time.time() if now is None else now;cfg=advanced.config(True)
    if not cfg['enabled']:
        HIGH_SINCE.clear();FAILURES.clear();return
    with sensors.LOCK:latest=dict(sensors.PREVIOUS.get('latest') or {})
    if latest and now-latest['time']<30:
        for key,value in [('cpu',latest.get('cpu')),('ram',latest.get('ram_percent'))]:
            if value is not None and value>=cfg[key]:
                HIGH_SINCE.setdefault(key,now)
                if cfg['notify_'+key] and now-HIGH_SINCE[key]>=cfg['hold_seconds']:alert(key,f'{key.upper()}: {value:.1f}% für mindestens {cfg["hold_seconds"]} Sekunden.',cfg,now)
            else:HIGH_SINCE.pop(key,None)
    else:HIGH_SINCE.clear()
    if cfg['notify_ssh'] and now-LAST_CHECK.get('ssh',0)>=60:
        LAST_CHECK['ssh']=now
        text=core.command(['journalctl','--since','1 minute ago','-t','sshd','-t','dropbear','--no-pager','-n','1000','-o','cat'],timeout=15)
        count=sum(bool(re.search(r'Failed password|Bad password attempt',line,re.I)) for line in text.splitlines())
        if count>=cfg['ssh_failures']:alert('ssh',str(count)+' fehlgeschlagene SSH-Loginmeldungen in ungefähr einer Minute.',cfg,now)
    if now-LAST_CHECK.get('heal',0)>=60:
        LAST_CHECK['heal']=now;heal(cfg,now)
    local=time.localtime(now);day=time.strftime('%Y-%m-%d',local)
    if cfg['janitor'] and local.tm_hour==cfg['janitor_hour'] and advanced.state('janitor_day')!=day:
        if not core.MUTEX.locked() and core.POWER_UNTIL<=now:
            core.enqueue(core.validate({'operation':'docker_clean'}));advanced.state('janitor_day',day)
            advanced.log_event('auto_janitor','Alte dangling Images und Build-Cache; keine Volumes oder Container.')


def loop():
    while True:
        try:tick()
        except Exception as exc:
            now=time.time()
            if now-LAST_CHECK.get('loop_error',0)>900:
                LAST_CHECK['loop_error']=now
                try:advanced.log_event('automation','Automatik konnte nicht vollständig ausgeführt werden: '+type(exc).__name__,'error')
                except Exception:pass
        time.sleep(15)
