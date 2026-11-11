"""External headline collection and offline corporate disclosure CSV readers."""
import csv
import datetime as dt
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


def headlines(query,max_items=15):
    url='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':query,'hl':'en-IN','gl':'IN','ceid':'IN:en'})
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 CodexIndiaDayTrader'})
    with urllib.request.urlopen(req,timeout=15) as f: tree=ET.fromstring(f.read())
    return [{'title':x.findtext('title',''),'url':x.findtext('link',''),
             'published':x.findtext('pubDate',''),'source':x.findtext('source','Google News')}
            for x in tree.findall('.//channel/item')[:max_items]]


def financial_report(path):
    """CSV: period,revenue,net_profit,eps; compare in file order, never invent metrics."""
    with open(path,newline='',encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    required={'period','revenue','net_profit','eps'}
    if not rows or not required.issubset(rows[0]):raise ValueError('Expected period,revenue,net_profit,eps columns')
    parsed=[{k:(float(v) if k!='period' else v) for k,v in r.items() if k in required} for r in rows]
    parsed.sort(key=lambda x:x['period'])
    latest=parsed[-1];prior=parsed[-2] if len(parsed)>1 else None
    out={'latest':latest,'previous':prior,'rows':len(parsed),'source':path,
         'warning':'Figures are user-supplied; verify period comparability and original filings.'}
    if prior:
        for key in ('revenue','net_profit','eps'):
            old=prior[key]
            out[key+'_change_pct']=round(100*(latest[key]-old)/abs(old),2) if old else None
    return out


def insider_summary(path):
    """India alternative to US Pelosi tracker, from user-supplied public disclosures.
    CSV: disclosure_date,symbol,insider,side,quantity,source_url
    """
    with open(path,newline='',encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    if rows and not {'disclosure_date','symbol','insider','side','quantity','source_url'}.issubset(rows[0]):
        raise ValueError('Expected disclosure_date,symbol,insider,side,quantity,source_url')
    return {'count':len(rows),'disclosures':rows,'source':path,
            'warning':'Exchange/public disclosures may be delayed; not proof of future returns.'}
