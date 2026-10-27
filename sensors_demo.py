"""Fixtures for the read-only sensor UI. Never reads the host."""
import math
import time


def read(data):
    view=data['view'];now=time.time()
    if view=='sensor_live':
        rows=[{'time':now-(59-i)*5,'cpu':20+8*math.sin(i/5),'ram':42+math.sin(i/8),'swap':0,'temperature':38+math.sin(i/10),'rx':(2+math.sin(i/7))*1048576,'tx':(1+math.sin(i/8)/2)*1048576} for i in range(60)]
        return {'rows':rows,'latest':{'time':now,'cpu':rows[-1]['cpu'],'cores':{'cpu0':15,'cpu1':22,'cpu2':9,'cpu3':31},'ram_percent':rows[-1]['ram'],'swap_percent':0,'memory':{'MemTotal':16*1073741824,'MemAvailable':9*1073741824},'temperatures':[{'name':'Demo CPU','celsius':38.2},{'name':'iwlwifi_demo','celsius':46},{'name':'nvme_demo','celsius':32.5}],'network':{'eth0':{'rx':rows[-1]['rx'],'tx':rows[-1]['tx']},'wlan0':{'rx':256,'tx':2048},'docker0':{'rx':0,'tx':0},'br-demo':{'rx':1250,'tx':420}}},'note':'Beispieldaten – keine Verbindung zu deinem Server.'}
    if view=='sensor_processes':return {'rows':[{'pid':1,'name':'systemd','uid':0,'state':'S','cpu':0.1,'rss':15000000},{'pid':1200,'name':'demo-web','uid':1000,'state':'S','cpu':4.2,'rss':240000000},{'pid':1250,'name':'demo-worker','uid':1000,'state':'R','cpu':23.1,'rss':120000000}],'total':3,'note':'Beispieldaten – keine Verbindung zu deinem Server.'}
    if view=='sensor_logs':return {'text':'DEMO '+time.strftime('%H:%M:%S')+' example-service: ready\nDEMO: no real server logs.','time':now,'note':'Beispieldaten – keine Verbindung zu deinem Server.'}
    if view=='sensor_ssh':return {'rows':[{'name':'permitrootlogin','value':'prohibit-password','recommended':'no','attention':True},{'name':'passwordauthentication','value':'no','recommended':'no','attention':False},{'name':'pubkeyauthentication','value':'yes','recommended':'yes','attention':False}],'port':'22','note':'Beispieldaten – keine Verbindung zu deinem Server.'}
    if view=='sensor_firewall':return {'backend':'ufw','text':'DEMO\nStatus: active\n[1] 22/tcp ALLOW IN Anywhere\n[2] 443/tcp ALLOW IN Anywhere','note':'Beispieldaten – keine Verbindung zu deinem Server.'}
    if view=='sensor_fail2ban':return {'text':'DEMO\nJail list: sshd\nCurrently banned: 1\nBanned IP list: 192.0.2.20','jails':['sshd']}
    if view=='sensor_unused':return {'volumes':['demo-unreferenced-volume'],'images':['sha256:'+'a'*64],'text':'DEMO: images 2.1 GB, volumes 8.4 GB','note':'Nicht referenziert heißt nicht leer oder entbehrlich. Volumes können Datenbanken und Dateien enthalten. Diese Ansicht löscht nichts.'}
    if view=='sensor_console':return {'command':[data.get('command','uptime')],'text':'DEMO: example command output; nothing was executed.','note':'Beispieldaten – keine Verbindung zu deinem Server.'}
    if view=='sensor_capabilities':return {'commands':['uptime','disk'],'tools':{'sshd':True,'ufw':True,'fail2ban-client':True}}
    if view=='sensor_proxy':return {'caddy':f"{data.get('domain','example.com')} {{\n    reverse_proxy {data.get('upstream','http://127.0.0.1:3000')}\n}}\n",'nginx':'# DEMO: nginx template','note':'Beispieldaten – keine Verbindung zu deinem Server.'}
    raise ValueError('Unbekannte Sensoransicht.')
