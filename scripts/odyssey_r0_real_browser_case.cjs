'use strict';
/* One actual Chromium UI interaction; only ephemeral localhost and synthetic notes. */
const path = require('node:path');
const puppeteer = require(process.env.ODYSSEY_PUPPETEER_MODULE ||
  path.join(process.env.HOME || '/home/ragdehl',
    '.npm/_npx/4b4c857f6efdfb61/node_modules/puppeteer'));
const executablePath = process.env.ODYSSEY_CHROMIUM_BINARY ||
  path.join(process.env.HOME || '/home/ragdehl',
    '.cache/puppeteer/chrome/linux_arm-154.0.8037.57/chrome-linux-arm64/chrome');
(async () => {
 let browser, page, checkpoint='boot';
 try {
  const url=process.env.ODYSSEY_R0_BROWSER_URL;
  const source=process.env.ODYSSEY_R0_SOURCE;
  const token=process.env.ODYSSEY_R0_AUTH;
  if(!/^http:\/\/127\.0\.0\.1:\d+\/$/.test(url)||!source||!token)
    throw Error('An isolated local source/browser gate is required');
  browser=await puppeteer.launch({executablePath,headless:true,
    args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--disable-background-networking']});
  page=await browser.newPage();
  await page.setViewport({width:390,height:844,deviceScaleFactor:1});
  let jsErrors=[];
  page.on('pageerror',e=>jsErrors.push(String(e.message).slice(0,160)));
  const unauth=await page.goto(url,{waitUntil:'domcontentloaded',timeout:18000});
  if(unauth.status()!==403)throw Error('unauthenticated browser was allowed');
  await page.setCookie({name:'odyssey_test_auth',value:token,url,httpOnly:true,sameSite:'Strict'});
  if((await page.goto(url,{waitUntil:'domcontentloaded',timeout:18000})).status()!==200)
    throw Error('authenticated UI cannot open');
  await page.waitForSelector('#request-input',{timeout:12000});
  checkpoint='visible_input';
  await page.type('#request-input',source,{delay:2});
  const typed=await page.$eval('#request-input',e=>e.value);
  if(typed!==source)throw Error('original message not typed byte-for-byte');
  checkpoint='visible_submit';
  await page.click('#send-button');
  checkpoint='await_reply';
  // A valid needs_attention reply is a plain .message-odyssey: it does NOT
  // have an acknowledgement/clarification/error class. Await the removal of
  // the loading placeholder, then inspect the actual assistant text/status.
  await page.waitForFunction(() => !document.querySelector('.message-loading') &&
    [...document.querySelectorAll('.message-odyssey')].some(m =>
      !!m.querySelector('.message-text')?.textContent?.trim()),{timeout:195000});
  const before=await page.evaluate(()=>({
    userMessages:[...document.querySelectorAll('.message-user')].map(x=>x.textContent),
    ack:!!document.querySelector('.message-acknowledgement'),
    error:!!document.querySelector('.message-error'),
    clarification:!!document.querySelector('.message-clarification'),
    details:document.querySelectorAll('.detail-button').length,
    noteSetButtons:document.querySelectorAll('.note-set-button').length,
    assistantTexts:[...document.querySelectorAll('.message-odyssey .message-text')].map(x=>x.textContent.slice(0,350)),
  }));
  checkpoint='reload';
  await page.reload({waitUntil:'domcontentloaded',timeout:18000});
  await page.waitForFunction(()=>document.querySelector('#interaction')?.childElementCount>0,
    {timeout:15000});
  const after=await page.evaluate(()=>({
    userMessages:[...document.querySelectorAll('.message-user')].map(x=>x.textContent),
    ack:!!document.querySelector('.message-acknowledgement'),
    error:!!document.querySelector('.message-error'),
    details:document.querySelectorAll('.detail-button').length,
    noteSetButtons:document.querySelectorAll('.note-set-button').length,
    assistantTexts:[...document.querySelectorAll('.message-odyssey .message-text')].map(x=>x.textContent.slice(0,350)),
  }));
  checkpoint='notes_ui';
  let notesChecked=false, calendarChecked=false, notesCount=null;
  let notesListTexts=[], openedNoteText='';
  const noteSet=await page.$('.note-set-button');
  if(noteSet){
    await noteSet.click();
  }else{
    const tab=await page.$('#notes-tab');
    if(!tab)throw Error('No real Notes navigation button was found');
    await tab.click();
  }
  await page.waitForFunction(()=>document.querySelector('#notes-surface')?.hidden===false,
    {timeout:12000});
  // An opened Notes surface is NOT evidence that the note was read. Await a
  // real result returned by NotesQueryService and click it like a user.
  await page.waitForSelector('#notes-list .note-row:not(.note-unavailable)',
    {visible:true,timeout:25000});
  notesListTexts=await page.$$eval('#notes-list .note-row:not(.note-unavailable)',
    els=>els.slice(0,12).map(e=>e.textContent.slice(0,170)));
  notesCount=notesListTexts.length;
  await page.click('#notes-list .note-row:not(.note-unavailable)');
  await page.waitForFunction(()=>{
    const detail=document.querySelector('#note-detail');
    return detail && detail.hidden===false && (detail.textContent||'').trim().length>35;
  },{timeout:20000});
  openedNoteText=await page.$eval('#note-detail',e=>e.textContent.slice(0,2500));
  notesChecked=notesCount>0 && openedNoteText.trim().length>35;
  const calendar=await page.$('#notes-calendar-tab');
  if(!calendar)throw Error('No Notes-to-Calendar navigation button');
  checkpoint='calendar_ui';
  await calendar.click();
  await page.waitForFunction(()=>document.querySelectorAll('.calendar-day-cell').length>0,
    {timeout:13000});
  calendarChecked=true;
  const sourceShown=before.userMessages.some(x=>x.includes(source)) &&
    after.userMessages.some(x=>x.includes(source));
  const pass=sourceShown && notesChecked && calendarChecked && jsErrors.length===0;
  console.log(JSON.stringify({pass,sourceShown,before,after,notesChecked,
    notesCount,notesListTexts,openedNoteText,calendarChecked,jsErrors}));
  if(!pass)process.exitCode=2;
 }catch(e){console.log(JSON.stringify({pass:false,checkpoint,error:String(e.message).slice(0,230)}));process.exitCode=1;}
 finally{if(browser)await browser.close();}
})();
