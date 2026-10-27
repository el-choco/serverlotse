def read(data):
    view=data['view']
    if view=='advanced_settings':return {'enabled':False,'notify_cpu':True,'notify_ram':True,'notify_ssh':False,'cpu':90,'ram':90,'hold_seconds':60,'cooldown_minutes':15,'ssh_failures':10,'webhook_kind':'discord','heal_containers':[],'heal_services':[],'janitor':False,'janitor_hour':3,'rclone_config':''}
    if view=='advanced_tools':return {'tools':{name:True for name in ['ufw','sshd','rclone','caddy','nginx','certbot','unattended-upgrade']}}
    if view=='advanced_remotes':return {'remotes':['serverlotse_backup:'],'config':['--config','/etc/serverlotse/remotes.conf']}
    if view=='advanced_updates':return {'installed':True,'timers':'DEMO: apt-daily-upgrade.timer at 03:00','policy':''}
    if view=='advanced_heal':return {'rows':[{'target':'example-web','suppressed':True,'attempts':[]}]}
    raise ValueError('Unbekannte Erweiterungsansicht.')
