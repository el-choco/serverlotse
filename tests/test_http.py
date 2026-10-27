import http.client
import json
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import auth
import server


class QuietHandler(server.Handler):
    def log_message(self, *args):
        pass


class HTTPAuthenticationTests(unittest.TestCase):
    def test_navigation_module_is_served_as_script(self):
        status,headers,body=self.request('GET','/navigation-ui.js')
        self.assertEqual(status,200);self.assertIn('javascript',headers['Content-Type'])
        self.assertIn(b'category-page',body)

    def test_terminal_requires_auth_origin_and_binds_owner_server_side(self):
        self.assertEqual(self.request('POST','/api/terminal',{'action':'prepare'})[0],401)
        headers={'Authorization':'Bearer '+self.key,'Origin':'https://foreign.invalid'}
        self.assertEqual(self.request('POST','/api/terminal',{'action':'prepare'},headers)[0],403)
        headers={'Authorization':'Bearer '+self.key}
        with patch.object(server.admin_client,'request',return_value={'nonce':'test'}) as relay:
            self.assertEqual(self.request('POST','/api/terminal',{'action':'prepare','owner':'attacker'},headers)[0],200)
            data=relay.call_args.args[1]
            self.assertEqual(len(data['owner']),64);self.assertNotEqual(data['owner'],'attacker')
        with patch.object(server,'DEMO',True),patch.object(server.admin_client,'request') as relay:
            self.assertEqual(self.request('POST','/api/terminal',{'action':'start'})[0],400)
            relay.assert_not_called()

    def test_terminal_styles_have_unique_nonce_without_blanket_inline_permission(self):
        status,headers,body=self.request('GET','/')
        self.assertEqual(status,200)
        policy=headers['Content-Security-Policy']
        self.assertNotIn('unsafe-inline',policy)
        import re
        nonce=re.search(b'name="terminal-style-nonce" content="([^"]+)"',body).group(1).decode()
        self.assertIn("'nonce-"+nonce+"'",policy)
        self.assertNotIn(nonce,self.request('GET','/')[2].decode())

    def setUp(self):
        self.key = "local-http-test-key-not-a-real-secret"
        self.token_patch = patch.object(server, "TOKEN", self.key)
        self.demo_patch = patch.object(server, "DEMO", False)
        self.token_patch.start()
        self.demo_patch.start()
        auth.ATTEMPTS.clear()
        auth.REVOKED.clear()
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(2)
        self.demo_patch.stop()
        self.token_patch.stop()

    def request(self, method, path, data=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.http.server_port, timeout=5)
        try:
            body = json.dumps(data) if data is not None else None
            connection.request(method, path, body, headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_login_cookie_automatic_access_and_logout(self):
        self.assertEqual(self.request("GET", "/api/settings")[0], 401)
        status, headers, body = self.request("POST", "/api/login", {"token": self.key, "remember": True})
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.assertNotIn(self.key, cookie + body.decode())
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertEqual(self.request("GET", "/api/settings", headers={"Cookie": cookie})[0], 200)
        # A new connection has no bearer token but is authenticated by its cookie.
        self.assertEqual(self.request("GET", "/api/jobs", headers={"Cookie": cookie})[0], 200)
        self.assertEqual(self.request("POST", "/api/logout", {}, {"Cookie": cookie})[0], 200)
        self.assertEqual(self.request("GET", "/api/settings", headers={"Cookie": cookie})[0], 401)

    def test_cross_origin_login_rejected(self):
        status, _, _ = self.request("POST", "/api/login", {"token": self.key}, {"Origin": "https://foreign.invalid"})
        self.assertEqual(status, 403)

    def test_admin_relay_requires_login_and_origin(self):
        self.assertEqual(self.request('POST','/api/admin/execute',{'nonce':'x'})[0],401)
        headers={'Authorization':'Bearer '+self.key,'Origin':'https://foreign.invalid'}
        with patch.object(server.admin_client,'request') as relay:
            self.assertEqual(self.request('POST','/api/admin/execute',{},headers)[0],403)
            relay.assert_not_called()

    def test_admin_changes_block_during_file_job(self):
        headers={'Authorization':'Bearer '+self.key}
        with patch.dict(server.JOBS,{'test-admin':{'status':'running'}}),patch.object(server.admin_client,'request') as relay:
            self.assertEqual(self.request('POST','/api/admin/execute',{'nonce':'x'},headers)[0],400)
            relay.assert_not_called()

    def test_demo_admin_has_fixtures_but_cannot_execute(self):
        with patch.object(server,'DEMO',True):
            self.assertEqual(self.request('GET','/api/admin/status')[0],200)
            status,_,body=self.request('POST','/api/admin/read',{'view':'health'})
            self.assertEqual(status,200);self.assertEqual(json.loads(body)['hostname'],'demo-server')
            status,_,body=self.request('POST','/api/admin/prepare',{'operation':'user_create','password':'test-secret'})
            self.assertEqual(status,200);self.assertNotIn(b'test-secret',body)
            with patch.object(server.admin_client,'request') as relay:
                self.assertEqual(self.request('POST','/api/admin/execute',{'nonce':'demo','confirmation':'AUSFUEHREN'})[0],400)
                relay.assert_not_called()

    def test_demo_preview_redacts_nested_new_credentials(self):
        with patch.object(server,'DEMO',True):
            status,_,body=self.request('POST','/api/admin/prepare',{'operation':'settings_save','settings':{'webhook_url':'https://example.invalid/my-private-url','telegram_token':'private-telegram-token'},'secret_key':'private-s3-key'})
            self.assertEqual(status,200)
            for value in [b'my-private-url',b'private-telegram-token',b'private-s3-key']:self.assertNotIn(value,body)
            status,_,body=self.request('POST','/api/admin/prepare',{'operation':'volume_delete','name':'demo-volume'})
            self.assertEqual(json.loads(body)['confirmation'],'LOESCHEN')

    def test_wrong_token_spanish_error_and_public_page(self):
        status, _, body = self.request("POST", "/api/login", {"token": "wrong"}, {"Accept-Language": "es"})
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(body)["error"], "Clave de acceso no válida")
        status, _, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertNotIn(self.key.encode(), body)

    def test_power_requires_login_and_blocks_running_jobs(self):
        data={"action":"reboot"}
        self.assertEqual(self.request("POST","/api/host/prepare",data)[0],401)
        headers={"Authorization":"Bearer "+self.key}
        with patch.object(server,"host_request") as relay,patch.object(server,"host_boot_ready",return_value=True):
            server.JOBS["power-test"]={"status":"running"}
            try:self.assertEqual(self.request("POST","/api/host/prepare",data,headers)[0],400)
            finally:del server.JOBS["power-test"]
            relay.assert_not_called()

    def test_power_execution_reserves_job_window_without_real_action(self):
        headers={"Authorization":"Bearer "+self.key}
        with patch.object(server,"HOST_POWER_UNTIL",0),patch.object(server,"host_boot_ready",return_value=True),patch.object(server,"host_request",return_value={"accepted":True}) as relay:
            status,_,_=self.request("POST","/api/host/execute",{"action":"reboot","nonce":"test","confirmation":"REBOOT"},headers)
            self.assertEqual(status,200)
            self.assertEqual(relay.call_args.args[0],"/execute")
            self.assertEqual(self.request("POST","/api/jobs",{"action":"scan","path":"/"},headers)[0],409)

    def test_reboot_requires_boot_view_setup(self):
        with patch.object(server,"host_boot_ready",return_value=False),patch.object(server,"host_request") as relay:
            status,_,_=self.request("POST","/api/host/prepare",{"action":"reboot"},{"Authorization":"Bearer "+self.key})
            self.assertEqual(status,400)
            relay.assert_not_called()
