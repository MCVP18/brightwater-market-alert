"""
Automated QA and UAT checks for the Brightwater alert review prototype.

Usage: python uat_checks.py index.html brightwater-alert-review-B.html uat-test-copy.html
  uat-test-copy.html = index.html with five QA test alerts added for store S999
  (four tied High alerts and one unknown alert type).
Needs: playwright  (pip install playwright; playwright install chromium)

Real-manager checks (UAT-2 behaviour, UAT-5 timing) are reported as NEEDS REAL MANAGER.
"""
from playwright.sync_api import sync_playwright
R=[]
def rec(t,c,ok,d=''): R.append((t,c,'PASS' if ok is True else ('FAIL' if ok is False else ok),d))
def login(pg,d,s,role=None):
    if pg.is_visible('#signOut'): pg.click('#signOut')
    if role: pg.select_option('#role',role)
    pg.select_option('#district',d)
    if s and pg.is_visible('#store'): pg.select_option('#store',s)
    pg.click('#signIn')
def rows(pg,sel): return pg.eval_on_selector_all(sel+' .row','els=>els.map(e=>({tier:e.querySelector(".pill").textContent,title:e.querySelector(".mid b").textContent,reason:e.querySelector(".mid span").textContent,meta:e.querySelector(".meta").innerText}))')
import sys, pathlib
A = pathlib.Path(sys.argv[1]).resolve().as_uri()   # Version A (index.html)
B = pathlib.Path(sys.argv[2]).resolve().as_uri()   # Version B (roles)
T = pathlib.Path(sys.argv[3]).resolve().as_uri()   # test copy with QA test alerts
with sync_playwright() as pw:
    b=pw.chromium.launch(); errs=[]
    # QA checks
    q=b.new_page(viewport={'width':1440,'height':900}); q.on('pageerror',lambda e:errs.append(str(e)))
    q.goto(T); q.evaluate("state.store='S999'; state.district='D9'"); q.click('#signIn')
    h=[x['title'].split(' · ')[1]+' '+x['meta'].split('·')[1].strip()[:3] for x in rows(q,'#highList')]
    rec('QA','Tied amounts: $600 Mon, $250 Thu, $250 Sat, $40 Tue',h==['$600.00 Mon','$250.00 Thu','$250.00 Sat','$40.00 Tue'],', '.join(h))
    m=[x for x in rows(q,'#medList') if 'Gift card' in x['title']]
    rec('QA','Unknown alert type lands in Medium with a sensible reason',bool(m) and 'undefined' not in m[0]['reason'],m[0]['reason'] if m else '')
    pg=b.new_page(viewport={'width':1440,'height':900}); pg.on('pageerror',lambda e:errs.append(str(e))); pg.goto(A)
    # UAT-1
    login(pg,'D4','S057')
    hi=[x['title'] for x in rows(pg,'#highList')]
    rec('UAT-1','High order $195.39, $195.26, $147.96, $108.36, $20.56',[t.split(' · ')[1] for t in hi]==['$195.39','$195.26','$147.96','$108.36','$20.56'])
    rec('UAT-1','Medium = $57.22',[x['title'].split(' · ')[1] for x in rows(pg,'#medList')]==['$57.22'])
    rec('UAT-1','Low shows 6, collapsed',pg.inner_text('#lowTitle')=='Low risk (6)' and pg.is_hidden('#lowBody'))
    ch=tuple(pg.inner_text(s) for s in ('#pieTotal','#lgHigh','#pcHigh','#lgMed','#pcMed','#lgLow','#pcLow'))
    rec('UAT-1','Chart 12 open: 5 (42%), 1 (8%), 6 (50%)',ch==('12','5','42%','1','8%','6','50%'),' '.join(ch))
    pg.click('#bConfirm'); rec('UAT-1','After marking: 11 open, High 4',pg.inner_text('#pieTotal')=='11' and pg.inner_text('#lgHigh')=='4')
    pg.click('.lg[data-jump=Low]'); rec('UAT-1','Selecting Low in legend opens Low',pg.is_visible('#lowBody'))
    # UAT-2 (observable part)
    login(pg,'D7','S100')
    counts=(pg.inner_text('#lgHigh'),pg.inner_text('#lgMed'),pg.inner_text('#lgLow'))
    first=rows(pg,'#highList')[0]
    rec('UAT-2','S100 queue: 9 High, 4 Medium, 7 Low',counts==('9','4','7'),' / '.join(counts))
    rec('UAT-2','Queue opens on High, with the top alert selected and its reason shown',first['tier']=='High' and first['title'].split(' · ')[1] in pg.inner_text('#details') and 'Reason:' in pg.inner_text('#details'),first['title'])
    rec('UAT-2','Manager starts in High and can explain the top alert','NEEDS REAL MANAGER','behaviour of a real D7 manager')
    # UAT-3
    login(pg,'D4','S057'); pg.click('#lowToggle')
    allr=rows(pg,'#highList')+rows(pg,'#medList')+rows(pg,'#lowList')
    bad=[x for x in allr if x['tier'] not in ('High','Medium','Low') or not x['reason'].startswith('Reason: ') or '$' not in x['title'] or 'Oct' not in x['meta']]
    rec('UAT-3','Every alert: tier in words, reason, amount, date',len(allr)==12 and not bad,f'{len(allr)} checked')
    ok=True
    for i in (0,5,8):
        pg.locator('.row').nth(i).click(); d=pg.inner_text('#details'); x=allr[i]
        ok&= x['tier'] in d and x['reason'].split(' · ')[0] in d and x['title'].split(' · ')[1] in d
    rec('UAT-3','Same details when opened (3 alerts)',ok)
    # UAT-4
    login(pg,'D4','S057'); pg.click('#lowToggle')
    lo=[x['title'].split(' · ')[1] for x in rows(pg,'#lowList')]
    rec('UAT-4','S057 Low opens to $36.40 … $9.74',lo==['$36.40','$34.54','$26.39','$18.89','$13.48','$9.74'],' '.join(lo))
    login(pg,'D3','S040'); rec('UAT-4','S040 shows "Low risk (0)"',pg.inner_text('#lowTitle')=='Low risk (0)' and pg.is_visible('#lowToggle'))
    # UAT-5
    login(pg,'D4','S057'); t1=rows(pg,'#highList')[0]['title']; pg.click('#bConfirm'); t2=rows(pg,'#highList')[0]['title']
    rec('UAT-5','Confirmed alert leaves queue; next opens',t1 not in [x['title'] for x in rows(pg,'#highList')] and t2.split(' · ')[1] in pg.inner_text('#details'))
    pg.click('#bNo'); rec('UAT-5','No issue alert leaves queue',t2 not in [x['title'] for x in rows(pg,'#highList')])
    # roles in Version B
    pb=b.new_page(viewport={'width':1440,'height':900}); pb.on('pageerror',lambda e:errs.append(str(e))); pb.goto(B)
    orders={}
    for role in ('Store Manager','Assistant Manager','District Manager'):
        login(pb,'D4','S057' if role!='District Manager' else None,role)
        if role=='District Manager': pb.select_option('#dmStore','S057')
        orders[role]=[x['title'] for x in rows(pb,'#highList')+rows(pb,'#medList')]
    rec('UAT-5','All three roles see the same order (Version B)',len({tuple(v) for v in orders.values()})==1)
    rec('UAT-5','Timed review no longer than current queue','NEEDS REAL MANAGER','stopwatch test')
    for t,c,o,d in R: print(f'{t:6} {o:18} {c}' + (f'  [{d}]' if d else ''))
    print('page errors:',errs); b.close()
