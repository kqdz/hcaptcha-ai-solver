

import hashlib
import requests
from   re                 import findall
from   time               import time
from   json               import dumps
from   datetime           import datetime
from   tls_client         import Session
from   modules.utils      import Print
from   modules.replier    import Replier
from   modules.motiondata import motion_data
from   concurrent.futures import ThreadPoolExecutor

api_js = requests.get('https://hcaptcha.com/1/api.js?render=explicit&onload=hcaptchaOnLoad').text
version = findall(r'v1\/([A-Za-z0-9]+)\/static', api_js)[1]

class Solver:
    def __init__(self, sitekey: str, host: str, proxy: str = None, rqdata: str = None) -> None:
        self.answers = {}

        self.session = Session(
            client_identifier = "firefox_121",
            random_tls_extension_order = True
        )
        self.session.headers = {
            "host": "hcaptcha.com",
            "connection": "keep-alive",
            "accept": "application/json",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Chromium";v="118", "Not A(Brand";v="24", "Google Chrome";v="118"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "origin": "https://newassets.hcaptcha.com",
            "referer": "https://newassets.hcaptcha.com/",
            "sec-fetch-site": "same-site",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "accept-encoding": "gzip, deflate, br",
            "accept-language": "nl-NL;q=0.9"
        }
        self.session.proxies = {
            "http": f"http://{proxy}",
            "https": f"https://{proxy}"
        } if proxy else None

        self.sitekey = sitekey
        self.host = host.split("//")[-1].split("/")[0]
        self.rqdata = rqdata
        
        self.motion = motion_data(self.session.headers["user-agent"], f"https://{host}")
        self.motiondata = self.motion.get_captcha()

        self.siteconfig = self.get_siteconfig()

        self.captcha1 = self.get_captcha1()
        self.captcha2 = self.get_captcha2()

    def hsw(self, req: str) -> str:
        return requests.post("http://localhost:5000/hsw", json={"req": req, "host": self.host}, timeout=30).text

    def get_siteconfig(self) -> dict:
        siteconfig = self.session.post(f"https://hcaptcha.com/checksiteconfig", params={
            'v': version,
            'sitekey': self.sitekey,
            'host': self.host,
            'sc': '1', 
            'swa': '1', 
            'spst': '1'
        })

        Print.inf(f"Got Site Config. ({siteconfig.status_code})")
        return siteconfig.json()
    
    def get_captcha1(self) -> dict:
        data = {
            'v': version,
            'sitekey': self.sitekey,
            'host': self.host,
            'hl': 'nl',
            'motionData': dumps(self.motiondata),
            'pdc':  {"s": round(datetime.now().timestamp() * 1000), "n":0, "p":0, "gcs":10},
            'n': self.hsw(self.siteconfig['c']['req']),
            'c': dumps(self.siteconfig['c']),
            'pst': False
        }

        if self.rqdata is not None:
            data['rqdata'] = self.rqdata

        getcaptcha = self.session.post(f"https://hcaptcha.com/getcaptcha/{self.sitekey}", data=data)
        Print.inf(f"Got Captcha Number 1. ({getcaptcha.status_code})")

        return getcaptcha.json()
    
    def get_captcha2(self) -> dict:
        data = {
            'v': version,
            'sitekey': self.sitekey,
            'host': self.host,
            'hl': 'en',
            'a11y_tfe': 'true',
            'action': 'challenge-refresh',
            'old_ekey'  : self.captcha1['key'],
            'extraData': self.captcha1,
            'motionData': dumps(self.motiondata),
            'pdc':  {"s": round(datetime.now().timestamp() * 1000), "n":0, "p":0, "gcs":10},
            'n': self.hsw(self.captcha1['c']['req']),
            'c': dumps(self.captcha1['c']),
            'pst': False
        }

        if self.rqdata is not None:
            data['rqdata'] = self.rqdata

        getcaptcha2 = self.session.post(f"https://hcaptcha.com/getcaptcha/{self.sitekey}", data=data)
        Print.inf(f"Got Captcha Number 2. ({getcaptcha2.status_code})")

        return getcaptcha2.json()
    
    def text(self, task: dict) -> str:
        s, q = time(), task["datapoint_text"]["en"]
        hashed_q = hashlib.sha1(q.encode()).hexdigest()
        
        response = Replier().reply(q)
        
        if response:
            Print.success(f"Solved Question -> {q} -> {response}")

            self.answers[hashed_q] = response

            return task['task_key'], {'text': response}
        
        return "yes"
    
    def solve(self) -> str:
        # try:
            cap = self.captcha2
            with ThreadPoolExecutor() as e: results = list(e.map(self.text, cap['tasklist']))
            answers = {key: value for key, value in results}
            submit = self.session.post(
                f"https://api.hcaptcha.com/checkcaptcha/{self.sitekey}/{cap['key']}",
                json={
                    'answers': answers,
                    'c': dumps(cap['c']),
                    'job_mode': cap['request_type'],
                    'motionData': dumps(self.motion.check_captcha()),
                    'n': self.hsw(cap['c']['req']),
                    'serverdomain': self.host,
                    'sitekey': self.sitekey,
                    'v': version,
                })
            
            if 'UUID' in submit.text:
                Print.success(f"Solved hCaptcha {submit.json()['generated_pass_UUID'][:70]}")

                return submit.json()['generated_pass_UUID']
            
            Print.error(f"Failed To Solve hCaptcha")
            return "None"
        # except Exception as e:
            Print.error(e)