// Читает историю в существующей сессии Wordstat, хранит ответы без данных входа.
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '..');
const cfg = JSON.parse(fs.readFileSync(path.join(root, 'configs/wordstat_pilot.json')));
const out = path.join(root, 'data/external/wordstat');
fs.mkdirSync(out, {recursive:true});

async function ownPage(browser, session, targetId) {
  for (let k=0;k<30;k++) {
    for (const page of browser.contexts()[0].pages()) {
      const s=await page.context().newCDPSession(page);
      const r=await s.send('Target.getTargetInfo'); await s.detach();
      if(r.targetInfo.targetId===targetId)return page;
    }
    await new Promise(r=>setTimeout(r,100));
  }
  throw Error('Не найдена собственная фоновая вкладка');
}
(async()=>{
  const b=await chromium.connectOverCDP('http://127.0.0.1:9222');
  const c=await b.newBrowserCDPSession();
  const {targetId}=await c.send('Target.createTarget',{url:'about:blank',background:true});
  try {
    const p=await ownPage(b,c,targetId);
    let template, headers;
    p.on('request',r=>{if(r.url()==='https://wordstat.yandex.ru/wordstat/api/getGraph'){
      template=r.postDataJSON();headers=r.headers();
    }});
    await p.goto('https://wordstat.yandex.ru/?region=all&view=graph&words='+encodeURIComponent('рестораны'));
    await p.waitForTimeout(3000);
    if(!template)throw Error('Нет авторизованного запроса Wordstat');
    for(const region of cfg.regions)for(const query of cfg.queries){
      const name=crypto.createHash('sha256').update(region.id+'|'+query.phrase).digest('hex').slice(0,16)+'.json';
      const file=path.join(out,name);
      if(fs.existsSync(file)){console.log(region.name,query.phrase,'кэш');continue;}
      const payload={...template, searchValue:query.phrase, startDate:cfg.startDate,endDate:cfg.endDate,
                     filters:{...template.filters,region:region.id},text:{}};
      const result=await p.evaluate(async({payload,headers})=>{
        const h={};for(const [k,v]of Object.entries(headers))if(k==='content-type'||k.includes('csrf')||k==='x-requested-with')h[k]=v;
        const r=await fetch('/wordstat/api/getGraph',{method:'POST',headers:h,body:JSON.stringify(payload)});
        return {status:r.status,body:await r.text()};
      },{payload,headers});
      let data;try{data=JSON.parse(result.body);}catch{throw Error('Неструктурированный ответ; вход или ограничение сервиса');}
      const series=data?.graph?.images?.timeSeries?.preparedValues;
      if(result.status!==200||!series?.absolute?.length)throw Error('Wordstat не отдал ряд: '+result.status);
      const periods=series.absolute.map(a=>`${a.year}-${String(a.month+1).padStart(2,'0')}`);
      if(periods.length!==36||periods[0]!=='2022-01'||periods.at(-1)!=='2024-12')throw Error('Wordstat изменил окно истории');
      fs.writeFileSync(file,JSON.stringify({retrieved_at:new Date().toISOString(),source:'https://wordstat.yandex.ru/',
        region,query,payload,status:result.status,response:data,historical_version_verified:false},null,2)+'\n');
      console.log(region.name,query.phrase,periods.length,'месяцев');
      await p.waitForTimeout(350);
    }
  } finally {await c.send('Target.closeTarget',{targetId});await b.close();}
})().catch(e=>{console.error(e.message);process.exit(1)});
